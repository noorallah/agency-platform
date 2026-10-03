"""Cash discount for early payment, and interest on late (SEL-14, A91).

Two halves of one arrangement on a customer's payment terms, the way Tally
and Zoho keep them:

* **Cash discount** -- "2% off if paid within 10 days". A bill still inside
  its window offers the percentage off what it still owes; Record Receipt
  takes it as the *discount allowed* deduction receipts already carry, so the
  books post Dr Discount Allowed and nothing about the bill's tax changes. The
  customer's own terms win; blank days take the firm's (on
  ``credit_control_settings``), zero days refuse a discount.
* **Interest on overdue bills** -- at the firm's yearly rate, on what a bill
  still owes, for each day past its due date once the grace days have run.
  Shown on the customer statement as it accrues; charged only when somebody
  raises it, as a customer debit note against the bill (interest for delayed
  payment is part of the value of the supply, CGST s.15(2)(d), so the note is
  taxed at the bill's own rates).

Both are worked out from what the receipt service says is still owed on each
bill, so a receipt, a credit note or a return moves them at once.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.money import ZERO, quantize_ledger
from app.core.utils.pricing import apportion
from app.customers.models import Customer
from app.customers.services.credit_control import CreditControlService
from app.settlements.schemas import OutstandingInvoiceRecord

if TYPE_CHECKING:
    from app.customer_debit_note.models import CustomerDebitNote

#: Days in the year interest is counted on.
YEAR_DAYS = Decimal("365")


@dataclass(frozen=True, slots=True)
class CashDiscountOffer:
    """What one bill offers off if paid on the day asked about."""

    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    outstanding: Decimal
    percent: Decimal
    #: The last day the discount stands.
    discount_until: date
    amount: Decimal


@dataclass(frozen=True, slots=True)
class OverdueInterest:
    """The interest one overdue bill has run up by a day."""

    invoice_id: UUID
    invoice_number: str
    due_date: date
    outstanding: Decimal
    days: int
    rate: Decimal
    interest: Decimal


class PaymentTermsService:
    """Work out cash discounts and overdue interest for a customer."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def discount_terms(self, customer: Customer) -> tuple[int, Decimal] | None:
        """Return the (days, percent) the customer is offered, or None."""
        days = customer.cash_discount_days
        percent = customer.cash_discount_percent
        if days is None:
            firm = CreditControlService(self._session).settings_response(
                customer.firm_id
            )
            days, percent = firm.cash_discount_days, firm.cash_discount_percent
        if not days or percent is None or Decimal(str(percent)) <= ZERO:
            return None
        return int(days), Decimal(str(percent))

    def cash_discounts(
        self, customer_id: UUID, *, firm_id: UUID, on: date
    ) -> list[CashDiscountOffer]:
        """Return the bills a payment made on ``on`` may take a discount on."""
        customer = self._customer(customer_id, firm_id=firm_id)
        terms = self.discount_terms(customer)
        if terms is None:
            return []
        days, percent = terms
        offers: list[CashDiscountOffer] = []
        for bill in self._outstanding(customer_id, firm_id=firm_id):
            until = bill.invoice_date + timedelta(days=days)
            if on < bill.invoice_date or on > until:
                continue
            owed = Decimal(str(bill.outstanding_amount))
            offers.append(
                CashDiscountOffer(
                    invoice_id=bill.invoice_id,
                    invoice_number=bill.invoice_number,
                    invoice_date=bill.invoice_date,
                    outstanding=owed,
                    percent=percent,
                    discount_until=until,
                    amount=quantize_ledger(owed * percent / Decimal("100")),
                )
            )
        return offers

    def overdue_interest(
        self, customer_id: UUID, *, firm_id: UUID, as_of: date
    ) -> list[OverdueInterest]:
        """Return the interest each overdue bill has run up by ``as_of``."""
        self._customer(customer_id, firm_id=firm_id)
        settings = CreditControlService(self._session).settings_response(firm_id)
        rate = Decimal(str(settings.overdue_interest_rate))
        if rate <= ZERO:
            return []
        grace = settings.interest_grace_days
        rows: list[OverdueInterest] = []
        for bill in self._outstanding(customer_id, firm_id=firm_id):
            due = bill.due_date or bill.invoice_date
            if as_of <= due + timedelta(days=grace):
                continue
            days = (as_of - due).days
            owed = Decimal(str(bill.outstanding_amount))
            interest = (owed * rate / Decimal("100") * days / YEAR_DAYS).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if interest <= ZERO:
                continue
            rows.append(
                OverdueInterest(
                    invoice_id=bill.invoice_id,
                    invoice_number=bill.invoice_number,
                    due_date=due,
                    outstanding=owed,
                    days=days,
                    rate=rate,
                    interest=interest,
                )
            )
        return rows

    def raise_interest_note(
        self,
        customer_id: UUID,
        invoice_id: UUID,
        *,
        firm_id: UUID,
        as_of: date,
        actor_id: UUID,
    ) -> "CustomerDebitNote":
        """Raise a draft customer debit note for one bill's interest.

        The interest is spread over the bill's lines by their taxable value,
        so each part is taxed at its own line's rate, and the note is left a
        draft for the usual approval.

        Raises:
            ValidationError: If the bill has run up no interest by ``as_of``.

        """
        from app.customer_debit_note.schemas import (
            CustomerDebitNoteCreate,
            CustomerDebitNoteLineWrite,
            CustomerDebitNoteReasonEnum,
        )
        from app.customer_debit_note.services import CustomerDebitNoteService
        from app.sales_invoice.models import SalesInvoiceLine

        found = next(
            (
                row
                for row in self.overdue_interest(
                    customer_id, firm_id=firm_id, as_of=as_of
                )
                if row.invoice_id == invoice_id
            ),
            None,
        )
        if found is None:
            raise ValidationError(
                "That bill has run up no interest by "
                f"{as_of.isoformat()}: it is not overdue, or interest is off."
            )
        lines = list(
            self._session.scalars(
                select(SalesInvoiceLine)
                .where(
                    SalesInvoiceLine.sales_invoice_id == invoice_id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceLine.line_number.asc())
            ).all()
        )
        weights = [
            max(
                Decimal(str(line.gross_amount))
                - Decimal(str(line.discount_amount))
                - Decimal(str(line.bill_discount_amount))
                + Decimal(str(line.freight_amount)),
                ZERO,
            )
            for line in lines
        ]
        if not lines or sum(weights, ZERO) <= ZERO:
            raise ValidationError("That bill has no taxed lines to charge against.")
        shares = apportion(found.interest, weights)
        writes = [
            CustomerDebitNoteLineWrite(
                sales_invoice_line_id=line.id,
                line_number=index,
                taxable_amount=share,
                description=(
                    f"Interest at {found.rate}% a year for {found.days} days, "
                    f"{found.invoice_number}"
                ),
            )
            for index, (line, share) in enumerate(zip(lines, shares, strict=True), 1)
            if share > ZERO
        ]
        return CustomerDebitNoteService(self._session).create_note(
            CustomerDebitNoteCreate(
                sales_invoice_id=invoice_id,
                debit_note_date=as_of,
                reason=CustomerDebitNoteReasonEnum.LATE_PAYMENT_INTEREST,
                remarks=(
                    f"Interest on {found.invoice_number}, overdue since "
                    f"{found.due_date.isoformat()}"
                ),
                lines=writes,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )

    # ---- helpers -----------------------------------------------------------

    def _customer(self, customer_id: UUID, *, firm_id: UUID) -> Customer:
        """Return the firm's customer or refuse it as not found."""
        customer = self._session.get(Customer, customer_id)
        if customer is None or customer.firm_id != firm_id or customer.is_deleted:
            raise ResourceNotFoundError("Customer not found.")
        return customer

    def _outstanding(
        self, customer_id: UUID, *, firm_id: UUID
    ) -> list[OutstandingInvoiceRecord]:
        """Return the customer's bills that still owe something."""
        from app.settlements.services import ReceiptService

        return [
            bill
            for bill in ReceiptService(self._session).outstanding_invoices(
                firm_id=firm_id, party_id=customer_id
            )
            if Decimal(str(bill.outstanding_amount)) > ZERO and not bill.is_opening_bill
        ]


__all__ = [
    "CashDiscountOffer",
    "OverdueInterest",
    "PaymentTermsService",
]
