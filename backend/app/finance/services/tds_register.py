"""The TDS registers: what the firm deducted, and what was deducted from it.

Backlog 53.1 item 4. The firm's accountant files the quarterly TDS return
(26Q) from the first and ticks the second against Form 26AS. Both are read
straight from the documents that carried a deduction -- payments and
expenses for the first, receipts for the second -- and store nothing.

The quarter is the return's, April to June first, whatever the firm's own
financial year: the return is filed on the government's calendar.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination.reports import ReportWindow
from app.customers.models import Customer
from app.expenses.models import Expense
from app.finance.tds import TDS_SECTIONS
from app.settlements.models import Settlement
from app.vendors.models import Vendor

ZERO = Decimal("0")
#: What a row says in place of a PAN the firm never recorded: a deductee with
#: no PAN is deducted at the higher rate (section 206AA), so it must show.
NO_PAN = "PAN not given"


def tds_quarter(on: date) -> str:
    """Name the return quarter ``on`` falls in, e.g. ``Q1 2026-27``."""
    start = on.year if on.month >= 4 else on.year - 1
    quarter = ((on.month - 4) % 12) // 3 + 1
    return f"Q{quarter} {start}-{(start + 1) % 100:02d}"


@dataclass(frozen=True)
class TdsRow:
    """One deduction, as the return and the 26AS match need it."""

    date: date
    quarter: str
    document_type: str
    document_number: str
    party_code: str | None
    party_name: str
    pan: str
    tan: str | None
    section: str
    section_name: str
    gross_amount: Decimal
    tds_amount: Decimal
    net_amount: Decimal
    status: str
    #: The payment, expense or receipt the deduction was made on (ACC-7:
    #: the return looks up the challan that paid it by this).
    document_id: UUID | None = None


class TdsRegisterService:
    """Read the two registers for a firm and a window."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def deducted_by_firm(self, firm_id: UUID, window: ReportWindow) -> list[TdsRow]:
        """Every deduction the firm made: payments to suppliers and expenses.

        Reversed payments and cancelled expenses are listed with their status,
        because a deduction already paid to the government by challan does not
        vanish when the document is reversed -- the accountant has to see both.
        """
        rows: list[TdsRow] = []
        payments = self._session.execute(
            select(Settlement, Vendor)
            .join(Vendor, Vendor.id == Settlement.vendor_id)
            .where(
                Settlement.firm_id == firm_id,
                Settlement.is_deleted.is_(False),
                Settlement.direction == "PAYMENT",
                Settlement.tds_amount > 0,
                *window.dated(Settlement.settlement_date),
            )
        ).all()
        for payment, vendor in payments:
            rows.append(
                self._row(
                    on=payment.settlement_date,
                    kind="Payment",
                    number=payment.settlement_number,
                    party_code=vendor.code,
                    party_name=vendor.name,
                    pan=vendor.pan,
                    tan=None,
                    section=payment.tds_section,
                    gross=payment.amount,
                    tds=payment.tds_amount,
                    status=payment.status,
                    document_id=payment.id,
                )
            )
        expenses = self._session.scalars(
            select(Expense).where(
                Expense.firm_id == firm_id,
                Expense.is_deleted.is_(False),
                Expense.tds_amount > 0,
                *window.dated(Expense.expense_date),
            )
        ).all()
        for expense in expenses:
            rows.append(
                self._row(
                    on=expense.expense_date,
                    kind="Expense",
                    number=expense.expense_number,
                    party_code=None,
                    party_name=expense.payee or "",
                    pan=expense.payee_pan,
                    tan=None,
                    section=expense.tds_section,
                    gross=expense.amount,
                    tds=expense.tds_amount,
                    status=expense.status,
                    document_id=expense.id,
                )
            )
        return _ordered(rows)

    def deducted_by_customers(
        self, firm_id: UUID, window: ReportWindow
    ) -> list[TdsRow]:
        """Every deduction a customer made from what it paid the firm.

        Each carries the customer's TAN, which is what Form 26AS names the
        deductor by, so the firm can tick its claim against the government's
        record.
        """
        receipts = self._session.execute(
            select(Settlement, Customer)
            .join(Customer, Customer.id == Settlement.customer_id)
            .where(
                Settlement.firm_id == firm_id,
                Settlement.is_deleted.is_(False),
                Settlement.direction == "RECEIPT",
                Settlement.tds_amount > 0,
                *window.dated(Settlement.settlement_date),
            )
        ).all()
        return _ordered(
            [
                self._row(
                    on=receipt.settlement_date,
                    kind="Receipt",
                    number=receipt.settlement_number,
                    party_code=customer.code,
                    party_name=customer.display_name or customer.name,
                    pan=customer.pan_number,
                    tan=customer.tan_number,
                    section=receipt.tds_section,
                    gross=receipt.amount,
                    tds=receipt.tds_amount,
                    status=receipt.status,
                    document_id=receipt.id,
                )
                for receipt, customer in receipts
            ]
        )

    @staticmethod
    def _row(
        *,
        on: date,
        kind: str,
        number: str,
        party_code: str | None,
        party_name: str,
        pan: str | None,
        tan: str | None,
        section: str | None,
        gross: Decimal,
        tds: Decimal,
        status: str,
        document_id: UUID | None = None,
    ) -> TdsRow:
        code = section or ""
        return TdsRow(
            date=on,
            quarter=tds_quarter(on),
            document_type=kind,
            document_number=number,
            party_code=party_code,
            party_name=party_name,
            pan=(pan or "").strip().upper() or NO_PAN,
            tan=tan,
            section=code,
            section_name=TDS_SECTIONS.get(code, ""),
            gross_amount=gross,
            tds_amount=tds,
            net_amount=gross - tds,
            status=status,
            document_id=document_id,
        )


def _ordered(rows: list[TdsRow]) -> list[TdsRow]:
    """Sort by date, then document, so pages are stable."""
    return sorted(rows, key=lambda row: (row.date, row.document_number))
