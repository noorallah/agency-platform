"""Response contract for uploaded document files."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentFileResponse(BaseModel):
    """One uploaded file's metadata; the bytes are a separate download."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purchase_invoice_id: UUID | None
    goods_receipt_id: UUID | None
    sales_quotation_id: UUID | None = None
    sales_order_id: UUID | None = None
    delivery_note_id: UUID | None = None
    sales_invoice_id: UUID | None = None
    sales_return_id: UUID | None = None
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    caption: str | None
    created_at: datetime
    created_by: UUID | None
    version: int


__all__ = ["DocumentFileResponse"]
