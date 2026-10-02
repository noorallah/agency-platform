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
"""

from __future__ import annotations

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
from app.finance.models.finance import LedgerAccount
from app.sales_invoice.services.invoice_pdf import amount_in_words
from app.settlements.models.cheque_layout import ChequeLayout
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
        self, payment_id: UUID, *, firm_id: UUID, payee: str | None = None
    ) -> tuple[bytes, str]:
        """Return the cheque PDF for a bank payment, and its file name."""
        row = self._session.scalar(
            select(Settlement).where(
                Settlement.id == payment_id,
                Settlement.firm_id == firm_id,
                Settlement.direction == SettlementDirection.PAYMENT.value,
                Settlement.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Payment not found.")
        content = self.cheque_content(row, payee=payee)
        layout = self.layout_for(row.ledger_account_id, firm_id=firm_id)
        pdf = self._renderer(layout).render(content)
        return pdf, f"cheque-{row.settlement_number}.pdf"

    def cheque_content(
        self, row: Settlement, *, payee: str | None = None
    ) -> ChequeContent:
        """Return what a payment's cheque says, refusing one with no cheque."""
        if row.status != SettlementStatus.POSTED.value:
            raise ValidationError("A reversed payment has no cheque to print.")
        if row.method != SettlementMethod.BANK.value:
            raise ValidationError("A cash payment has no cheque to print.")
        mode = row.payment_mode
        if mode is not None and mode != "CHEQUE":
            raise ValidationError(
                f"This payment was made by {mode.replace('_', ' ')}" ", not by cheque."
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
            vendor = self._session.get(Vendor, row.vendor_id)
            name = (vendor.legal_name or vendor.name) if vendor is not None else ""
        return ChequeContent(
            payee=name,
            amount=moved,
            cheque_date=row.instrument_date or row.settlement_date,
        )

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
