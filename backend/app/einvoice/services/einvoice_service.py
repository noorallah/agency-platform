"""Registering an invoice, raising its e-way bill, and withdrawing either.

The rules that are this module's own, rather than the portal's:

- **an invoice is registered once.** A second registration would leave two
  references for one supply and nothing to say which the customer holds;
- **a registration is withdrawn, never deleted**, and the row keeps saying what
  it was;
- **a refusal is recorded on the invoice**, not only in a log, because the
  person who has to correct the document is looking at the document;
- and **nothing pretends a rehearsal was a filing**: the mode is written on
  every row and the sandbox marks every reference it mints.
"""

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import as_utc, utc_now
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote
from app.einvoice.models import (
    EInvoiceProvider,
    EInvoiceRegistration,
    EWayBill,
    EWayBillStatus,
    RegistrationMode,
    RegistrationStatus,
    TransportMode,
)
from app.einvoice.services.eway_payload import eway_payload
from app.einvoice.services.payload import EInvoicePayloadBuilder
from app.einvoice.services.portal import PortalResult, portal_for
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceSource,
)

#: How long the authority allows a registration to be withdrawn. Judged in UTC
#: like every other clock here -- reading the server's local time would make
#: the window an hour wrong for part of every day on a non-UTC deployment.
_CANCELLATION_WINDOW_HOURS = 24


class EInvoiceService:
    """Register invoices and raise e-way bills through whichever portal."""

    def __init__(
        self,
        session: Session,
        *,
        mode: str | None = None,
        provider: str | None = None,
    ) -> None:
        """Bind the service, and the route its registrations take.

        Both default to the sandbox rather than to a firm setting, because a
        default that could resolve to LIVE is a default that files a return by
        accident; ``for_firm`` reads the firm's own choice (A42). The mode
        follows the provider: only the sandbox rehearses.
        """
        self._session = session
        # A LIVE mode named with no provider keeps refusing, as it always
        # has, rather than quietly rehearsing: ``portal_for("LIVE")`` raises.
        self._provider = provider or (
            mode
            if mode is not None and mode != RegistrationMode.SANDBOX.value
            else EInvoiceProvider.SANDBOX.value
        )
        self._mode = mode or (
            RegistrationMode.SANDBOX.value
            if self._provider == EInvoiceProvider.SANDBOX.value
            else RegistrationMode.LIVE.value
        )
        self._payloads = EInvoicePayloadBuilder(session)

    @property
    def mode(self) -> str:
        """SANDBOX or LIVE: whether this service's registrations are filings."""
        return self._mode

    @property
    def provider(self) -> str:
        """The route this service's documents take (A42)."""
        return self._provider

    @classmethod
    def for_firm(cls, session: Session, firm_id: UUID) -> "EInvoiceService":
        """Return the service on the provider the firm chose (decision A42)."""
        from app.einvoice.services.settings import EInvoiceSettingsService

        provider = EInvoiceSettingsService(session).provider(firm_id)
        return cls(session, provider=provider)

    # ---- reads ---------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[EInvoiceRegistration]], firm_id: UUID
    ) -> Select[tuple[EInvoiceRegistration]]:
        """Restrict a query to one firm's live registrations."""
        return statement.where(
            EInvoiceRegistration.firm_id == firm_id,
            EInvoiceRegistration.is_deleted.is_(False),
        )

    def invoice_labels(
        self, *, firm_scope: UUID, invoice_ids: Iterable[UUID]
    ) -> dict[UUID, tuple[str, str]]:
        """Return invoice number and customer name for each invoice named.

        One query for the page rather than one per row.
        """
        wanted = set(invoice_ids)
        if not wanted:
            return {}
        rows = self._session.execute(
            select(SalesInvoice.id, SalesInvoice.invoice_number, Customer.name)
            .join(Customer, Customer.id == SalesInvoice.customer_id, isouter=True)
            .where(SalesInvoice.firm_id == firm_scope, SalesInvoice.id.in_(wanted))
        ).all()
        return {
            invoice_id: (number or "", name or "") for invoice_id, number, name in rows
        }

    def list_registrations(
        self, *, firm_scope: UUID, page: int, page_size: int, status: str | None = None
    ) -> tuple[list[EInvoiceRegistration], int]:
        """Return one page of registrations, newest first.

        Args:
            firm_scope: The owning firm.
            page: One-based page number.
            page_size: How many rows to return.
            status: Restrict to one state.

        Returns:
            The page and the total matching count.

        """
        statement = self._scoped(select(EInvoiceRegistration), firm_scope)
        if status is not None:
            statement = statement.where(EInvoiceRegistration.status == status)
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = list(
            self._session.scalars(
                statement.order_by(
                    EInvoiceRegistration.created_at.desc(),
                    EInvoiceRegistration.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(total or 0)

    def registration_for(
        self, invoice_id: UUID, *, firm_scope: UUID
    ) -> EInvoiceRegistration | None:
        """Return an invoice's registration, or None where it has none."""
        return self._session.scalar(
            self._scoped(select(EInvoiceRegistration), firm_scope).where(
                EInvoiceRegistration.sales_invoice_id == invoice_id
            )
        )

    def eway_bill_for(self, invoice_id: UUID, *, firm_scope: UUID) -> EWayBill | None:
        """Return an invoice's e-way bill, or None where it has none."""
        return self._session.scalar(
            select(EWayBill).where(
                EWayBill.firm_id == firm_scope,
                EWayBill.sales_invoice_id == invoice_id,
                EWayBill.is_deleted.is_(False),
            )
        )

    # ---- registering ---------------------------------------------------

    def register(
        self, invoice_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> EInvoiceRegistration:
        """Register one approved invoice with the portal.

        A refusal is not an exception: the row records what the portal said
        and comes back FAILED, so the person correcting the invoice can read
        it beside the invoice and try again. A payload this module can already
        see is wrong *is* refused outright, because sending it would swap a
        sentence naming the field for a numeric code.

        Args:
            invoice_id: The invoice to register.
            firm_scope: The owning firm.
            actor_id: The user registering it.

        Returns:
            The registration, REGISTERED or FAILED.

        Raises:
            ConflictError: If the invoice already carries a live registration,
                or carried one that was withdrawn.
            ValidationError: If the invoice cannot produce a valid payload.

        """
        invoice = self._invoice(invoice_id, firm_scope=firm_scope)
        existing = self.registration_for(invoice_id, firm_scope=firm_scope)
        registered = RegistrationStatus.REGISTERED.value
        if existing is not None and existing.status == registered:
            raise ConflictError(
                f"{invoice.invoice_number} is already registered as "
                f"{existing.irn}. Cancel that registration before raising "
                "another."
            )
        # The authority never reissues a cancelled IRN, and never registers
        # the same document number twice: the IRN is a hash of the seller's
        # GSTIN, the year, the document type and its number. A withdrawn
        # registration is history -- reusing its row overwrote the withdrawal
        # and handed back the same IRN (D-CMP-6). The supply is corrected by
        # a new invoice under a new number.
        if existing is not None and existing.status == (
            RegistrationStatus.CANCELLED.value
        ):
            raise ConflictError(
                f"{invoice.invoice_number}'s registration {existing.irn} was "
                "withdrawn, and a cancelled IRN cannot be reused for the same "
                "document number. Cancel this invoice and raise a new one to "
                "register the supply again."
            )
        payload = self._payloads.build(invoice, firm_id=firm_scope)
        row = existing or EInvoiceRegistration(
            firm_id=firm_scope,
            sales_invoice_id=invoice.id,
            mode=self._mode,
            provider=self._provider,
            created_by=actor_id,
        )
        # A retry after a refusal keeps the row and the count: no IRN was
        # issued, so there is nothing to keep as history. Two rows for one
        # invoice would break the promise that a supply has one reference.
        row.mode = self._mode
        row.provider = self._provider
        row.request_payload = payload
        row.attempts = int(row.attempts or 0) + 1
        row.updated_by = actor_id
        result = portal_for(self._provider).register_invoice(payload)
        self._apply(row, result)
        if existing is None:
            self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="einvoice.registered" if result.ok else "einvoice.refused",
            entity_type="einvoice_registration",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=self._snapshot(row),
        )
        return row

    @staticmethod
    def _apply(row: EInvoiceRegistration, result: PortalResult) -> None:
        """Write what the portal answered onto the registration."""
        if result.ok:
            row.status = RegistrationStatus.REGISTERED.value
            row.irn = result.reference
            row.acknowledgement_number = result.acknowledgement_number
            row.acknowledged_at = utc_now()
            row.signed_qr_code = result.signed_qr_code
            row.signed_invoice = result.signed_document
            row.error_code = None
            row.error_message = None
            return
        row.status = RegistrationStatus.FAILED.value
        row.error_code = result.error_code
        row.error_message = result.error_message

    def cancel(
        self, invoice_id: UUID, *, reason: str, firm_scope: UUID, actor_id: UUID
    ) -> EInvoiceRegistration:
        """Withdraw a registration, inside the window the authority allows.

        Args:
            invoice_id: The registered invoice.
            reason: Why it is being withdrawn. The portal requires one.
            firm_scope: The owning firm.
            actor_id: The user withdrawing it.

        Returns:
            The cancelled registration.

        Raises:
            ValidationError: If it is not registered, the reason is empty, or
                the window has closed.

        """
        row = self.registration_for(invoice_id, firm_scope=firm_scope)
        if row is None or row.status != RegistrationStatus.REGISTERED.value:
            raise ValidationError("This invoice has no live registration.")
        if not reason.strip():
            raise ValidationError("Say why the registration is being withdrawn.")
        # The authority will not cancel an IRN while an e-way bill generated
        # against it stands: the goods may be on the road under that bill.
        # Withdrawing the registration here left the bill live and quoting an
        # IRN that no longer existed (D-CMP-5).
        live_bill = self.eway_bill_for(invoice_id, firm_scope=firm_scope)
        if live_bill is not None and live_bill.status == EWayBillStatus.GENERATED.value:
            raise ValidationError(
                f"E-way bill {live_bill.eway_bill_number} is still live against "
                "this registration. Withdraw the e-way bill first; the "
                "authority will not cancel an IRN while its e-way bill stands."
            )
        acknowledged = row.acknowledged_at
        if acknowledged is not None:
            hours = (utc_now() - as_utc(acknowledged)).total_seconds() / 3600
            if hours > _CANCELLATION_WINDOW_HOURS:
                raise ValidationError(
                    "A registration can only be withdrawn within "
                    f"{_CANCELLATION_WINDOW_HOURS} hours. Raise a credit note "
                    "instead, which is how a supply is corrected afterwards."
                )
        result = portal_for(row.provider or row.mode).cancel_invoice(
            row.irn or "", reason=reason
        )
        if not result.ok:
            raise ValidationError(
                result.error_message or "The portal refused the cancellation."
            )
        row.status = RegistrationStatus.CANCELLED.value
        row.cancelled_at = utc_now()
        row.cancellation_reason = reason.strip()[:200]
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="einvoice.cancelled",
            entity_type="einvoice_registration",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=self._snapshot(row),
        )
        return row

    # ---- e-way bills ---------------------------------------------------

    def generate_eway_bill(
        self,
        invoice_id: UUID,
        *,
        distance_km: Decimal | None,
        transport_mode: str | None,
        transporter_id: str | None,
        transporter_name: str | None,
        vehicle_number: str | None,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> EWayBill:
        """Raise an e-way bill for the goods an invoice covers.

        A registered invoice raises it from its IRN. One the firm must
        e-invoice but has not registered is refused: a bill on the road that
        the authority cannot match to a supply is worse than none. One the
        firm need not e-invoice -- a consumer, or a firm below the threshold --
        raises it from the invoice itself (backlog 77 row 9).

        Args:
            invoice_id: The registered invoice.
            distance_km: How far the goods travel, which decides the validity.
                None takes the delivery note's.
            transport_mode: ROAD, RAIL, AIR or SHIP; None takes the note's,
                else ROAD.
            transporter_id: The transporter's GSTIN or enrolment number.
            transporter_name: Their name, for the bill.
            vehicle_number: Required for road, meaningless otherwise.
            firm_scope: The owning firm.
            actor_id: The user raising it.

        Returns:
            The e-way bill, GENERATED or FAILED.

        Raises:
            ConflictError: If one already stands for this invoice.
            ValidationError: If the invoice is not registered, or road
                transport names no vehicle.

        """
        invoice = self._invoice(invoice_id, firm_scope=firm_scope)
        registration = self.registration_for(invoice_id, firm_scope=firm_scope)
        registered = (
            registration is not None
            and registration.status == RegistrationStatus.REGISTERED.value
        )
        if not registered and self._must_einvoice(invoice, firm_scope=firm_scope):
            raise ValidationError(
                "Register the invoice before raising its e-way bill: the bill "
                "quotes the IRN, and one without it cannot be matched to a "
                "supply."
            )
        existing = self.eway_bill_for(invoice_id, firm_scope=firm_scope)
        if existing is not None and existing.status == EWayBillStatus.GENERATED.value:
            raise ConflictError(
                f"{invoice.invoice_number} already has e-way bill "
                f"{existing.eway_bill_number}."
            )
        # What the person leaves blank comes from the note that carried the
        # goods (backlog 67 row 5): the transport was recorded there once.
        carried = self._carrying_note(invoice.id)
        if carried is not None:
            if distance_km is None and carried.distance_km:
                distance_km = Decimal(carried.distance_km)
            transport_mode = transport_mode or carried.transport_mode
            transporter_id = transporter_id or carried.transporter_gstin
            transporter_name = transporter_name or carried.transporter_name
            vehicle_number = vehicle_number or carried.vehicle
        if distance_km is None:
            raise ValidationError(
                "State the distance the goods travel: the e-way bill's validity "
                "is decided by it, and the delivery note records none."
            )
        mode = (transport_mode or TransportMode.ROAD.value).strip().upper()
        if mode not in {item.value for item in TransportMode}:
            raise ValidationError("Transport mode must be ROAD, RAIL, AIR or SHIP.")
        if mode == TransportMode.ROAD.value and not (vehicle_number or "").strip():
            raise ValidationError(
                "Goods moving by road need a vehicle number on the e-way bill."
            )
        payload: dict[str, object] = (
            {"Irn": registration.irn}
            if registered and registration is not None
            else eway_payload(
                self._session,
                firm_id=firm_scope,
                customer_id=invoice.customer_id,
                doc_type="INV",
                number=invoice.invoice_number,
                on=invoice.invoice_date.strftime("%d/%m/%Y"),
                reason="SALE",
                reason_note=None,
                lines=self._invoice_lines(invoice.id),
                quantity_of="current_invoice_quantity",
                total_value=invoice.grand_total,
            )
        )
        payload |= {
            "TransDistance": float(distance_km),
            "TransMode": mode,
            "TransId": (transporter_id or "").strip() or None,
            "TransName": (transporter_name or "").strip() or None,
            "VehNo": (vehicle_number or "").strip().upper() or None,
        }
        if carried is not None and carried.lr_number:
            # The transporter's document, which Part B carries beside the
            # vehicle for rail, air and ship, and for road where one exists.
            payload["TransDocNo"] = carried.lr_number
            if carried.lr_date is not None:
                payload["TransDocDt"] = carried.lr_date.strftime("%d/%m/%Y")
        route_mode = registration.mode if registered and registration else self._mode
        route = (
            (registration.provider or registration.mode)
            if registered and registration
            else self._provider
        )
        row = existing or EWayBill(
            firm_id=firm_scope,
            sales_invoice_id=invoice.id,
            mode=route_mode,
            created_by=actor_id,
        )
        row.mode = route_mode
        row.distance_km = distance_km
        row.transport_mode = mode
        row.transporter_id = payload["TransId"]  # type: ignore[assignment]
        row.transporter_name = payload["TransName"]  # type: ignore[assignment]
        row.vehicle_number = payload["VehNo"]  # type: ignore[assignment]
        row.request_payload = payload
        row.updated_by = actor_id
        result = portal_for(route).generate_eway_bill(payload)
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
                "eway_bill_number": row.eway_bill_number,
                "status": row.status,
                "mode": row.mode,
            },
        )
        return row

    def cancel_eway_bill(
        self, invoice_id: UUID, *, reason: str, firm_scope: UUID, actor_id: UUID
    ) -> EWayBill:
        """Withdraw an e-way bill.

        Args:
            invoice_id: The invoice whose bill is being withdrawn.
            reason: Why. The portal requires one.
            firm_scope: The owning firm.
            actor_id: The user withdrawing it.

        Returns:
            The cancelled bill.

        Raises:
            ValidationError: If there is no live bill or the reason is empty.

        """
        row = self.eway_bill_for(invoice_id, firm_scope=firm_scope)
        if row is None or row.status != EWayBillStatus.GENERATED.value:
            raise ValidationError("This invoice has no live e-way bill.")
        if not reason.strip():
            raise ValidationError("Say why the e-way bill is being withdrawn.")
        result = portal_for(
            self._provider if row.mode == self._mode else row.mode
        ).cancel_eway_bill(row.eway_bill_number or "", reason=reason)
        if not result.ok:
            raise ValidationError(
                result.error_message or "The portal refused the cancellation."
            )
        row.status = EWayBillStatus.CANCELLED.value
        row.cancelled_at = utc_now()
        row.cancellation_reason = reason.strip()[:200]
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="eway_bill.cancelled",
            entity_type="eway_bill",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"status": row.status, "reason": row.cancellation_reason},
        )
        return row

    # ---- helpers -------------------------------------------------------

    def _must_einvoice(self, invoice: SalesInvoice, *, firm_scope: UUID) -> bool:
        """Whether this invoice is one the firm has to register first (77.9).

        From the firm's dated *e-invoicing applies* setting, for a buyer with
        a GSTIN: a consumer's bill is never e-invoiced.
        """
        from app.tax.services.gst_compliance import GstComplianceService

        since = (
            GstComplianceService(self._session)
            .settings_response(firm_scope)
            .einvoice_applicable_from
        )
        if since is None or invoice.invoice_date < since:
            return False
        customer = self._session.get(Customer, invoice.customer_id)
        return bool((getattr(customer, "gst_number", None) or "").strip())

    def _invoice_lines(self, invoice_id: UUID) -> list[SalesInvoiceLine]:
        """Return an invoice's live lines, in order."""
        return list(
            self._session.scalars(
                select(SalesInvoiceLine)
                .where(
                    SalesInvoiceLine.sales_invoice_id == invoice_id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceLine.line_number.asc())
            )
        )

    def _carrying_note(self, invoice_id: UUID) -> DeliveryNote | None:
        """Return the delivery note whose transport an e-way bill reads.

        The latest of the bill's delivery notes: a consignment of several
        dispatches travels on the last one's vehicle.
        """
        return self._session.scalar(
            select(DeliveryNote)
            .join(
                SalesInvoiceSource,
                SalesInvoiceSource.source_document_id == DeliveryNote.id,
            )
            .where(
                SalesInvoiceSource.sales_invoice_id == invoice_id,
                SalesInvoiceSource.source_document_type == "DELIVERY_NOTE",
                SalesInvoiceSource.is_deleted.is_(False),
            )
            .order_by(
                DeliveryNote.delivery_date.desc(),
                DeliveryNote.delivery_note_number.desc(),
            )
            .limit(1)
        )

    def _invoice(self, invoice_id: UUID, *, firm_scope: UUID) -> SalesInvoice:
        """Return the invoice, if this firm has it."""
        invoice = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if invoice is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        return invoice

    @staticmethod
    def _snapshot(row: EInvoiceRegistration) -> dict[str, object]:
        """Describe a registration for the audit trail."""
        return {
            "sales_invoice_id": str(row.sales_invoice_id),
            "mode": row.mode,
            "status": row.status,
            "irn": row.irn,
            "acknowledgement_number": row.acknowledgement_number,
            "attempts": row.attempts,
            "error_code": row.error_code,
            "error_message": row.error_message,
        }


__all__ = ["EInvoiceService"]
