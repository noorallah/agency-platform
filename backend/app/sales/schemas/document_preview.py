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
    available_quantity: Decimal = Decimal("0")
