"""What a supplier bill line is still worth to claim against (D-PRC-67).

A purchase return and a debit note both take value off a supplier bill line,
and neither read the other: a bill of 1,699.20 took a price-difference debit
note of 472.00 and was then returned in full for 1,699.20 -- 2,171.20 claimed
from the supplier against a bill of 1,699.20, and Trade Payables 472.00 in
debit. Both documents now read what has already come off the line from here,
so no more is claimed from a supplier than they billed. The buying twin of
``app/sales_return/billing.py`` (D-SELL-88).

**A receipt billed in parts.** A return raised off a goods receipt line names
no bill line, and the receipt line may have been billed by several. The bills
are taken **earliest first**, each for the units it billed that have not
already gone back. A return raised off a bill line takes that line's units
first, and where they have all gone back -- by a return off the receipt that
was placed there -- the rest come off the other bills of the same receipt
line, earliest first: the goods are the receipt's, whichever bill is named.
What went back before any bill reached it (``unbilled_quantity``, D-BUY-26)
claimed nothing and is placed nowhere.

**Placed once.** Where a return's units fell, and what they claimed there, is
decided when the return completes and stored
(``purchase_return_bill_placements``, D-PRC-73). Every reader takes a
completed return from those rows and never works it out again. It used to be
derived on every read with the returns raised off bill lines counted first,
so a later return naming the first bill's own line moved an earlier return
off the receipt onto the next bill, after it had been valued at the first
bill's price: its value did not fit there, and the first bill's line was
priced afresh as though nothing had come off it. Only returns that have not
completed are still derived -- on top of the stored rows, in the order they
were raised -- because nothing about them is final.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.debit_note.models import DebitNote, DebitNoteLine, DebitNoteStatus
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_return.models import (
    PurchaseReturn,
    PurchaseReturnBillPlacement,
    PurchaseReturnLine,
)

ZERO = Decimal("0")
_FOUR = Decimal("0.0001")

_BILL = "PURCHASE_INVOICE"
_RECEIPT = "GOODS_RECEIPT"
#: A bill in one of these has raised a payable.
_BILLED = ("APPROVED", "CLOSED")
#: A return in one of these has sent its goods back and claimed their value.
COMPLETED = ("COMPLETED", "CLOSED")
#: A return in one of these still claims the goods it names: all but a
#: cancelled one.
LIVE = ("DRAFT", "APPROVED", "COMPLETED", "CLOSED")


@dataclass(frozen=True, slots=True)
class BillLineClaims:
    """What has already come off one supplier bill line, before tax."""

    #: Billed units that returns sent back, in the bill line's own unit.
    returned_quantity: Decimal = ZERO
    #: What those returns claimed, before tax.
    returned_taxable: Decimal = ZERO
    #: What approved debit notes claimed, before tax.
    claimed_taxable: Decimal = ZERO


def billed_share(line: PurchaseReturnLine) -> Decimal:
    """Return the part of a return line that reverses a bill, as a fraction.

    What went back before billing (``unbilled_quantity``) raised no payable
    and took no input credit, so it claims nothing.
    """
    quantity = Decimal(str(line.current_return_quantity))
    if quantity <= ZERO:
        return Decimal("1")
    unbilled = min(Decimal(str(line.unbilled_quantity or ZERO)), quantity)
    return (quantity - unbilled) / quantity


def goods_billed(line: PurchaseInvoiceLine) -> Decimal:
    """Return what a bill line charged for its goods, before tax.

    Gross, less both discounts, plus the line's own charges: the base the
    bill handed the tax engine, and the one a debit note's cap reads.
    """
    return (
        Decimal(str(line.gross_amount))
        - Decimal(str(line.discount_amount))
        - Decimal(str(line.bill_discount_amount))
        + Decimal(str(line.charges_amount))
    ).quantize(_FOUR)


def charged_for(billed: PurchaseInvoiceLine, *, quantity: Decimal) -> Decimal:
    """Return what a bill line charged for some of its units, before tax.

    The goods and the line's own charges, by quantity: the most a return of
    those units can state, whatever it has typed (D-PRC-71).
    """
    units = Decimal(str(billed.current_invoice_quantity))
    if units <= ZERO or quantity <= ZERO:
        return ZERO
    return (goods_billed(billed) * min(quantity, units) / units).quantize(_FOUR)


def charging_bill_lines(
    session: Session, receipt_line_ids: Iterable[UUID]
) -> dict[UUID, list[PurchaseInvoiceLine]]:
    """Return the bill lines that charged each receipt line, earliest first.

    Every standing bill of the line, in the order they are netted: by the
    bill's date, then its number, then the line's. A receipt line nobody has
    billed has none.
    """
    ids = list(set(receipt_line_ids))
    found: dict[UUID, list[PurchaseInvoiceLine]] = defaultdict(list)
    if not ids:
        return found
    for line in session.scalars(
        select(PurchaseInvoiceLine)
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
        )
        .where(
            PurchaseInvoiceLine.source_document_type == _RECEIPT,
            PurchaseInvoiceLine.source_document_line_id.in_(ids),
            PurchaseInvoiceLine.is_deleted.is_(False),
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status.in_(_BILLED),
        )
        .order_by(
            PurchaseInvoice.invoice_date.asc(),
            PurchaseInvoice.invoice_number.asc(),
            PurchaseInvoiceLine.line_number.asc(),
        )
    ).all():
        found[line.source_document_line_id].append(line)
    return found


def _debit_notes(
    session: Session, bill_line_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """Sum what approved debit notes claimed on each bill line, before tax."""
    return {
        line_id: Decimal(str(total))
        for line_id, total in session.execute(
            select(
                DebitNoteLine.purchase_invoice_line_id,
                func.coalesce(func.sum(DebitNoteLine.taxable_amount), 0),
            )
            .join(DebitNote, DebitNote.id == DebitNoteLine.debit_note_id)
            .where(
                DebitNoteLine.purchase_invoice_line_id.in_(list(bill_line_ids)),
                DebitNoteLine.is_deleted.is_(False),
                DebitNote.is_deleted.is_(False),
                # Approval is what posts; a draft has claimed nothing yet.
                DebitNote.status == DebitNoteStatus.APPROVED.value,
            )
            .group_by(DebitNoteLine.purchase_invoice_line_id)
        ).all()
    }


def _pending_returns(
    session: Session,
    *,
    source_type: str,
    source_line_ids: Sequence[UUID],
    states: Sequence[str],
    exclude_return_id: UUID | None,
    ahead_of: tuple[date, str] | None = None,
) -> list[tuple[tuple[date, str, int, str], PurchaseReturnLine, bool]]:
    """Return the lines still to be placed, each with its place in line.

    A completed return is read from its stored placements, so what is asked
    for here is the returns short of that -- and a completed line with no
    stored row, which is one written straight into the store without
    completing through the service (sample data does), counted as it always
    was. The key orders the lines as they were raised: by the return's
    date, its number, then the line's.

    Args:
        session: The firm's session.
        source_type: The kind of document the lines were raised off.
        source_line_ids: Its lines.
        states: The states in which a return counts.
        exclude_return_id: The return being priced or completed.
        ahead_of: That return's own date and number. Of the returns not yet
            completed, only those raised **before** it are given: the ones
            raised after it are placed after it, and say nothing about what
            it is worth (D-PRC-81).

    Returns:
        Each line with its key and whether its return has completed.

    """
    if not states or not source_line_ids:
        return []
    placed = (
        select(PurchaseReturnBillPlacement.id)
        .where(
            PurchaseReturnBillPlacement.purchase_return_line_id
            == PurchaseReturnLine.id,
            PurchaseReturnBillPlacement.is_deleted.is_(False),
        )
        .exists()
    )
    statement = (
        select(
            PurchaseReturnLine,
            PurchaseReturn.return_date,
            PurchaseReturn.return_number,
            PurchaseReturn.status,
        )
        .join(
            PurchaseReturn,
            PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
        )
        .where(
            PurchaseReturnLine.source_document_type == source_type,
            PurchaseReturnLine.source_document_line_id.in_(list(source_line_ids)),
            PurchaseReturnLine.is_deleted.is_(False),
            PurchaseReturn.is_deleted.is_(False),
            PurchaseReturn.status.in_(list(states)),
            or_(PurchaseReturn.status.not_in(COMPLETED), ~placed),
        )
    )
    if exclude_return_id is not None:
        statement = statement.where(PurchaseReturn.id != exclude_return_id)
    if ahead_of is not None:
        raised_on, number = ahead_of
        statement = statement.where(
            or_(
                PurchaseReturn.status.in_(COMPLETED),
                PurchaseReturn.return_date < raised_on,
                and_(
                    PurchaseReturn.return_date == raised_on,
                    PurchaseReturn.return_number < number,
                ),
            )
        )
    return [
        (
            (raised_on, number, line.line_number, str(line.id)),
            line,
            status in COMPLETED,
        )
        for line, raised_on, number, status in session.execute(statement).all()
    ]


def _left_to_bill(
    session: Session, receipt_line_ids: Iterable[UUID]
) -> dict[UUID, Decimal]:
    """Return what no bill has reached yet on some goods receipt lines."""
    # Imported here: the receipt's billing reads this module's models.
    from app.goods_receipt.billing import receipt_line_billing
    from app.goods_receipt.models import GoodsReceiptLine

    ids = list(set(receipt_line_ids))
    if not ids:
        return {}
    lines = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.id.in_(ids))
    ).all()
    return {
        line_id: position.left_to_bill
        for line_id, position in receipt_line_billing(session, lines).items()
    }


def _placed(
    session: Session,
    bill_line_ids: Sequence[UUID],
    *,
    exclude_return_id: UUID | None,
) -> list[tuple[UUID, Decimal, Decimal]]:
    """Return what completed returns placed on each bill line: units and value.

    The stored rows (D-PRC-73). A cancelled return's rows are removed when
    it is cancelled; the status is asked as well, so a row that outlived its
    return can never count.
    """
    statement = (
        select(
            PurchaseReturnBillPlacement.purchase_invoice_line_id,
            func.coalesce(func.sum(PurchaseReturnBillPlacement.quantity), 0),
            func.coalesce(func.sum(PurchaseReturnBillPlacement.taxable_amount), 0),
        )
        .join(
            PurchaseReturn,
            PurchaseReturn.id == PurchaseReturnBillPlacement.purchase_return_id,
        )
        .where(
            PurchaseReturnBillPlacement.purchase_invoice_line_id.in_(
                list(bill_line_ids)
            ),
            PurchaseReturnBillPlacement.is_deleted.is_(False),
            PurchaseReturn.is_deleted.is_(False),
            PurchaseReturn.status.in_(COMPLETED),
        )
        .group_by(PurchaseReturnBillPlacement.purchase_invoice_line_id)
    )
    if exclude_return_id is not None:
        statement = statement.where(PurchaseReturn.id != exclude_return_id)
    return [
        (line_id, Decimal(str(units)), Decimal(str(value)))
        for line_id, units, value in session.execute(statement).all()
    ]


def placing_order(
    named: PurchaseInvoiceLine, family: Sequence[PurchaseInvoiceLine]
) -> list[PurchaseInvoiceLine]:
    """Return the bill lines a return off a bill line takes its units from.

    The line it names first; then the other standing bills of the same
    receipt line, earliest first, for units the named line no longer holds
    because a return off the receipt was placed on it.
    """
    return [named, *(line for line in family if line.id != named.id)]


def bill_line_claims(
    session: Session,
    bill_lines: Iterable[PurchaseInvoiceLine],
    *,
    bill_returns: Sequence[str] = LIVE,
    receipt_returns: Sequence[str] = LIVE,
    exclude_return_id: UUID | None = None,
    ahead_of: tuple[date, str] | None = None,
) -> dict[UUID, BillLineClaims]:
    """Return what returns and debit notes have already taken off bill lines.

    **Debit notes** once approved, which is when one posts. **Completed
    returns** from where they were placed when they completed, by either
    route (D-PRC-73). **Returns not yet completed** -- and a completed line
    nothing was stored for -- are placed here, on top of those, in the
    order they were raised: one off a bill line on that
    line first, one off a goods receipt line on the bills of that line
    earliest first (see the module's note). Only the billed part of a return
    counts: a return off a receipt that has not completed is set first
    against what no bill has reached, as its completion will set it.

    **One order, whichever return asks** (D-PRC-81). The return being priced
    or completed takes its own place in that order -- after the open returns
    raised before it, ahead of the ones raised after. It used to be placed
    after *every* other open return, so each of two open returns took the
    other to be ahead of it: both were valued on the second bill, the first
    bill's units were claimed by neither, and the one completed first was
    refused for a debit note nobody had approved.

    Args:
        session: The firm's session.
        bill_lines: The bill lines asked about.
        bill_returns: The states in which a return raised off the bill line
            counts. Every live one for a return being priced, drafts
            included, so two returns of one line cannot both take the same
            remaining worth.
        receipt_returns: The same for a return raised off the receipt line.
            A debit note's cap asks for completed ones only: until a return
            completes, how much of it reverses a bill is not yet decided.
        exclude_return_id: A return being priced or completed, whose own
            lines are not "already".
        ahead_of: That return's date and number: of the open returns, only
            those raised before it count. None counts every one, which is
            what a debit note and a bill's cancel ask.

    Returns:
        One entry per bill line given, by its id.

    """
    asked = {line.id: line for line in bill_lines}
    if not asked:
        return {}
    quantity, taxable, claimed, _ = _derive(
        session,
        asked,
        bill_returns=bill_returns,
        receipt_returns=receipt_returns,
        exclude_return_id=exclude_return_id,
        ahead_of=ahead_of,
    )
    return {
        line_id: BillLineClaims(
            returned_quantity=quantity[line_id].quantize(_FOUR),
            returned_taxable=taxable[line_id].quantize(_FOUR),
            claimed_taxable=claimed.get(line_id, ZERO).quantize(_FOUR),
        )
        for line_id in asked
    }


def _derive(
    session: Session,
    asked: dict[UUID, PurchaseInvoiceLine],
    *,
    bill_returns: Sequence[str],
    receipt_returns: Sequence[str],
    exclude_return_id: UUID | None,
    ahead_of: tuple[date, str] | None = None,
) -> tuple[
    dict[UUID, Decimal],
    dict[UUID, Decimal],
    dict[UUID, Decimal],
    list[tuple[UUID, PurchaseInvoiceLine, Decimal, Decimal]],
]:
    """Work out what stands against some bill lines, and whose it is.

    The reading behind `bill_line_claims`, kept whole so the question "which
    returns rest on this bill" is answered by the same placing and can never
    disagree with it (D-PRC-80).

    Returns:
        Units and value returned per bill line, what debit notes claimed
        per bill line, and -- for the returns placed here and not read from
        stored rows -- each return with a bill line its units fell on, the
        units and what they claim there.

    """
    # Placing a receipt's returns needs every bill of the receipt line, not
    # only the ones asked about.
    families = charging_bill_lines(
        session,
        (
            line.source_document_line_id
            for line in asked.values()
            if line.source_document_type == _RECEIPT
            and line.source_document_line_id is not None
        ),
    )
    every = dict(asked)
    for family in families.values():
        for line in family:
            every.setdefault(line.id, line)
    quantity: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    taxable: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for line_id, units, value in _placed(
        session, list(every), exclude_return_id=exclude_return_id
    ):
        quantity[line_id] += units
        taxable[line_id] += value
    claimed = _debit_notes(session, list(every))
    waiting = _pending_returns(
        session,
        source_type=_BILL,
        source_line_ids=list(every),
        states=bill_returns,
        exclude_return_id=exclude_return_id,
        ahead_of=ahead_of,
    ) + _pending_returns(
        session,
        source_type=_RECEIPT,
        source_line_ids=list(families),
        states=receipt_returns,
        exclude_return_id=exclude_return_id,
        ahead_of=ahead_of,
    )
    # A return off a receipt that has not completed has no split yet: its
    # completion will set it first against what no bill has reached
    # (D-BUY-26), so that is where it is taken to fall here. Counted as
    # billed whole, an open return of an unbilled unit took a unit of the
    # bill, and a return of that bill's own line was valued a unit short.
    unbilled_left = _left_to_bill(
        session,
        (
            back.source_document_line_id
            for _, back, completed in waiting
            if not completed and back.source_document_type == _RECEIPT
        ),
    )
    fell: list[tuple[UUID, PurchaseInvoiceLine, Decimal, Decimal]] = []
    for _, back, completed in sorted(waiting, key=lambda item: item[0]):
        share = billed_share(back)
        returned = Decimal(str(back.current_return_quantity))
        if not completed and back.source_document_type == _RECEIPT and returned > ZERO:
            still_open = unbilled_left.get(back.source_document_line_id, ZERO)
            unbilled = min(returned, max(still_open, ZERO))
            unbilled_left[back.source_document_line_id] = still_open - unbilled
            share = (returned - unbilled) / returned
        units = returned * share
        if units <= ZERO:
            continue
        worth = (Decimal(str(back.net_amount)) - Decimal(str(back.tax_amount))) * share
        last: PurchaseInvoiceLine | None
        if back.source_document_type == _BILL:
            named = every[back.source_document_line_id]
            family = (
                families.get(named.source_document_line_id, [])
                if named.source_document_type == _RECEIPT
                else []
            )
            order = placing_order(named, family)
            last = named
        else:
            order = families[back.source_document_line_id]
            last = order[-1] if order else None
        placed = place_on_bills(order, units, returned=quantity)
        # More sent back than the standing bills hold -- a bill was
        # cancelled since. The rest stays with the bill named, or the last
        # of the receipt's, so the value is never lost from the count.
        rest = units - sum((part for _, part in placed), ZERO)
        if rest > ZERO and last is not None:
            placed.append((last, rest))
        # Its value follows the units, and no more to one bill than that
        # bill was still worth while another has room: which is how the
        # return was priced.
        limits = [
            still_worth(
                line,
                BillLineClaims(
                    returned_quantity=quantity[line.id],
                    returned_taxable=taxable[line.id],
                    claimed_taxable=claimed.get(line.id, ZERO),
                ),
                quantity=part,
            )
            for line, part in placed
        ]
        shares = share_out(
            worth,
            [(part, limit) for (_, part), limit in zip(placed, limits, strict=True)],
        )
        for (line, part), value in zip(placed, shares, strict=True):
            quantity[line.id] += part
            taxable[line.id] += value
            fell.append((back.purchase_return_id, line, part, value))
    return quantity, taxable, claimed, fell


@dataclass(frozen=True, slots=True)
class Standing:
    """One document that stands against a supplier bill line."""

    #: "debit note" or "purchase return".
    kind: str
    number: str
    purchase_invoice_id: UUID
    #: What it claims on the bill line, before tax.
    taxable: Decimal


def standing_against(
    session: Session,
    bill_lines: Iterable[PurchaseInvoiceLine],
    *,
    exclude_return_id: UUID,
    ahead_of: tuple[date, str],
) -> list[Standing]:
    """Name what stands against some bill lines ahead of one return.

    For the refusal of a return that no longer fits its bill (D-PRC-81):
    the approved debit notes on those lines, the completed returns placed on
    them, and the open returns raised before this one that would be placed
    on them -- exactly what `bill_line_claims` counted against it. One of
    them is what changed since the return was priced.
    """
    asked = {line.id: line for line in bill_lines}
    if not asked:
        return []
    totals: dict[tuple[str, str, UUID], Decimal] = defaultdict(lambda: ZERO)
    for number, line_id, value in session.execute(
        select(
            DebitNote.debit_note_number,
            DebitNoteLine.purchase_invoice_line_id,
            func.coalesce(func.sum(DebitNoteLine.taxable_amount), 0),
        )
        .join(DebitNote, DebitNote.id == DebitNoteLine.debit_note_id)
        .where(
            DebitNoteLine.purchase_invoice_line_id.in_(list(asked)),
            DebitNoteLine.is_deleted.is_(False),
            DebitNote.is_deleted.is_(False),
            DebitNote.status == DebitNoteStatus.APPROVED.value,
        )
        .group_by(DebitNote.debit_note_number, DebitNoteLine.purchase_invoice_line_id)
    ).all():
        bill_id = asked[line_id].purchase_invoice_id
        totals[("debit note", number, bill_id)] += Decimal(str(value))
    for number, line_id, value in session.execute(
        select(
            PurchaseReturn.return_number,
            PurchaseReturnBillPlacement.purchase_invoice_line_id,
            func.coalesce(func.sum(PurchaseReturnBillPlacement.taxable_amount), 0),
        )
        .join(
            PurchaseReturn,
            PurchaseReturn.id == PurchaseReturnBillPlacement.purchase_return_id,
        )
        .where(
            PurchaseReturnBillPlacement.purchase_invoice_line_id.in_(list(asked)),
            PurchaseReturnBillPlacement.is_deleted.is_(False),
            PurchaseReturn.is_deleted.is_(False),
            PurchaseReturn.status.in_(COMPLETED),
            PurchaseReturn.id != exclude_return_id,
        )
        .group_by(
            PurchaseReturn.return_number,
            PurchaseReturnBillPlacement.purchase_invoice_line_id,
        )
    ).all():
        bill_id = asked[line_id].purchase_invoice_id
        totals[("purchase return", number, bill_id)] += Decimal(str(value))
    *_, fell = _derive(
        session,
        asked,
        bill_returns=LIVE,
        receipt_returns=LIVE,
        exclude_return_id=exclude_return_id,
        ahead_of=ahead_of,
    )
    open_ones = {return_id for return_id, line, _, _ in fell if line.id in asked}
    numbers = (
        dict(
            session.execute(
                select(PurchaseReturn.id, PurchaseReturn.return_number).where(
                    PurchaseReturn.id.in_(open_ones)
                )
            )
            .tuples()
            .all()
        )
        if open_ones
        else {}
    )
    for return_id, line, _, value in fell:
        if line.id in asked:
            key = ("purchase return", numbers[return_id], line.purchase_invoice_id)
            totals[key] += value
    return [
        Standing(kind=kind, number=number, purchase_invoice_id=bill_id, taxable=value)
        for (kind, number, bill_id), value in sorted(
            totals.items(), key=lambda item: (item[0][0], item[0][1], str(item[0][2]))
        )
    ]


def returns_resting_on(session: Session, *, invoice_id: UUID) -> set[UUID]:
    """Return the purchase returns that have taken units of one supplier bill.

    What stops a bill being cancelled (D-PRC-80). A return raised off a
    goods receipt names no bill, and one raised off another bill of the same
    receipt line spills onto this one once its own line's units are back;
    both claim from the supplier what **this** bill charged. Asked only of
    the returns that name the bill, the cancel went through under them: the
    claim stood with no bill behind it, the supplier's credit could be spent
    on another bill, and the input tax was reversed twice. So three kinds
    rest on a bill, the buying twin of the sales side's rule (D-PRC-77):

    - a live return with a line raised off one of the bill's own lines;
    - a completed return whose units were **placed** on it
      (``purchase_return_bill_placements``), whichever document it names;
    - a return not yet completed whose units would be placed on it as the
      bills stand, by the same placing that prices it.

    A return of the same receipt that took nothing of this bill is not
    here: one that went back before any bill reached its goods, one placed
    on the receipt's other bills -- and any return off the receipt where
    the bill is a draft, which has charged nothing.
    """
    lines = list(
        session.scalars(
            select(PurchaseInvoiceLine).where(
                PurchaseInvoiceLine.purchase_invoice_id == invoice_id,
                PurchaseInvoiceLine.is_deleted.is_(False),
            )
        ).all()
    )
    if not lines:
        return set()
    line_ids = [line.id for line in lines]
    resting = set(
        session.scalars(
            select(PurchaseReturnLine.purchase_return_id)
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
            )
            .where(
                PurchaseReturnLine.source_document_type == _BILL,
                PurchaseReturnLine.source_document_line_id.in_(line_ids),
                PurchaseReturnLine.is_deleted.is_(False),
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(LIVE),
            )
        ).all()
    )
    resting |= set(
        session.scalars(
            select(PurchaseReturnBillPlacement.purchase_return_id)
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnBillPlacement.purchase_return_id,
            )
            .where(
                PurchaseReturnBillPlacement.purchase_invoice_line_id.in_(line_ids),
                PurchaseReturnBillPlacement.is_deleted.is_(False),
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(COMPLETED),
            )
        ).all()
    )
    *_, fell = _derive(
        session,
        {line.id: line for line in lines},
        bill_returns=LIVE,
        receipt_returns=LIVE,
        exclude_return_id=None,
    )
    resting |= {
        return_id
        for return_id, line, _, _ in fell
        if line.purchase_invoice_id == invoice_id
    }
    return resting


def share_out(
    amount: Decimal, parts: Sequence[tuple[Decimal, Decimal]]
) -> list[Decimal]:
    """Share a return line's value over the bill lines its units were placed on.

    By the units on each, and never more to one than it was still worth
    while another has room; what no bill line has room for stays with the
    last, so the whole amount is always counted.

    Args:
        amount: The value to share, before tax.
        parts: Per bill line, the units placed on it and what they were
            still worth.

    Returns:
        One share per part, in order, adding up to ``amount``.

    """
    whole = sum((units for units, _ in parts), ZERO)
    if not parts or whole <= ZERO:
        return [ZERO for _ in parts]
    shares = [min(amount * units / whole, limit) for units, limit in parts]
    left = amount - sum(shares, ZERO)
    for index, (_, limit) in enumerate(parts):
        if left <= ZERO:
            break
        more = min(limit - shares[index], left)
        if more > ZERO:
            shares[index] += more
            left -= more
    if left > ZERO:
        shares[-1] += left
    return shares


def place_on_bills(
    family: Sequence[PurchaseInvoiceLine],
    units: Decimal,
    *,
    returned: dict[UUID, Decimal],
) -> list[tuple[PurchaseInvoiceLine, Decimal]]:
    """Share units going back over the bills of their receipt line.

    Earliest bill first, each for what it billed less what has already gone
    back off it. Units no standing bill holds are placed nowhere.

    Args:
        family: The bill lines of one receipt line, earliest first.
        units: The billed units going back.
        returned: Units already back, by bill line id.

    Returns:
        The bill lines taken from, each with its part.

    """
    placed: list[tuple[PurchaseInvoiceLine, Decimal]] = []
    left = units
    for line in family:
        if left <= ZERO:
            break
        room = Decimal(str(line.current_invoice_quantity)) - returned.get(line.id, ZERO)
        part = min(left, room)
        if part <= ZERO:
            continue
        placed.append((line, part))
        left -= part
    return placed


def still_worth(
    billed: PurchaseInvoiceLine,
    claims: BillLineClaims,
    *,
    quantity: Decimal,
    taken_quantity: Decimal = ZERO,
    taken_taxable: Decimal = ZERO,
) -> Decimal:
    """Return what some units of a bill line are still worth, before tax.

    What the line charged for its goods, less what debit notes and earlier
    returns have taken off it, spread over the units still held: 2 boxes
    billed 1,440.00 with 400.00 claimed are worth 520.00 each, and once one
    has gone back the other is worth all of what is left. So the returns of
    a line and its debit notes add up to what it billed and no more,
    whichever came first.

    Args:
        billed: The bill line.
        claims: What has already come off it.
        quantity: The units going back, in the bill line's unit.
        taken_quantity: Units earlier lines of the same return send back.
        taken_taxable: What those earlier lines claim.

    Returns:
        The most these units may claim, never below nothing.

    """
    left = (
        goods_billed(billed)
        - claims.claimed_taxable
        - claims.returned_taxable
        - taken_taxable
    )
    units = (
        Decimal(str(billed.current_invoice_quantity))
        - claims.returned_quantity
        - taken_quantity
    )
    if left <= ZERO or units <= ZERO or quantity <= ZERO:
        return ZERO
    return (left * min(quantity, units) / units).quantize(_FOUR)


@dataclass(frozen=True, slots=True)
class BilledWorth:
    """What the billed units of one return line are still worth."""

    #: The bill lines the units were placed on, each with its part and what
    #: that part is still worth.
    parts: tuple[tuple[PurchaseInvoiceLine, Decimal, Decimal], ...]
    #: True where a bill line among them carries an approved debit note:
    #: what the units are still worth is then less than they were billed at.
    claimed_against: bool
    #: What the bills charged for those units, goods and the lines' own
    #: charges, before anything was taken off them (D-PRC-71).
    charged: Decimal = ZERO

    @property
    def quantity(self) -> Decimal:
        """Return how many of the units a standing bill holds."""
        return sum((part for _, part, _ in self.parts), ZERO)

    @property
    def amount(self) -> Decimal:
        """Return the most those units may claim, before tax."""
        return sum((worth for _, _, worth in self.parts), ZERO)


class BillWorths:
    """Read, for one return, what its lines' bills are still worth.

    One per pricing or completion of a return. It remembers what earlier
    lines of the same return took, so two lines sending back the same bill
    line's goods share what is left of it.
    """

    def __init__(
        self,
        session: Session,
        *,
        return_id: UUID,
        raised: tuple[date, str] | None = None,
    ) -> None:
        """Bind the session and the return whose own lines are not "already".

        ``raised`` is the return's date and number, its place among the
        returns not yet completed: only those raised before it are counted
        ahead of it (D-PRC-81).
        """
        self._session = session
        self._return_id = return_id
        self._raised = raised
        self._claims: dict[UUID, BillLineClaims] = {}
        self._taken: dict[UUID, tuple[Decimal, Decimal]] = defaultdict(
            lambda: (ZERO, ZERO)
        )

    def bill_lines(
        self, source_type: str, source_line_id: UUID
    ) -> list[PurchaseInvoiceLine]:
        """Return the bill lines that charged a return's source line.

        The bill line itself for a return raised off a bill; the standing
        bills of the receipt line, earliest first, for one raised off a
        goods receipt; none for one raised off an order.
        """
        if source_type == _BILL:
            line = self._session.get(PurchaseInvoiceLine, source_line_id)
            return [] if line is None else [line]
        if source_type != _RECEIPT:
            return []
        return charging_bill_lines(self._session, [source_line_id])[source_line_id]

    def placing(
        self, source_type: str, source_line_id: UUID
    ) -> list[PurchaseInvoiceLine]:
        """Return the bill lines a return line's units are placed on, in order.

        As `bill_lines`, and for a return raised off a bill line the other
        standing bills of the same receipt line after it: where the named
        line's units have already gone back off the receipt, the rest come
        off those (D-PRC-73).
        """
        named = self.bill_lines(source_type, source_line_id)
        if source_type != _BILL or not named:
            return named
        line = named[0]
        receipt_line_id = line.source_document_line_id
        if line.source_document_type != _RECEIPT or receipt_line_id is None:
            return named
        family = charging_bill_lines(self._session, [receipt_line_id])
        return placing_order(line, family[receipt_line_id])

    def hold(self, bill_lines: Iterable[PurchaseInvoiceLine]) -> None:
        """Take the bill lines before reading what is left of them to claim.

        What a line is still worth is a sum over debit notes and other
        returns, which no row version guards. A debit note takes the same
        lock before its own cap, so the two wait for each other.
        """
        ids = sorted({line.id for line in bill_lines}, key=str)
        if ids:
            self._session.execute(
                select(PurchaseInvoiceLine.id)
                .where(PurchaseInvoiceLine.id.in_(ids))
                .order_by(PurchaseInvoiceLine.id)
                .with_for_update()
            )

    def worth(
        self,
        bill_lines: Sequence[PurchaseInvoiceLine],
        quantity: Decimal,
        *,
        exact: Decimal | None = None,
    ) -> BilledWorth:
        """Return what these billed units are still worth on their bills.

        Args:
            bill_lines: The bill lines that charged the units, earliest first.
            quantity: The billed units going back, as the line stores them.
            exact: The same units before rounding, for a line typed in
                another unit: seven pieces of a box at 720.00 are worth
                420.00, and the 0.5833 of a box stored is worth 419.98.

        Returns:
            The bill lines the units fall on, with what they are worth.

        """
        scale = Decimal("1")
        if exact is not None and quantity > ZERO:
            scale = exact / quantity
        missing = [line for line in bill_lines if line.id not in self._claims]
        if missing:
            self._claims.update(
                bill_line_claims(
                    self._session,
                    missing,
                    exclude_return_id=self._return_id,
                    ahead_of=self._raised,
                )
            )
        returned = {
            line.id: self._claims[line.id].returned_quantity + self._taken[line.id][0]
            for line in bill_lines
        }
        parts = []
        charged = ZERO
        for line, part in place_on_bills(bill_lines, quantity, returned=returned):
            taken_quantity, taken_taxable = self._taken[line.id]
            parts.append(
                (
                    line,
                    part,
                    still_worth(
                        line,
                        self._claims[line.id],
                        quantity=part * scale,
                        taken_quantity=taken_quantity,
                        taken_taxable=taken_taxable,
                    ),
                )
            )
            charged += charged_for(line, quantity=part * scale)
        return BilledWorth(
            parts=tuple(parts),
            claimed_against=any(
                self._claims[line.id].claimed_taxable > ZERO for line, _, _ in parts
            ),
            charged=charged,
        )

    def take(
        self, worth: BilledWorth, taxable: Decimal
    ) -> list[tuple[PurchaseInvoiceLine, Decimal, Decimal]]:
        """Record what a line of this return claims off the bills it reverses.

        Shared over the bill lines by the units placed on each, and never
        more on one than it was still worth while another has room.

        Returns:
            Where the line fell: each bill line with the units placed on it
            and what they claim there, to the fourth place and adding up to
            ``taxable`` -- what completion stores (D-PRC-73).

        """
        shares = share_out(taxable, [(part, limit) for _, part, limit in worth.parts])
        placed: list[tuple[PurchaseInvoiceLine, Decimal, Decimal]] = []
        for (line, part, _), share in zip(worth.parts, shares, strict=True):
            taken_quantity, taken_taxable = self._taken[line.id]
            self._taken[line.id] = (taken_quantity + part, taken_taxable + share)
            placed.append((line, part, share.quantize(_FOUR)))
        if placed:
            # The rounding of the parts goes on the last, so they add up.
            line, part, share = placed[-1]
            residual = taxable.quantize(_FOUR) - sum(
                (value for _, _, value in placed), ZERO
            )
            placed[-1] = (line, part, share + residual)
        return placed


__all__ = [
    "COMPLETED",
    "LIVE",
    "BillLineClaims",
    "BillWorths",
    "BilledWorth",
    "Standing",
    "bill_line_claims",
    "billed_share",
    "charged_for",
    "charging_bill_lines",
    "goods_billed",
    "place_on_bills",
    "placing_order",
    "returns_resting_on",
    "share_out",
    "standing_against",
    "still_worth",
]
