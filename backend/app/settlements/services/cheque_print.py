"""Print a supplier payment onto the bank's cheque leaf (ACC-12, decision A66).

Indian cheques follow CTS-2010: a leaf 203.2 x 93.2 mm with the date boxes at
the top right, the payee and the amount in words across the middle, and the
amount box on the right. The positions below are that standard's, measured
from the leaf's top-left corner; a firm moves them all by the offsets kept on
the bank account it pays from (:class:`ChequeLayout`) after one test print.

What goes on the cheque is what left the bank: the payment less the TDS and
the rounding and discount it settled without moving money. The payee is the
supplier's legal name, which is what their bank account is held in, and can be
overridden for a cheque made out to someone else. A reversed payment, a cash
payment and one recorded as UPI or a transfer have no cheque to print.

**A cheque is printed from a record, never from a form** (row F13, COL-11).
Besides a supplier's payment that is a refund to a customer, an expense paid
from a bank account, and any cheque in the register of cheques the firm has
written -- which carries its own date, so one dated ahead prints with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.expenses.models import Expense, ExpenseStatus
from app.finance.models.finance import LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.money_accounts import KIND_BANK, money_accounts
from app.sales_invoice.services.invoice_pdf import amount_in_words
from app.settlements.models.cheque_layout import ChequeLayout
from app.settlements.models.post_dated_cheque import (
    PostDatedCheque,
    PostDatedChequeStatus,
)
from app.settlements.models.settlement import (
    Settlement,
    SettlementDirection,
    SettlementMethod,
    SettlementStatus,
)
from app.vendors.models.vendor import Vendor

#: CTS-2010 leaf size.
LEAF_WIDTH = 203.2 * mm
LEAF_HEIGHT = 93.2 * mm

#: How far a firm may move the print, in millimetres, either way.
MAX_OFFSET_MM = Decimal("30")

# Positions on the leaf, millimetres from its top-left corner to the text's
# baseline. The date is eight boxes of 1/5 inch, DDMMYYYY.
_DATE_X, _DATE_Y, _DATE_PITCH = 158.6, 12.0, 5.08
_PAYEE_X, _PAYEE_Y = 22.0, 24.5
_WORDS_1_X, _WORDS_1_Y = 34.0, 32.5
_WORDS_2_X, _WORDS_2_Y = 12.0, 40.5
_FIGURE_X, _FIGURE_Y = 160.0, 41.0
_PAYEE_END = 182.0
_WORDS_END = 150.0

_FONT = "Helvetica-Bold"
_SIZE = 10.0


@dataclass(frozen=True)
class ChequeContent:
    """What one cheque says."""

    payee: str
    amount: Decimal
    cheque_date: date


def indian_grouping(amount: Decimal) -> str:
    """Return ``amount`` grouped the Indian way: 12,34,567.00."""
    whole, _, paise = f"{amount.quantize(Decimal('0.01'))}".partition(".")
    sign = "-" if whole.startswith("-") else ""
    whole = whole.lstrip("-")
    head, tail = whole[:-3], whole[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return sign + ",".join([*groups, tail]) + "." + paise


def _split_words(words: str, first: float, second: float) -> tuple[str, str]:
    """Split the amount in words over the cheque's two lines, by whole words.

    Raises:
        ValidationError: If even two lines cannot hold it.

    """
    line_1: list[str] = []
    remaining = words.split()
    while remaining:
        candidate = " ".join([*line_1, remaining[0]])
        if stringWidth(candidate, _FONT, _SIZE) > first:
            break
        line_1.append(remaining.pop(0))
    line_2 = " ".join(remaining)
    if stringWidth(line_2, _FONT, _SIZE) > second:
        raise ValidationError(
            "The amount in words does not fit on the cheque's two lines."
        )
    return " ".join(line_1), line_2


class ChequeRenderer:
    """Draw a cheque's text where a CTS-2010 leaf expects it."""

    def __init__(
        self,
        *,
        offset_x_mm: Decimal = Decimal("0"),
        offset_y_mm: Decimal = Decimal("0"),
        ac_payee: bool = True,
    ) -> None:
        """Remember the firm's offsets and whether to cross the cheque."""
        self._dx = float(offset_x_mm) * mm
        self._dy = float(offset_y_mm) * mm
        self._ac_payee = ac_payee

    def _at(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        """Return the PDF point for a position on the leaf, offsets applied."""
        return x_mm * mm + self._dx, LEAF_HEIGHT - y_mm * mm - self._dy

    def render(self, cheque: ChequeContent) -> bytes:
        """Return a one-page PDF the size of the leaf."""
        if cheque.amount <= 0:
            raise ValidationError("A cheque must be for more than nothing.")
        payee = cheque.payee.strip()
        if not payee:
            raise ValidationError("Name who the cheque is payable to.")
        if stringWidth(payee, _FONT, _SIZE) > (_PAYEE_END - _PAYEE_X) * mm:
            raise ValidationError(
                "The payee's name is too long for the cheque's line; shorten it."
            )
        words = amount_in_words(cheque.amount, currency="Rupees")
        line_1, line_2 = _split_words(
            words,
            (_WORDS_END - _WORDS_1_X) * mm,
            (_WORDS_END - _WORDS_2_X) * mm,
        )

        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=(LEAF_WIDTH, LEAF_HEIGHT))
        canvas.setTitle("Cheque")
        canvas.setFont(_FONT, _SIZE)

        for index, digit in enumerate(f"{cheque.cheque_date:%d%m%Y}"):
            x, y = self._at(_DATE_X + index * _DATE_PITCH, _DATE_Y)
            canvas.drawCentredString(x + _DATE_PITCH * mm / 2, y, digit)

        canvas.drawString(*self._at(_PAYEE_X, _PAYEE_Y), payee)
        canvas.drawString(*self._at(_WORDS_1_X, _WORDS_1_Y), line_1)
        if line_2:
            canvas.drawString(*self._at(_WORDS_2_X, _WORDS_2_Y), line_2)
        canvas.drawString(
            *self._at(_FIGURE_X, _FIGURE_Y),
            f"**{indian_grouping(cheque.amount)}/-",
        )

        if self._ac_payee:
            # Two parallel lines across the top-left corner, the words between.
            canvas.setLineWidth(0.8)
            for gap in (0.0, 6.0):
                canvas.line(*self._at(8.0 + gap, 20.0), *self._at(24.0 + gap, 4.0))
            canvas.saveState()
            x, y = self._at(14.5, 15.5)
            canvas.translate(x, y)
            canvas.rotate(45)
            canvas.setFont("Helvetica-Bold", 7)
            canvas.drawString(0, 0, "A/c Payee")
            canvas.restoreState()

        canvas.showPage()
        canvas.save()
        return buffer.getvalue()


class ChequeService:
    """Keep each bank account's layout and print payments onto cheques."""

    def __init__(self, session: Session) -> None:
        """Keep the firm store's session."""
        self._session = session

    def layouts(self, *, firm_id: UUID) -> list[ChequeLayout]:
        """Return every bank account's layout the firm has saved."""
        return list(
            self._session.scalars(
                select(ChequeLayout).where(
                    ChequeLayout.firm_id == firm_id,
                    ChequeLayout.is_deleted.is_(False),
                )
            )
        )

    def layout_for(self, ledger_account_id: UUID, *, firm_id: UUID) -> ChequeLayout:
        """Return the account's layout, unsaved and at zero where none is kept."""
        row = self._session.scalar(
            select(ChequeLayout).where(
                ChequeLayout.firm_id == firm_id,
                ChequeLayout.ledger_account_id == ledger_account_id,
                ChequeLayout.is_deleted.is_(False),
            )
        )
        if row is not None:
            return row
        return ChequeLayout(
            firm_id=firm_id,
            ledger_account_id=ledger_account_id,
            offset_x_mm=Decimal("0"),
            offset_y_mm=Decimal("0"),
            print_ac_payee=True,
        )

    def save_layout(
        self,
        ledger_account_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        offset_x_mm: Decimal,
        offset_y_mm: Decimal,
        print_ac_payee: bool,
    ) -> ChequeLayout:
        """Store how far this account's cheques are off, and audit it."""
        self._account(ledger_account_id, firm_id=firm_id)
        for value in (offset_x_mm, offset_y_mm):
            if abs(value) > MAX_OFFSET_MM:
                raise ValidationError(
                    f"Move the print by at most {MAX_OFFSET_MM} mm either way."
                )
        row = self.layout_for(ledger_account_id, firm_id=firm_id)
        is_new = sa_inspect(row).transient
        before = (
            None
            if is_new
            else {
                "offset_x_mm": str(row.offset_x_mm),
                "offset_y_mm": str(row.offset_y_mm),
                "print_ac_payee": row.print_ac_payee,
            }
        )
        if is_new:
            row.created_by = actor_id
            self._session.add(row)
        row.offset_x_mm = offset_x_mm
        row.offset_y_mm = offset_y_mm
        row.print_ac_payee = print_ac_payee
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="cheque_layout.saved",
            entity_type="cheque_layout",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={
                "ledger_account_id": str(ledger_account_id),
                "offset_x_mm": str(offset_x_mm),
                "offset_y_mm": str(offset_y_mm),
                "print_ac_payee": print_ac_payee,
            },
        )
        self._session.commit()
        return row

    def test_print(self, ledger_account_id: UUID, *, firm_id: UUID) -> bytes:
        """Return a sample cheque for lining the account's leaf up."""
        self._account(ledger_account_id, firm_id=firm_id)
        layout = self.layout_for(ledger_account_id, firm_id=firm_id)
        return self._renderer(layout).render(
            ChequeContent(
                payee="Sample Supplier Private Limited",
                amount=Decimal("1234567.89"),
                cheque_date=date(2026, 12, 31),
            )
        )

    def payment_cheque(
        self,
        payment_id: UUID,
        *,
        firm_id: UUID,
        payee: str | None = None,
        direction: SettlementDirection = SettlementDirection.PAYMENT,
    ) -> tuple[bytes, str]:
        """Return the cheque PDF for a bank payment, and its file name.

        ``direction`` is ``REFUND`` for money handed back to a customer,
        which is a cheque like any other; a receipt has none to print.
        """
        is_refund = direction == SettlementDirection.REFUND
        if direction == SettlementDirection.RECEIPT:
            raise ValueError("A receipt is not paid by the firm's cheque.")
        row = self._session.scalar(
            select(Settlement).where(
                Settlement.id == payment_id,
                Settlement.firm_id == firm_id,
                Settlement.direction == direction.value,
                Settlement.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError(
                "Refund not found." if is_refund else "Payment not found."
            )
        content = self.cheque_content(row, payee=payee)
        layout = self.layout_for(row.ledger_account_id, firm_id=firm_id)
        pdf = self._renderer(layout).render(content)
        return pdf, f"cheque-{row.settlement_number}.pdf"

    def cheque_content(
        self, row: Settlement, *, payee: str | None = None
    ) -> ChequeContent:
        """Return what a payment's cheque says, refusing one with no cheque."""
        what = "refund" if row.customer_id is not None else "payment"
        if row.status != SettlementStatus.POSTED.value:
            raise ValidationError(f"A reversed {what} has no cheque to print.")
        if row.method != SettlementMethod.BANK.value:
            raise ValidationError(f"A cash {what} has no cheque to print.")
        mode = row.payment_mode
        if mode is not None and mode != "CHEQUE":
            raise ValidationError(
                f"This {what} was made by {mode.replace('_', ' ')}, not by cheque."
            )
        moved = (
            row.amount
            - row.tds_amount
            - row.rounding_amount
            - row.bank_charges_amount
            - row.discount_amount
        )
        name = payee
        if not name:
            name = self._party_name(row.vendor_id, row.customer_id)
        return ChequeContent(
            payee=name,
            amount=moved,
            cheque_date=row.instrument_date or row.settlement_date,
        )

    def expense_cheque(
        self, expense_id: UUID, *, firm_id: UUID, payee: str | None = None
    ) -> tuple[bytes, str]:
        """Return the cheque PDF for an expense paid from a bank account.

        What goes on it is what left the bank: the expense less the TDS
        deducted. The payee is the one the expense names, or ``payee``.

        Raises:
            ResourceNotFoundError: If the firm has no such expense.
            ValidationError: If it is cancelled, or was paid in cash.

        """
        row = self._session.scalar(
            select(Expense).where(
                Expense.id == expense_id,
                Expense.firm_id == firm_id,
                Expense.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Expense not found.")
        if row.status != ExpenseStatus.POSTED.value:
            raise ValidationError("A cancelled expense has no cheque to print.")
        kinds = {
            account.id: kind for account, kind in money_accounts(self._session, firm_id)
        }
        if kinds.get(row.paid_from_account_id) != KIND_BANK:
            raise ValidationError(
                "This expense was not paid from a bank account, so it has no "
                "cheque to print."
            )
        layout = self.layout_for(row.paid_from_account_id, firm_id=firm_id)
        pdf = self._renderer(layout).render(
            ChequeContent(
                payee=payee or row.payee or "",
                amount=row.amount - row.tds_amount,
                cheque_date=row.expense_date,
            )
        )
        return pdf, f"cheque-{row.expense_number}.pdf"

    def written_cheque(
        self, cheque_id: UUID, *, firm_id: UUID, payee: str | None = None
    ) -> tuple[bytes, str]:
        """Return the PDF of a cheque in the register of cheques written.

        It prints with its own date, so one dated ahead is printed now and
        handed over. A cancelled or returned cheque is not printed again.

        Raises:
            ResourceNotFoundError: If the firm wrote no such cheque.
            ValidationError: If it is cancelled or was returned.

        """
        row = self._session.scalar(
            select(PostDatedCheque).where(
                PostDatedCheque.id == cheque_id,
                PostDatedCheque.firm_id == firm_id,
                PostDatedCheque.direction == SettlementDirection.PAYMENT.value,
                PostDatedCheque.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Cheque not found.")
        if row.status in (
            PostDatedChequeStatus.CANCELLED.value,
            PostDatedChequeStatus.BOUNCED.value,
        ):
            raise ValidationError(
                f"Cheque {row.cheque_number} is {row.status.lower()}, so it "
                "is not printed again."
            )
        bank_account_id = row.bank_account_id or ControlAccountService(
            self._session
        ).resolve(firm_id, ControlAccountPurpose.BANK)
        layout = self.layout_for(bank_account_id, firm_id=firm_id)
        pdf = self._renderer(layout).render(
            ChequeContent(
                payee=payee
                or row.payee_name
                or self._party_name(row.vendor_id, row.customer_id),
                amount=row.amount,
                cheque_date=row.cheque_date,
            )
        )
        number = re.sub(r"[^A-Za-z0-9-]", "", row.cheque_number) or "written"
        return pdf, f"cheque-{number}.pdf"

    def _party_name(self, vendor_id: UUID | None, customer_id: UUID | None) -> str:
        """Return the name a cheque to a supplier or a customer is made out in.

        A supplier's legal name, which is what their bank account is held
        in; a customer keeps one name.
        """
        if vendor_id is not None:
            vendor = self._session.get(Vendor, vendor_id)
            return (vendor.legal_name or vendor.name) if vendor is not None else ""
        if customer_id is not None:
            customer = self._session.get(Customer, customer_id)
            return customer.name if customer is not None else ""
        return ""

    def _account(self, ledger_account_id: UUID, *, firm_id: UUID) -> LedgerAccount:
        """Return the firm's ledger account or raise."""
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == ledger_account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ResourceNotFoundError("Bank account not found.")
        return account

    @staticmethod
    def _renderer(layout: ChequeLayout) -> ChequeRenderer:
        """Return a renderer carrying the layout's offsets."""
        return ChequeRenderer(
            offset_x_mm=layout.offset_x_mm,
            offset_y_mm=layout.offset_y_mm,
            ac_payee=layout.print_ac_payee,
        )
