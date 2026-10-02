"""Payment reminders a person sends, from a customer's account (MSG-3, §51 A4).

*Remind* on the overdue list or a customer's statement sends the customer their
statement of account -- the movement, the balance and the bills still unpaid --
by email through the firm's account, or from the person's own WhatsApp the way
an invoice is shared (MSG-1). A customer marked *no reminders* gets none, by
either road: the flag is the customer's wish, not the channel's.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.customers.services.statement_service import CustomerStatementService
from app.document_framework.services.print_support import load_template
from app.messaging.models import MessagingOutbox
from app.messaging.schemas import HandShareResponse, ReminderRequest
from app.messaging.services.common import (
    QUEUED,
    channel_configs,
    day,
    is_usable,
    money,
    recipient_for,
)
from app.messaging.services.hand_share import whatsapp_number

#: What a reminder sent by hand is recorded as in the outbox.
MANUAL_REMINDER = "MANUAL_REMINDER"
#: The "document" a reminder is about: the customer's statement of account.
CUSTOMER_STATEMENT = "CUSTOMER_STATEMENT"


class ReminderService:
    """Send a customer their statement as a payment reminder."""

    def __init__(self, session: Session) -> None:
        """Keep the firm's session."""
        self._session = session

    def remind_by_email(
        self, data: ReminderRequest, *, firm_id: UUID, actor_id: UUID
    ) -> MessagingOutbox:
        """Queue the statement to go by email now. Commits.

        Raises:
            ResourceNotFoundError: When the customer is not this firm's.
            ValidationError: When messaging or email is off, the customer asked
                for no reminders, owes nothing, or has no email to send to.

        """
        customer = self._customer(data.customer_id, firm_id=firm_id)
        self._may_remind(customer)
        from app.messaging.services.messaging_service import MessagingService

        settings = MessagingService(self._session)._settings_row(firm_id)
        if settings is None or not settings.is_enabled:
            raise ValidationError(
                "Messaging is off for this firm. Switch it on under Settings > "
                "Messaging first, or remind on WhatsApp by hand."
            )
        account = channel_configs(self._session, firm_id).get("EMAIL")
        why_not = is_usable(account)
        if why_not is not None:
            raise ValidationError(f"Email cannot send: {why_not}.")
        balance, text = self._wording(customer, firm_id=firm_id)
        recipient = (data.recipient or "").strip() or None
        if recipient is None:
            recipient, why_not = recipient_for(self._session, customer, "EMAIL")
            if recipient is None:
                raise ValidationError(f"Cannot send: {why_not}. Enter an address.")
        firm = FirmMetadataReader(self._session).get(firm_id)
        today = utc_now().date()
        row = MessagingOutbox(
            firm_id=firm_id,
            event_code=MANUAL_REMINDER,
            document_type=CUSTOMER_STATEMENT,
            document_id=customer.id,
            document_number=f"Statement {day(today)}",
            customer_id=customer.id,
            channel="EMAIL",
            provider=None if account is None else account.provider,
            recipient=recipient,
            status=QUEUED,
            subject=(
                f"Statement of account and payment reminder from {firm.name or ''}"
            ).strip()[:300],
            body=(data.message or "").strip() or text,
            variables=[],
            attach_pdf=True,
            fallback_channels=[],
            requested_by=actor_id,
            next_attempt_at=None,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="message.reminder_requested",
            entity_type="customer",
            entity_id=customer.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "channel": "EMAIL",
                "recipient": recipient,
                "balance": str(balance),
            },
        )
        self._session.commit()
        return row

    def prepare_whatsapp(
        self, customer_id: UUID, *, firm_id: UUID
    ) -> HandShareResponse:
        """Say whom to remind on WhatsApp by hand, and what to say.

        Raises:
            ResourceNotFoundError: When the customer is not this firm's.
            ValidationError: When the customer asked for no reminders or owes
                nothing.

        """
        customer = self._customer(customer_id, firm_id=firm_id)
        self._may_remind(customer)
        _, text = self._wording(customer, firm_id=firm_id)
        phone, _ = recipient_for(
            self._session, customer, "WHATSAPP", require_opt_in=False
        )
        today = utc_now().date()
        safe = "".join(
            ch if ch.isalnum() or ch in "-_" else "-" for ch in customer.code
        )
        return HandShareResponse(
            document_type=CUSTOMER_STATEMENT,
            document_id=customer.id,
            document_number=f"Statement {day(today)}",
            phone=phone,
            whatsapp_number=whatsapp_number(phone),
            text=text,
            file_name=f"statement-{safe}-{today.isoformat()}.pdf",
        )

    # ------------------------------------------------------------------
    def _customer(self, customer_id: UUID, *, firm_id: UUID) -> Customer:
        """Return the firm's customer, or refuse."""
        customer = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if customer is None:
            raise ResourceNotFoundError("Customer not found.")
        return customer

    @staticmethod
    def _may_remind(customer: Customer) -> None:
        """Refuse a customer who asked for no reminders."""
        if customer.no_reminders:
            raise ValidationError(
                f"{customer.display_name or customer.name} has asked for no "
                "reminders (on the customer record). Untick it there to remind "
                "them."
            )

    def _wording(self, customer: Customer, *, firm_id: UUID) -> tuple[Decimal, str]:
        """Return the balance and the reminder's message.

        Raises:
            ValidationError: When the customer owes nothing.

        """
        ageing = next(
            iter(
                CustomerStatementService(self._session).ageing(
                    firm_scope=firm_id, customer_id=customer.id
                )
            ),
            None,
        )
        balance = Decimal("0") if ageing is None else ageing.account_balance
        if balance <= 0:
            raise ValidationError(
                f"{customer.display_name or customer.name} owes nothing, so there "
                "is nothing to remind them of."
            )
        overdue = [
            bill
            for bill in (ageing.invoices if ageing else [])
            if bill.days_overdue > 0
        ]
        firm = FirmMetadataReader(self._session).get(firm_id)
        name = customer.display_name or customer.name
        text = (
            f"Dear {name},\n\nA reminder from {firm.name or 'us'}: your balance "
            f"with us is {money(balance)} as of {day(utc_now().date())}."
        )
        if overdue:
            past_due = sum((bill.outstanding for bill in overdue), Decimal("0"))
            text += (
                f" Of this, {money(past_due)} on {len(overdue)} "
                f"bill{'s' if len(overdue) > 1 else ''} is past due: "
                + ", ".join(bill.invoice_number for bill in overdue[:5])
                + (" and more" if len(overdue) > 5 else "")
                + "."
            )
        text += " Please find our statement of account attached."
        upi_id = load_template(
            self._session, firm_scope=firm_id, document_type="SALES_INVOICE"
        ).upi_id
        if upi_id:
            text += f"\n\nYou may pay by UPI to {upi_id}."
        text += f"\n\nRegards,\n{firm.name or ''}".rstrip()
        return balance, text
