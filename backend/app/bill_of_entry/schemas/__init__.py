"""Contracts for Bills of Entry (PG-12 part B, backlog 86 #5)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BillOfEntrySchema(BaseModel):
    """Base contract: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")


class BillOfEntryLineWrite(BillOfEntrySchema):
    """One item and its duty; an amount left out is worked out from its rate.

    A typed amount wins over its rate. ``sws_rate`` left out is 10% of the
    basic duty. IGST is charged on assessable value + BCD + SWS.
    """

    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    assessable_value: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    bcd_rate: Decimal | None = Field(
        default=None, ge=0, le=1000, max_digits=9, decimal_places=4
    )
    bcd_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    sws_rate: Decimal | None = Field(
        default=None, ge=0, le=1000, max_digits=9, decimal_places=4
    )
    sws_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    igst_rate: Decimal | None = Field(
        default=None, ge=0, le=1000, max_digits=9, decimal_places=4
    )
    igst_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    cess_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )


class BillOfEntryCreate(BillOfEntrySchema):
    """Type a draft Bill of Entry: the whole document."""

    boe_number: str = Field(min_length=1, max_length=30)
    boe_date: date
    port_code: str = Field(min_length=1, max_length=10)
    vendor_id: UUID
    branch_id: UUID | None = None
    #: The invoice currency customs assessed; blank or ``INR`` for rupees.
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    #: Customs' rate, rupees per unit of ``currency_code``.
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    purchase_invoice_ids: list[UUID] = Field(default_factory=list, max_length=50)
    goods_receipt_ids: list[UUID] = Field(default_factory=list, max_length=50)
    remarks: str | None = Field(default=None, max_length=2000)
    lines: list[BillOfEntryLineWrite] = Field(min_length=1, max_length=500)


class BillOfEntryUpdate(BillOfEntrySchema):
    """Change a draft; a field left out is left alone, ``null`` clears it."""

    boe_number: str | None = Field(default=None, min_length=1, max_length=30)
    boe_date: date | None = None
    port_code: str | None = Field(default=None, min_length=1, max_length=10)
    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    #: Each replaces its whole list when sent.
    purchase_invoice_ids: list[UUID] | None = Field(default=None, max_length=50)
    goods_receipt_ids: list[UUID] | None = Field(default=None, max_length=50)
    remarks: str | None = Field(default=None, max_length=2000)
    #: Replaces the lines whole when sent, reconciled on line number.
    lines: list[BillOfEntryLineWrite] | None = Field(
        default=None, min_length=1, max_length=500
    )


class BillOfEntryCancel(BillOfEntrySchema):
    """Why a Bill of Entry is withdrawn."""

    reason: str = Field(min_length=1, max_length=1000)


class BillOfEntryLineResponse(BillOfEntrySchema):
    """One item, its duty and where the cost part went when posted."""

    id: UUID
    line_number: int
    product_id: UUID
    product_code: str
    product_name: str
    quantity: Decimal
    assessable_value: Decimal
    bcd_rate: Decimal | None
    bcd_amount: Decimal
    sws_rate: Decimal | None
    sws_amount: Decimal
    #: Assessable value + BCD + SWS: what the IGST is charged on.
    igst_base: Decimal
    igst_rate: Decimal | None
    igst_amount: Decimal
    cess_amount: Decimal
    total_duty: Decimal
    inventory_amount: Decimal
    cogs_amount: Decimal
    expense_amount: Decimal


class BillOfEntryInvoiceLink(BillOfEntrySchema):
    """A supplier bill the goods came on."""

    purchase_invoice_id: UUID
    invoice_number: str
    supplier_invoice_number: str
    invoice_date: date
    status: str
    currency_code: str | None
    exchange_rate: Decimal | None
    grand_total: Decimal
    #: The bill in rupees at its own rate; null on a rupee bill.
    base_grand_total: Decimal | None


class BillOfEntryReceiptLink(BillOfEntrySchema):
    """A goods receipt the goods arrived on."""

    goods_receipt_id: UUID
    grn_number: str
    receipt_date: date
    status: str
    #: Named on the Bill of Entry itself, or reached through a linked bill.
    via_invoice: bool


class BillOfEntryResponse(BillOfEntrySchema):
    """One Bill of Entry, its lines and what it is linked to."""

    id: UUID
    document_number: str
    boe_number: str
    boe_date: date
    port_code: str
    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    branch_id: UUID | None
    currency_code: str | None
    exchange_rate: Decimal | None
    assessable_value: Decimal
    basic_customs_duty: Decimal
    social_welfare_surcharge: Decimal
    #: BCD + SWS: the part that is a cost of the goods, with no credit.
    customs_duty: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    total_duty: Decimal
    inventory_amount: Decimal
    cogs_amount: Decimal
    expense_amount: Decimal
    #: ``DRAFT``, ``POSTED`` or ``CANCELLED``.
    status: str
    posted_at: datetime | None
    journal_entry_id: UUID | None
    remarks: str | None
    cancel_reason: str | None
    version: int
    purchase_invoices: list[BillOfEntryInvoiceLink]
    goods_receipts: list[BillOfEntryReceiptLink]
    lines: list[BillOfEntryLineResponse]
