"""Response models for the supplier statement of account (backlog 74 row 4)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SupplierStatementSchema(BaseModel):
    """Shared configuration for every statement payload."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SupplierStatementLine(SupplierStatementSchema):
    """One movement on a supplier's account."""

    transaction_date: date
    #: BILL, OPENING_BILL, PAYMENT, PURCHASE_RETURN, DEBIT_NOTE or ADJUSTMENT,
    #: with ``_REVERSAL`` added for the mirror that undid one.
    transaction_type: str
    reference_number: str | None = None
    remarks: str | None = None
    #: What the firm owes less of: a payment, a return, a debit note, a
    #: write-back or set-off -- the side the payable is debited on.
    debit: Decimal
    #: What the firm owes more of: a bill, an opening bill, a reversal of a
    #: payment.
    credit: Decimal
    #: What the firm owes the supplier after this line, recomputed in date
    #: order. Negative is an advance or a credit the supplier owes back.
    balance: Decimal


class SupplierStatement(SupplierStatementSchema):
    """A supplier's account over one period."""

    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    from_date: date
    to_date: date
    #: What the firm owed the supplier at the start of ``from_date``.
    opening_balance: Decimal
    closing_balance: Decimal
    total_debit: Decimal
    total_credit: Decimal
    lines: list[SupplierStatementLine]


__all__ = ["SupplierStatement", "SupplierStatementLine", "SupplierStatementSchema"]
