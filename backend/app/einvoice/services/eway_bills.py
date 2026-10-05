"""E-way bills beyond the registered invoice (backlog 77 rows 9 and 10).

* **From a delivery note**, only where no invoice bills its goods yet -- job
  work, goods on approval, a van loaded before its sales are made. Once an
  invoice bills the note, the e-way bill is the invoice's.
* **Recorded by hand**: a firm filing offline (A42) raises the bill on the
  e-way bill portal and types its number here, for an invoice or a note.
* **Due**: a consignment worth more than the firm's limit (₹50,000 unless the
  firm says otherwise, A35) with no live e-way bill. The screen prompts with
  it after a dispatch or an approval, and lists what is still due.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.einvoice.models import (
    EWayBill,
    EWayBillStatus,
    RegistrationMode,
    TransportMode,
)
from app.einvoice.services.eway_payload import eway_payload
from app.einvoice.services.portal import portal_for
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.tax.services.gst_compliance import GstComplianceService

#: The states a note's goods have left in, or are about to.
_MOVING = ("APPROVED", "DISPATCHED", "COMPLETED")

#: How far back the due list looks.
DUE_WINDOW_DAYS = 30


@dataclass(frozen=True)
class EWayBillDue:
    """One consignment above the limit with no live e-way bill."""

    document_type: str
    document_id: UUID
    number: str
    on: date
    value: Decimal


class EWayBillService:
    """Raise, record and find the e-way bills beyond a registered invoice."""

    def __init__(self, session: Session, *, mode: str, provider: str) -> None:
        """Bind the firm's route (see ``EInvoiceService.for_firm``)."""
        self._session = session
        self._mode = mode
        self._provider = provider

    # ---- reads ---------------------------------------------------------

    def for_note(self, note_id: UUID, *, firm_scope: UUID) -> EWayBill | None:
        """Return a delivery note's e-way bill, or None."""
        return self._session.scalar(
            select(EWayBill).where(
                EWayBill.firm_id == firm_scope,
                EWayBill.delivery_note_id == note_id,
                EWayBill.is_deleted.is_(False),
            )
        )

    def limit(self, firm_id: UUID) -> Decimal:
        """Return the value above which a consignment needs an e-way bill."""
        return (
            GstComplianceService(self._session)
            .settings_response(firm_id)
            .eway_bill_limit
        )

    def due(self, firm_id: UUID) -> list[EWayBillDue]:
        """List recent consignments above the limit with no live e-way bill.

        Approved invoices, and delivery notes on the move that no invoice
        bills yet, from the last ``DUE_WINDOW_DAYS`` days, newest first.
        """
        limit = self.limit(firm_id)
        since = firm_today(self._session, firm_id) - timedelta(days=DUE_WINDOW_DAYS)
        live = {
            row.sales_invoice_id or row.delivery_note_id
            for row in self._session.scalars(
                select(EWayBill).where(
                    EWayBill.firm_id == firm_id,
                    EWayBill.is_deleted.is_(False),
                    EWayBill.status == EWayBillStatus.GENERATED.value,
                )
            )
        }
        found: list[EWayBillDue] = []
        for invoice in self._session.scalars(
            select(SalesInvoice).where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status == "APPROVED",
                SalesInvoice.invoice_date >= since,
                SalesInvoice.grand_total > limit,
            )
        ):
            if invoice.id not in live:
                found.append(
                    EWayBillDue(
                        "SALES_INVOICE",
                        invoice.id,
                        invoice.invoice_number,
                        invoice.invoice_date,
                        Decimal(str(invoice.grand_total)),
                    )
                )
        for note in self._session.scalars(
            select(DeliveryNote).where(
                DeliveryNote.firm_id == firm_id,
                DeliveryNote.is_deleted.is_(False),
                DeliveryNote.status.in_(_MOVING),
                DeliveryNote.delivery_date >= since,
                DeliveryNote.grand_total > limit,
            )
        ):
            if note.id not in live and not self._billed(note.id):
                found.append(
                    EWayBillDue(
                        "DELIVERY_NOTE",
                        note.id,
                        note.delivery_note_number,
                        note.delivery_date,
                        Decimal(str(note.grand_total)),
                    )
                )
        return sorted(found, key=lambda item: (item.on, item.number), reverse=True)

    # ---- raising --------------------------------------------------------

    def generate_for_note(
        self,
        note_id: UUID,
        *,
        distance_km: Decimal | None,
        transport_mode: str | None,
        transporter_id: str | None,
        transporter_name: str | None,
        vehicle_number: str | None,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> EWayBill:
        """Raise an e-way bill for a delivery note no invoice bills (77.9).

        Raises:
            ValidationError: When an invoice bills the note, it is not on the
                move, or the transport is incomplete.
            ConflictError: When it already has a live e-way bill.

        """
        note = self._note(note_id, firm_scope=firm_scope)
        self._refuse_if_billed(note)
        existing = self.for_note(note.id, firm_scope=firm_scope)
        if existing is not None and existing.status == EWayBillStatus.GENERATED.value:
            raise ConflictError(
                f"{note.delivery_note_number} already has e-way bill "
                f"{existing.eway_bill_number}."
            )
        distance = distance_km if distance_km is not None else note.distance_km
        if not distance:
            raise ValidationError(
                "State the distance the goods travel: the e-way bill's validity "
                "is decided by it, and the delivery note records none."
            )
        mode = transport_mode or note.transport_mode or TransportMode.ROAD.value
        mode = mode.strip().upper()
        if mode not in {item.value for item in TransportMode}:
            raise ValidationError("Transport mode must be ROAD, RAIL, AIR or SHIP.")
        vehicle = (vehicle_number or note.vehicle or "").strip().upper()
        if mode == TransportMode.ROAD.value and not vehicle:
            raise ValidationError(
                "Goods moving by road need a vehicle number on the e-way bill."
            )
        payload = eway_payload(
            self._session,
            firm_id=firm_scope,
            customer_id=note.customer_id,
            doc_type="CHL",
            number=note.delivery_note_number,
            on=note.delivery_date.strftime("%d/%m/%Y"),
            reason=note.challan_reason or "SALE",
            reason_note=note.challan_reason_note,
            lines=self._session.scalars(
                select(DeliveryNoteLine)
                .where(
                    DeliveryNoteLine.delivery_note_id == note.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
                .order_by(DeliveryNoteLine.line_number.asc())
            ),
            quantity_of="delivered_quantity",
            total_value=note.grand_total,
            branch_id=note.branch_id,
        ) | {
            "TransDistance": float(distance),
            "TransMode": mode,
            "TransId": (transporter_id or note.transporter_gstin or "").strip() or None,
            "TransName": (transporter_name or note.transporter_name or "").strip()
            or None,
            "VehNo": vehicle or None,
        }
        row = existing or EWayBill(
            firm_id=firm_scope,
            delivery_note_id=note.id,
            mode=self._mode,
            created_by=actor_id,
        )
        row.mode = self._mode
        row.distance_km = Decimal(str(distance))
        row.transport_mode = mode
        row.transporter_id = payload["TransId"]  # type: ignore[assignment]
        row.transporter_name = payload["TransName"]  # type: ignore[assignment]
        row.vehicle_number = payload["VehNo"]  # type: ignore[assignment]
        row.request_payload = payload
        row.updated_by = actor_id
        result = portal_for(self._provider).generate_eway_bill(payload)
        if result.ok:
            row.status = EWayBillStatus.GENERATED.value
            row.eway_bill_number = result.reference
            row.valid_until = result.valid_until
            row.error_code = None
            row.error_message = None
        else:
            row.status = EWayBillStatus.FAILED.value
            row.error_code = result.error_code
            row.error_message = result.error_message
        if existing is None:
            self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="eway_bill.generated" if result.ok else "eway_bill.refused",
            entity_type="eway_bill",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "delivery_note": note.delivery_note_number,
                "eway_bill_number": row.eway_bill_number,
                "status": row.status,
                "mode": row.mode,
            },
        )
        return row

    def record(
        self,
        *,
        invoice_id: UUID | None,
        note_id: UUID | None,
        eway_bill_number: str,
        valid_until: date | None,
        distance_km: Decimal | None,
        vehicle_number: str | None,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> EWayBill:
        """Record an e-way bill raised by hand on the portal (A42).

        For an invoice, or a delivery note no invoice bills. The number is the
        portal's twelve digits.

        Raises:
            ValidationError: When the number is not twelve digits, or the note
                is billed.
            ConflictError: When the document already has a live e-way bill.

        """
        number = "".join(eway_bill_number.split())
        if not (number.isdigit() and len(number) == 12):
            raise ValidationError("An e-way bill number is twelve digits.")
        if (invoice_id is None) == (note_id is None):
            raise ValidationError("Name an invoice or a delivery note, not both.")
        if invoice_id is not None:
            invoice = self._session.get(SalesInvoice, invoice_id)
            if invoice is None or invoice.firm_id != firm_scope or invoice.is_deleted:
                raise ResourceNotFoundError("Sales invoice not found.")
            label = invoice.invoice_number
            existing = self._session.scalar(
                select(EWayBill).where(
                    EWayBill.firm_id == firm_scope,
                    EWayBill.sales_invoice_id == invoice_id,
                    EWayBill.is_deleted.is_(False),
                )
            )
        else:
            assert note_id is not None
            note = self._note(note_id, firm_scope=firm_scope)
            self._refuse_if_billed(note)
            label = note.delivery_note_number
            existing = self.for_note(note_id, firm_scope=firm_scope)
        if existing is not None and existing.status == EWayBillStatus.GENERATED.value:
            raise ConflictError(
                f"{label} already has e-way bill {existing.eway_bill_number}."
            )
        row = existing or EWayBill(
            firm_id=firm_scope,
            sales_invoice_id=invoice_id,
            delivery_note_id=note_id,
            mode=RegistrationMode.LIVE.value,
            created_by=actor_id,
        )
        row.mode = RegistrationMode.LIVE.value
        row.entered_by_hand = True
        row.status = EWayBillStatus.GENERATED.value
        row.eway_bill_number = number
        row.valid_until = valid_until
        if distance_km is not None:
            row.distance_km = distance_km
        row.vehicle_number = (vehicle_number or "").strip().upper() or None
        row.error_code = None
        row.error_message = None
        row.updated_by = actor_id
        if existing is None:
            self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="eway_bill.recorded",
            entity_type="eway_bill",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"document": label, "eway_bill_number": number},
        )
        return row

    def cancel_for_note(
        self, note_id: UUID, *, reason: str, firm_scope: UUID, actor_id: UUID
    ) -> EWayBill:
        """Withdraw a delivery note's e-way bill.

        Raises:
            ValidationError: When it has no live bill, or no reason is given,
                or the portal refuses.

        """
        row = self.for_note(note_id, firm_scope=firm_scope)
        if row is None or row.status != EWayBillStatus.GENERATED.value:
            raise ValidationError("This delivery note has no live e-way bill.")
        if not reason.strip():
            raise ValidationError("Say why the e-way bill is being withdrawn.")
        route = "OFFLINE" if row.entered_by_hand else self._provider
        result = portal_for(route).cancel_eway_bill(
            row.eway_bill_number or "", reason=reason
        )
        if not result.ok:
            raise ValidationError(
                result.error_message or "The portal refused the withdrawal."
            )
        row.status = EWayBillStatus.CANCELLED.value
        row.cancelled_at = utc_now()
        row.cancellation_reason = reason.strip()
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="eway_bill.cancelled",
            entity_type="eway_bill",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"reason": row.cancellation_reason},
        )
        return row

    # ---- helpers --------------------------------------------------------

    def _note(self, note_id: UUID, *, firm_scope: UUID) -> DeliveryNote:
        """Return a delivery note on the move.

        Raises:
            ResourceNotFoundError: When the firm has no such note.
            ValidationError: When it is still a draft or was cancelled.

        """
        note = self._session.get(DeliveryNote, note_id)
        if note is None or note.firm_id != firm_scope or note.is_deleted:
            raise ResourceNotFoundError("Delivery note not found.")
        if note.status not in _MOVING:
            raise ValidationError(
                f"{note.delivery_note_number} is {note.status.lower()}; an e-way "
                "bill is raised for goods approved to move."
            )
        return note

    def _billed(self, note_id: UUID) -> bool:
        """Whether a live, uncancelled invoice bills the note."""
        return (
            self._session.scalar(
                select(SalesInvoiceLine.id)
                .join(
                    SalesInvoice,
                    SalesInvoice.id == SalesInvoiceLine.sales_invoice_id,
                )
                .where(
                    SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
                    SalesInvoiceLine.source_document_id == note_id,
                    SalesInvoiceLine.is_deleted.is_(False),
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.status != "CANCELLED",
                )
                .limit(1)
            )
            is not None
        )

    def _refuse_if_billed(self, note: DeliveryNote) -> None:
        """Refuse a note an invoice bills: its e-way bill is the invoice's."""
        if self._billed(note.id):
            raise ValidationError(
                f"{note.delivery_note_number} is billed; raise the e-way bill "
                "on its invoice."
            )
