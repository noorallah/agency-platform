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
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.utils.pricing import LineDiscount
from app.core.utils.quantities import at_quantity_scale
from app.customers.models import CustomerGroup
from app.pricing.services.price_list_service import PriceListRef
from app.promotions.models.line_offer import LineOfferMixin
from app.promotions.schemas import (
    LineOfferResponse,
    PromotionApplication,
    PromotionLineShare,
)

ZERO = Decimal("0")

#: The words a line's ``discount_source`` uses for a standing arrangement.
STANDING_SOURCES = frozenset({"price_list", "customer", "customer_group"})
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
                    state="APPLIED",
                    chosen=False,
                    discount_amount=item.discount_amount,
                    free_quantity=item.free_quantity,
                    part_share=False,
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
