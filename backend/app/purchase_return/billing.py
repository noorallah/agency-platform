"""What a supplier bill line is still worth to claim against (D-PRC-67).

A purchase return and a debit note both take value off a supplier bill line,
and neither read the other: a bill of 1,699.20 took a price-difference debit
note of 472.00 and was then returned in full for 1,699.20 -- 2,171.20 claimed
from the supplier against a bill of 1,699.20, and Trade Payables 472.00 in
debit. Both documents now read what has already come off the line from here,
so no more is claimed from a supplier than they billed. The buying twin of
``app/sales_return/billing.py`` (D-SELL-88).

**A receipt billed in parts.** A return raised off a goods receipt line names
no bill line, and the receipt line may have been billed by several. Nothing
stored says which bill charged the units going back, so it is decided here,
the same way on every read: the bills are taken **earliest first**, each for
the units it billed that have not already gone back. Earlier returns off the
receipt are placed by that rule before the one being asked about, in the order
they were raised. What went back before any bill reached it
(``unbilled_quantity``, D-BUY-26) claimed nothing and is placed nowhere.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.debit_note.models import DebitNote, DebitNoteLine, DebitNoteStatus
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

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


def _returns(
    session: Session,
    *,
    source_type: str,
    source_line_ids: Sequence[UUID],
    states: Sequence[str],
    exclude_return_id: UUID | None,
) -> list[PurchaseReturnLine]:
    """Return the return lines raised off these source lines, oldest first."""
    statement = (
        select(PurchaseReturnLine)
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
        )
        .order_by(
            PurchaseReturn.return_date.asc(),
            PurchaseReturn.return_number.asc(),
            PurchaseReturnLine.line_number.asc(),
        )
    )
    if exclude_return_id is not None:
        statement = statement.where(PurchaseReturn.id != exclude_return_id)
    return list(session.scalars(statement).all())


def bill_line_claims(
    session: Session,
    bill_lines: Iterable[PurchaseInvoiceLine],
    *,
    bill_returns: Sequence[str] = LIVE,
    receipt_returns: Sequence[str] = LIVE,
    exclude_return_id: UUID | None = None,
) -> dict[UUID, BillLineClaims]:
    """Return what returns and debit notes have already taken off bill lines.

    **Debit notes** once approved, which is when one posts. **Returns** by
    either route: raised on the bill line itself, or on the goods receipt
    line it billed, placed on the bills of that line earliest first (see the
    module's note). Only the billed part of a return counts.

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

    Returns:
        One entry per bill line given, by its id.

    """
    asked = {line.id: line for line in bill_lines}
    if not asked:
        return {}
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
    for back in _returns(
        session,
        source_type=_BILL,
        source_line_ids=list(every),
        states=bill_returns,
        exclude_return_id=exclude_return_id,
    ):
        quantity[back.source_document_line_id] += Decimal(
            str(back.current_return_quantity)
        )
        taxable[back.source_document_line_id] += Decimal(
            str(back.net_amount)
        ) - Decimal(str(back.tax_amount))
    claimed = _debit_notes(session, list(every))
    if families:
        for back in _returns(
            session,
            source_type=_RECEIPT,
            source_line_ids=list(families),
            states=receipt_returns,
            exclude_return_id=exclude_return_id,
        ):
            share = billed_share(back)
            units = Decimal(str(back.current_return_quantity)) * share
            if units <= ZERO:
                continue
            worth = (
                Decimal(str(back.net_amount)) - Decimal(str(back.tax_amount))
            ) * share
            family = families[back.source_document_line_id]
            placed = place_on_bills(family, units, returned=quantity)
            # More sent back than the standing bills hold -- a bill was
            # cancelled since. The rest stays with the last bill, so the
            # value is never lost from the count.
            rest = units - sum((part for _, part in placed), ZERO)
            if rest > ZERO and family:
                placed.append((family[-1], rest))
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
                [
                    (part, limit)
                    for (_, part), limit in zip(placed, limits, strict=True)
                ],
            )
            for (line, part), value in zip(placed, shares, strict=True):
                quantity[line.id] += part
                taxable[line.id] += value
    return {
        line_id: BillLineClaims(
            returned_quantity=quantity[line_id].quantize(_FOUR),
            returned_taxable=taxable[line_id].quantize(_FOUR),
            claimed_taxable=claimed.get(line_id, ZERO).quantize(_FOUR),
        )
        for line_id in asked
    }


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
    #: only then is there anything to net.
    claimed_against: bool

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

    def __init__(self, session: Session, *, return_id: UUID) -> None:
        """Bind the session and the return whose own lines are not "already"."""
        self._session = session
        self._return_id = return_id
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
        self, bill_lines: Sequence[PurchaseInvoiceLine], quantity: Decimal
    ) -> BilledWorth:
        """Return what these billed units are still worth on their bills."""
        missing = [line for line in bill_lines if line.id not in self._claims]
        if missing:
            self._claims.update(
                bill_line_claims(
                    self._session, missing, exclude_return_id=self._return_id
                )
            )
        returned = {
            line.id: self._claims[line.id].returned_quantity + self._taken[line.id][0]
            for line in bill_lines
        }
        parts = []
        for line, part in place_on_bills(bill_lines, quantity, returned=returned):
            taken_quantity, taken_taxable = self._taken[line.id]
            parts.append(
                (
                    line,
                    part,
                    still_worth(
                        line,
                        self._claims[line.id],
                        quantity=part,
                        taken_quantity=taken_quantity,
                        taken_taxable=taken_taxable,
                    ),
                )
            )
        return BilledWorth(
            parts=tuple(parts),
            claimed_against=any(
                self._claims[line.id].claimed_taxable > ZERO for line, _, _ in parts
            ),
        )

    def take(self, worth: BilledWorth, taxable: Decimal) -> None:
        """Record what a line of this return claims off the bills it reverses.

        Shared over the bill lines by the units placed on each, and never
        more on one than it was still worth while another has room.
        """
        shares = share_out(taxable, [(part, limit) for _, part, limit in worth.parts])
        for (line, part, _), share in zip(worth.parts, shares, strict=True):
            taken_quantity, taken_taxable = self._taken[line.id]
            self._taken[line.id] = (taken_quantity + part, taken_taxable + share)


__all__ = [
    "COMPLETED",
    "LIVE",
    "BillLineClaims",
    "BillWorths",
    "BilledWorth",
    "bill_line_claims",
    "billed_share",
    "charging_bill_lines",
    "goods_billed",
    "place_on_bills",
    "share_out",
    "still_worth",
]
