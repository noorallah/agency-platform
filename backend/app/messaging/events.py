"""The events a firm may choose to send a message on, and what each offers.

A template is filled from the event's **variables, in the order listed here**:
WhatsApp's ``{{1}}`` and MSG91's ``var1`` are the first, and so on. Email
subject and body use the names, ``{customer_name}``. The order is therefore a
contract with every template a firm has had approved, and must only ever be
appended to.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MessagingEvent:
    """One event a firm may switch on."""

    code: str
    label: str
    #: The module code of the document it is about.
    document_type: str
    variables: tuple[str, ...]
    default_subject: str
    default_body: str
    #: A reminder: the customer's *no reminders* skips it.
    is_reminder: bool = False
    #: Email attaches the document's PDF.
    attaches_pdf: bool = False


_SIGN_OFF = "\n\nRegards,\n{firm_name}"

EVENTS: tuple[MessagingEvent, ...] = (
    MessagingEvent(
        code="SALES_INVOICE_APPROVED",
        label="Invoice approved",
        document_type="SALES_INVOICE",
        variables=(
            "customer_name",
            "document_number",
            "document_date",
            "amount",
            "due_date",
            "firm_name",
        ),
        default_subject="Invoice {document_number} from {firm_name}",
        default_body=(
            "Dear {customer_name},\n\nPlease find attached invoice "
            "{document_number} dated {document_date} for {amount}, due on "
            "{due_date}." + _SIGN_OFF
        ),
        attaches_pdf=True,
    ),
    MessagingEvent(
        code="SALES_ORDER_APPROVED",
        label="Sales order approved",
        document_type="SALES_ORDER",
        variables=(
            "customer_name",
            "document_number",
            "document_date",
            "amount",
            "firm_name",
        ),
        default_subject="Order {document_number} confirmed",
        default_body=(
            "Dear {customer_name},\n\nYour order {document_number} dated "
            "{document_date} for {amount} is confirmed." + _SIGN_OFF
        ),
    ),
    MessagingEvent(
        code="DELIVERY_DISPATCHED",
        label="Goods dispatched",
        document_type="DELIVERY_NOTE",
        variables=("customer_name", "document_number", "document_date", "firm_name"),
        default_subject="Goods dispatched: {document_number}",
        default_body=(
            "Dear {customer_name},\n\nThe goods on delivery note "
            "{document_number} were dispatched on {document_date}." + _SIGN_OFF
        ),
    ),
    MessagingEvent(
        code="RECEIPT_POSTED",
        label="Payment received",
        document_type="RECEIPT",
        variables=(
            "customer_name",
            "document_number",
            "document_date",
            "amount",
            "firm_name",
        ),
        default_subject="Payment received: {document_number}",
        default_body=(
            "Dear {customer_name},\n\nWe have received {amount} on "
            "{document_date}, receipt {document_number}. Thank you." + _SIGN_OFF
        ),
    ),
    MessagingEvent(
        code="PAYMENT_DUE_SOON",
        label="Payment due soon",
        document_type="SALES_INVOICE",
        variables=(
            "customer_name",
            "document_number",
            "amount_due",
            "due_date",
            "firm_name",
        ),
        default_subject="Reminder: invoice {document_number} is due on {due_date}",
        default_body=(
            "Dear {customer_name},\n\nA reminder that {amount_due} on invoice "
            "{document_number} falls due on {due_date}." + _SIGN_OFF
        ),
        is_reminder=True,
    ),
    MessagingEvent(
        code="PAYMENT_OVERDUE",
        label="Payment overdue",
        document_type="SALES_INVOICE",
        variables=(
            "customer_name",
            "document_number",
            "amount_due",
            "due_date",
            "days_overdue",
            "firm_name",
        ),
        default_subject="Overdue: invoice {document_number}",
        default_body=(
            "Dear {customer_name},\n\nInvoice {document_number} fell due on "
            "{due_date} and {amount_due} is still outstanding, "
            "{days_overdue} days overdue. Please arrange payment." + _SIGN_OFF
        ),
        is_reminder=True,
    ),
)

EVENTS_BY_CODE: dict[str, MessagingEvent] = {event.code: event for event in EVENTS}

#: What a person sending an invoice by hand is recorded as. Not configurable:
#: it borrows the template the firm named for SALES_INVOICE_APPROVED.
MANUAL_SEND = "MANUAL_SEND"


class _Blank(dict[str, str]):
    """A mapping that renders an unknown placeholder as itself."""

    def __missing__(self, key: str) -> str:
        """Leave ``{unknown}`` in place rather than failing the send."""
        return "{" + key + "}"


def render(template: str, values: dict[str, str]) -> str:
    """Fill ``{name}`` placeholders; a stray brace never fails a send."""
    try:
        return template.format_map(_Blank(values))
    except (ValueError, IndexError):
        return template
