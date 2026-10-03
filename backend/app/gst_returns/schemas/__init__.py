"""GST settlement request and response schemas (backlog 63)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GstSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class GstHeadRow(GstSchema):
    """One head of a month's settlement: owed, credit, paid, carried."""

    #: IGST, CGST, SGST or CESS.
    head: str
    liability: Decimal
    credit_brought_forward: Decimal
    credit_available: Decimal
    paid_by_credit: Decimal
    cash: Decimal
    credit_used: Decimal
    carried_forward: Decimal
    #: Reverse charge on inward supplies (3.1(d)): paid in cash only, never
    #: by credit, on top of `cash` (backlog 68 row 8).
    reverse_charge: Decimal = Decimal("0")
    #: Of the cash, what PMT-06 deposits paid rather than the bank (GST-7).
    paid_from_deposits: Decimal = Decimal("0")


class GstUtilisationRow(GstSchema):
    """How much of one head's credit paid one head's liability."""

    credit_head: str
    liability_head: str
    amount: Decimal


class GstPaymentPreviewResponse(GstSchema):
    """What a month owes, what its credit pays, what is left to pay in cash."""

    return_period: str
    due_date: date
    #: False when no settlement of the month before is recorded, so the
    #: brought-forward credit is what was stated as the opening credit.
    previous_settled: bool
    days_late: int
    #: Section 50 interest at 18% a year on the cash, for the days late.
    suggested_interest: Decimal
    cash_total: Decimal
    heads: list[GstHeadRow]
    utilisation: list[GstUtilisationRow]
    #: The first day covered: the month's, or the quarter's (GST-7).
    period_from: date | None = None
    #: What the PMT-06 deposits pay of ``cash_total``.
    deposits_total: Decimal = Decimal("0")
    #: What is left for the bank, before interest and late fee.
    bank_total: Decimal = Decimal("0")


class GstPaymentCreate(GstSchema):
    """Record a month's challan: the set-off and the cash paid."""

    return_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    payment_date: date
    money_account_id: UUID
    challan_cpin: str | None = Field(default=None, max_length=20)
    challan_cin: str | None = Field(default=None, max_length=30)
    interest_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    interest_account_id: UUID | None = None
    late_fee_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    late_fee_account_id: UUID | None = None
    #: The credit brought forward on the firm's first month here, from the
    #: portal's electronic credit ledger. Ignored once a month is recorded.
    opening_credit_igst: Decimal | None = Field(default=None, ge=0)
    opening_credit_cgst: Decimal | None = Field(default=None, ge=0)
    opening_credit_sgst: Decimal | None = Field(default=None, ge=0)
    opening_credit_cess: Decimal | None = Field(default=None, ge=0)
    narration: str | None = Field(default=None, max_length=2000)


class GstPaymentReverse(GstSchema):
    """Why a month's settlement is being taken back."""

    reason: str = Field(min_length=1, max_length=500)


class GstPaymentResponse(GstSchema):
    """One recorded month's settlement."""

    id: UUID
    return_period: str
    payment_date: date
    status: str
    challan_cpin: str | None
    challan_cin: str | None
    money_account_id: UUID
    heads: list[GstHeadRow]
    cash_total: Decimal
    #: What the PMT-06 deposits paid of ``cash_total`` (GST-7).
    deposits_total: Decimal = Decimal("0")
    interest_amount: Decimal
    late_fee_amount: Decimal
    narration: str | None
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    reversal_reason: str | None
    reversed_at: datetime | None
    version: int


__all__ = [
    "FilingCheckRowResponse",
    "FilingChecksResponse",
    "GstHeadRow",
    "GstPaymentCreate",
    "GstPaymentPreviewResponse",
    "GstPaymentResponse",
    "GstPaymentReverse",
    "GstUtilisationRow",
]


class TaxCalendarItemResponse(GstSchema):
    """One return or deposit a month owes, on Home's tax calendar (63.4)."""

    #: ``GSTR1``, ``GSTR3B``, ``TCS``; for a quarterly filer's months 1 and
    #: 2, ``IFF`` and ``PMT06`` (GST-7).
    kind: str
    return_period: str
    due_date: date
    #: GSTR-1: the month's output tax. GSTR-3B: the cash its payment works
    #: out to. TCS: what was collected.
    amount: Decimal
    #: ``DONE``, ``DUE`` or ``LATE``; ``OPTIONAL`` for an IFF not filed.
    status: str
    days_late: int
    done_on: date | None = None
    #: The ARN, or the challan's CPIN, where one was kept.
    reference: str | None = None
    #: The filed-return record behind a done item, which can be withdrawn.
    filing_id: UUID | None = None
    #: The first day the item covers: its month's, or its quarter's (GST-7).
    period_from: date | None = None


class GstReturnFilingCreate(GstSchema):
    """Say a return was filed on the portal (63.4)."""

    #: IFF only for month 1 or 2 of a quarter filed quarterly (GST-7).
    return_type: Literal["GSTR1", "GSTR3B", "IFF"]
    return_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    filed_on: date
    arn: str | None = Field(default=None, max_length=30)
    remarks: str | None = Field(default=None, max_length=500)


class GstReturnFilingResponse(GstSchema):
    """A return recorded as filed."""

    id: UUID
    return_type: str
    return_period: str
    filed_on: date
    arn: str | None = None
    remarks: str | None = None


class Gstr2bImportCreate(GstSchema):
    """One month's GSTR-2B JSON, as downloaded from the portal (78.3)."""

    return_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    #: The file's text. A 2B for a busy month runs to a few megabytes.
    content: str = Field(min_length=2, max_length=20_000_000)
    source_name: str | None = Field(default=None, max_length=260)


class Gstr2bImportResponse(GstSchema):
    """What an import read."""

    id: UUID
    return_period: str
    gstin: str | None
    source_name: str | None
    document_count: int
    skipped_sections: str | None


class Gstr2bMatchRequest(GstSchema):
    """Match a 2B row to a bill by hand; null undoes a hand match."""

    purchase_invoice_id: UUID | None


class Rule37Heads(GstSchema):
    """Tax by GST head."""

    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal


class Rule37RowResponse(GstSchema):
    """One bill with credit to reverse or reclaim under rule 37 (78.4)."""

    purchase_invoice_id: UUID
    invoice_number: str
    supplier_invoice_number: str | None
    vendor_name: str
    bill_date: date
    days: int
    bill_total: Decimal
    outstanding: Decimal
    #: The credit the bill claimed in 4(A)(5).
    credit: Rule37Heads
    #: What stands reversed on it now.
    reversed: Rule37Heads
    #: REVERSE or RECLAIM.
    action: str
    #: How much to move, by head, always positive.
    amount: Rule37Heads


class Rule37Response(GstSchema):
    """The rule 37 list as of a day, with the firm's choice."""

    as_of: date
    #: OFF, REPORT or POST (Settings > Tax > GST Documents).
    mode: str
    rows: list[Rule37RowResponse]


class Rule37Post(GstSchema):
    """Post what is due as of a day; every bill listed, or only these."""

    as_of: date
    purchase_invoice_ids: list[UUID] | None = Field(default=None, max_length=1000)


class FilingCheckRowResponse(GstSchema):
    """One thing to put right before a return is filed (GST-5)."""

    #: GSTIN_INVALID, HSN_MISSING, HSN_SHORT, PLACE_OF_SUPPLY_MISSING,
    #: IRN_MISSING, CREDIT_NOTE_LATE or CREDIT_NOTE_ON_CANCELLED_INVOICE.
    check: str
    #: ERROR: the portal or the law refuses it. WARNING: worth a look.
    severity: str
    #: SALES_INVOICE, CREDIT_NOTE, CUSTOMER_DEBIT_NOTE, PURCHASE_INVOICE or
    #: FIRM (the firm's own GSTIN).
    document_type: str
    document_id: UUID | None
    document_number: str
    document_date: date | None
    party_name: str
    message: str


class FilingChecksResponse(GstSchema):
    """What a period's documents would trip on, before filing."""

    from_date: date
    to_date: date
    #: Digits an HSN must carry: six once the firm e-invoices (turnover past
    #: 5 crore), four below it.
    required_hsn_digits: int
    #: Rows by check, for the summary line.
    counts: dict[str, int]
    rows: list[FilingCheckRowResponse]


class GstCashDepositCreate(GstSchema):
    """Record a PMT-06 challan for month 1 or 2 of a quarter (GST-7)."""

    return_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    deposit_date: date
    money_account_id: UUID
    #: FIXED_SUM or SELF_ASSESSMENT; the firm's setting when left out.
    method: Literal["FIXED_SUM", "SELF_ASSESSMENT"] | None = None
    amount_igst: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    amount_cgst: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    amount_sgst: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    amount_cess: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    challan_cpin: str | None = Field(default=None, max_length=20)
    challan_cin: str | None = Field(default=None, max_length=30)
    narration: str | None = Field(default=None, max_length=2000)


class GstCashDepositResponse(GstSchema):
    """One PMT-06 deposit."""

    id: UUID
    return_period: str
    deposit_date: date
    method: str
    money_account_id: UUID
    challan_cpin: str | None
    challan_cin: str | None
    amount_igst: Decimal
    amount_cgst: Decimal
    amount_sgst: Decimal
    amount_cess: Decimal
    total: Decimal
    narration: str | None
    status: str
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    reversal_reason: str | None
    reversed_at: datetime | None
    version: int


class GstDepositSuggestionResponse(GstSchema):
    """What a month's PMT-06 deposit should be, and why (GST-7)."""

    return_period: str
    method: str
    due_date: date
    heads: Rule37Heads
    total: Decimal
    basis: str
    #: What standing deposits for the month already paid.
    deposited: Rule37Heads


class GstFilingPlanResponse(GstSchema):
    """How the firm files, and the cash ledger's balance (GST-7)."""

    filing_frequency: str
    quarterly_from: date | None
    qrmp_payment_method: str
    #: PMT-06 deposits no settlement has used yet.
    cash_ledger: Rule37Heads
