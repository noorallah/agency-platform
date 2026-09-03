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
from app.einvoice.models import (
    EInvoiceRegistration,
    EWayBill,
    EWayBillStatus,
    RegistrationMode,
    RegistrationStatus,
    TransportMode,
)
from app.einvoice.services.payload import EInvoicePayloadBuilder
from app.einvoice.services.portal import PortalResult, portal_for
from app.sales_invoice.models import SalesInvoice

#: How long the authority allows a registration to be withdrawn. Judged in UTC
#: like every other clock here -- reading the server's local time would make
#: the window an hour wrong for part of every day on a non-UTC deployment.
_CANCELLATION_WINDOW_HOURS = 24


class EInvoiceService:
    """Register invoices and raise e-way bills through whichever portal."""

    def __init__(self, session: Session, *, mode: str | None = None) -> None:
        """Bind the service, and the mode its registrations are made in.

        The mode defaults to SANDBOX rather than to a firm setting, because a
        default that could resolve to LIVE is a default that files a return by
        accident.
        """
        self._session = session
        self._mode = mode or RegistrationMode.SANDBOX.value
        self._payloads = EInvoicePayloadBuilder(session)

    # ---- reads ---------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[EInvoiceRegistration]], firm_id: UUID
    ) -> Select[tuple[EInvoiceRegistration]]:
        """Restrict a query to one firm's live registrations."""
        return statement.where(
            EInvoiceRegistration.firm_id == firm_id,
            EInvoiceRegistration.is_deleted.is_(False),
        )

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
            ConflictError: If the invoice already carries a live registration.
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
        payload = self._payloads.build(invoice, firm_id=firm_scope)
        row = existing or EInvoiceRegistration(
            firm_id=firm_scope,
            sales_invoice_id=invoice.id,
            mode=self._mode,
            created_by=actor_id,
        )
        # A retry keeps the row and the count. Two rows for one invoice would
        # break the promise that a supply has one reference.
        row.mode = self._mode
        row.request_payload = payload
        row.attempts = int(row.attempts or 0) + 1
        row.updated_by = actor_id
        result = portal_for(self._mode).register_invoice(payload)
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
        acknowledged = row.acknowledged_at
        if acknowledged is not None:
            hours = (utc_now() - as_utc(acknowledged)).total_seconds() / 3600
            if hours > _CANCELLATION_WINDOW_HOURS:
                raise ValidationError(
                    "A registration can only be withdrawn within "
                    f"{_CANCELLATION_WINDOW_HOURS} hours. Raise a credit note "
                    "instead, which is how a supply is corrected afterwards."
                )
        result = portal_for(row.mode).cancel_invoice(row.irn or "", reason=reason)
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
        distance_km: Decimal,
        transport_mode: str,
        transporter_id: str | None,
        transporter_name: str | None,
        vehicle_number: str | None,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> EWayBill:
        """Raise an e-way bill for the goods an invoice covers.

        The invoice must be registered first. An e-way bill quotes the IRN, so
        raising one against an unregistered invoice would put a reference on
        the road that the authority cannot match to a supply.

        Args:
            invoice_id: The registered invoice.
            distance_km: How far the goods travel, which decides the validity.
            transport_mode: ROAD, RAIL, AIR or SHIP.
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
        if (
            registration is None
            or registration.status != RegistrationStatus.REGISTERED.value
        ):
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
        mode = (transport_mode or TransportMode.ROAD.value).strip().upper()
        if mode not in {item.value for item in TransportMode}:
            raise ValidationError("Transport mode must be ROAD, RAIL, AIR or SHIP.")
        if mode == TransportMode.ROAD.value and not (vehicle_number or "").strip():
            raise ValidationError(
                "Goods moving by road need a vehicle number on the e-way bill."
            )
        payload: dict[str, object] = {
            "Irn": registration.irn,
            "TransDistance": float(distance_km),
            "TransMode": mode,
            "TransId": (transporter_id or "").strip() or None,
            "TransName": (transporter_name or "").strip() or None,
            "VehNo": (vehicle_number or "").strip().upper() or None,
        }
        row = existing or EWayBill(
            firm_id=firm_scope,
            sales_invoice_id=invoice.id,
            mode=registration.mode,
            created_by=actor_id,
        )
        row.mode = registration.mode
        row.distance_km = distance_km
        row.transport_mode = mode
        row.transporter_id = payload["TransId"]  # type: ignore[assignment]
        row.transporter_name = payload["TransName"]  # type: ignore[assignment]
        row.vehicle_number = payload["VehNo"]  # type: ignore[assignment]
        row.request_payload = payload
        row.updated_by = actor_id
        result = portal_for(registration.mode).generate_eway_bill(payload)
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
        result = portal_for(row.mode).cancel_eway_bill(
            row.eway_bill_number or "", reason=reason
        )
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
