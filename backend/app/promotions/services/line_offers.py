"""The rows naming what priced a sales line, built once for two documents (L7).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md``, sections 3.9 and 6 step 2.
The order and the quotation each keep a table of one shape
(``LineOfferMixin``); what goes in it is decided here, so the two cannot drift.

A line's APPLIED rows add up to its ``discount_amount`` and to the free goods
its offers gave. The promotion engine answers each offer's share
(``PromotionLineShare``); this module only decides which of them reached the
line, because the shared discount rule may have taken a typed figure, a price
list or a standing rate instead -- in which case the offers named still gave
their free goods, but took nothing off.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.utils.money import quantize_money
from app.core.utils.pricing import LineDiscount
from app.core.utils.quantities import at_quantity_scale, plain_quantity
from app.customers.models import CustomerGroup
from app.pricing.services.price_list_service import PriceListBreak, PriceListRef
from app.promotions.models.line_offer import LineOfferMixin
from app.promotions.schemas import (
    LineOfferResponse,
    OfferCandidate,
    OfferGives,
    PromotionApplication,
    PromotionLineShare,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")

#: The words a line's ``discount_source`` uses for a standing arrangement.
STANDING_SOURCES = frozenset({"price_list", "customer", "customer_group"})
#: The two states a row holds (design 3.9).
APPLIED = "APPLIED"
REFUSED = "REFUSED"
#: How long ``name`` may be on the row (``LineOfferMixin``).
_NAME_LENGTH = 120


@dataclass(frozen=True, slots=True)
class OfferRow:
    """The values of one row, before it is given a document and a line."""

    source: str
    code: str
    name: str
    discount_amount: Decimal = ZERO
    #: In **stock units**, as the column says: the line's own figure times
    #: the stock units one of its units holds.
    free_quantity: Decimal = ZERO
    promotion_id: UUID | None = None
    promotion_group_id: UUID | None = None
    price_list_id: UUID | None = None
    #: Put there by a person rather than by the server (L7 step 5).
    chosen: bool = False
    #: The free goods were given as a part share (L7 step 7).
    part_share: bool = False
    #: ``APPLIED``, or ``REFUSED`` for an arrangement the start applied and a
    #: person's choice passed over (L7 step 9): what it would have given.
    state: str = APPLIED

    @property
    def key(self) -> str:
        """Return the key a candidate and a choice name this arrangement by."""
        if self.promotion_group_id is not None:
            return str(self.promotion_group_id)
        if self.price_list_id is not None:
            return str(self.price_list_id)
        return {"customer": "CUSTOMER", "customer_group": "CUSTOMER_GROUP"}.get(
            self.source, self.code
        )


@dataclass(frozen=True, slots=True)
class StandingArrangement:
    """The customer's standing terms a line may have been priced at.

    Read once per document by the caller. ``price_list`` is asked per line,
    from what the resolver already loaded, so naming it costs no statement.
    """

    group_code: str | None = None
    group_name: str | None = None


def standing_arrangement(
    session: Session, group_id: UUID | None
) -> StandingArrangement:
    """Name the customer's segment for a line priced at its rate.

    The caller has just read the segment to learn its rate, so this is
    answered from the session's identity map rather than by a statement.
    """
    group = None if group_id is None else session.get(CustomerGroup, group_id)
    if group is None:
        return StandingArrangement()
    return StandingArrangement(group_code=group.code, group_name=group.name)


def line_offer_rows(
    *,
    shares: Sequence[PromotionLineShare],
    priced: LineDiscount,
    engine_free: bool,
    stock_factor: Decimal,
    price_list: PriceListRef | None = None,
    standing: StandingArrangement | None = None,
) -> list[OfferRow]:
    """Return the APPLIED rows of one line the customer asked for.

    Args:
        shares: What each offer gave the line, in the order applied.
        priced: The shared rule's answer for the line. An offer's discount
            reached the line only where its ``source`` is ``promotion``.
        engine_free: True where the line's free goods are the engine's --
            nobody typed a free quantity -- so the offers' free goods stand.
        stock_factor: The stock units one of the line's units holds.
        price_list: The list that answered, where ``source`` is
            ``price_list``.
        standing: The customer's segment, where ``source`` is
            ``customer_group``.

    A typed, inherited or absent discount names no arrangement: a person
    deciding is not an arrangement.

    """
    rows: list[OfferRow] = []
    takes = priced.source == "promotion"
    for share in shares:
        discount = share.discount_amount if takes else ZERO
        free = share.free_quantity if engine_free else ZERO
        if discount <= ZERO and free <= ZERO:
            continue
        rows.append(
            OfferRow(
                source="promotion",
                code=share.code,
                name=share.name[:_NAME_LENGTH],
                discount_amount=discount,
                free_quantity=at_quantity_scale(free * stock_factor),
                promotion_id=share.promotion_id,
                promotion_group_id=share.promotion_group_id,
                part_share=share.part_share and free > ZERO,
            )
        )
    if takes:
        _settle_residual(rows, priced.amount)
    elif priced.source == "price_list" and price_list is not None:
        rows.append(
            OfferRow(
                source="price_list",
                code=price_list.code,
                name=price_list.name[:_NAME_LENGTH],
                discount_amount=priced.amount,
                price_list_id=price_list.id,
            )
        )
    elif priced.source == "customer":
        rows.append(
            OfferRow(
                source="customer",
                code="CUSTOMER",
                name="Standing rate",
                discount_amount=priced.amount,
            )
        )
    elif priced.source == "customer_group" and standing is not None:
        rows.append(
            OfferRow(
                source="customer_group",
                code=standing.group_code or "CUSTOMER_GROUP",
                name=(standing.group_name or "Customer group")[:_NAME_LENGTH],
                discount_amount=priced.amount,
            )
        )
    return rows


def gift_offer_rows(
    application: PromotionApplication | None,
    *,
    free_quantity: Decimal,
    stock_factor: Decimal,
) -> list[OfferRow]:
    """Return the row of a gift line: the offer that gave it, and nothing else."""
    if application is None or free_quantity <= ZERO:
        return []
    return [
        OfferRow(
            source="promotion",
            code=application.code,
            name=application.name[:_NAME_LENGTH],
            free_quantity=at_quantity_scale(free_quantity * stock_factor),
            promotion_id=application.promotion_id,
            promotion_group_id=application.promotion_group_id,
        )
    ]


def bill_offer_rows(
    shares: Sequence[PromotionLineShare], *, applies: bool
) -> list[OfferRow]:
    """Return the rows of the offers on the whole bill, with a null line.

    ``applies`` is False where a person typed the bill discount: the offers'
    figure was never used, so nothing is named.
    """
    if not applies:
        return []
    return [
        OfferRow(
            source="promotion",
            code=share.code,
            name=share.name[:_NAME_LENGTH],
            discount_amount=share.discount_amount,
            promotion_id=share.promotion_id,
            promotion_group_id=share.promotion_group_id,
        )
        for share in shares
        if share.discount_amount > ZERO
    ]


def rewrite_offer_rows(
    session: Session,
    model: type[Any],
    *,
    document_column: str,
    line_column: str,
    document_id: UUID,
    firm_id: UUID,
    actor_id: UUID,
    rows: Sequence[tuple[UUID | None, Sequence[OfferRow]]],
) -> None:
    """Replace a document's rows: one delete, then each line's in sequence.

    Nothing refers to a row by id, so a line priced again is simply written
    again. Flushes and never commits: the caller is mid-document.
    """
    session.execute(
        delete(model)
        .where(getattr(model, document_column) == document_id)
        .execution_options(synchronize_session=False)
    )
    for line_id, line_rows in rows:
        for sequence, item in enumerate(line_rows, start=1):
            session.add(
                model(
                    **{document_column: document_id, line_column: line_id},
                    firm_id=firm_id,
                    sequence=sequence,
                    source=item.source,
                    promotion_id=item.promotion_id,
                    promotion_group_id=item.promotion_group_id,
                    price_list_id=item.price_list_id,
                    code=item.code,
                    name=item.name,
                    state=item.state,
                    chosen=item.chosen,
                    discount_amount=item.discount_amount,
                    free_quantity=item.free_quantity,
                    part_share=item.part_share,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
    session.flush()


def offers_by_line[RowT: LineOfferMixin](
    rows: Sequence[RowT], *, line_of: Callable[[RowT], UUID | None]
) -> dict[UUID | None, list[LineOfferResponse]]:
    """Group a document's rows by line, in sequence; the bill's under None."""
    grouped: dict[UUID | None, list[LineOfferResponse]] = {}
    for row in sorted(rows, key=lambda item: item.sequence):
        grouped.setdefault(line_of(row), []).append(
            LineOfferResponse.model_validate(row)
        )
    return grouped


#: Why a standing arrangement is not the one in the price shown, by the
#: source of the discount that is.
_PASSED_OVER = {
    "promotion": "An offer gives this line its discount.",
    "price_list": "The price list gives this line its discount.",
    "customer": "The customer's standing rate gives this line its discount.",
    "customer_group": "The customer's group rate gives this line its discount.",
    "inherited": "The line keeps the discount of the document it continues.",
}
#: The sources a person typed: every arrangement is passed over by them.
_TYPED = frozenset({"amount", "percent"})
_TYPED_REASON = "A discount is typed on this line."


def line_candidates(
    *,
    offered: Sequence[OfferCandidate],
    rows: Sequence[OfferRow],
    priced: LineDiscount,
    gross: Decimal,
    price_list: PriceListRef | None = None,
    price_list_percent: Decimal | None = None,
    customer_percent: Decimal | None = None,
    group_percent: Decimal | None = None,
    standing: StandingArrangement | None = None,
    quantity: Decimal | None = None,
    stock_factor: Decimal = Decimal("1"),
    next_break: PriceListBreak | None = None,
) -> list[OfferCandidate]:
    """Return what one line could take: its offers, then its standing terms (L7).

    ``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` sections 3.1 and 3.2.

    Args:
        offered: The engine's candidates for the line, in the order applied.
        rows: The line's rows (`line_offer_rows`): an offer is in the price
            shown only where it has an APPLIED one, so the list and the rows
            the document keeps cannot disagree. REFUSED rows are left out.
        priced: The shared rule's answer for the line.
        gross: The line's value before discount, to value each standing rate.
        price_list: The list whose break the line's quantity takes.
        price_list_percent: That list's rate there; None where it names none.
        customer_percent: The customer's standing rate; None where unset.
        group_percent: The customer's group's rate; None where unset.
        standing: The group's code and name.
        quantity: The quantity typed on the line, in its own unit: the
            window of the "buy N more" hint (step 4). None gives no hint.
        stock_factor: The stock units one of the line's units holds.
        next_break: The price list's next break above the line's quantity
            (`PriceListResolver.next_break`), for its hint.

    Nothing is chosen in this step: ``chosen`` stays False throughout. Each
    standing rate is valued alone on the line's gross, as the shared rule
    would take it.

    """
    in_rows = {
        str(row.promotion_group_id)
        for row in rows
        if row.promotion_group_id and row.state == APPLIED
    }
    candidates: list[OfferCandidate] = []
    for item in offered:
        if item.applied and item.key not in in_rows:
            item = item.model_copy(
                update={
                    "applied": False,
                    "reason": (
                        _TYPED_REASON
                        if priced.source in _TYPED
                        else _PASSED_OVER.get(priced.source, "Not applied.")
                    ),
                }
            )
        candidates.append(item)
    if price_list is not None and price_list_percent is not None:
        candidates.append(
            _standing_candidate(
                key=str(price_list.id),
                source="price_list",
                code=price_list.code,
                name=price_list.name,
                percent=price_list_percent,
                gross=gross,
                priced=priced,
            )
        )
    if quantity is not None and next_break is not None and priced.source not in _TYPED:
        candidates = _with_break_hint(
            candidates,
            next_break=next_break,
            quantity=quantity,
            stock_factor=stock_factor,
            listed=price_list is not None and price_list_percent is not None,
        )
    if customer_percent is not None and customer_percent > ZERO:
        candidates.append(
            _standing_candidate(
                key="CUSTOMER",
                source="customer",
                code="CUSTOMER",
                name="Standing rate",
                percent=customer_percent,
                gross=gross,
                priced=priced,
            )
        )
    if group_percent is not None and group_percent > ZERO:
        group = standing or StandingArrangement()
        candidates.append(
            _standing_candidate(
                key="CUSTOMER_GROUP",
                source="customer_group",
                code=group.group_code or "CUSTOMER_GROUP",
                name=group.group_name or "Customer group",
                percent=group_percent,
                gross=gross,
                priced=priced,
            )
        )
    return candidates if quantity is None else nearest_hints(candidates, quantity)


#: How many hints a line shows at most (design section 3.6).
HINTS_PER_LINE = 2


def in_line_units(stock_shortfall: Decimal, stock_factor: Decimal) -> Decimal:
    """Return a shortfall in stock units as the line's own unit, rounded up.

    At the four places a quantity holds, and up rather than to the nearest:
    a hint that falls short of the break by a fraction earns nothing.
    """
    factor = stock_factor if stock_factor > ZERO else Decimal("1")
    return (stock_shortfall / factor).quantize(
        Decimal("0.0001"), rounding=ROUND_CEILING
    )


def nearest_hints(
    candidates: Sequence[OfferCandidate], quantity: Decimal
) -> list[OfferCandidate]:
    """Keep the line's two nearest hints within its window (L7 step 4).

    Section 3.6: a hint is shown where the shortfall is no more than the
    quantity typed, nearest first, two a line at most. A candidate past the
    window or the two keeps its place with the hint cleared, except one
    listed only for its hint -- never available, as a hint cannot be
    chosen -- which is dropped. Ties keep the list's order.
    """
    shown = sorted(
        (item.needs_more, at)
        for at, item in enumerate(candidates)
        if item.needs_more is not None and item.needs_more <= quantity
    )
    kept = {at for _, at in shown[:HINTS_PER_LINE]}
    result: list[OfferCandidate] = []
    for at, item in enumerate(candidates):
        if item.needs_more is None or at in kept:
            result.append(item)
        elif item.available:
            result.append(
                item.model_copy(update={"needs_more": None, "then_gives": None})
            )
    return result


def _with_break_hint(
    candidates: list[OfferCandidate],
    *,
    next_break: PriceListBreak,
    quantity: Decimal,
    stock_factor: Decimal,
    listed: bool,
) -> list[OfferCandidate]:
    """Put the price list's next break on its candidate, or list it for it.

    A line below the list's first break has no price list candidate yet:
    it is listed for the hint alone, worth nothing and not available.
    """
    stock = quantity * stock_factor
    if next_break.starts_at <= stock:
        return candidates
    needs_more = in_line_units(next_break.starts_at - stock, stock_factor)
    rate = quantize_money(next_break.percent)
    then_gives = f"{plain_quantity(rate)}% off"
    key = str(next_break.price_list.id)
    if listed:
        return [
            (
                item.model_copy(
                    update={"needs_more": needs_more, "then_gives": then_gives}
                )
                if item.source == "price_list"
                else item
            )
            for item in candidates
        ]
    return [
        *candidates,
        OfferCandidate(
            key=key,
            source="price_list",
            code=next_break.price_list.code,
            name=next_break.price_list.name[:_NAME_LENGTH],
            gives=OfferGives(
                kind="PERCENT", percent=rate, sentence=f"{plain_quantity(rate)}% off"
            ),
            worth=ZERO,
            applied=False,
            combines=False,
            available=False,
            reason=f"{plain_quantity(needs_more)} more to earn it.",
            needs_more=needs_more,
            then_gives=then_gives,
        ),
    ]


def _standing_candidate(
    *,
    key: str,
    source: str,
    code: str,
    name: str,
    percent: Decimal,
    gross: Decimal,
    priced: LineDiscount,
) -> OfferCandidate:
    """Return one standing arrangement as a candidate, valued on the gross."""
    applied = priced.source == source
    typed = priced.source in _TYPED
    rate = quantize_money(percent)
    return OfferCandidate(
        key=key,
        source=source,
        code=code,
        name=name[:_NAME_LENGTH],
        gives=OfferGives(
            kind="PERCENT", percent=rate, sentence=f"{plain_quantity(rate)}% off"
        ),
        worth=quantize_money(quantize_money(gross) * rate / HUNDRED),
        applied=applied,
        combines=False,
        available=not typed,
        reason=(
            None
            if applied
            else (
                _TYPED_REASON
                if typed
                else _PASSED_OVER.get(priced.source, "Not applied.")
            )
        ),
    )


def _settle_residual(rows: list[OfferRow], target: Decimal) -> None:
    """Make the rows' discounts add up to the line's, to the paisa.

    The engine's shares already do; this is the guard for the shared rule
    rounding its figure once more. The difference goes on the last offer that
    took something off, as the cap takes from it first.
    """
    residual = target - sum((row.discount_amount for row in rows), ZERO)
    if residual == ZERO:
        return
    for position in reversed(range(len(rows))):
        row = rows[position]
        if row.discount_amount > ZERO:
            rows[position] = replace(
                row, discount_amount=row.discount_amount + residual
            )
            return
