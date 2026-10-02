"""Share a document from the person's own WhatsApp, by hand (MSG-1, §51 A2).

No account, no API and no cost -- what Vyapar and most small-business products
do. The server says whom to send to and what to say; the desktop opens
WhatsApp at that number with the message typed in, saves the PDF and opens
its folder, and the person attaches it and presses send. Messaging does not
need to be switched on for this, and the customer's WhatsApp opt-in is not
asked for: the firm's account is not sending anything.

What the desktop cannot know is whether the person then pressed send, so the
timeline line says *shared by hand*, never *sent* or *delivered* (A5).
"""

from __future__ import annotations

import re
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.document_framework.models import (
    DocumentLifecycleEvent,
    DocumentTypeDefinition,
)
from app.messaging.events import EVENTS_BY_CODE, render
from app.messaging.models import MessagingEventConfig
from app.messaging.schemas import HandShareRecord, HandShareResponse
from app.messaging.services.common import day, money, recipient_for
from app.sales_invoice.models import SalesInvoice

#: India's calling code: a ten-digit mobile typed without it is Indian.
_COUNTRY_CODE = "91"
SHARED_BY_HAND = "MESSAGE_SHARED"


def whatsapp_number(phone: str | None) -> str | None:
    """Return a phone number as ``wa.me`` wants it: digits with the country code.

    ``98765 43210``, ``098765 43210`` and ``+91 98765-43210`` are all
    ``919876543210``. A number that is plainly not a phone number is None, so
    WhatsApp asks whom to send to rather than opening a stranger's chat.
    """
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = _COUNTRY_CODE + digits
    if not 11 <= len(digits) <= 15:
        return None
    return digits


class HandShareService:
    """Prepare and record a document shared by hand."""

    def __init__(self, session: Session) -> None:
        """Keep the firm's session."""
        self._session = session

    def prepare(self, invoice_id: UUID, *, firm_id: UUID) -> HandShareResponse:
        """Return whom to share an approved invoice with, and what to say.

        The message is the firm's own wording for *Invoice approved* by email
        where it has saved one -- that is the covering note it already sends
        with the PDF -- or the platform's. Where the firm prints a UPI QR
        (MSG-2) and the bill still owes money, the UPI ID is added, so a
        customer reading the chat on the phone they pay from can pay.

        Raises:
            ResourceNotFoundError: When the firm has no such invoice.
            ValidationError: When the invoice is a draft or cancelled.

        """
        invoice = self._invoice(invoice_id, firm_id=firm_id)
        customer = self._session.get(Customer, invoice.customer_id)
        phone, _ = recipient_for(
            self._session, customer, "WHATSAPP", require_opt_in=False
        )
        due = self._due(invoice, firm_id=firm_id)
        firm = FirmMetadataReader(self._session).get(firm_id)
        values = {
            "customer_name": (
                "" if customer is None else customer.display_name or customer.name
            )
            or "",
            "document_number": invoice.invoice_number,
            "document_date": day(invoice.invoice_date),
            "amount": money(invoice.grand_total),
            "amount_due": money(due),
            "due_date": day(invoice.due_date),
            "firm_name": firm.name or "",
            "days_overdue": "",
        }
        text = render(self._wording(firm_id), values).strip()
        upi_id = self._upi_id(firm_id)
        if upi_id and due > 0:
            text += f"\n\nPay {money(due)} by UPI to {upi_id}."
        safe = invoice.invoice_number.replace("/", "-").replace(" ", "-")
        return HandShareResponse(
            document_id=invoice.id,
            document_number=invoice.invoice_number,
            phone=phone,
            whatsapp_number=whatsapp_number(phone),
            text=text,
            file_name=f"{safe}.pdf",
        )

    def record(
        self, data: HandShareRecord, *, firm_id: UUID, actor_id: UUID
    ) -> DocumentLifecycleEvent | None:
        """Put a hand share on the document's timeline and in the trail. Commits.

        Returns:
            The timeline line, or None where the firm has no document type
            for invoices set up to hang it on (the trail still has it).

        """
        invoice = self._invoice(data.document_id, firm_id=firm_id)
        recipient = (data.recipient or "").strip() or None
        type_id = self._session.scalar(
            select(DocumentTypeDefinition.id).where(
                DocumentTypeDefinition.firm_id == firm_id,
                DocumentTypeDefinition.code == data.document_type,
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        event: DocumentLifecycleEvent | None = None
        if type_id is not None:
            remark = "WhatsApp shared by hand"
            if recipient:
                remark += f" to {recipient}"
            event = DocumentLifecycleEvent(
                firm_id=firm_id,
                document_type_id=type_id,
                source_document_id=invoice.id,
                source_module_code=data.document_type,
                document_number=invoice.invoice_number,
                action=SHARED_BY_HAND,
                remarks=remark,
                details_json={"channel": data.channel, "by_hand": True},
                actor_id=actor_id,
                created_by=actor_id,
                updated_by=actor_id,
                occurred_at=utc_now(),
            )
            self._session.add(event)
        record_audit(
            self._session,
            action="message.shared_by_hand",
            entity_type="sales_invoice",
            entity_id=invoice.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "document_number": invoice.invoice_number,
                "channel": data.channel,
                "recipient": recipient,
            },
        )
        self._session.commit()
        return event

    # ------------------------------------------------------------------
    def _invoice(self, invoice_id: UUID, *, firm_id: UUID) -> SalesInvoice:
        """Return an approved invoice of the firm's, or refuse."""
        invoice = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if invoice is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        if invoice.status in {"DRAFT", "CANCELLED"}:
            raise ValidationError("Only an approved invoice can be shared.")
        return invoice

    def _due(self, invoice: SalesInvoice, *, firm_id: UUID) -> Decimal:
        """Return what the bill still owes, as the print's QR reads it."""
        from app.settlements.services.settlement_service import settled_against

        settled = settled_against(
            self._session, firm_id=firm_id, invoice_ids=[invoice.id]
        ).get(invoice.id, Decimal("0"))
        return max(invoice.grand_total - settled, Decimal("0"))

    def _wording(self, firm_id: UUID) -> str:
        """Return the firm's covering note for an approved invoice."""
        saved = self._session.scalar(
            select(MessagingEventConfig.body).where(
                MessagingEventConfig.firm_id == firm_id,
                MessagingEventConfig.event_code == "SALES_INVOICE_APPROVED",
                MessagingEventConfig.channel == "EMAIL",
                MessagingEventConfig.is_deleted.is_(False),
            )
        )
        return saved or EVENTS_BY_CODE["SALES_INVOICE_APPROVED"].default_body

    def _upi_id(self, firm_id: UUID) -> str | None:
        """Return the UPI ID the firm prints on its bills, if any."""
        from app.document_framework.models import DocumentPrintTemplate

        return self._session.scalar(
            select(DocumentPrintTemplate.upi_id).where(
                DocumentPrintTemplate.firm_id == firm_id,
                DocumentPrintTemplate.document_type == "SALES_INVOICE",
                DocumentPrintTemplate.is_deleted.is_(False),
            )
        )
