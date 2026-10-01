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
    instrument_reference: str | None = Field(default=None, max_length=120)
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
    #: What settled the bills without moving as money (backlog 74 row 2).
    rounding_amount: Decimal = Decimal("0")
    bank_charges_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    cash_amount: Decimal | None = None
    method: SettlementMethodEnum
    ledger_account_id: UUID
    ledger_account_name: str
    instrument_reference: str | None
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
    """One purchase return's credit on a supplier's account (D-FIN-19).

    A return raised from the goods receipt names no bill, so its payables
    debit stands on the vendor's account until somebody sets it against one.
    `available_amount` is what is left to set; it is derived, never stored.
    """

    purchase_return_id: UUID
    return_number: str
    return_date: date
    vendor_id: UUID
    credit_amount: Decimal
    applied_amount: Decimal
    available_amount: Decimal
    applied_to: list[str]


class SupplierCreditApplyRequest(SettlementSchema):
    """Set part of a supplier credit against one of the supplier's bills."""

    invoice_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


__all__ = [
    "SettlementAllocateRequest",
    "OutstandingInvoiceRecord",
    "SettlementPartyRecord",
    "SettlementAllocationResponse",
    "SettlementAllocationWrite",
    "SettlementCreate",
    "SettlementDirectionEnum",
    "SettlementMethodEnum",
    "SettlementResponse",
    "SettlementReverseRequest",
    "SettlementSchema",
    "SupplierCreditApplyRequest",
    "SupplierCreditRecord",
]
