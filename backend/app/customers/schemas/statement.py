"""Response models for the customer statement and the receivables ageing."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StatementSchema(BaseModel):
    """Shared configuration for every statement payload."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CustomerStatementLine(StatementSchema):
    """One movement on a customer's account."""

    transaction_date: date
    transaction_type: str
    reference_number: str | None = None
    remarks: str | None = None
    #: Split from one signed delta so the statement reads the way a ledger
    #: does: a debit is what the customer owes more of.
    debit: Decimal
    credit: Decimal
    #: Recomputed in date order rather than read off the stored snapshot,
    #: which was taken in the order rows were written.
    balance: Decimal


class CustomerStatement(StatementSchema):
    """A customer's account over one period."""

    customer_id: UUID
    customer_code: str
    customer_name: str
    from_date: date
    to_date: date
    opening_balance: Decimal
    closing_balance: Decimal
    #: Held on account and not yet applied to any bill. Beside the balance
    #: rather than folded into it: netting them hides an advance the customer
    #: is entitled to have applied.
    unapplied_advance: Decimal
    lines: list[CustomerStatementLine]


class OverdueInvoice(StatementSchema):
    """One bill that is still owed, and for how long."""

    invoice_number: str
    invoice_date: date
    #: The invoice's own due date where it has one, and its date otherwise: a
    #: bill with no terms is due when it is raised.
    due_date: date
    outstanding: Decimal
    days_overdue: int


class AgeingBucket(StatementSchema):
    """One band of an ageing report."""

    from_days: int
    #: None on the last band, which is open-ended -- a debt older than the
    #: final boundary still has to appear somewhere.
    to_days: int | None
    amount: Decimal


class CustomerAgeing(StatementSchema):
    """What one customer still owes, split by how long they have owed it."""

    customer_id: UUID
    customer_code: str
    customer_name: str
    as_of: date
    #: What the unpaid **bills** add up to. The buckets split exactly this.
    total_outstanding: Decimal
    #: What the customer's account actually stands at. It is not the same
    #: number: a credit note or a sales return reduces the account and sits on
    #: no invoice, and tax collected at source raises it without being billed
    #: at all. Two reports about one customer that disagree with nothing to
    #: explain the gap is a bug report waiting to be filed.
    account_balance: Decimal
    #: Credits the customer holds that no bill has been set against -- the
    #: part of the gap that is in their favour.
    unapplied_credits: Decimal
    #: Charges on the account that no bill carries, chiefly TCS -- the part of
    #: the gap that is against them. Exactly one of these two is ever
    #: non-zero, and
    #: ``total_outstanding - unapplied_credits + charges_not_billed`` is the
    #: account balance.
    charges_not_billed: Decimal
    buckets: list[AgeingBucket]
    invoices: list[OverdueInvoice]
