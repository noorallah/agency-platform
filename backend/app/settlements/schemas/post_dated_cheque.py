"""Post-dated cheque request and response schemas (backlog 42.3, ACC-2)."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from app.settlements.schemas import SettlementAllocationWrite, SettlementSchema


class PostDatedChequeStatusEnum(StrEnum):
    """Where a post-dated cheque has got to."""

    HELD = "HELD"
    DEPOSITED = "DEPOSITED"
    CLEARED = "CLEARED"
    BOUNCED = "BOUNCED"
    CANCELLED = "CANCELLED"


class PostDatedChequeCreate(SettlementSchema):
    """Record a cheque dated ahead. Nothing is posted until it is banked."""

    party_id: UUID
    cheque_number: str = Field(min_length=1, max_length=30)
    cheque_date: date
    drawn_on_bank: str | None = Field(default=None, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    #: The day the cheque was taken in, or handed over.
    received_on: date
    narration: str | None = Field(default=None, max_length=2000)


class ChequePaidToEnum(StrEnum):
    """Who one of the firm's own cheques pays."""

    SUPPLIER = "SUPPLIER"
    CUSTOMER = "CUSTOMER"
    EXPENSE = "EXPENSE"
    ACCOUNT = "ACCOUNT"


class ChequeWrite(SettlementSchema):
    """Write one of the firm's cheques, to any account (row F13).

    Exactly one of ``supplier_id``, ``customer_id`` and ``account_id`` says
    who it pays; an account that is an expense account makes it an expense.
    Dated today or before it is recorded at once as the payment it is; dated
    ahead it is held, and posts nothing until it is presented.
    """

    #: The firm's bank account the cheque is drawn on.
    bank_account_id: UUID
    supplier_id: UUID | None = None
    #: A customer, for money handed back: presenting it records a refund.
    customer_id: UUID | None = None
    #: An expense account, or any other ledger account.
    account_id: UUID | None = None
    #: The name on the cheque. Blank takes it from the account paid.
    payee_name: str | None = Field(default=None, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    cheque_number: str = Field(min_length=1, max_length=30)
    cheque_date: date
    narration: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _pays_one_account(self) -> "ChequeWrite":
        """Hold the cheque to exactly one payee."""
        named = [
            value
            for value in (self.supplier_id, self.customer_id, self.account_id)
            if value is not None
        ]
        if len(named) != 1:
            raise ValueError(
                "Say who the cheque pays: a supplier, a customer or an "
                "account, and only one of them."
            )
        return self


class ChequeAccountRecord(SettlementSchema):
    """One ledger account offered when a cheque is written."""

    id: UUID
    code: str
    name: str


class ChequeAccountChoices(SettlementSchema):
    """The accounts *Write a cheque* offers.

    ``bank_accounts`` are what a cheque can be drawn on; ``expense_accounts``
    and ``other_accounts`` are what one can pay besides a supplier or a
    customer, who are picked from their own lists.
    """

    bank_accounts: list[ChequeAccountRecord]
    expense_accounts: list[ChequeAccountRecord]
    other_accounts: list[ChequeAccountRecord]


class PostDatedChequeDeposit(SettlementSchema):
    """Bank a held cheque, which records it as a receipt or payment."""

    #: The day it was paid in (or presented); not before the cheque's date.
    deposited_on: date
    #: The bills the money clears. Blank leaves it on account, to be applied
    #: later like any advance.
    allocations: list[SettlementAllocationWrite] = Field(default_factory=list)


class PostDatedChequeClear(SettlementSchema):
    """Record that the bank honoured a deposited cheque."""

    cleared_on: date


class PostDatedChequeBounce(SettlementSchema):
    """Record that the bank returned a deposited cheque."""

    bounced_on: date
    reason: str = Field(min_length=1, max_length=500)
    #: What the firm's own bank charged for the return. Blank or 0 is none.
    bank_charges_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    #: What the firm charges the customer for it; a customer's cheque only.
    customer_charge_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )


class PostDatedChequeCancel(SettlementSchema):
    """Cancel a held cheque: handed back, or replaced by another."""

    reason: str = Field(min_length=1, max_length=500)


class PostDatedChequeResponse(SettlementSchema):
    """One post-dated cheque and where it has got to."""

    id: UUID
    firm_id: UUID
    direction: str
    party_id: UUID
    party_code: str
    party_name: str
    #: Who the firm's own cheque pays; ``party_id`` is then that supplier,
    #: customer or ledger account. Blank on a customer's cheque.
    paid_to_kind: ChequePaidToEnum | None = None
    #: The name written on the firm's cheque.
    payee_name: str | None = None
    #: The firm's bank account it is drawn on.
    bank_account_id: UUID | None = None
    bank_account_name: str | None = None
    cheque_number: str
    cheque_date: date
    drawn_on_bank: str | None
    amount: Decimal
    received_on: date
    narration: str | None
    status: PostDatedChequeStatusEnum
    #: Held, and its date has come: it can be banked today.
    is_due: bool
    settlement_id: UUID | None
    settlement_number: str | None
    #: The expense it became, for a cheque to an expense account.
    expense_id: UUID | None = None
    expense_number: str | None = None
    #: The payment voucher it posted, for a cheque to any other account.
    journal_entry_id: UUID | None = None
    deposited_on: date | None
    cleared_on: date | None
    bounced_on: date | None
    bounce_reason: str | None
    bank_charges_amount: Decimal
    customer_charge_amount: Decimal
    charges_journal_entry_id: UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime
