"""A customer's statement of account as a letter, for a payment reminder (MSG-3).

The reminder Tally prints and Zoho mails: the account's movement over the
period, the balance it closes at, and the bills still unpaid with how long each
has been owed. The figures are the screen's own -- the statement from
``CustomerStatementService.statement`` and the open bills from its ``ageing``
-- so the paper and the Statement screen cannot disagree.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.customers.schemas import CustomerAgeing
from app.customers.services.statement_service import CustomerStatementService
from app.document_framework.services.letter_pdf import (
    LetterPage,
    LetterPdfRenderer,
    LetterTable,
)
from app.document_framework.services.print_support import (
    customer_party,
    firm_party,
    load_template,
)
from app.sales_invoice.services.invoice_pdf import PartyBlock

#: How far back a statement reaches when nothing is unpaid to start it from.
_DEFAULT_DAYS = 30


def _rupees(value: Decimal) -> str:
    """Render an amount as a statement prints it."""
    return f"{value:,.2f}"


def _day(value: date) -> str:
    """Render a date as a statement prints it."""
    return value.strftime("%d-%m-%Y")


def statement_period(open_bills: CustomerAgeing | None, today: date) -> date:
    """Return the first day a reminder's statement covers.

    From the oldest bill still unpaid, so every bill the reminder is about is
    on it with what came off it since; thirty days where nothing is unpaid.
    """
    oldest = min(
        (bill.invoice_date for bill in (open_bills.invoices if open_bills else [])),
        default=None,
    )
    return oldest if oldest is not None else today - timedelta(days=_DEFAULT_DAYS)


class CustomerStatementPdfService:
    """Draw one customer's statement of account with their unpaid bills."""

    def __init__(self, session: Session) -> None:
        """Keep the firm's session."""
        self._session = session

    def render(
        self,
        customer_id: UUID,
        *,
        firm_id: UUID,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[bytes, str]:
        """Return the PDF and its file name.

        Args:
            customer_id: The account.
            firm_id: The owning firm.
            from_date: First day; the oldest unpaid bill's date when None.
            to_date: Last day; today (UTC) when None.

        Raises:
            ResourceNotFoundError: If the customer is not this firm's.
            ValidationError: If the period runs backwards.

        """
        today = to_date or utc_now().date()
        statements = CustomerStatementService(self._session)
        open_bills = next(
            iter(statements.ageing(firm_scope=firm_id, customer_id=customer_id)),
            None,
        )
        start = from_date or statement_period(open_bills, today)
        statement = statements.statement(
            customer_id, firm_scope=firm_id, from_date=start, to_date=today
        )
        addressee = customer_party(self._session, customer_id, "BILLING") or PartyBlock(
            name=statement.customer_name, address_lines=[]
        )
        overdue = [
            bill
            for bill in (open_bills.invoices if open_bills else [])
            if bill.days_overdue > 0
        ]
        overdue_total = sum((bill.outstanding for bill in overdue), ZERO)

        paragraphs = [
            f"Dear {statement.customer_name},",
            f"Please find below your statement of account from {_day(start)} to "
            f"{_day(today)}. The balance due to us is Rs. "
            f"{_rupees(statement.closing_balance)}.",
        ]
        if overdue:
            paragraphs.append(
                f"{len(overdue)} bill{'s are' if len(overdue) > 1 else ' is'} "
                f"past due, Rs. {_rupees(overdue_total)} in all. Please arrange "
                "payment at the earliest."
            )
        template = load_template(
            self._session, firm_scope=firm_id, document_type="SALES_INVOICE"
        )
        upi_id = template.upi_id
        if upi_id and statement.closing_balance > 0:
            paragraphs.append(f"You may pay by UPI to {upi_id}.")
        paragraphs.append(
            "If you have already paid, please ignore this reminder and send us "
            "the payment details so that we can match it."
        )

        tables = [
            LetterTable(
                heading="ACCOUNT",
                columns=("Date", "Type", "Reference", "Debit", "Credit", "Balance"),
                rows=[
                    (
                        _day(start),
                        "Opening balance",
                        "",
                        "",
                        "",
                        _rupees(statement.opening_balance),
                    ),
                    *(
                        (
                            _day(line.transaction_date),
                            line.transaction_type.replace("_", " ").title(),
                            line.reference_number or "",
                            _rupees(line.debit) if line.debit else "",
                            _rupees(line.credit) if line.credit else "",
                            _rupees(line.balance),
                        )
                        for line in statement.lines
                    ),
                    (
                        _day(today),
                        "Closing balance",
                        "",
                        "",
                        "",
                        _rupees(statement.closing_balance),
                    ),
                ],
                numeric=frozenset({"Debit", "Credit", "Balance"}),
            )
        ]
        if open_bills is not None and open_bills.invoices:
            tables.append(
                LetterTable(
                    heading="BILLS UNPAID",
                    columns=("Bill", "Date", "Due", "Days overdue", "Unpaid"),
                    rows=[
                        (
                            bill.invoice_number,
                            _day(bill.invoice_date),
                            _day(bill.due_date),
                            str(bill.days_overdue) if bill.days_overdue > 0 else "-",
                            _rupees(bill.outstanding),
                        )
                        for bill in open_bills.invoices
                    ],
                    numeric=frozenset({"Days overdue", "Unpaid"}),
                )
            )

        page = LetterPage(
            firm=firm_party(firm_id),
            title="STATEMENT OF ACCOUNT",
            facts=[
                ("Date", _day(today)),
                (
                    "Your account",
                    f"{statement.customer_code} {statement.customer_name}",
                ),
                ("Balance due", f"Rs. {_rupees(statement.closing_balance)}"),
            ],
            addressee=addressee,
            paragraphs=paragraphs,
            tables=tables,
        )
        pdf = LetterPdfRenderer(template.accent_color).render([page])
        safe = "".join(
            ch if ch.isalnum() or ch in "-_" else "-" for ch in statement.customer_code
        )
        return pdf, f"statement-{safe}-{today.isoformat()}.pdf"
