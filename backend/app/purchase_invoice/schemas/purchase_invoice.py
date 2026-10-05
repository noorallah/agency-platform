"""Validated contracts for purchase invoices."""

import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.business.schemas import AttributeValueInput, AttributeValueResponse
from app.sales.schemas.document_preview import DocumentPreviewLine
from app.settlements.schemas import SettlementMethodEnum, SettlementModeEnum


class PurchaseInvoiceSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


def normalize_irn(value: str | None) -> str | None:
    """Return an IRN in lower case, None for blank; refuse a malformed one.

    An IRN is the SHA-256 hash the portal returns: 64 hexadecimal characters.
    """
    if value is None or not str(value).strip():
        return None
    token = str(value).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise ValueError(
            "An IRN is 64 letters and digits (0-9, a-f), as printed under the "
            "QR code on the supplier's e-invoice."
        )
    return token


class PurchaseInvoiceStatus(StrEnum):
    """Supported purchase invoice lifecycle statuses."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class PurchaseInvoiceSourceType(StrEnum):
    """Documents a purchase invoice can be raised from."""

    GOODS_RECEIPT = "GOODS_RECEIPT"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    MANUAL = "MANUAL"


class PurchaseInvoiceAccountingEventType(StrEnum):
    """Accounting events a purchase invoice can raise."""

    PURCHASE_EXPENSE = "PURCHASE_EXPENSE"
    INPUT_TAX = "INPUT_TAX"
    ACCOUNTS_PAYABLE = "ACCOUNTS_PAYABLE"


class PurchaseInvoiceAttachmentWrite(PurchaseInvoiceSchema):
    """Carry one purchase invoice attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(
        default="PURCHASE_INVOICE_FILE", min_length=1, max_length=40
    )


class PurchaseInvoiceNoteWrite(PurchaseInvoiceSchema):
    """Carry one purchase invoice note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class PurchaseInvoiceSourceWrite(PurchaseInvoiceSchema):
    """Carry one purchase invoice source into a request."""

    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID


class PurchaseInvoiceLineWrite(PurchaseInvoiceSchema):
    """Carry one purchase invoice line into a request.

    A line names the goods-receipt line it bills. For a firm that switched the
    purchase-order and goods-receipt stages off (`purchase_workflow_settings`)
    a line may instead name only a **product** -- the source fields left out --
    and `PurchaseChainService` raises the order and the receipt behind the bill
    and points the line at them. ``free_quantity`` is read on such a line only;
    on a line naming a receipt the free goods are the receipt's.
    """

    source_document_type: PurchaseInvoiceSourceType | None = None
    source_document_id: UUID | None = None
    source_document_line_id: UUID | None = None
    product_id: UUID | None = None
    free_quantity: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    line_number: int = Field(ge=1)
    current_invoice_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    #: None means the caller said nothing, so the price on the source line
    #: carries over. Zero is an instruction, not a default: it defaulted to
    #: zero once, and a bill sent without prices was valued at nothing
    #: (D-BUY-3).
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: None means the caller said nothing, so the rate on the source line
    #: carries over. Zero means they said no discount on this one.
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    charges_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    #: Whether this line's tax is claimable (backlog 78 row 1). None takes the
    #: product's setting, then a tax rule's *Input credit blocked*.
    itc_eligibility: Literal["ELIGIBLE", "BLOCKED", "INELIGIBLE"] | None = None
    #: Capital goods (PG-13): approving the bill raises a fixed asset in
    #: ``asset_class_id`` instead of putting the goods into stock. The line
    #: bills the bill's own receipt (a firm typing only the bill), or a
    #: receipt line that was itself received as capital goods (D-BUY-40);
    #: a line a receipt has already taken into stock is refused. Absent takes
    #: the receipt line's mark; false on a line received as capital goods is
    #: refused.
    is_capital_goods: bool | None = None
    asset_class_id: UUID | None = None
    packaging_type_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    invoice_uom_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    expiry_date: date | None = None
    manufacturing_date: date | None = None
    remarks: str | None = None


class PurchaseInvoiceCreate(PurchaseInvoiceSchema):
    """Create one purchase invoice."""

    #: The firm's own fields on the document (MST-6). Replaced whole when
    #: sent; an update that omits them leaves them alone.
    attributes: list[AttributeValueInput] = Field(default_factory=list, max_length=100)

    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    business_profile_id: UUID | None = None
    invoice_date: date
    supplier_invoice_number: str = Field(min_length=1, max_length=120)
    supplier_invoice_date: date
    #: The IRN on the supplier's e-invoice (backlog 78 row 5). Absent on an
    #: edit keeps the one on file; null clears it.
    supplier_irn: str | None = None
    #: The currency the supplier billed in (PG-12), an ISO code. Blank or INR
    #: is rupees; absent on a new bill takes the supplier's currency, absent
    #: on an edit keeps the bill's. Any other currency needs
    #: ``exchange_rate``: the rupees one unit was worth on the bill's date.
    #: Rates and totals are typed in the bill's currency.
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    payment_terms: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    #: TCS the supplier charged on the bill (206C(1H), PG-6). A typed
    #: ``tcs_amount`` wins; with only the rate the amount is the rate on the
    #: grand total. Both absent on an edit keep what the bill has; null
    #: clears.
    tcs_rate_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    tcs_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    invoice_number: str | None = Field(default=None, max_length=60)
    source_documents: list[PurchaseInvoiceSourceWrite] = Field(
        default_factory=list, max_length=100
    )
    lines: list[PurchaseInvoiceLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[PurchaseInvoiceAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[PurchaseInvoiceNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("invoice_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None

    @field_validator("supplier_irn", mode="before")
    @classmethod
    def _irn(cls, value: str | None) -> str | None:
        """Check the IRN's shape and store it in lower case."""
        return normalize_irn(value)


class PurchaseInvoiceSupplierIrnWrite(PurchaseInvoiceSchema):
    """Record or clear the IRN on a bill already approved (backlog 78 row 5)."""

    supplier_irn: str | None

    @field_validator("supplier_irn", mode="before")
    @classmethod
    def _irn(cls, value: str | None) -> str | None:
        """Check the IRN's shape and store it in lower case."""
        return normalize_irn(value)


class PurchaseInvoicePaymentNow(PurchaseInvoiceSchema):
    """Money paid over the counter as the bill is approved (PG-3, §86 #19).

    Recorded as an ordinary payment, the same row ``POST /payments`` writes,
    allocated to this bill, so reversing it is the usual payment reversal.
    """

    #: CASH or BANK; the money leaves the account the firm mapped to it.
    method: SettlementMethodEnum
    #: How the money moved within its method; blank takes CASH for cash.
    payment_mode: SettlementModeEnum | None = None
    #: Blank pays what the bill owes once approved -- its grand total. Less
    #: leaves the rest outstanding; more is refused, since an advance is
    #: recorded on its own through ``/payments``.
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    #: Blank takes the bill's own date.
    payment_date: date | None = None
    instrument_reference: str | None = Field(default=None, max_length=120)
    instrument_date: date | None = None
    narration: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _mode_fits_the_method(self) -> "PurchaseInvoicePaymentNow":
        """Hold the mode to its method, as a payment does."""
        if self.payment_mode is None:
            if self.method == SettlementMethodEnum.CASH:
                self.payment_mode = SettlementModeEnum.CASH
            return self
        cash = self.payment_mode == SettlementModeEnum.CASH
        if cash != (self.method == SettlementMethodEnum.CASH):
            raise ValueError(
                "Cash is paid as cash; a cheque, UPI, transfer, card or draft "
                "goes through a bank. Choose the matching method."
            )
        return self


class PurchaseInvoiceApproveRequest(PurchaseInvoiceSchema):
    """Approve a bill, optionally paying it in the same transaction (PG-3)."""

    payment: PurchaseInvoicePaymentNow | None = None
    #: Overrides the TDS the bill proposes under 194C or 194J (PG-5). Absent
    #: or null takes the proposal; 0 deducts nothing. The bill keeps the
    #: proposal beside it and the trail records both.
    tds_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )


class PurchaseInvoiceUpdate(PurchaseInvoiceCreate):
    """Replace one purchase invoice."""

    pass


class PurchaseInvoiceImportRequest(PurchaseInvoiceSchema):
    """Import a validated batch of purchase invoices."""

    records: list[PurchaseInvoiceCreate] = Field(min_length=1, max_length=500)


class PurchaseInvoiceAttachmentResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice attachment."""

    id: UUID
    purchase_invoice_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceNoteResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceSourceResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice source."""

    id: UUID
    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_date: date
    vendor_id: UUID
    branch_id: UUID
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceAccountingEventResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice accounting event."""

    id: UUID
    event_type: PurchaseInvoiceAccountingEventType
    account_name: str
    direction: str
    amount: Decimal
    narration: str | None
    source_line_id: UUID | None
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceLineTaxResponse(PurchaseInvoiceSchema):
    """One tax component the line was charged, as it was charged.

    Read from the bill rather than recomputed: rules are effective-dated, so
    asking the engine again a year later can answer differently from what the
    supplier charged, and the input credit claimed against it.
    """

    id: UUID
    sequence: int
    tax_component_id: UUID | None
    component_code: str
    component_label: str
    percentage: Decimal
    base_amount: Decimal
    amount: Decimal
    included_in_price: bool
    recoverable: bool
    #: Owed by the firm under reverse charge, not charged by the supplier.
    reverse_charge: bool = False


class PurchaseInvoiceLineResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice line."""

    id: UUID
    purchase_invoice_id: UUID
    line_number: int
    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    description: str | None
    received_quantity: Decimal
    already_invoiced_quantity: Decimal
    current_invoice_quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    bill_discount_amount: Decimal = Decimal("0")
    charges_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    itc_eligibility: str = "ELIGIBLE"
    is_capital_goods: bool = False
    asset_class_id: UUID | None = None
    tax_amount: Decimal
    net_amount: Decimal
    packaging_type_id: UUID | None
    purchase_uom_id: UUID | None
    invoice_uom_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    batch_number: str | None
    expiry_date: date | None
    manufacturing_date: date | None
    remarks: str | None
    accounting_event_reference: str | None
    taxes: list[PurchaseInvoiceLineTaxResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    #: The tax rule that decided the line and its version; null when the
    #: profile alone did (GST-8).
    tax_rule_code: str | None = None
    tax_rule_version: int | None = None


class PurchaseInvoiceResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice."""

    #: The firm's own fields on the document (MST-6).
    attributes: list[AttributeValueResponse] = Field(default_factory=list)
    #: How many uploaded files the bill carries (PG-4), so a list can show a
    #: paper clip without asking per row. Counted once for the page.
    attached_file_count: int = 0

    id: UUID
    firm_id: UUID
    vendor_id: UUID
    #: Whose document it is, so the list can say so (owner, 2026-09-27).
    #: Empty for a supplier since removed.
    vendor_name: str = ""
    vendor_code: str = ""
    branch_id: UUID
    business_profile_id: UUID | None
    invoice_number: str
    invoice_date: date
    supplier_invoice_number: str
    supplier_invoice_date: date
    supplier_irn: str | None = None
    currency_code: str | None
    exchange_rate: Decimal | None
    payment_terms: str | None
    due_date: date | None
    reference_number: str | None
    remarks: str | None
    status: PurchaseInvoiceStatus
    total_source_quantity: Decimal
    total_already_invoiced_quantity: Decimal
    total_current_invoice_quantity: Decimal
    line_discount_total: Decimal
    subtotal: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    #: Tax owed by the firm under reverse charge, outside the payable
    #: (backlog 68 row 8), and the self-invoice raised for it.
    reverse_charge_tax_total: Decimal = Decimal("0")
    self_invoice_number: str | None = None
    #: TDS deducted on the bill at approval (PG-5): the section, what it was
    #: deducted on (the bill before GST), what the server proposed and what
    #: was deducted. The supplier is owed ``grand_total - tds_amount``.
    tds_section: str | None = None
    tds_base_amount: Decimal = Decimal("0")
    tds_proposed_amount: Decimal | None = None
    tds_amount: Decimal = Decimal("0")
    #: TCS the supplier charged (PG-6), outside GST; the supplier is owed
    #: ``amount_owed``: ``grand_total + tcs_amount - tds_amount``.
    tcs_rate_percent: Decimal | None = None
    tcs_amount: Decimal = Decimal("0")
    amount_owed: Decimal = Decimal("0")
    #: The bill in rupees (PG-12). For a bill in another currency -- whose
    #: ``currency_code``, ``exchange_rate`` and every figure above are as the
    #: supplier billed -- these are what the ledger posted at the bill's
    #: rate, the goods and the tax each rounded on their own. For a rupee
    #: bill they repeat its own totals.
    base_tax_total: Decimal = Decimal("0")
    base_grand_total: Decimal = Decimal("0")
    base_amount_owed: Decimal = Decimal("0")
    approved_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    close_reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lines: list[PurchaseInvoiceLineResponse] = Field(default_factory=list)
    sources: list[PurchaseInvoiceSourceResponse] = Field(default_factory=list)
    attachments: list[PurchaseInvoiceAttachmentResponse] = Field(default_factory=list)
    notes: list[PurchaseInvoiceNoteResponse] = Field(default_factory=list)
    accounting_events: list[PurchaseInvoiceAccountingEventResponse] = Field(
        default_factory=list
    )
    duplicate_warning: str | None = None
    #: Why the IRN wants a look (backlog 78 row 5): the supplier e-invoices
    #: and the bill has none, or another bill carries the same one.
    irn_warning: str | None = None
    # Set when the bill is entered past 30 November after the year of the
    # supplier's invoice, so its credit can no longer be claimed (s.16(4),
    # GST-3).
    credit_time_limit_warning: str | None = None


class PurchaseInvoiceListFilters(PurchaseInvoiceSchema):
    """Narrow a purchase invoice list to the rows a caller asked for."""

    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    status: PurchaseInvoiceStatus | None = None
    invoice_from: date | None = None
    invoice_to: date | None = None
    due_from: date | None = None
    due_to: date | None = None
    include_deleted: bool = False


class PurchaseInvoiceSummary(PurchaseInvoiceSchema):
    """Aggregate purchase invoice counts for the visible firm scope."""

    total: int
    draft: int
    approved: int
    cancelled: int
    closed: int
    total_value: Decimal
    pending_invoices: int
    overdue_invoices: int


class PurchaseInvoiceRegisterRecord(PurchaseInvoiceSchema):
    """One row of the purchase invoice register report."""

    invoice_id: UUID
    invoice_number: str
    supplier_invoice_number: str
    vendor_id: UUID
    #: Each id keeps a name beside it: the grid derives its columns from the
    #: row, so a register of ids alone showed two columns of UUIDs (D-RPT-17).
    vendor_name: str
    branch_id: UUID
    branch_name: str
    invoice_date: date
    due_date: date | None
    grand_total: Decimal
    status: PurchaseInvoiceStatus


class PurchaseInvoiceReconciliationRecord(PurchaseInvoiceSchema):
    """One source line and what has been billed against it.

    One row per goods-receipt line, not per invoice line: the quantities are
    summed over the live invoices that bill it -- `invoiced_quantity` from
    APPROVED and CLOSED ones, `draft_quantity` from DRAFT -- and `pending` is
    what is left. The report used to answer one row per invoice line carrying
    the three quantities snapshotted on that line when it was written, so a
    source billed twice appeared twice with the older `pending` stale, and a
    cancelled invoice's line still claimed its quantity billed (D-RPT-13).
    """

    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    #: The product named as well as identified, in one read for the report
    #: (D-RPT-17): a reconciliation whose only product column is a UUID
    #: cannot be read against the receipt it reconciles.
    product_code: str
    product_name: str
    received_quantity: Decimal
    invoiced_quantity: Decimal
    draft_quantity: Decimal
    pending_quantity: Decimal
    invoice_numbers: str


class PurchaseInvoiceVendorOutstandingRecord(PurchaseInvoiceSchema):
    """One row of the purchase invoice vendor outstanding report.

    ``outstanding_amount`` is what the supplier's bills still owe once every
    posted payment, completed return and applied credit is taken off -- the
    same derivation Record Payment offers -- and ``invoice_count`` counts only
    the bills still owing anything. The report used to sum ``grand_total`` of
    every non-cancelled bill and count them all, so a supplier paid in full was
    owed the whole bill for ever (D-RPT-2).
    """

    vendor_id: UUID
    vendor_name: str
    outstanding_amount: Decimal
    invoice_count: int


class PurchaseInvoiceOverdueRecord(PurchaseInvoiceSchema):
    """One bill past its due date and still owing something.

    A flat row rather than the whole document: the desktop showed six columns
    of it and the endpoint answered forty fields, lines, attachments and notes
    per bill (D-RPT-16). ``outstanding_amount`` is derived as Record Payment
    derives it, so a bill paid in full leaves the list the day it is paid, and
    a DRAFT -- not yet a debt -- was never on it.
    """

    invoice_id: UUID
    invoice_number: str
    supplier_invoice_number: str | None
    vendor_id: UUID
    vendor_name: str
    invoice_date: date
    due_date: date
    days_overdue: int
    #: How many days until it falls due: 0 on the overdue list, and on the
    #: due list (ACC-6) 0 for today, 1 for tomorrow.
    days_until_due: int = 0
    grand_total: Decimal
    allocated_amount: Decimal
    outstanding_amount: Decimal


class PurchaseInvoiceMsmeDueRecord(PurchaseInvoiceSchema):
    """One unpaid bill to a micro or small supplier, against its legal date.

    Backlog 68 row 2. ``state`` is OVERDUE past ``pay_by``, DUE_SOON within
    seven days of it, otherwise OPEN; an overdue one is an expense the firm
    cannot claim this year (Income Tax s.43B(h)) until it is paid.
    """

    invoice_id: UUID
    invoice_number: str
    supplier_invoice_number: str | None
    vendor_id: UUID
    vendor_name: str
    udyam_number: str | None
    msme_category: str | None
    invoice_date: date
    due_date: date | None
    pay_by: date
    days_left: int
    state: Literal["OVERDUE", "DUE_SOON", "OPEN"]
    outstanding_amount: Decimal


class PurchaseInvoicePreview(PurchaseInvoiceSchema):
    """A supplier bill priced exactly as saving it would, without saving it.

    ``interstate`` says how its tax splits: IGST from a supplier in another
    state, CGST and SGST from one in the firm's own. ``lines`` carries each
    line's last price from this vendor and the stock where it was received.
    """

    invoice: PurchaseInvoiceResponse
    interstate: bool
    lines: list[DocumentPreviewLine]
