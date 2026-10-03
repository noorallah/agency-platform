"""The documents a person may email by hand, beyond the invoice (MSG-4, A95).

The invoice could already be sent from its screen. A distributor sends far
more than invoices: the quotation an enquiry asked for, the order confirmation,
the statement before a collection visit, the receipt a customer asks for, and
the purchase order to a supplier. Each goes the same way -- queued in the
outbox, sent by the worker, logged on the document's timeline -- with its own
PDF attached and a covering note that names it.

Only email carries them. WhatsApp and SMS from the firm's own account send
registered templates, and the templates are registered for events (an invoice
approved, a payment due); a document sent by hand that way would need a
template per document type nobody has registered. A person who wants to send
one on WhatsApp shares it from their own phone (MSG-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.messaging.services.common import MessagingDocument

#: What each document is called in a covering note.
LABELS = {
    "SALES_QUOTATION": "quotation",
    "SALES_ORDER": "order confirmation",
    "CUSTOMER_STATEMENT": "statement of account",
    "RECEIPT": "receipt",
    "PURCHASE_ORDER": "purchase order",
}


@dataclass(frozen=True, slots=True)
class HandDocument:
    """One document ready to email, and to whom by default."""

    document: MessagingDocument
    customer: Customer | None
    #: The supplier's address, for a purchase order.
    vendor_email: str | None
    label: str
    party_name: str


def load_hand_document(
    session: Session, *, firm_id: UUID, document_type: str, document_id: UUID
) -> HandDocument:
    """Read a document that may be emailed by hand, refusing one that may not.

    Raises:
        ResourceNotFoundError: If it is not the firm's.
        ValidationError: If it is cancelled, reversed or otherwise not to be
            sent.

    """
    if document_type == "SALES_QUOTATION":
        from app.quotation.models import SalesQuotation

        quote = session.get(SalesQuotation, document_id)
        if quote is None or quote.firm_id != firm_id or quote.is_deleted:
            raise ResourceNotFoundError("Quotation not found.")
        _refuse_dead(quote.status, "quotation")
        return _for_customer(
            session,
            document_type,
            document_id,
            quote.quotation_number,
            quote.quotation_date,
            quote.customer_id,
            quote.grand_total,
        )
    if document_type == "SALES_ORDER":
        from app.sales_order.models import SalesOrder

        order = session.get(SalesOrder, document_id)
        if order is None or order.firm_id != firm_id or order.is_deleted:
            raise ResourceNotFoundError("Sales order not found.")
        _refuse_dead(order.status, "sales order")
        return _for_customer(
            session,
            document_type,
            document_id,
            order.order_number,
            order.order_date,
            order.customer_id,
            order.grand_total,
        )
    if document_type == "CUSTOMER_STATEMENT":
        customer = session.get(Customer, document_id)
        if customer is None or customer.firm_id != firm_id or customer.is_deleted:
            raise ResourceNotFoundError("Customer not found.")
        today = utc_now().date()
        return HandDocument(
            document=MessagingDocument(
                document_type=document_type,
                document_id=customer.id,
                document_number=f"Statement {today:%d %b %Y}",
                document_date=today,
                customer_id=customer.id,
                amount=customer.current_outstanding,
            ),
            customer=customer,
            vendor_email=None,
            label=LABELS[document_type],
            party_name=customer.display_name or customer.name,
        )
    if document_type == "RECEIPT":
        from app.settlements.models.settlement import Settlement

        receipt = session.get(Settlement, document_id)
        if (
            receipt is None
            or receipt.firm_id != firm_id
            or receipt.is_deleted
            or receipt.direction != "RECEIPT"
        ):
            raise ResourceNotFoundError("Receipt not found.")
        if receipt.status == "REVERSED":
            raise ValidationError("A reversed receipt is not sent as proof of payment.")
        return _for_customer(
            session,
            document_type,
            document_id,
            receipt.settlement_number,
            receipt.settlement_date,
            receipt.customer_id,
            receipt.amount,
        )
    if document_type == "PURCHASE_ORDER":
        from app.purchase.models import PurchaseOrder
        from app.vendors.models import Vendor

        po = session.get(PurchaseOrder, document_id)
        if po is None or po.firm_id != firm_id or po.is_deleted:
            raise ResourceNotFoundError("Purchase order not found.")
        _refuse_dead(po.status, "purchase order")
        vendor = session.get(Vendor, po.vendor_id)
        return HandDocument(
            document=MessagingDocument(
                document_type=document_type,
                document_id=po.id,
                document_number=po.po_number,
                document_date=po.purchase_date,
                customer_id=None,
                amount=po.grand_total,
            ),
            customer=None,
            vendor_email=None if vendor is None else vendor.email,
            label=LABELS[document_type],
            party_name="" if vendor is None else vendor.name,
        )
    raise ValidationError(f"{document_type} cannot be sent from here.")


def covering_note(
    session: Session, firm_id: UUID, hand: HandDocument
) -> tuple[str, str]:
    """Return the subject and body of the email a document goes under."""
    firm = FirmMetadataReader(session).get(firm_id).name or ""
    number = hand.document.document_number
    subject = f"{hand.label.capitalize()} {number} from {firm}".strip()
    greeting = f"Dear {hand.party_name}," if hand.party_name else "Hello,"
    body = (
        f"{greeting}\n\nPlease find attached our {hand.label} {number}.\n\n"
        f"Regards,\n{firm}"
    )
    return subject[:300], body


def render_attachment(
    session: Session, *, firm_id: UUID, document_type: str, document_id: UUID, on: date
) -> tuple[bytes, str] | None:
    """Return the PDF a hand-sent document attaches, rendered at send time."""
    if document_type == "SALES_QUOTATION":
        from app.quotation.services.quotation_print_service import (
            QuotationPrintService,
        )

        return QuotationPrintService(session).render(document_id, firm_scope=firm_id)
    if document_type == "SALES_ORDER":
        from app.sales_order.services.order_print_service import (
            SalesOrderPrintService,
        )

        return SalesOrderPrintService(session).render(document_id, firm_scope=firm_id)
    if document_type == "RECEIPT":
        from app.settlements.services.receipt_print import ReceiptPrintService

        return ReceiptPrintService(session).render(document_id, firm_scope=firm_id)
    if document_type == "PURCHASE_ORDER":
        from app.purchase.services.purchase_print_service import (
            PurchaseOrderPrintService,
        )

        return PurchaseOrderPrintService(session).render(
            document_id, firm_scope=firm_id
        )
    if document_type == "CUSTOMER_STATEMENT":
        from app.customers.services.statement_pdf import CustomerStatementPdfService

        return CustomerStatementPdfService(session).render(
            document_id, firm_id=firm_id, to_date=on
        )
    return None


def _refuse_dead(status: str, what: str) -> None:
    """Refuse a cancelled or rejected document."""
    if status in {"CANCELLED", "REJECTED"}:
        raise ValidationError(f"A {status.lower()} {what} is not sent.")


def _for_customer(
    session: Session,
    document_type: str,
    document_id: UUID,
    number: str,
    on: date,
    customer_id: UUID | None,
    amount: object,
) -> HandDocument:
    """Build a customer's document."""
    from decimal import Decimal

    customer = session.get(Customer, customer_id) if customer_id else None
    return HandDocument(
        document=MessagingDocument(
            document_type=document_type,
            document_id=document_id,
            document_number=number,
            document_date=on,
            customer_id=customer_id,
            amount=None if amount is None else Decimal(str(amount)),
        ),
        customer=customer,
        vendor_email=None,
        label=LABELS[document_type],
        party_name=(
            "" if customer is None else (customer.display_name or customer.name)
        ),
    )


__all__ = [
    "LABELS",
    "HandDocument",
    "covering_note",
    "load_hand_document",
    "render_attachment",
]
