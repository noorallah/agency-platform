"""What a sales return credits, and what it leaves to bill (D-SELL-55).

Goods can come back against a delivery note before any bill has charged for
them -- the note was never billed, or its bill was cancelled. Nothing was
charged, so nothing is credited: such goods move stock and cost only, reverse
no output tax, and lower what the note may still be billed for. The selling
twin of ``app/goods_receipt/billing.py`` (D-BUY-26).

The split is decided when the return completes and stored on the return line
(``unbilled_quantity``): returned goods are taken first from the part of the
note line no approved bill has reached, and only the rest is a credit note.
Everything that asks "what did this return credit" -- the journal, the
customer's account, GSTR-1, the GST sales register, the sales analysis --
reads it from here, so they cannot disagree.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Row, Select, case, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.selectable import ScalarSelect

from app.core.utils.chunks import chunks
from app.credit_note.models import CreditNote, CreditNoteLine, CreditNoteStatus
from app.delivery_note.models import DeliveryNoteLine
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_return.models import SalesReturn, SalesReturnLine, SalesReturnLineTax

ZERO = Decimal("0")
_FOUR = Decimal("0.0001")

#: A return in one of these has brought its goods back and split them.
_COMPLETED = ("COMPLETED", "CLOSED")
#: A bill in one of these has charged the customer.
_CHARGED = ("APPROVED", "CLOSED")
#: A return in one of these still claims the goods it names: everything but
#: a cancelled one.
_LIVE = ("DRAFT", "APPROVED", "COMPLETED", "CLOSED")


def billed_share(line: SalesReturnLine) -> Decimal:
    """Return the part of a line that reverses a bill, as a fraction of it.

    What came back before billing (``unbilled_quantity``) was never charged,
    so it credits nothing and reverses no tax.
    """
    quantity = Decimal(str(line.current_return_quantity))
    if quantity <= ZERO:
        return Decimal("1")
    unbilled = min(Decimal(str(line.unbilled_quantity or ZERO)), quantity)
    return (quantity - unbilled) / quantity


def billed_part(
    amount: ColumnElement[Any] | InstrumentedAttribute[Any],
) -> ColumnElement[Any]:
    """Return the billed share of a return line's figure, for a query.

    The SQL form of :func:`billed_share`, for reports that group in the
    database: the figure, scaled by how much of the line reversed a bill.
    """
    quantity = SalesReturnLine.current_return_quantity
    unbilled = SalesReturnLine.unbilled_quantity
    return case(
        # Left exactly as stored where nothing came back before billing --
        # every line but the rare one -- so no division touches it.
        (unbilled <= 0, amount),
        (quantity > 0, amount * (quantity - unbilled) / quantity),
        else_=amount,
    )


def credits_a_bill() -> ColumnElement[bool]:
    """Match the returns that credited something: not wholly before billing.

    A return whose every line came back before billing is no credit note, so
    GSTR-1 and the GST sales register leave it out.
    """
    return SalesReturn.id.in_(
        select(SalesReturnLine.sales_return_id).where(
            SalesReturnLine.is_deleted.is_(False),
            SalesReturnLine.current_return_quantity > SalesReturnLine.unbilled_quantity,
        )
    )


def unbilled_taxable() -> ScalarSelect[Any]:
    """Return, per return in the outer query, the pre-tax value never billed.

    A correlated subquery over ``SalesReturn``: what its lines are worth
    before tax, for the part that came back before billing.
    """
    quantity = SalesReturnLine.current_return_quantity
    return (
        select(
            func.coalesce(
                func.sum(
                    (SalesReturnLine.net_amount - SalesReturnLine.tax_amount)
                    * SalesReturnLine.unbilled_quantity
                    / quantity
                ),
                0,
            )
        )
        .where(
            SalesReturnLine.sales_return_id == SalesReturn.id,
            SalesReturnLine.is_deleted.is_(False),
            quantity > 0,
        )
        .correlate(SalesReturn)
        .scalar_subquery()
    )


def unbilled_quantities(
    session: Session, return_ids: Iterable[UUID]
) -> dict[UUID, Decimal]:
    """Return how much of each return came back before billing, in all."""
    ids = list(set(return_ids))
    if not ids:
        return {}
    return {
        return_id: Decimal(str(quantity))
        for return_id, quantity in session.execute(
            select(
                SalesReturnLine.sales_return_id,
                func.coalesce(func.sum(SalesReturnLine.unbilled_quantity), 0),
            )
            .where(
                SalesReturnLine.sales_return_id.in_(ids),
                SalesReturnLine.is_deleted.is_(False),
            )
            .group_by(SalesReturnLine.sales_return_id)
        ).all()
    }


def return_billed_amounts(
    session: Session, rows: Sequence[SalesReturn]
) -> dict[UUID, tuple[Decimal, Decimal]]:
    """Return what each return takes off the customer's account, and its tax.

    The credit-note part only: the document total and its tax, less the value
    of what came back before any bill charged for it. A return wholly against
    unbilled goods credits nothing -- its rounding and charges included. The
    journal and the customer's account both read this, so they cannot drift.
    """
    if not rows:
        return {}
    parts: dict[UUID, list[SalesReturnLine]] = defaultdict(list)
    for line in session.scalars(
        select(SalesReturnLine).where(
            SalesReturnLine.sales_return_id.in_([row.id for row in rows]),
            SalesReturnLine.is_deleted.is_(False),
        )
    ).all():
        parts[line.sales_return_id].append(line)
    amounts: dict[UUID, tuple[Decimal, Decimal]] = {}
    for row in rows:
        total = Decimal(str(row.grand_total))
        tax_total = Decimal(str(row.tax_total))
        lines = parts.get(row.id, [])
        if lines and all(billed_share(line) == ZERO for line in lines):
            amounts[row.id] = (ZERO, ZERO)
            continue
        for line in lines:
            unbilled = Decimal("1") - billed_share(line)
            if unbilled == ZERO:
                continue
            total -= (Decimal(str(line.net_amount)) * unbilled).quantize(_FOUR)
            tax_total -= (Decimal(str(line.tax_amount)) * unbilled).quantize(_FOUR)
        amounts[row.id] = (max(total, ZERO), max(tax_total, ZERO))
    return amounts


def billed_tax_by_component(session: Session, return_id: UUID) -> dict[str, Decimal]:
    """Sum the tax a return reverses per component code, billed part only.

    Tax inside a price is left out, as the return's own tax total leaves it
    out. Empty when the lines recorded no components.
    """
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for line, component in session.execute(
        select(SalesReturnLine, SalesReturnLineTax)
        .join(
            SalesReturnLineTax,
            SalesReturnLineTax.sales_return_line_id == SalesReturnLine.id,
        )
        .where(
            SalesReturnLine.sales_return_id == return_id,
            SalesReturnLine.is_deleted.is_(False),
            SalesReturnLineTax.is_deleted.is_(False),
            SalesReturnLineTax.included_in_price.is_(False),
        )
    ).all():
        share = billed_share(line)
        if share == ZERO:
            continue
        totals[component.component_code] += Decimal(str(component.amount)) * share
    return dict(totals)


@dataclass(frozen=True, slots=True)
class NoteLineBilling:
    """Where one delivery note line stands against billing."""

    delivered: Decimal
    #: What bills that charged the customer (approved or closed) took.
    charged: Decimal
    #: What completed returns took off the line before any bill reached it.
    returned_unbilled: Decimal

    @property
    def left_to_bill(self) -> Decimal:
        """Return what a bill may still charge for on this line."""
        return max(self.delivered - self.charged - self.returned_unbilled, ZERO)


def returned_unbilled(
    session: Session,
    note_line_ids: Iterable[UUID],
    *,
    exclude_return_id: UUID | None = None,
) -> dict[UUID, Decimal]:
    """Return what came back before billing, per delivery note line.

    Only completed returns count: the split is written at completion and
    cleared when a completed return is cancelled.
    """
    ids = list(set(note_line_ids))
    if not ids:
        return {}
    statement = (
        select(
            SalesReturnLine.source_document_line_id,
            func.coalesce(func.sum(SalesReturnLine.unbilled_quantity), 0),
        )
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(
            SalesReturnLine.source_document_type == "DELIVERY_NOTE",
            SalesReturnLine.source_document_line_id.in_(ids),
            SalesReturnLine.is_deleted.is_(False),
            SalesReturn.is_deleted.is_(False),
            SalesReturn.status.in_(_COMPLETED),
        )
        .group_by(SalesReturnLine.source_document_line_id)
    )
    if exclude_return_id is not None:
        statement = statement.where(SalesReturn.id != exclude_return_id)
    return {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(statement).all()
        if Decimal(str(quantity)) > ZERO
    }


def free_returned_off_notes(
    session: Session, note_line_ids: Iterable[UUID]
) -> dict[UUID, Decimal]:
    """Return the free goods that came back, per delivery note line.

    What completed returns raised **against the note line** state as free
    (``sales_return_lines.free_quantity``), in the note line's unit. A bill
    raised afterwards states the free goods the customer still holds: the
    charged quantity is netted by ``returned_unbilled`` and the free one was
    not, so a bill printed "0 + 2 free" after one of the two had come back
    (D-PRC-61). A return raised against a bill names the bill's line, which
    had already stated those goods, and is not counted here.
    """
    ids = list(set(note_line_ids))
    if not ids:
        return {}
    return {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(
            select(
                SalesReturnLine.source_document_line_id,
                func.coalesce(func.sum(SalesReturnLine.free_quantity), 0),
            )
            .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
            .where(
                SalesReturnLine.source_document_type == "DELIVERY_NOTE",
                SalesReturnLine.source_document_line_id.in_(ids),
                SalesReturnLine.is_deleted.is_(False),
                SalesReturnLine.free_quantity > 0,
                SalesReturn.is_deleted.is_(False),
                SalesReturn.status.in_(_COMPLETED),
            )
            .group_by(SalesReturnLine.source_document_line_id)
        ).all()
        if Decimal(str(quantity)) > ZERO
    }


def note_line_billing(
    session: Session,
    note_line_ids: Iterable[UUID],
    *,
    exclude_return_id: UUID | None = None,
    exclude_invoice_id: UUID | None = None,
) -> dict[UUID, NoteLineBilling]:
    """Return where each of these delivery note lines stands against billing.

    Judged on bills that **charged** the customer. A draft bill has charged
    nothing, so goods returned while one is waiting are returned before
    billing, and the draft is then refused at approval for what came back.
    """
    ids = list(set(note_line_ids))
    if not ids:
        return {}
    delivered = {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(
            select(
                DeliveryNoteLine.id, DeliveryNoteLine.current_delivery_quantity
            ).where(DeliveryNoteLine.id.in_(ids))
        ).all()
    }
    bills = (
        select(
            SalesInvoiceLine.source_document_line_id,
            func.coalesce(func.sum(SalesInvoiceLine.current_invoice_quantity), 0),
        )
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        .where(
            SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
            SalesInvoiceLine.source_document_line_id.in_(ids),
            SalesInvoiceLine.is_deleted.is_(False),
            SalesInvoice.is_deleted.is_(False),
            SalesInvoice.status.in_(_CHARGED),
        )
        .group_by(SalesInvoiceLine.source_document_line_id)
    )
    if exclude_invoice_id is not None:
        bills = bills.where(SalesInvoice.id != exclude_invoice_id)
    charged = {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(bills).all()
    }
    back = returned_unbilled(session, ids, exclude_return_id=exclude_return_id)
    return {
        line_id: NoteLineBilling(
            delivered=quantity,
            charged=charged.get(line_id, ZERO),
            returned_unbilled=back.get(line_id, ZERO),
        )
        for line_id, quantity in delivered.items()
    }


# ---- what a bill line is still worth (D-SELL-88) ----------------------------
#
# A sales return and a credit note both credit a bill line, and neither read
# the other: a bill of 2,832.00 took a rate-difference credit note of 472.00
# and was then returned in full for 2,832.00 -- 3,304.00 credited against a
# bill of 2,832.00. Both documents now read what has already come off the line
# from here, so a customer is never credited more than they were billed.
#
# The cap runs on every return, credit note or none (D-PRC-64): a return that
# typed 1,500.00 a box against a bill at 1,200.00 credited 3,540.00 against
# 2,832.00, because the cap was only reached once a credit note existed.
#
# A delivery note line can be billed in parts, and a return raised off the
# note then brings back units of more than one bill (D-PRC-65). They are set
# against **every** bill line that charged the note line, earliest first, each
# for the units it billed that are still out, and are worth what those units
# are still worth on their own bills. Read against the earliest bill alone, a
# credit note on the second bill was never netted (472.00 over) and one on the
# first was netted twice (472.00 short).
#
# Nothing stores that split: it is worked out here, the same way every time,
# from the bills, the credit notes and the returns as they stand
# (``BillLedger``). Units a return names on a bill line itself are that
# line's; what returns off the note brought back fills the units left, oldest
# return first, earliest bill first.


#: Units below this are the rounding of a part typed in another unit, not
#: goods: three parts of two boxes typed in pieces can add up to 2.0001.
_DUST = Decimal("0.0005")


@dataclass(frozen=True, slots=True)
class BillLineCredits:
    """What has already come off one bill line, before tax."""

    #: Billed units that returns took, in the bill line's own unit.
    returned_quantity: Decimal
    #: What those returns credited, before tax.
    returned_taxable: Decimal
    #: What approved credit notes credited, before tax.
    credited_taxable: Decimal


@dataclass(slots=True)
class BillStanding:
    """One bill line, and what has come off it."""

    line_id: UUID
    invoice_id: UUID
    #: Units the line billed, in its own unit.
    quantity: Decimal
    #: What it charged for them before tax (``goods_charged``).
    goods: Decimal
    #: What approved credit notes took, before tax.
    credited: Decimal = ZERO
    #: What returns raised on the bill line itself took.
    direct_quantity: Decimal = ZERO
    direct_taxable: Decimal = ZERO
    #: What returns raised on the note line took of this bill's units.
    note_quantity: Decimal = ZERO
    note_taxable: Decimal = ZERO
    #: Units a return in hand names on this line, not yet valued.
    reserved: Decimal = ZERO

    @property
    def open_units(self) -> Decimal:
        """Return the billed units still with the customer."""
        return max(self.quantity - self.direct_quantity - self.note_quantity, ZERO)

    @property
    def room(self) -> Decimal:
        """Return the units a return off the note may still be set against."""
        return max(self.open_units - self.reserved, ZERO)

    @property
    def left(self) -> Decimal:
        """Return what the line is still worth, before tax."""
        return max(
            self.goods - self.credited - self.direct_taxable - self.note_taxable,
            ZERO,
        )


@dataclass(frozen=True, slots=True)
class NoteReturn:
    """The billed part of one return line raised off a delivery note line."""

    line_id: UUID | None
    return_id: UUID | None
    #: Units that reversed a bill: the line's quantity less what came back
    #: before billing.
    quantity: Decimal
    #: What those units credited, before tax.
    taxable: Decimal


@dataclass(frozen=True, slots=True)
class BillShare:
    """What one return line raised off a note took off one bill line."""

    return_line_id: UUID | None
    return_id: UUID | None
    bill_line_id: UUID
    invoice_id: UUID
    quantity: Decimal
    taxable: Decimal
    #: This share of the return line's billed value, as a fraction of it.
    of_value: Decimal
    #: This share of the return line's billed units, as a fraction of them.
    of_units: Decimal


@dataclass(frozen=True, slots=True)
class BillPart:
    """Units of one bill line that a return is about to bring back."""

    bill_line_id: UUID
    invoice_id: UUID
    quantity: Decimal
    #: The most these units may credit: what they are still worth.
    worth: Decimal
    #: What the bill charged for them, before any credit.
    charged: Decimal


def spread_over(worths: Sequence[Decimal], value: Decimal) -> list[Decimal]:
    """Split a return's value over the bills its units came from.

    Earliest bill first: each takes up to what its units were still worth
    and the last takes the rest, so a return priced below its bills (a
    restocking deduction) is short on the last of them and no bill is ever
    credited past what it charged.
    """
    parts: list[Decimal] = []
    rest = max(value, ZERO)
    for position, worth in enumerate(worths):
        part = rest if position == len(worths) - 1 else min(rest, max(worth, ZERO))
        parts.append(part)
        rest -= part
    return parts


def _units_worth(
    left: Decimal, quantity: Decimal, exact: Decimal | None, out: Decimal
) -> Decimal:
    """Return what some of a bill line's units still out are worth.

    What is left of the line, spread over the units still out: 2 boxes
    charged 2,400.00 and credited 400.00 are worth 1,000.00 each, and once
    one has come back the other is worth all of what is left. ``exact`` is
    the same units before rounding, for a part typed in another unit: seven
    pieces of a box of twelve are seven twelfths of it, not 0.5833 of it.
    """
    if left <= ZERO or quantity <= ZERO or out <= ZERO:
        return ZERO
    if quantity >= out:
        return left.quantize(_FOUR)
    units = quantity if exact is None else exact
    return min(left, left * units / out).quantize(_FOUR)


def _allocate(
    bills: list[BillStanding], backs: Sequence[NoteReturn]
) -> list[BillShare]:
    """Set what came back off the note against the bills that charged it.

    Oldest return first, earliest bill first, each bill for the units it
    billed that are still out. The bills are updated as it goes. Units no
    bill has room for -- their bill was cancelled since -- are set against
    nothing, and their value goes with them.
    """
    shares: list[BillShare] = []
    for back in backs:
        if back.quantity <= ZERO:
            continue
        units = back.quantity
        takes: list[tuple[BillStanding, Decimal]] = []
        for bill in bills:
            room = bill.room
            if room <= ZERO:
                continue
            took = min(units, room)
            takes.append((bill, took))
            units -= took
            if units <= ZERO:
                break
        if not takes:
            continue
        value = max(back.taxable, ZERO)
        if units > _DUST:
            value = value * (back.quantity - units) / back.quantity
        # Each bill's units are worth their share of what is left of it: all
        # of it, unless a return in hand names some of its units itself.
        parts = spread_over(
            [
                bill.left * min(took / bill.open_units, Decimal("1"))
                for bill, took in takes
            ],
            value,
        )
        for (bill, took), part in zip(takes, parts, strict=True):
            bill.note_quantity += took
            bill.note_taxable += part
            shares.append(
                BillShare(
                    return_line_id=back.line_id,
                    return_id=back.return_id,
                    bill_line_id=bill.line_id,
                    invoice_id=bill.invoice_id,
                    quantity=took,
                    taxable=part,
                    of_value=(
                        part / back.taxable
                        if back.taxable > ZERO
                        else took / back.quantity
                    ),
                    of_units=took / back.quantity,
                )
            )
    return shares


class BillLedger:
    """The bills of one delivery note line, and what has come off each.

    One bill line on its own where the bill was not raised from a note. A
    return being priced or completed adds its own lines as it goes
    (``hold_direct``, ``hold_through_note``), so two lines of one return
    cannot both take the same remaining worth.
    """

    def __init__(self, bills: list[BillStanding], backs: list[NoteReturn]) -> None:
        """Keep the bills in billing order and the returns oldest first."""
        self._bills = bills
        self._backs = backs
        self._held: dict[UUID, tuple[Decimal, Decimal]] = {}
        self._mine: list[NoteReturn] = []

    @property
    def bills(self) -> list[BillStanding]:
        """Return the bill lines, earliest first, before any return off the note."""
        return self._bills

    @property
    def credit_noted(self) -> bool:
        """Say whether any of the bill lines carries an approved credit note."""
        return any(bill.credited > ZERO for bill in self._bills)

    def standing(
        self, *, reserve: tuple[UUID, Decimal] | None = None
    ) -> tuple[list[BillStanding], list[BillShare]]:
        """Return where each bill stands, and how the note's returns were split.

        Args:
            reserve: A bill line and the units a return is about to bring
                back on it by name. Units named on a bill line are that
                line's, so the returns off the note are set against the
                rest.

        """
        bills = [replace(bill) for bill in self._bills]
        for bill in bills:
            quantity, taxable = self._held.get(bill.line_id, (ZERO, ZERO))
            bill.direct_quantity += quantity
            bill.direct_taxable += taxable
            if reserve is not None and reserve[0] == bill.line_id:
                bill.reserved = reserve[1]
        return bills, _allocate(bills, [*self._backs, *self._mine])

    def credits(self, bill_line_id: UUID) -> BillLineCredits:
        """Return what returns and credit notes have taken off one bill line."""
        bills, _shares = self.standing()
        for bill in bills:
            if bill.line_id == bill_line_id:
                return BillLineCredits(
                    returned_quantity=(
                        bill.direct_quantity + bill.note_quantity
                    ).quantize(_FOUR),
                    returned_taxable=(bill.direct_taxable + bill.note_taxable).quantize(
                        _FOUR
                    ),
                    credited_taxable=bill.credited.quantize(_FOUR),
                )
        return BillLineCredits(ZERO, ZERO, ZERO)

    def direct_part(
        self, bill_line_id: UUID, *, quantity: Decimal, exact: Decimal | None = None
    ) -> BillPart | None:
        """Price units a return names on one bill line."""
        bills, _shares = self.standing(reserve=(bill_line_id, quantity))
        for bill in bills:
            if bill.line_id != bill_line_id:
                continue
            units = quantity if exact is None else exact
            return BillPart(
                bill_line_id=bill.line_id,
                invoice_id=bill.invoice_id,
                quantity=quantity,
                worth=_units_worth(bill.left, quantity, exact, bill.open_units),
                charged=_part_of(bill.goods, units, bill.quantity),
            )
        return None

    def note_parts(
        self, *, quantity: Decimal, exact: Decimal | None = None
    ) -> list[BillPart]:
        """Price billed units a return brings back off the note line.

        Earliest bill first, each for the units it billed that are still
        out; the parts together are what the units are still worth.
        """
        if quantity <= ZERO:
            return []
        bills, _shares = self.standing()
        scale = Decimal("1") if exact is None else exact / quantity
        parts: list[BillPart] = []
        units = quantity
        for bill in bills:
            room = bill.open_units
            if room <= ZERO:
                continue
            took = min(units, room)
            parts.append(
                BillPart(
                    bill_line_id=bill.line_id,
                    invoice_id=bill.invoice_id,
                    quantity=took,
                    worth=_units_worth(
                        bill.left, took, None if exact is None else took * scale, room
                    ),
                    charged=_part_of(bill.goods, took * scale, bill.quantity),
                )
            )
            units -= took
            if units <= ZERO:
                break
        return parts

    def hold_direct(
        self, bill_line_id: UUID, *, quantity: Decimal, taxable: Decimal
    ) -> None:
        """Count a line of the return in hand, named on a bill line."""
        held_quantity, held_taxable = self._held.get(bill_line_id, (ZERO, ZERO))
        self._held[bill_line_id] = (
            held_quantity + quantity,
            held_taxable + taxable,
        )

    def hold_through_note(self, *, quantity: Decimal, taxable: Decimal) -> None:
        """Count the billed part of a line of the return in hand, off the note."""
        self._mine.append(NoteReturn(None, None, quantity, taxable))


def _part_of(goods: Decimal, units: Decimal, billed: Decimal) -> Decimal:
    """Return what a bill line charged for some of its units, before tax."""
    if billed <= ZERO or units <= ZERO:
        return ZERO
    return (goods * units / billed).quantize(_FOUR)


_BILL_COLUMNS = (
    SalesInvoiceLine.id,
    SalesInvoiceLine.sales_invoice_id,
    SalesInvoiceLine.source_document_type,
    SalesInvoiceLine.source_document_line_id,
    SalesInvoiceLine.current_invoice_quantity,
    SalesInvoiceLine.gross_amount,
    SalesInvoiceLine.discount_amount,
    SalesInvoiceLine.bill_discount_amount,
    SalesInvoiceLine.charges_amount,
    SalesInvoice.invoice_date,
    SalesInvoice.invoice_number,
    SalesInvoiceLine.line_number,
)


def _standing(row: Row[Any]) -> BillStanding:
    """Build one bill line's standing from its row, with nothing off it yet."""
    return BillStanding(
        line_id=row.id,
        invoice_id=row.sales_invoice_id,
        quantity=Decimal(str(row.current_invoice_quantity)),
        goods=(
            Decimal(str(row.gross_amount))
            - Decimal(str(row.discount_amount))
            - Decimal(str(row.bill_discount_amount))
            + Decimal(str(row.charges_amount))
        ).quantize(_FOUR),
    )


class BillBook:
    """The ledgers of the bills some returns reverse, read in bulk.

    The one reading of "what came back against this bill": a return being
    priced, a credit note's cap, and everything that asks what a bill still
    owes or what its salesman is paid on all come here, so they cannot
    disagree about which bill a return off a note took its units from.
    """

    def __init__(
        self,
        session: Session,
        *,
        firm_id: UUID,
        completed_only: bool,
        exclude_return_id: UUID | None = None,
        as_of: date | None = None,
    ) -> None:
        """Remember which returns and credit notes count.

        Args:
            session: The firm's session.
            firm_id: The owning firm.
            completed_only: Count only returns that have credited the
                customer (completed or closed), which is what a credit
                note's cap and every report want. A return being priced
                asks for every live one instead, drafts included, so two
                returns of one line cannot both take the same remaining
                worth.
            exclude_return_id: A return being priced or completed, whose
                own lines are not "already".
            as_of: Count only returns and credit notes dated on or before
                this day; None counts what stands now.

        """
        self._session = session
        self._firm_id = firm_id
        self._statuses = _COMPLETED if completed_only else _LIVE
        self._exclude_return_id = exclude_return_id
        self._as_of = as_of
        self._by_note: dict[UUID, BillLedger | None] = {}
        self._by_bill: dict[UUID, BillLedger] = {}

    def of_note_line(self, note_line_id: UUID) -> BillLedger | None:
        """Return the ledger of a note line's bills; None if nobody billed it."""
        if note_line_id not in self._by_note:
            self.load(note_line_ids=[note_line_id])
        return self._by_note.get(note_line_id)

    def of_bill_line(self, bill_line_id: UUID) -> BillLedger | None:
        """Return the ledger one bill line belongs to."""
        if bill_line_id not in self._by_bill:
            self.load(bill_line_ids=[bill_line_id])
        return self._by_bill.get(bill_line_id)

    def shares(self) -> list[BillShare]:
        """Return how every loaded return off a note was split over its bills."""
        answer: list[BillShare] = []
        for ledger in self._by_note.values():
            if ledger is not None:
                answer.extend(ledger.standing()[1])
        return answer

    def load(
        self,
        *,
        note_line_ids: Iterable[UUID] = (),
        bill_line_ids: Iterable[UUID] = (),
    ) -> None:
        """Read the ledgers of these note lines and bill lines, in bulk.

        A fixed number of statements per chunk of ids, however many lines
        are asked about.
        """
        notes = [item for item in dict.fromkeys(note_line_ids)]
        asked: dict[UUID, Row[Any]] = {}
        for part in chunks(list(dict.fromkeys(bill_line_ids))):
            for row in self._session.execute(
                select(*_BILL_COLUMNS)
                .join(
                    SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id
                )
                .where(SalesInvoiceLine.id.in_(part))
            ).all():
                asked[row.id] = row
                if row.source_document_type == "DELIVERY_NOTE":
                    notes.append(row.source_document_line_id)
        notes = [item for item in dict.fromkeys(notes) if item not in self._by_note]
        by_note: dict[UUID, list[BillStanding]] = defaultdict(list)
        standing: dict[UUID, BillStanding] = {}
        for part in chunks(notes):
            for row in self._session.execute(
                select(*_BILL_COLUMNS)
                .join(
                    SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id
                )
                .where(
                    SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
                    SalesInvoiceLine.source_document_line_id.in_(part),
                    SalesInvoiceLine.is_deleted.is_(False),
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.status.in_(_CHARGED),
                )
                .order_by(
                    SalesInvoice.invoice_date.asc(),
                    SalesInvoice.invoice_number.asc(),
                    SalesInvoiceLine.line_number.asc(),
                )
            ).all():
                bill = _standing(row)
                by_note[row.source_document_line_id].append(bill)
                standing[bill.line_id] = bill
        lone: list[BillStanding] = []
        for line_id, row in asked.items():
            if line_id in standing or line_id in self._by_bill:
                continue
            bill = _standing(row)
            standing[line_id] = bill
            lone.append(bill)
        self._read_credit_notes(standing)
        self._read_returns_on_bills(standing)
        backs = self._read_returns_on_notes(list(by_note))
        for note_line_id in notes:
            bills = by_note.get(note_line_id)
            if not bills:
                self._by_note[note_line_id] = None
                continue
            ledger = BillLedger(bills, backs.get(note_line_id, []))
            self._by_note[note_line_id] = ledger
            for bill in bills:
                self._by_bill[bill.line_id] = ledger
        for bill in lone:
            self._by_bill[bill.line_id] = BillLedger([bill], [])

    def _read_credit_notes(self, standing: dict[UUID, BillStanding]) -> None:
        """Put what approved credit notes took on each bill line."""
        for part in chunks(list(standing)):
            statement = (
                select(
                    CreditNoteLine.sales_invoice_line_id,
                    func.coalesce(func.sum(CreditNoteLine.taxable_amount), 0),
                )
                .join(CreditNote, CreditNote.id == CreditNoteLine.credit_note_id)
                .where(
                    CreditNoteLine.firm_id == self._firm_id,
                    CreditNoteLine.sales_invoice_line_id.in_(part),
                    CreditNoteLine.is_deleted.is_(False),
                    CreditNote.is_deleted.is_(False),
                    CreditNote.status == CreditNoteStatus.APPROVED.value,
                )
                .group_by(CreditNoteLine.sales_invoice_line_id)
            )
            if self._as_of is not None:
                statement = statement.where(CreditNote.credit_note_date <= self._as_of)
            for line_id, taxable in self._session.execute(statement).all():
                standing[line_id].credited = Decimal(str(taxable or 0))

    def _returns(
        self, *columns: ColumnElement[Any] | InstrumentedAttribute[Any]
    ) -> Select[Any]:
        """Start a statement over the return lines that count."""
        statement = (
            select(*columns)
            .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
            .where(
                SalesReturnLine.firm_id == self._firm_id,
                SalesReturnLine.is_deleted.is_(False),
                SalesReturn.is_deleted.is_(False),
                SalesReturn.status.in_(self._statuses),
            )
        )
        if self._exclude_return_id is not None:
            statement = statement.where(SalesReturn.id != self._exclude_return_id)
        if self._as_of is not None:
            statement = statement.where(SalesReturn.return_date <= self._as_of)
        return statement

    def _read_returns_on_bills(self, standing: dict[UUID, BillStanding]) -> None:
        """Put what returns raised on each bill line itself took."""
        for part in chunks(list(standing)):
            for line_id, quantity, taxable in self._session.execute(
                self._returns(
                    SalesReturnLine.source_document_line_id,
                    func.coalesce(func.sum(SalesReturnLine.current_return_quantity), 0),
                    func.coalesce(
                        func.sum(
                            SalesReturnLine.net_amount - SalesReturnLine.tax_amount
                        ),
                        0,
                    ),
                )
                .where(
                    SalesReturnLine.source_document_type == "SALES_INVOICE",
                    SalesReturnLine.source_document_line_id.in_(part),
                )
                .group_by(SalesReturnLine.source_document_line_id)
            ).all():
                standing[line_id].direct_quantity = Decimal(str(quantity or 0))
                standing[line_id].direct_taxable = Decimal(str(taxable or 0))

    def _read_returns_on_notes(
        self, note_line_ids: Sequence[UUID]
    ) -> dict[UUID, list[NoteReturn]]:
        """Read the billed part of each return line raised off these note lines.

        Oldest first: by when each completed, then by when it was raised, so
        the split of an earlier return does not move when a later one lands.
        """
        found: list[tuple[tuple[Any, ...], UUID, NoteReturn]] = []
        for part in chunks(list(note_line_ids)):
            for row in self._session.execute(
                self._returns(
                    SalesReturnLine.id,
                    SalesReturnLine.sales_return_id,
                    SalesReturnLine.source_document_line_id,
                    SalesReturnLine.current_return_quantity,
                    SalesReturnLine.unbilled_quantity,
                    SalesReturnLine.net_amount,
                    SalesReturnLine.tax_amount,
                    SalesReturnLine.line_number,
                    SalesReturn.completed_at,
                    SalesReturn.created_at,
                    SalesReturn.return_number,
                ).where(
                    SalesReturnLine.source_document_type == "DELIVERY_NOTE",
                    SalesReturnLine.source_document_line_id.in_(part),
                )
            ).all():
                quantity = Decimal(str(row.current_return_quantity or 0))
                if quantity <= ZERO:
                    continue
                billed = quantity - min(
                    Decimal(str(row.unbilled_quantity or 0)), quantity
                )
                if billed <= ZERO:
                    continue
                taxable = (
                    (Decimal(str(row.net_amount)) - Decimal(str(row.tax_amount)))
                    * billed
                    / quantity
                )
                found.append(
                    (
                        (
                            row.completed_at is None,
                            str(row.completed_at or ""),
                            str(row.created_at or ""),
                            row.return_number,
                            row.line_number,
                        ),
                        row.source_document_line_id,
                        NoteReturn(row.id, row.sales_return_id, billed, taxable),
                    )
                )
        backs: dict[UUID, list[NoteReturn]] = defaultdict(list)
        for _order, note_line_id, back in sorted(found, key=lambda item: item[0]):
            backs[note_line_id].append(back)
        return backs


def bill_line_credits(
    session: Session,
    charged: SalesInvoiceLine,
    *,
    completed_only: bool,
    exclude_return_id: UUID | None = None,
) -> BillLineCredits:
    """Return what returns and credit notes have already taken off a bill line.

    **Returns** by either route: raised on the bill line itself, or on the
    delivery note line it billed, for the units of that return this bill
    charged (``BillLedger``). Only the billed part of each counts; what came
    back before billing credited nothing. **Credit notes** once approved,
    which is when one posts.

    Args:
        session: The firm's session.
        charged: The bill line being asked about.
        completed_only: Count only returns that have credited the customer
            (completed or closed), which is what a credit note's cap wants.
        exclude_return_id: A return whose own lines are not "already".

    Returns:
        The quantity and value returned, and the value credited by notes.

    """
    ledger = BillBook(
        session,
        firm_id=charged.firm_id,
        completed_only=completed_only,
        exclude_return_id=exclude_return_id,
    ).of_bill_line(charged.id)
    if ledger is None:
        return BillLineCredits(ZERO, ZERO, ZERO)
    return ledger.credits(charged.id)


def goods_charged(charged: SalesInvoiceLine) -> Decimal:
    """Return what a bill line charged for its goods, before tax.

    Gross, less both discounts, plus the line's own charges -- without its
    share of the delivery charge, which is not goods and does not come back
    with them.
    """
    return (
        Decimal(str(charged.gross_amount))
        - Decimal(str(charged.discount_amount))
        - Decimal(str(charged.bill_discount_amount))
        + Decimal(str(charged.charges_amount))
    ).quantize(_FOUR)
