"""Settlement request and response schemas."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.finance.tds import check_tds


class SettlementSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SettlementDirectionEnum(StrEnum):
    """Which way the money went."""

    RECEIPT = "RECEIPT"
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"


class SettlementMethodEnum(StrEnum):
    """How the money moved."""

    CASH = "CASH"
    BANK = "BANK"


class SettlementModeEnum(StrEnum):
    """How the money moved within its method (backlog ACC-3).

    CASH is the cash method; every other mode is money through a bank.
    """

    CASH = "CASH"
    CHEQUE = "CHEQUE"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    DEMAND_DRAFT = "DEMAND_DRAFT"
    OTHER = "OTHER"


#: The words a screen or a report shows for each mode; ``BANK`` names a bank
#: settlement recorded before the mode was asked for.
MODE_LABELS = {
    "CASH": "Cash",
    "CHEQUE": "Cheque",
    "UPI": "UPI",
    "BANK_TRANSFER": "Bank transfer",
    "CARD": "Card",
    "DEMAND_DRAFT": "Demand draft",
    "OTHER": "Other",
    "BANK": "Bank (mode not recorded)",
}


class SettlementAllocationWrite(SettlementSchema):
    """Allocate part of a settlement to one invoice."""

    invoice_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class SettlementAllocateRequest(SettlementSchema):
    """Set money already received against an invoice raised since."""

    invoice_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class SettlementReverseRequest(SettlementSchema):
    """Carry why a settlement was taken back."""

    reason: str | None = Field(default=None, max_length=500)


class SettlementCreate(SettlementSchema):
    """Record one receipt or payment that has already happened."""

    party_id: UUID
    settlement_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    method: SettlementMethodEnum
    #: How the money moved (backlog ACC-3). Blank takes CASH for the cash
    #: method and leaves a bank settlement's mode unrecorded.
    payment_mode: SettlementModeEnum | None = None
    instrument_reference: str | None = Field(default=None, max_length=120)
    #: The cheque's or draft's own date.
    instrument_date: date | None = None
    narration: str | None = Field(default=None, max_length=2000)
    settlement_number: str | None = Field(default=None, max_length=60)
    #: The sales order this money came in against, where it came in against
    #: one. A note about why the money arrived, not a ring-fence around it --
    #: if the order is cancelled the deposit stays on the customer's account.
    #: Receipts only; a payment to a vendor has no sales order behind it.
    sales_order_id: UUID | None = None
    allocations: list[SettlementAllocationWrite] = Field(default_factory=list)
    #: Tax deducted at source out of ``amount`` (backlog 53.1). ``amount`` is
    #: what settles the party -- the bill's full value -- and the cash or bank
    #: moves ``amount - tds_amount``: on a payment the firm deducted the rest
    #: and owes it to the government, on a receipt the customer did and the
    #: firm claims it. Blank or 0 means nothing was deducted.
    tds_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    #: The section the deduction is filed under, e.g. ``194Q``.
    tds_section: str | None = Field(default=None, max_length=10)
    #: What settled the bills without moving as money (backlog 74 row 2),
    #: each out of ``amount`` like TDS: a few rupees short or rounded off,
    #: bank charges a customer's bank took (receipts only), and a discount
    #: allowed on a receipt or received on a payment. Blank or 0 means none.
    #: They must be allocated: together they cannot exceed what the
    #: allocations clear, since a discount on money held on account settles
    #: nothing.
    rounding_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    bank_charges_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    #: A payment to a supplier's bills in another currency (PG-12): its ISO
    #: code and the day's rate, rupees per unit. With one, ``amount`` and each
    #: allocation's ``amount`` are in that currency, every allocation must be
    #: to a bill in it, and they must use the whole amount. The rupees paid
    #: are the amount at this rate; against the bills' own rate the
    #: difference is an exchange gain or loss. Blank or INR is rupees.
    currency_code: str | None = Field(default=None, max_length=3)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )

    @model_validator(mode="after")
    def _mode_fits_the_method(self) -> "SettlementCreate":
        """Hold the mode to its method: cash is cash, the rest are a bank's."""
        if self.payment_mode is None:
            if self.method == SettlementMethodEnum.CASH:
                self.payment_mode = SettlementModeEnum.CASH
            return self
        cash = self.payment_mode == SettlementModeEnum.CASH
        if cash != (self.method == SettlementMethodEnum.CASH):
            raise ValueError(
                "Cash is received or paid as cash; a cheque, UPI, transfer, "
                "card or draft goes through a bank. Choose the matching method."
            )
        return self

    @model_validator(mode="after")
    def _tds_can_be_filed(self) -> "SettlementCreate":
        """Refuse a deduction with no section, or one that is not a part."""
        if self.tds_section is not None:
            self.tds_section = self.tds_section.strip().upper() or None
        check_tds(self.amount, self.tds_amount, self.tds_section)
        return self

    @model_validator(mode="after")
    def _some_money_moved(self) -> "SettlementCreate":
        """Refuse deductions that, with TDS, leave no money moving.

        A balance cleared with no money at all is a party adjustment -- a
        write-off or a set-off -- with its own approval, not a receipt.
        """
        taken = (
            (self.tds_amount or Decimal("0"))
            + (self.rounding_amount or Decimal("0"))
            + (self.bank_charges_amount or Decimal("0"))
            + (self.discount_amount or Decimal("0"))
        )
        if taken >= self.amount:
            raise ValueError(
                "TDS and deductions must leave some money moving. A balance "
                "cleared without money is a party adjustment."
            )
        return self

    @model_validator(mode="after")
    def _one_row_per_invoice(self) -> "SettlementCreate":
        """Refuse the same invoice twice in one settlement.

        Two lines against one invoice are one allocation. Accepting both would
        make the invoice's outstanding depend on how somebody typed it, and the
        database refuses it anyway -- better to say so in the language of the
        request than as a constraint violation.
        """
        seen = {allocation.invoice_id for allocation in self.allocations}
        if len(seen) != len(self.allocations):
            raise ValueError("An invoice can appear only once in one settlement.")
        return self


class SettlementAllocationResponse(SettlementSchema):
    """Return one allocation with the invoice it cleared."""

    id: UUID
    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    invoice_total: Decimal
    amount: Decimal
    #: The day the money met the bill -- the settlement's date, or later for
    #: an advance applied to a bill raised since. Commission and targets count
    #: the collection in this day's period (D-TER-6).
    allocated_on: date
    #: Against a bill in another currency (PG-12): what this cleared in the
    #: bill's currency, what that part of the bill was worth in rupees at
    #: the bill's rate, and ``amount`` (the rupees paid at the payment's
    #: rate) less that -- a loss above zero, a gain below. Null and zero on
    #: a rupee allocation.
    currency_amount: Decimal | None = None
    base_amount: Decimal | None = None
    exchange_difference: Decimal = Decimal("0")


class SettlementResponse(SettlementSchema):
    """Return one settlement."""

    id: UUID
    direction: SettlementDirectionEnum
    party_id: UUID
    party_code: str
    party_name: str
    settlement_number: str
    settlement_date: date
    amount: Decimal
    allocated_amount: Decimal
    unallocated_amount: Decimal
    sales_order_id: UUID | None = None
    sales_order_number: str | None = None
    #: Tax deducted at source out of ``amount``, and what actually moved
    #: through the cash or bank account.
    tds_amount: Decimal = Decimal("0")
    tds_section: str | None = None
    #: What the server proposed a payment deduct under 194C or 194J (PG-5),
    #: kept beside ``tds_amount`` so an override shows; null where nothing
    #: was proposed (a receipt, or a supplier under neither section).
    tds_proposed_amount: Decimal | None = None
    #: What settled the bills without moving as money (backlog 74 row 2).
    rounding_amount: Decimal = Decimal("0")
    bank_charges_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    cash_amount: Decimal | None = None
    #: A payment in another currency (PG-12): the currency, the day's rate,
    #: the amount in that currency (``amount`` is the rupees), and the
    #: exchange difference posted -- a loss above zero, a gain below.
    currency_code: str | None = None
    exchange_rate: Decimal | None = None
    currency_amount: Decimal | None = None
    exchange_difference: Decimal = Decimal("0")
    method: SettlementMethodEnum
    payment_mode: SettlementModeEnum | None = None
    ledger_account_id: UUID
    ledger_account_name: str
    instrument_reference: str | None
    instrument_date: date | None = None
    narration: str | None
    status: str
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None
    allocations: list[SettlementAllocationResponse]
    version: int


class OutstandingInvoiceRecord(SettlementSchema):
    """Return one invoice with what is still owed on it.

    `outstanding_amount` is the invoice total less everything allocated to it,
    derived rather than stored. A stored paid-to-date column is a second copy
    of the allocations and drifts the first time one is written outside the
    service that maintains it.
    """

    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    invoice_total: Decimal
    allocated_amount: Decimal
    outstanding_amount: Decimal
    #: Whose bill it is, and when it fell due. Both were absent while the
    #: list was only ever asked about one party; the vendor outstanding and
    #: overdue reports ask about every party at once (D-RPT-2).
    party_id: UUID | None = None
    due_date: date | None = None
    #: A bill the supplier was owed before the firm started here, rather than
    #: a purchase invoice. It is paid the same way, but it is not a purchase
    #: invoice and cannot be opened as one.
    is_opening_bill: bool = False
    #: A supplier's bill in another currency (PG-12): the three figures above
    #: are rupees at the bill's rate; these are the bill's own currency, its
    #: total and what it still owes in it -- what a payment allocates. Null
    #: for a rupee bill.
    currency_code: str | None = None
    exchange_rate: Decimal | None = None
    currency_total: Decimal | None = None
    currency_outstanding: Decimal | None = None


class SettlementPartyRecord(SettlementSchema):
    """One party money can be taken from or paid to: a name and nothing else.

    Deliberately three fields. The money screens need to name who is paying,
    and the customer and vendor masters answer that question with credit
    limits, balances, addresses, tax registrations and everything else a
    master carries -- so reaching for them made `CUSTOMER_VIEW` the real gate
    on recording a receipt. `CASHIER` holds `RECEIPT_CREATE`, `RECEIPT_VIEW`,
    `PAYMENT_CREATE` and `PAYMENT_VIEW`, and not `CUSTOMER_VIEW`, so a cashier
    could open the till, see the Receipts screen, and be refused at the party
    lookup before the receipt they were authorised for was ever attempted.

    The alternative was granting `CUSTOMER_VIEW` to `CASHIER`, which widens a
    counter role to the whole customer master to fix a name lookup. This is
    the same answer `GET /api/v1/firm-members` gave when three copies of a
    people-list sat behind three different permissions and no screen could
    call any of them: one narrow list, gated on the thing it exists for.
    """

    id: UUID
    code: str
    name: str


class SupplierCreditRecord(SettlementSchema):
    """One return's or debit note's credit on a supplier's account (D-FIN-19).

    A return raised from the goods receipt names no bill, so its payables
    debit stands on the vendor's account until somebody sets it against one;
    a return or debit note off a bill already paid leaves what the bill could
    not absorb (D-BUY-20, A4). `available_amount` is what is left to set; it is
    derived, never stored. `source_id` is what the apply and refund routes
    take; exactly one of `purchase_return_id` and `debit_note_id` is set.
    `return_number` and `return_date` are the source document's.
    """

    source_id: UUID
    #: PURCHASE_RETURN or DEBIT_NOTE.
    source_type: str
    purchase_return_id: UUID | None = None
    debit_note_id: UUID | None = None
    return_number: str
    return_date: date
    vendor_id: UUID
    credit_amount: Decimal
    applied_amount: Decimal
    available_amount: Decimal
    #: Paid back by the supplier (backlog 69 row 7).
    refunded_amount: Decimal = Decimal("0")
    #: CREDIT, REPLACEMENT or REFUND: what the return comes back as.
    outcome: str = "CREDIT"
    applied_to: list[str]


class SupplierRefundCreate(SettlementSchema):
    """Money a supplier paid back against a return's credit (69 row 7)."""

    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    refunded_on: date
    method: SettlementMethodEnum
    reference: str | None = Field(default=None, max_length=120)
    remarks: str | None = Field(default=None, max_length=500)


class SupplierRefundReverse(SettlementSchema):
    """Why a supplier refund is being taken back."""

    reason: str = Field(min_length=1, max_length=500)


class SupplierRefundResponse(SettlementSchema):
    """One supplier refund."""

    id: UUID
    purchase_return_id: UUID | None = None
    debit_note_id: UUID | None = None
    vendor_id: UUID
    refunded_on: date
    amount: Decimal
    method: str
    reference: str | None = None
    remarks: str | None = None
    status: str
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None = None
    reversal_reason: str | None = None


class SupplierCreditApplyRequest(SettlementSchema):
    """Set part of a supplier credit against one of the supplier's bills."""

    invoice_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


__all__ = [
    "SupplierRefundCreate",
    "SupplierRefundResponse",
    "SupplierRefundReverse",
    "SettlementAllocateRequest",
    "OutstandingInvoiceRecord",
    "SettlementPartyRecord",
    "SettlementAllocationResponse",
    "SettlementAllocationWrite",
    "SettlementCreate",
    "SettlementDirectionEnum",
    "SettlementMethodEnum",
    "SettlementModeEnum",
    "MODE_LABELS",
    "SettlementResponse",
    "SettlementReverseRequest",
    "SettlementSchema",
    "SupplierCreditApplyRequest",
    "SupplierCreditRecord",
]
