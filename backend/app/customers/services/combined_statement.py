"""One statement for a business that is both customer and supplier (ACC-11).

A shop that buys from the firm and sells to it has two accounts: what it owes
the firm (receivable) and what the firm owes it (payable). Tally and Zoho show
the two side by side and net them, because the conversation with the shop is
about the net: "we owe you 40,000, you owe us 65,000, send 25,000".

The two halves come from the two statement services unchanged -- the customer
statement off the receivable ledger, the supplier statement off the payables
ledger -- and are interleaved in date order, so each line still reads as its
own account recorded it. The **net** is receivable less payable: positive, the
business owes the firm; negative, the firm owes it. Nothing is stored and
nothing is set off; a set-off is a party adjustment, preselected from the link.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.money import quantize_ledger
from app.customers.models import Customer
from app.customers.services.statement_service import CustomerStatementService
from app.vendors.services.statement_service import SupplierStatementService

RECEIVABLE = "RECEIVABLE"
PAYABLE = "PAYABLE"


@dataclass(frozen=True, slots=True)
class CombinedLine:
    """One movement on either account, signed as the net reads it."""

    transaction_date: date
    #: RECEIVABLE (the customer account) or PAYABLE (the supplier account).
    account: str
    transaction_type: str
    reference_number: str | None
    remarks: str | None
    #: What the business owes the firm more of: a sale, or the firm paying
    #: off what it owed.
    debit: Decimal
    #: What it owes the firm less of: its payment, or a bill it sent.
    credit: Decimal
    #: Receivable less payable after this line.
    net_balance: Decimal


@dataclass(frozen=True, slots=True)
class CombinedStatement:
    """Both accounts of one business over a period, and the net."""

    customer_id: UUID
    customer_name: str
    vendor_id: UUID
    vendor_name: str
    from_date: date
    to_date: date
    receivable_opening: Decimal
    payable_opening: Decimal
    receivable_closing: Decimal
    payable_closing: Decimal
    lines: list[CombinedLine]

    @property
    def net_opening(self) -> Decimal:
        """Return receivable less payable at the start."""
        return self.receivable_opening - self.payable_opening

    @property
    def net_closing(self) -> Decimal:
        """Return receivable less payable at the end."""
        return self.receivable_closing - self.payable_closing


class CombinedStatementService:
    """Build the combined statement of a customer and its linked supplier."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def for_customer(
        self, customer_id: UUID, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> CombinedStatement:
        """Return the customer's statement merged with its linked supplier's.

        Raises:
            ResourceNotFoundError: If the customer is not the firm's.
            ValidationError: If it is linked to no supplier.

        """
        customer = self._session.get(Customer, customer_id)
        if customer is None or customer.firm_id != firm_scope or customer.is_deleted:
            raise ResourceNotFoundError("Customer not found.")
        if customer.linked_vendor_id is None:
            raise ValidationError(
                f"{customer.name} is not linked to a supplier. Link one on the "
                "customer to see both accounts together."
            )
        receivable = CustomerStatementService(self._session).statement(
            customer_id, firm_scope=firm_scope, from_date=from_date, to_date=to_date
        )
        payable = SupplierStatementService(self._session).statement(
            customer.linked_vendor_id,
            firm_scope=firm_scope,
            from_date=from_date,
            to_date=to_date,
        )
        # (date, account order, position) keeps each account's own order
        # within a day, receivable first.
        movements: list[tuple[date, int, int, CombinedLine]] = []
        for index, line in enumerate(receivable.lines):
            movements.append(
                (
                    line.transaction_date,
                    0,
                    index,
                    CombinedLine(
                        transaction_date=line.transaction_date,
                        account=RECEIVABLE,
                        transaction_type=line.transaction_type,
                        reference_number=line.reference_number,
                        remarks=line.remarks,
                        debit=line.debit,
                        credit=line.credit,
                        net_balance=Decimal("0"),
                    ),
                )
            )
        for index, item in enumerate(payable.lines):
            # On the payable side a credit is the firm owing more, which the
            # net reads as the business owing the firm less -- and a debit
            # (the firm paying) as it owing more.
            movements.append(
                (
                    item.transaction_date,
                    1,
                    index,
                    CombinedLine(
                        transaction_date=item.transaction_date,
                        account=PAYABLE,
                        transaction_type=item.transaction_type,
                        reference_number=item.reference_number,
                        remarks=item.remarks,
                        debit=item.debit,
                        credit=item.credit,
                        net_balance=Decimal("0"),
                    ),
                )
            )
        movements.sort(key=lambda entry: entry[:3])
        running = receivable.opening_balance - payable.opening_balance
        lines: list[CombinedLine] = []
        for _, _, _, moved in movements:
            running += moved.debit - moved.credit
            lines.append(
                CombinedLine(
                    transaction_date=moved.transaction_date,
                    account=moved.account,
                    transaction_type=moved.transaction_type,
                    reference_number=moved.reference_number,
                    remarks=moved.remarks,
                    debit=moved.debit,
                    credit=moved.credit,
                    net_balance=quantize_ledger(running),
                )
            )
        return CombinedStatement(
            customer_id=customer.id,
            customer_name=customer.name,
            vendor_id=payable.vendor_id,
            vendor_name=payable.vendor_name,
            from_date=from_date,
            to_date=to_date,
            receivable_opening=receivable.opening_balance,
            payable_opening=payable.opening_balance,
            receivable_closing=receivable.closing_balance,
            payable_closing=payable.closing_balance,
            lines=lines,
        )


__all__ = ["CombinedLine", "CombinedStatement", "CombinedStatementService"]
