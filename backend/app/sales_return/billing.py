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

from sqlalchemy import ColumnElement, Row, Select, case, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.selectable import ScalarSelect

from app.core.utils.chunks import chunks
from app.credit_note.models import CreditNote, CreditNoteLine, CreditNoteStatus
from app.delivery_note.models import DeliveryNoteLine
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_return.models import (
    SalesReturn,
    SalesReturnBillPlacement,
    SalesReturnLine,
    SalesReturnLineTax,
)

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
# That split is **written down when the return completes and never moves**
# (``sales_return_bill_placements``, D-PRC-72). It used to be worked out
# afresh on every read, and so it moved: with two bills of 1,416.00 and a
# credit note of 472.00 on the second, a box back off the note was valued on
# the first bill, and a box then named on the first bill's own line pushed it
# onto the second -- where its 1,200.00 did not fit the 800.00 left -- and was
# itself priced at the first bill's full 1,200.00. 3,304.00 credited against
# 2,832.00; with the note on the first bill, 472.00 short.
#
# So ``BillLedger`` reads three things, in this order:
#
# * what completed returns off the note were **placed** on each bill line,
#   as stored;
# * what returns name on a bill line itself -- that line's, and refused once
#   the line has no units left out, because a unit a completed return has
#   already brought back cannot come back again against the same bill;
# * only then what returns off the note that have **not** completed would
#   take -- drafts and approved ones, counted so two returns cannot both be
#   priced on the same remaining worth -- oldest first, earliest bill first.
#   A completed return with no placement (one no bill had room for) is read
#   the same way.


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
    #: What returns raised on the note line took of this bill's units: as
    #: placed when each completed, and as worked out for those that have not.
    note_quantity: Decimal = ZERO
    note_taxable: Decimal = ZERO
    #: Units a return in hand names on this line, not yet valued.
    reserved: Decimal = ZERO
    #: The units that came back, before each part typed in another unit was
    #: rounded to four places: seven pieces of a box are seven twelfths.
    gone_exact: Decimal = ZERO

    @property
    def open_units(self) -> Decimal:
        """Return the billed units still with the customer."""
        return max(self.quantity - self.direct_quantity - self.note_quantity, ZERO)

    @property
    def open_exact(self) -> Decimal:
        """Return the units still out, unrounded.

        What a part of them is worth is its share of **these**: three
        returns of seven pieces left 0.8334 of a box by the stored figures
        where ten twelfths were out, and each took paise less than its
        share until a bill returned in full read 0.07 outstanding
        (D-PRC-79).
        """
        return max(self.quantity - self.gone_exact, ZERO)

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
    #: What those units took off the customer's account: with their tax.
    net: Decimal = ZERO
    #: The billed units as they were typed, where that was another unit.
    entered: Decimal | None = None
    #: How many of the source line's unit one typed unit is.
    factor: Decimal = ZERO


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
    #: What this share took off the customer's account: with its tax.
    net: Decimal = ZERO
    #: This share of the units as typed, where that was another unit.
    entered: Decimal | None = None
    #: How many of the bill line's unit one typed unit is.
    factor: Decimal = ZERO
    #: Whether this is a placement as stored, not one worked out on the read.
    placed: bool = False


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
    #: Whether these are all of the line's units still out, so that what
    #: they credit is all the line is still worth.
    closes: bool = False


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


def _exact(quantity: object, entered: object, factor: object) -> Decimal:
    """Return a stored quantity before it was rounded to four places.

    What was typed times its factor where the line was typed in another
    unit, and never further from the stored figure than rounding put it.
    """
    stored = Decimal(str(quantity or 0))
    if entered is None:
        return stored
    exact = Decimal(str(entered)) * Decimal(str(factor or 1))
    return exact if abs(exact - stored) <= _FOUR else stored


def _units_worth(
    left: Decimal,
    quantity: Decimal,
    exact: Decimal | None,
    out: Decimal,
    out_exact: Decimal | None = None,
) -> Decimal:
    """Return what some of a bill line's units still out are worth.

    What is left of the line, spread over the units still out: 2 boxes
    charged 2,400.00 and credited 400.00 are worth 1,000.00 each, and once
    one has come back the other is worth all of what is left. ``exact`` is
    the same units before rounding, for a part typed in another unit: seven
    pieces of a box of twelve are seven twelfths of it, not 0.5833 of it --
    and ``out_exact`` is the units still out read the same way, so the
    share is seven of the seventeen pieces out and not 0.5833 of 1.4167
    (D-PRC-79).
    """
    if left <= ZERO or quantity <= ZERO or out <= ZERO:
        return ZERO
    if quantity >= out:
        return left.quantize(_FOUR)
    units = quantity if exact is None else exact
    over = out if out_exact is None or out_exact <= ZERO else out_exact
    return min(left, left * units / over).quantize(_FOUR)


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
            of_units = took / back.quantity
            bill.note_quantity += took
            bill.note_taxable += part
            bill.gone_exact += (
                took
                if back.entered is None
                else _exact(took, back.entered * of_units, back.factor)
            )
            of_value = part / back.taxable if back.taxable > ZERO else of_units
            shares.append(
                BillShare(
                    return_line_id=back.line_id,
                    return_id=back.return_id,
                    bill_line_id=bill.line_id,
                    invoice_id=bill.invoice_id,
                    quantity=took,
                    taxable=part,
                    of_value=of_value,
                    of_units=of_units,
                    net=back.net * of_value,
                    entered=None if back.entered is None else back.entered * of_units,
                    factor=back.factor,
                )
            )
    return shares


class BillLedger:
    """The bills of one delivery note line, and what has come off each.

    One bill line on its own where the bill was not raised from a note. The
    bills arrive with what completed returns off the note were **placed** on
    them already counted (``sales_return_bill_placements``); ``backs`` are
    only the returns off the note whose split is not settled yet. A return
    being priced or completed adds its own lines as it goes
    (``hold_direct``, ``hold_through_note``), so two lines of one return
    cannot both take the same remaining worth.
    """

    def __init__(self, bills: list[BillStanding], backs: list[NoteReturn]) -> None:
        """Keep the bills in billing order and the returns oldest first."""
        self._bills = bills
        self._backs = backs
        self._held: dict[UUID, tuple[Decimal, Decimal, Decimal]] = {}
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
        """Return where each bill stands, and how the unsettled returns split.

        The shares are of the returns off the note that have no stored
        placement; what was placed is already on the bills.

        Args:
            reserve: A bill line and the units a return is about to bring
                back on it by name. Units named on a bill line are that
                line's, so the returns off the note are set against the
                rest.

        """
        bills = [replace(bill) for bill in self._bills]
        for bill in bills:
            quantity, taxable, exact = self._held.get(bill.line_id, (ZERO, ZERO, ZERO))
            bill.direct_quantity += quantity
            bill.direct_taxable += taxable
            bill.gone_exact += exact
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

    def named_room(self, bill_line_id: UUID) -> tuple[Decimal, Decimal]:
        """Return what one bill line billed, and how much of it can be named.

        The units a return may still bring back **against this line by
        name**: what it billed, less what other returns named on it, less
        what completed returns off the note were placed on it. A placement
        does not move (D-PRC-72), so once those units are gone the line has
        nothing left to return; a return off the note that has not completed
        gives way instead, and is set against the next bill.
        """
        for bill in self._bills:
            if bill.line_id != bill_line_id:
                continue
            held = self._held.get(bill_line_id, (ZERO, ZERO, ZERO))[0]
            return bill.quantity, max(bill.open_units - held, ZERO)
        return ZERO, ZERO

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
                worth=_units_worth(
                    bill.left, quantity, exact, bill.open_units, bill.open_exact
                ),
                charged=_part_of(bill.goods, units, bill.quantity),
                closes=quantity >= bill.open_units,
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
                        bill.left,
                        took,
                        None if exact is None else took * scale,
                        room,
                        bill.open_exact,
                    ),
                    charged=_part_of(bill.goods, took * scale, bill.quantity),
                    closes=took >= room,
                )
            )
            units -= took
            if units <= ZERO:
                break
        return parts

    def hold_direct(
        self,
        bill_line_id: UUID,
        *,
        quantity: Decimal,
        taxable: Decimal,
        exact: Decimal | None = None,
    ) -> None:
        """Count a line of the return in hand, named on a bill line."""
        held_quantity, held_taxable, held_exact = self._held.get(
            bill_line_id, (ZERO, ZERO, ZERO)
        )
        self._held[bill_line_id] = (
            held_quantity + quantity,
            held_taxable + taxable,
            held_exact + (quantity if exact is None else exact),
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
        """Return how the loaded returns with no stored placement were split."""
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
        self._read_placements(standing)
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
            for row in self._session.execute(
                self._returns(
                    SalesReturnLine.source_document_line_id,
                    SalesReturnLine.current_return_quantity,
                    SalesReturnLine.entered_quantity,
                    SalesReturnLine.conversion_factor,
                    SalesReturnLine.net_amount,
                    SalesReturnLine.tax_amount,
                ).where(
                    SalesReturnLine.source_document_type == "SALES_INVOICE",
                    SalesReturnLine.source_document_line_id.in_(part),
                )
            ).all():
                bill = standing[row.source_document_line_id]
                bill.direct_quantity += Decimal(str(row.current_return_quantity or 0))
                bill.direct_taxable += Decimal(str(row.net_amount or 0)) - Decimal(
                    str(row.tax_amount or 0)
                )
                bill.gone_exact += _exact(
                    row.current_return_quantity,
                    row.entered_quantity,
                    row.conversion_factor,
                )

    def _read_placements(self, standing: dict[UUID, BillStanding]) -> None:
        """Put what completed returns off the note were placed on each bill line.

        As written when each completed (D-PRC-72), whatever has happened to
        the bills since. Only a completed return has any, so they are read
        whichever returns this book otherwise counts.
        """
        for part in chunks(list(standing)):
            statement = _placements(
                self._firm_id,
                SalesReturnBillPlacement.sales_invoice_line_id,
                SalesReturnBillPlacement.quantity,
                SalesReturnBillPlacement.entered_quantity,
                SalesReturnBillPlacement.conversion_factor,
                SalesReturnBillPlacement.taxable_amount,
                as_of=self._as_of,
            ).where(SalesReturnBillPlacement.sales_invoice_line_id.in_(part))
            if self._exclude_return_id is not None:
                statement = statement.where(
                    SalesReturnBillPlacement.sales_return_id != self._exclude_return_id
                )
            for row in self._session.execute(statement).all():
                bill = standing[row.sales_invoice_line_id]
                bill.note_quantity += Decimal(str(row.quantity or 0))
                bill.note_taxable += Decimal(str(row.taxable_amount or 0))
                bill.gone_exact += _exact(
                    row.quantity, row.entered_quantity, row.conversion_factor
                )

    def _read_returns_on_notes(
        self, note_line_ids: Sequence[UUID]
    ) -> dict[UUID, list[NoteReturn]]:
        """Read the billed part of each unsettled return line off these note lines.

        The ones with no stored placement: a draft or an approved return,
        which has not been split yet, and a completed one no bill had room
        for. Oldest first: by when each completed, then by when it was
        raised.
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
                    SalesReturnLine.entered_quantity,
                    SalesReturnLine.conversion_factor,
                    SalesReturn.completed_at,
                    SalesReturn.created_at,
                    SalesReturn.return_number,
                ).where(
                    SalesReturnLine.source_document_type == "DELIVERY_NOTE",
                    SalesReturnLine.source_document_line_id.in_(part),
                    ~_placed(),
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
                share = billed / quantity
                net = Decimal(str(row.net_amount)) * share
                taxable = net - Decimal(str(row.tax_amount)) * share
                entered = row.entered_quantity
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
                        NoteReturn(
                            row.id,
                            row.sales_return_id,
                            billed,
                            taxable,
                            net=net,
                            entered=(
                                None
                                if entered is None
                                else Decimal(str(entered)) * share
                            ),
                            factor=Decimal(str(row.conversion_factor or 0)),
                        ),
                    )
                )
        backs: dict[UUID, list[NoteReturn]] = defaultdict(list)
        for _order, note_line_id, back in sorted(found, key=lambda item: item[0]):
            backs[note_line_id].append(back)
        return backs


def _placed() -> ColumnElement[bool]:
    """Match a return line whose split over its bills is written down."""
    return (
        select(SalesReturnBillPlacement.id)
        .where(
            SalesReturnBillPlacement.sales_return_line_id == SalesReturnLine.id,
            SalesReturnBillPlacement.is_deleted.is_(False),
        )
        .exists()
    )


def _placements(
    firm_id: UUID,
    *columns: ColumnElement[Any] | InstrumentedAttribute[Any],
    as_of: date | None,
) -> Select[Any]:
    """Start a statement over the placements of returns that credited."""
    statement = (
        select(*columns)
        .join(SalesReturn, SalesReturn.id == SalesReturnBillPlacement.sales_return_id)
        .where(
            SalesReturnBillPlacement.firm_id == firm_id,
            SalesReturnBillPlacement.is_deleted.is_(False),
            SalesReturn.is_deleted.is_(False),
            SalesReturn.status.in_(_COMPLETED),
        )
    )
    if as_of is not None:
        statement = statement.where(SalesReturn.return_date <= as_of)
    return statement


def returns_off_notes_against(
    session: Session,
    *,
    firm_id: UUID,
    invoice_ids: Sequence[UUID] | None,
    as_of: date | None = None,
) -> list[BillShare]:
    """Return what completed returns raised off delivery notes took off bills.

    A return raised off a note after its bill exists credits the customer
    and reverses the bill's tax, and names no bill: read only off returns
    that name one, the bill went on reading wholly outstanding, its salesman
    was paid on goods that had come back and the target counted them
    (D-PRC-66). Each such return line is set against the bills that charged
    its units by the split that priced it (``BillLedger``), so what a bill
    still owes, ageing, targets and commission read the units and the value
    on the bills they came from. A return off a note nobody has billed
    counts against nothing: it credited nothing.

    The split is the one written when each return completed
    (``sales_return_bill_placements``, D-PRC-72) and is read as stored, so a
    bill never reads differently because something else happened to the
    note since. Only a completed return with nothing stored is still worked
    out.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        invoice_ids: The sales invoices to ask about -- no more than one
            chunk of them -- or None for every invoice of the firm.
        as_of: Count only returns and credit notes dated on or before this
            day.

    Returns:
        One share per return line and bill line it took units from.

    """
    if invoice_ids is not None and not invoice_ids:
        return []
    stored = _placements(
        firm_id,
        SalesReturnBillPlacement.sales_return_line_id,
        SalesReturnBillPlacement.sales_return_id,
        SalesReturnBillPlacement.sales_invoice_line_id,
        SalesReturnBillPlacement.sales_invoice_id,
        SalesReturnBillPlacement.quantity,
        SalesReturnBillPlacement.entered_quantity,
        SalesReturnBillPlacement.conversion_factor,
        SalesReturnBillPlacement.taxable_amount,
        SalesReturnBillPlacement.net_amount,
        as_of=as_of,
    )
    if invoice_ids is not None:
        stored = stored.where(
            SalesReturnBillPlacement.sales_invoice_id.in_(invoice_ids)
        )
    answer = [
        BillShare(
            return_line_id=row.sales_return_line_id,
            return_id=row.sales_return_id,
            bill_line_id=row.sales_invoice_line_id,
            invoice_id=row.sales_invoice_id,
            quantity=Decimal(str(row.quantity or 0)),
            taxable=Decimal(str(row.taxable_amount or 0)),
            of_value=ZERO,
            of_units=ZERO,
            net=Decimal(str(row.net_amount or 0)),
            entered=(
                None
                if row.entered_quantity is None
                else Decimal(str(row.entered_quantity))
            ),
            factor=Decimal(str(row.conversion_factor or 0)),
            placed=True,
        )
        for row in session.execute(stored).all()
    ]
    off_notes = (
        select(SalesReturnLine.source_document_line_id)
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(
            SalesReturnLine.firm_id == firm_id,
            SalesReturnLine.source_document_type == "DELIVERY_NOTE",
            SalesReturnLine.is_deleted.is_(False),
            SalesReturnLine.current_return_quantity > SalesReturnLine.unbilled_quantity,
            SalesReturn.is_deleted.is_(False),
            SalesReturn.status.in_(_COMPLETED),
            ~_placed(),
        )
    )
    if as_of is not None:
        off_notes = off_notes.where(SalesReturn.return_date <= as_of)
    if invoice_ids is None:
        note_line_ids = session.scalars(off_notes.distinct()).all()
    else:
        note_line_ids = session.scalars(
            select(SalesInvoiceLine.source_document_line_id)
            .where(
                SalesInvoiceLine.sales_invoice_id.in_(invoice_ids),
                SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
                SalesInvoiceLine.is_deleted.is_(False),
                SalesInvoiceLine.source_document_line_id.in_(off_notes),
            )
            .distinct()
        ).all()
    if not note_line_ids:
        return answer
    book = BillBook(session, firm_id=firm_id, completed_only=True, as_of=as_of)
    book.load(note_line_ids=note_line_ids)
    wanted = None if invoice_ids is None else set(invoice_ids)
    answer.extend(
        share for share in book.shares() if wanted is None or share.invoice_id in wanted
    )
    return answer


def returns_resting_on(
    session: Session, *, firm_id: UUID, invoice_id: UUID
) -> set[UUID]:
    """Return the returns off delivery notes that have taken units of one bill.

    What stops a bill being cancelled (D-PRC-77): a completed return whose
    units were **placed** on this bill has credited the customer for goods
    it charged, and cancelling the bill would take the whole of it off the
    customer on top of that credit. A return off the note that has not
    completed counts where its units would be set against this bill as the
    bills stand.

    A return of the same note that took nothing of this bill is not here:
    one that came back before any bill had charged its goods, one placed on
    the note's other bills -- and any return at all where the bill is a
    draft, which has charged nobody.
    """
    resting = set(
        session.scalars(
            _placements(
                firm_id, SalesReturnBillPlacement.sales_return_id, as_of=None
            ).where(SalesReturnBillPlacement.sales_invoice_id == invoice_id)
        ).all()
    )
    note_line_ids = session.scalars(
        select(SalesInvoiceLine.source_document_line_id).where(
            SalesInvoiceLine.sales_invoice_id == invoice_id,
            SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
            SalesInvoiceLine.is_deleted.is_(False),
        )
    ).all()
    if note_line_ids:
        book = BillBook(session, firm_id=firm_id, completed_only=False)
        book.load(note_line_ids=note_line_ids)
        resting |= {
            share.return_id
            for share in book.shares()
            if share.invoice_id == invoice_id and share.return_id is not None
        }
    return resting


def _split_header(
    amount: Decimal, bills: Sequence[tuple[UUID, Decimal, Decimal]]
) -> dict[UUID, Decimal]:
    """Split a return's header credit over the bills it gave it back to.

    Args:
        amount: The return's ``additional_charges`` and ``round_off``.
        bills: The bills its goods were charged on, earliest first, each
            with the header charges it made and what the return's lines
            took off it.

    Returns:
        Each bill's part. In proportion to the header charges the bills
        made, because those are what is being given back; where none made
        any -- a round-off alone -- in proportion to what the lines took
        off each. The last bill takes what rounding left.

    """
    if not bills:
        return {}
    weights = [max(charge, ZERO) for _bill, charge, _net in bills]
    if sum(weights, ZERO) <= ZERO:
        weights = [max(net, ZERO) for _bill, _charge, net in bills]
    whole = sum(weights, ZERO)
    parts: dict[UUID, Decimal] = {}
    rest = amount
    for position, (bill_id, _charge, _net) in enumerate(bills):
        if position == len(bills) - 1:
            part = rest
        elif whole > ZERO:
            part = (amount * weights[position] / whole).quantize(_FOUR)
        else:
            part = ZERO
        parts[bill_id] = part
        rest -= part
    return parts


def header_credits_against(
    session: Session,
    *,
    firm_id: UUID,
    invoice_ids: Sequence[UUID] | None,
    as_of: date | None = None,
    worked_out: Sequence[BillShare] = (),
) -> dict[UUID, Decimal]:
    """Return what completed returns' header figures took off each bill.

    The sum, per bill, of ``header_credit_parts``; see there.
    """
    answer: dict[UUID, Decimal] = defaultdict(Decimal)
    for by_bill in header_credit_parts(
        session,
        firm_id=firm_id,
        invoice_ids=invoice_ids,
        as_of=as_of,
        worked_out=worked_out,
    ).values():
        for invoice_id, amount in by_bill.items():
            answer[invoice_id] += amount
    return dict(answer)


def header_credit_parts(
    session: Session,
    *,
    firm_id: UUID,
    invoice_ids: Sequence[UUID] | None,
    as_of: date | None = None,
    worked_out: Sequence[BillShare] = (),
) -> dict[UUID, dict[UUID, Decimal]]:
    """Return what each completed return's header figures took off each bill.

    A return's ``additional_charges`` -- and its ``round_off`` -- credit the
    customer with no line behind them: they are in the return's total, the
    journal and the customer's account, and in no line. Read off the lines
    alone, a bill of 2,932.00 returned in full with its 100.00 of charges
    given back went on reading 100.00 outstanding, aged, and took a receipt
    nobody owed (D-PRC-74).

    They are set against the bills the return's goods were charged on -- the
    bill a line names, and the bills a line off a note was **placed** on
    (``sales_return_bill_placements``), so the answer does not move -- in
    proportion to the header charges those bills made (``_split_header``).
    A return whose goods no bill had charged credited nothing, and counts
    against nothing. Nothing is posted here: the customer's account moved
    once, when the return completed.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        invoice_ids: The sales invoices to ask about -- no more than one
            chunk of them -- or None for every invoice of the firm.
        as_of: Count only returns dated on or before this day.
        worked_out: The shares of completed returns off notes that have no
            stored placement, as ``returns_off_notes_against`` gave them.

    Returns:
        The amount per return and, within it, per invoice, for those with
        any -- per return because the credit a return leaves on a paid bill
        is that return's to give (D-PRC-75).

    """
    if invoice_ids is not None and not invoice_ids:
        return {}
    header = SalesReturn.additional_charges + SalesReturn.round_off
    headed = select(SalesReturn.id, header).where(
        SalesReturn.firm_id == firm_id,
        SalesReturn.is_deleted.is_(False),
        SalesReturn.status.in_(_COMPLETED),
        header != 0,
    )
    if as_of is not None:
        headed = headed.where(SalesReturn.return_date <= as_of)
    loose: dict[UUID, dict[UUID, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for share in worked_out:
        if share.return_id is not None:
            loose[share.return_id][share.invoice_id] += share.net
    amounts: dict[UUID, Decimal] = {}
    if invoice_ids is None:
        found = session.execute(headed).all()
    else:
        named = select(SalesReturnLine.sales_return_id).where(
            SalesReturnLine.firm_id == firm_id,
            SalesReturnLine.source_document_type == "SALES_INVOICE",
            SalesReturnLine.source_document_id.in_(invoice_ids),
            SalesReturnLine.is_deleted.is_(False),
        )
        placed = select(SalesReturnBillPlacement.sales_return_id).where(
            SalesReturnBillPlacement.firm_id == firm_id,
            SalesReturnBillPlacement.sales_invoice_id.in_(invoice_ids),
            SalesReturnBillPlacement.is_deleted.is_(False),
        )
        found = list(
            session.execute(
                headed.where(or_(SalesReturn.id.in_(named), SalesReturn.id.in_(placed)))
            ).all()
        )
        for part in chunks(list(loose)):
            found.extend(session.execute(headed.where(SalesReturn.id.in_(part))).all())
    for return_id, amount in found:
        amounts[return_id] = Decimal(str(amount or 0))
    if not amounts:
        return {}
    # What each of those returns' lines took off each bill.
    took: dict[UUID, dict[UUID, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for part in chunks(list(amounts)):
        for return_id, invoice_id, net in session.execute(
            select(
                SalesReturnLine.sales_return_id,
                SalesReturnLine.source_document_id,
                func.coalesce(func.sum(SalesReturnLine.net_amount), 0),
            )
            .where(
                SalesReturnLine.sales_return_id.in_(part),
                SalesReturnLine.source_document_type == "SALES_INVOICE",
                SalesReturnLine.is_deleted.is_(False),
            )
            .group_by(
                SalesReturnLine.sales_return_id, SalesReturnLine.source_document_id
            )
        ).all():
            took[return_id][invoice_id] += Decimal(str(net or 0))
        for return_id, invoice_id, net in session.execute(
            select(
                SalesReturnBillPlacement.sales_return_id,
                SalesReturnBillPlacement.sales_invoice_id,
                func.coalesce(func.sum(SalesReturnBillPlacement.net_amount), 0),
            )
            .where(
                SalesReturnBillPlacement.sales_return_id.in_(part),
                SalesReturnBillPlacement.is_deleted.is_(False),
            )
            .group_by(
                SalesReturnBillPlacement.sales_return_id,
                SalesReturnBillPlacement.sales_invoice_id,
            )
        ).all():
            took[return_id][invoice_id] += Decimal(str(net or 0))
    for return_id, by_bill in loose.items():
        if return_id in amounts:
            for invoice_id, net in by_bill.items():
                took[return_id][invoice_id] += net
    bills: dict[UUID, tuple[tuple[Any, ...], Decimal]] = {}
    for part in chunks(list({bill for by_bill in took.values() for bill in by_bill})):
        for row in session.execute(
            select(
                SalesInvoice.id,
                SalesInvoice.invoice_date,
                SalesInvoice.invoice_number,
                SalesInvoice.additional_charges,
            ).where(SalesInvoice.id.in_(part))
        ).all():
            bills[row.id] = (
                (str(row.invoice_date), row.invoice_number),
                Decimal(str(row.additional_charges or 0)),
            )
    wanted = None if invoice_ids is None else set(invoice_ids)
    answer: dict[UUID, dict[UUID, Decimal]] = {}
    for return_id, amount in amounts.items():
        on = sorted(
            (bill for bill in took.get(return_id, {}) if bill in bills),
            key=lambda bill: bills[bill][0],
        )
        split = _split_header(
            amount, [(bill, bills[bill][1], took[return_id][bill]) for bill in on]
        )
        for invoice_id, part_amount in split.items():
            if wanted is None or invoice_id in wanted:
                answer.setdefault(return_id, {})[invoice_id] = part_amount
    return answer


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


@dataclass(frozen=True, slots=True)
class CreditedBill:
    """One bill a return line was credited against (D-PRC-84)."""

    invoice_id: UUID
    invoice_line_id: UUID
    invoice_number: str
    invoice_date: date
    #: What the return line credited on this bill before tax, where a stored
    #: placement says. None where nothing was split: the line names its bill,
    #: or it completed before placements were kept, and the whole of what it
    #: credited is this bill's.
    taxable: Decimal | None = None


def bills_credited(
    session: Session,
    lines: Sequence[SalesReturnLine],
    *,
    completed: bool = True,
) -> dict[UUID, list[CreditedBill]]:
    """Return, per return line, the bills it was credited against, in order.

    A credit note refers to the invoice it corrects, and a return's readers
    -- its print, GSTR-1's ``cdnr`` row and the GST sales register -- must
    name the same ones:

    * a line raised on a **bill's own line** names that bill;
    * a line raised **off a delivery note** names every bill its billed units
      were set against when it completed, from the stored placements
      (``sales_return_bill_placements``, D-PRC-72), each with the value it
      took, earliest bill first;
    * such a line completed before placements were kept has none, and names
      the earliest bill that stands of its note line, as it always read.

    A line no bill charged -- all of it came back before billing -- names
    none. Three statements for any number of lines, each asked in chunks.

    Args:
        session: The firm's session.
        lines: The return lines to read for.
        completed: False for a return that has not completed: a line off a
            note has not been set against any bill yet, so it names none.

    Returns:
        The bills per return line id; a line that names none is absent.

    """
    found: dict[UUID, list[CreditedBill]] = defaultdict(list)
    named = {
        line.id: (line.source_document_id, line.source_document_line_id)
        for line in lines
        if line.source_document_type == "SALES_INVOICE"
    }
    bills: dict[UUID, tuple[str, date]] = {}
    for group in chunks([invoice_id for invoice_id, _ in named.values()]):
        for invoice_id, number, dated in session.execute(
            select(
                SalesInvoice.id, SalesInvoice.invoice_number, SalesInvoice.invoice_date
            ).where(SalesInvoice.id.in_(group))
        ).all():
            bills[invoice_id] = (number, dated)
    for line_id, (invoice_id, invoice_line_id) in named.items():
        if invoice_id in bills:
            number, dated = bills[invoice_id]
            found[line_id].append(
                CreditedBill(invoice_id, invoice_line_id, number, dated)
            )
    if not completed:
        return dict(found)
    off_notes = [line for line in lines if line.source_document_type == "DELIVERY_NOTE"]
    for group in chunks([line.id for line in off_notes]):
        for row in session.execute(
            select(
                SalesReturnBillPlacement.sales_return_line_id,
                SalesReturnBillPlacement.sales_invoice_id,
                SalesReturnBillPlacement.sales_invoice_line_id,
                SalesInvoice.invoice_number,
                SalesInvoice.invoice_date,
                SalesReturnBillPlacement.taxable_amount,
            )
            .join(
                SalesInvoice,
                SalesInvoice.id == SalesReturnBillPlacement.sales_invoice_id,
            )
            .where(
                SalesReturnBillPlacement.sales_return_line_id.in_(group),
                SalesReturnBillPlacement.is_deleted.is_(False),
            )
            .order_by(
                SalesInvoice.invoice_date,
                SalesInvoice.invoice_number,
                SalesReturnBillPlacement.id,
            )
        ).all():
            placed = found[row[0]]
            taxable = Decimal(str(row[5] or 0))
            for index, earlier in enumerate(placed):
                if earlier.invoice_id == row[1]:
                    # Two lines of one bill charged the note line: one bill.
                    placed[index] = replace(
                        earlier, taxable=(earlier.taxable or ZERO) + taxable
                    )
                    break
            else:
                placed.append(CreditedBill(row[1], row[2], row[3], row[4], taxable))
    # Completed before placements were kept, with something a bill charged.
    by_note_line: dict[UUID, list[UUID]] = defaultdict(list)
    for line in off_notes:
        if line.id not in found and billed_share(line) > ZERO:
            by_note_line[line.source_document_line_id].append(line.id)
    seen: set[UUID] = set()
    for group in chunks(list(by_note_line)):
        for note_line_id, invoice_id, invoice_line_id, number, dated in session.execute(
            select(
                SalesInvoiceLine.source_document_line_id,
                SalesInvoiceLine.sales_invoice_id,
                SalesInvoiceLine.id,
                SalesInvoice.invoice_number,
                SalesInvoice.invoice_date,
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
                SalesInvoiceLine.source_document_line_id.in_(group),
                SalesInvoiceLine.is_deleted.is_(False),
                SalesInvoice.status.in_(_CHARGED),
                SalesInvoice.is_deleted.is_(False),
            )
            .order_by(SalesInvoice.invoice_date.asc(), SalesInvoice.invoice_number)
        ).all():
            if note_line_id in seen:
                continue
            seen.add(note_line_id)
            for line_id in by_note_line[note_line_id]:
                found[line_id].append(
                    CreditedBill(invoice_id, invoice_line_id, number, dated)
                )
    return dict(found)
