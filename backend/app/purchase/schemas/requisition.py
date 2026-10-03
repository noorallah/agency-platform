"""Contracts for purchase requisitions (BUY-7, decision A109)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PurchaseRequisitionLineWrite(BaseModel):
    """One product asked for."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    #: Blank takes the product's preferred supplier when converted.
    vendor_id: UUID | None = None
    remarks: str | None = Field(default=None, max_length=500)


class PurchaseRequisitionWrite(BaseModel):
    """Raise or change a requisition: the whole document."""

    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    warehouse_id: UUID
    requisition_date: date
    needed_by: date | None = None
    remarks: str | None = Field(default=None, max_length=1000)
    lines: list[PurchaseRequisitionLineWrite] = Field(min_length=1, max_length=500)


class PurchaseRequisitionLineResponse(BaseModel):
    """One requisition line, with its product named."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    line_number: int
    product_id: UUID
    product_code: str
    product_name: str
    quantity: Decimal
    vendor_id: UUID | None
    remarks: str | None
    purchase_order_id: UUID | None


class PurchaseRequisitionResponse(BaseModel):
    """One requisition and its lines."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    branch_id: UUID
    warehouse_id: UUID
    requisition_number: str
    requisition_date: date
    needed_by: date | None
    status: str
    remarks: str | None
    requested_by: UUID | None
    approved_by: UUID | None
    approved_at: datetime | None
    cancel_reason: str | None
    version: int
    lines: list[PurchaseRequisitionLineResponse]


class PurchaseRequisitionCancel(BaseModel):
    """Why a requisition is called off."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)
