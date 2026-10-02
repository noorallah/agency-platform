"""What a sales document's screen shows beside each line while it is typed."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentPreviewLine(BaseModel):
    """One line's companions in a priced preview of a sales document.

    The same for a quotation, an order and an invoice: what this customer
    last paid for the product and on which bill, and the stock free to
    promise in the warehouse the line ships from.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    line_number: int
    product_id: UUID
    #: None when the customer has never been billed for the product.
    last_price: Decimal | None = None
    last_invoice_number: str | None = None
    last_invoice_date: date | None = None
    #: The discount rate that bill carried on the line (backlog 55 G6), so
    #: the screen says what the customer last paid *net*, not only the rate.
    last_discount_percent: Decimal | None = None
    available_quantity: Decimal = Decimal("0")
    #: On open purchase orders for that warehouse, not yet received (STK-10).
    incoming_quantity: Decimal = Decimal("0")
    #: Promised on open sales orders there, not yet dispatched nor reserved.
    outgoing_quantity: Decimal = Decimal("0")
