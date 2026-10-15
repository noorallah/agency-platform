"""The bill maker's choice on a sales line, settled once for two documents (L7).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` sections 3.3 to 3.5 and 3.8,
step 5 of section 6. A line of a sales order or a quotation may carry an
``offer_choice``: the arrangement its discount comes from, and the offers it
takes. The client sends keys, never amounts; this module decides what the
keys are worth, and the order and the quotation each call it so the two
cannot drift.

On every save and every preview the candidates are built afresh -- the
**start**, the engine's answer with nobody choosing -- and then:

1. a line with a discount typed **and** a choice is refused: two answers;
2. a key that is not an available candidate of that line is refused by
   name ("Line 2: offer TEA-5 does not apply to this line any more. Choose
   again."); under "best one only" a second offer on a line is refused;
3. the chosen offers are run through the same engine, in the same order,
   limited to those chosen, and one the engine does not reach is refused
   ("Line 1: TEA-9 does not combine with TEA-5.");
4. **a choice equal to the start is not a choice**: a line whose chosen set
   gives the same arrangements as the start is stored as the server's, so
   an editor that sends back what it read is harmless;
5. what is left is a real choice, and needs ``SALES_OFFER_CHOOSE``.

A save raises the first refusal. A preview is lenient: it reports each
refusal on its line, drops that line's choice and prices it from the start.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, ValidationError
from app.core.utils.pricing import (
    CHOSEN_CUSTOMER,
    CHOSEN_CUSTOMER_GROUP,
    CHOSEN_OFFERS,
    LineDiscount,
    LineTiers,
    chosen_tiers,
    resolve_line_discount,
)
from app.pricing.models import PriceList
from app.pricing.services.price_list_service import PriceListRef
from app.promotions.models import Promotion
from app.promotions.models.line_offer import LineOfferMixin
from app.promotions.schemas import (
    OfferCandidate,
    OfferChoice,
    PromotionEvaluationRequest,
    PromotionEvaluationResponse,
    PromotionLineOutcome,
)
from app.promotions.services.line_offers import (
    OfferRow,
    StandingArrangement,
    line_offer_rows,
)
from app.promotions.services.promotion_service import PromotionService

ZERO = Decimal("0")
#: The permission a real choice needs (design 3.8).
CHOOSE_PERMISSION = "SALES_OFFER_CHOOSE"
_NOT_COMBINING = "Does not combine with "


@dataclass(frozen=True, slots=True)
class LineTerms:
    """One line the customer asked for, as a choice on it is judged.

    Built by the document from what it already read for the line: nothing
    here costs a statement.
    """

    line_number: int
    gross: Decimal
    #: What the line chose; None where it chose nothing.
    choice: OfferChoice | None = None
    #: True where the choice was not sent but kept from the line as saved:
    #: the record of an earlier choice, judged again but not as a new one.
    kept: bool = False
    #: A discount figure typed on the line, a zero included.
    typed: bool = False
    #: Nobody typed the line's free quantity, so its offers' free goods stand.
    engine_free: bool = True
    price_list: PriceListRef | None = None
    price_list_percent: Decimal | None = None
    customer_percent: Decimal | None = None
    group_percent: Decimal | None = None

    @property
    def price_list_key(self) -> str | None:
        """Return the key the line's price list is chosen by, if it has one."""
        if self.price_list is None or self.price_list_percent is None:
            return None
        return str(self.price_list.id)

    def standing(self) -> dict[str, str]:
        """Return the standing arrangements the line may take, key to code."""
        found: dict[str, str] = {}
        key = self.price_list_key
        if key is not None and self.price_list is not None:
            found[key] = self.price_list.code
        if self.customer_percent is not None and self.customer_percent > ZERO:
            found[CHOSEN_CUSTOMER] = CHOSEN_CUSTOMER
        if self.group_percent is not None and self.group_percent > ZERO:
            found[CHOSEN_CUSTOMER_GROUP] = CHOSEN_CUSTOMER_GROUP
        return found


def chosen_line_discount(
    terms: LineTerms,
    *,
    percent: Decimal | None,
    amount: Decimal | None,
    promotion_amount: Decimal | None,
    discount_from: str | None,
) -> LineDiscount:
    """Resolve one line's discount with the tiers its choice did not name blanked."""
    tiers = chosen_tiers(
        LineTiers(
            promotion_amount=promotion_amount,
            price_list_percent=terms.price_list_percent,
            customer_default=terms.customer_percent,
            customer_group_default=terms.group_percent,
        ),
        discount_from=discount_from,
        price_list_key=terms.price_list_key,
    )
    return resolve_line_discount(
        gross=terms.gross,
        percent=percent,
        amount=amount,
        promotion_amount=tiers.promotion_amount,
        price_list_percent=tiers.price_list_percent,
        customer_default=tiers.customer_default,
        customer_group_default=tiers.customer_group_default,
    )


@dataclass(frozen=True, slots=True)
class SettledChoice:
    """A real choice on one line: what it takes, and what the start took."""

    discount_from: str | None
    #: The keys of the offers the line takes: those named, or -- where the
    #: choice named none -- those the engine gave it, so the rows marked
    #: chosen are the whole record of the choice.
    offers: frozenset[str]
    #: The codes of the arrangements the start applied, and of those taken.
    start: tuple[str, ...]
    taken: tuple[str, ...]

    def keys(self) -> frozenset[str]:
        """Return every key the person chose on the line."""
        named = set(self.offers)
        if self.discount_from not in (None, CHOSEN_OFFERS):
            named.add(str(self.discount_from))
        return frozenset(named)

    def mark_rows(self, rows: Sequence[OfferRow]) -> list[OfferRow]:
        """Return the line's rows with the chosen ones marked so."""
        keys = self.keys()
        return [replace(row, chosen=row.key in keys) for row in rows]

    def mark_candidates(
        self, candidates: Sequence[OfferCandidate]
    ) -> list[OfferCandidate]:
        """Return the line's candidates with the chosen ones marked so."""
        keys = self.keys()
        return [
            item.model_copy(update={"chosen": True}) if item.key in keys else item
            for item in candidates
        ]

    def audit(self, line_number: int) -> dict[str, object]:
        """Describe the choice for the audit trail (decision 4)."""
        return {
            "line_number": line_number,
            "start": list(self.start),
            "taken": list(self.taken),
            "discount_from": self.discount_from,
            "offers": sorted(self.offers),
        }


@dataclass(slots=True)
class SettledChoices:
    """The engine's answer for a document, and the choices it honours."""

    request: PromotionEvaluationRequest
    outcome: PromotionEvaluationResponse
    #: The real choices, by the line's position among the lines asked.
    choices: dict[int, SettledChoice] = field(default_factory=dict)
    #: What a preview refused, by line number, to show beside the line.
    refused: dict[int, str] = field(default_factory=dict)

    def discount_from(self, index: int) -> str | None:
        """Return the arrangement line ``index`` chose its discount from."""
        settled = self.choices.get(index)
        return None if settled is None else settled.discount_from


class _RefusalError(Exception):
    """One line's choice refused, held until the caller decides how to say it."""

    def __init__(self, message: str, *, permission: bool = False) -> None:
        """Keep the message and whether it is a missing permission."""
        super().__init__(message)
        self.message = message
        self.permission = permission


def settle_choices(
    session: Session,
    *,
    firm_id: UUID,
    terms: Sequence[LineTerms],
    build_request: Callable[[Mapping[int, list[UUID]]], PromotionEvaluationRequest],
    may_choose: bool,
    lenient: bool,
) -> SettledChoices:
    """Price a document's offers with the choices on its lines (design 3.3).

    Args:
        session: The document's session; nothing is committed.
        firm_id: The firm whose offers and setting apply.
        terms: Each line the customer asked for, in order.
        build_request: Builds the engine's request with each line's offers
            limited, by the line's position, to the keys given.
        may_choose: Whether the person holds ``SALES_OFFER_CHOOSE``.
        lenient: A preview: refusals are reported, not raised.

    Returns:
        The answer to price the document by, logged as the engine logs it,
        with each real choice and what a preview refused.

    Raises:
        ValidationError: A choice the line cannot take, on a save.
        AuthorizationError: A real choice without the permission, on a save.

    """
    engine = PromotionService(session)
    active = {
        index: item
        for index, item in enumerate(terms)
        if item.choice is not None
        and (item.choice.discount_from is not None or item.choice.offers is not None)
    }
    if not active:
        request = build_request({})
        return SettledChoices(
            request=request, outcome=engine.evaluate(request, firm_scope=firm_id)
        )

    refused: dict[int, str] = {}

    def refuse(index: int, problem: _RefusalError) -> None:
        """Raise a refusal on a save; note it and drop the choice on a preview."""
        if not lenient:
            if problem.permission:
                raise AuthorizationError(problem.message)
            raise ValidationError(problem.message, details={"field": "lines"})
        refused[terms[index].line_number] = problem.message
        active.pop(index, None)

    start_request = build_request({})
    start = engine.evaluate(start_request, firm_scope=firm_id, record=False)
    mode = engine.promotion_mode(firm_id)
    for index, item in list(active.items()):
        try:
            _check_keys(session, item, start.lines[index], mode=mode)
        except _RefusalError as problem:
            refuse(index, problem)

    request, outcome = start_request, start
    settled: dict[int, SettledChoice] = {}
    while active:
        limits = {
            index: [UUID(key) for key in item.choice.offers]
            for index, item in active.items()
            if item.choice is not None and item.choice.offers is not None
        }
        request = build_request(limits) if limits else start_request
        outcome = (
            engine.evaluate(request, firm_scope=firm_id, record=False)
            if limits
            else start
        )
        settled = {}
        dropped = False
        for index, item in list(active.items()):
            try:
                found = _judge(item, outcome.lines[index], start.lines[index])
            except _RefusalError as problem:
                refuse(index, problem)
                dropped = True
                continue
            if found is None:
                # Equal to the start: the line follows the server.
                active.pop(index)
                dropped = True
                continue
            if not may_choose and not item.kept:
                # Judged after "equal to the start", so an editor that sends
                # back what it read is harmless to a person without it.
                refuse(
                    index,
                    _RefusalError(
                        f"Line {item.line_number}: choosing what a line takes "
                        f"needs the permission {CHOOSE_PERMISSION}.",
                        permission=True,
                    ),
                )
                dropped = True
                continue
            settled[index] = found
        if not dropped:
            break
    if not active:
        request, outcome, settled = start_request, start, {}
    engine.record(request, outcome, firm_scope=firm_id)
    return SettledChoices(
        request=request, outcome=outcome, choices=settled, refused=refused
    )


def _check_keys(
    session: Session, terms: LineTerms, start: PromotionLineOutcome, *, mode: str
) -> None:
    """Refuse a choice the line cannot take, before anything is priced again."""
    choice = terms.choice
    if choice is None:
        return
    number = terms.line_number
    if terms.typed:
        raise _RefusalError(
            f"Line {number}: a discount is typed and a choice of offers is "
            "sent -- two answers on one line. Clear the discount or the choice."
        )
    offered = {item.key: item for item in start.candidates}
    standing = terms.standing()
    if (
        choice.discount_from is not None
        and choice.discount_from != CHOSEN_OFFERS
        and choice.discount_from not in standing
    ):
        raise _RefusalError(
            f"Line {number}: "
            f"{_name(session, choice.discount_from, standing=standing)} "
            "does not apply to this line any more. Choose again."
        )
    for key in choice.offers or []:
        candidate = offered.get(key)
        if candidate is None or not (
            candidate.available or (candidate.reason or "").startswith(_NOT_COMBINING)
        ):
            code = (
                candidate.code
                if candidate is not None
                else _name(session, key, standing=standing)
            )
            raise _RefusalError(
                f"Line {number}: offer {code} does not apply to this line any "
                "more. Choose again."
            )
    if mode == "BEST_OFFER" and len(set(choice.offers or [])) > 1:
        codes = ", ".join(
            offered[key].code for key in dict.fromkeys(choice.offers or [])
        )
        raise _RefusalError(
            f"Line {number}: the firm gives the best one offer a line, and "
            f"{codes} were chosen. Choose one."
        )


def _judge(
    terms: LineTerms, outcome: PromotionLineOutcome, start: PromotionLineOutcome
) -> SettledChoice | None:
    """Return the line's choice as taken, or None where it is the start.

    Raises a refusal for a chosen offer the engine did not reach.
    """
    choice = terms.choice
    assert choice is not None
    priced = chosen_line_discount(
        terms,
        percent=None,
        amount=None,
        promotion_amount=_promotion_amount(outcome),
        discount_from=choice.discount_from,
    )
    rows = _rows(terms, outcome, priced)
    taken = {row.key for row in rows}
    offered = {item.key: item for item in outcome.candidates}
    for key in dict.fromkeys(choice.offers or []):
        if key in taken:
            continue
        candidate = offered.get(key)
        code = candidate.code if candidate is not None else key
        reason = None if candidate is None else candidate.reason
        if reason is not None and reason.startswith(_NOT_COMBINING):
            raise _RefusalError(
                f"Line {terms.line_number}: {code} does not combine with "
                f"{reason[len(_NOT_COMBINING) :]}"
            )
        share = next(
            (item for item in outcome.offers if str(item.promotion_group_id) == key),
            None,
        )
        if share is not None and share.discount_amount > ZERO:
            raise _RefusalError(
                f"Line {terms.line_number}: {code} gives a discount, and the "
                "line takes its discount from "
                f"{_from_code(terms, choice.discount_from)}. Choose one of them."
            )
        raise _RefusalError(
            f"Line {terms.line_number}: offer {code} gives this line nothing"
            + (f" ({reason.rstrip('.')})." if reason else ".")
        )
    begun = chosen_line_discount(
        terms,
        percent=None,
        amount=None,
        promotion_amount=_promotion_amount(start),
        discount_from=None,
    )
    start_rows = _rows(terms, start, begun)
    if taken == {row.key for row in start_rows} and priced.source == begun.source:
        return None
    named = (
        frozenset(dict.fromkeys(choice.offers))
        if choice.offers is not None
        else frozenset(row.key for row in rows if row.source == "promotion")
    )
    return SettledChoice(
        discount_from=choice.discount_from,
        offers=named,
        start=tuple(row.code for row in start_rows),
        taken=tuple(row.code for row in rows),
    )


def _promotion_amount(outcome: PromotionLineOutcome) -> Decimal | None:
    """Return what the offers took off a line, None where nothing (as priced)."""
    return outcome.discount_amount if outcome.discount_amount > ZERO else None


def _rows(
    terms: LineTerms, outcome: PromotionLineOutcome, priced: LineDiscount
) -> list[OfferRow]:
    """Return the arrangements a line's price names, for comparing choices."""
    return line_offer_rows(
        shares=outcome.offers,
        priced=priced,
        engine_free=terms.engine_free,
        stock_factor=Decimal("1"),
        price_list=terms.price_list if priced.source == "price_list" else None,
        standing=StandingArrangement(),
    )


def _from_code(terms: LineTerms, discount_from: str | None) -> str:
    """Name the arrangement a choice took the line's discount from."""
    if discount_from is None:
        return "the ranking"
    return terms.standing().get(discount_from, discount_from)


def _name(session: Session, key: str, *, standing: Mapping[str, str]) -> str:
    """Name a key the line no longer lists: an offer's code, a list's code.

    Asked only on a refusal, so the statement is never on the way of a
    choice that stands.
    """
    if key in standing:
        return standing[key]
    try:
        identity = UUID(key)
    except ValueError:
        return key
    code = session.scalar(
        select(Promotion.code)
        .where(Promotion.version_group_id == identity)
        .order_by(Promotion.version_number.desc())
        .limit(1)
    )
    if code is None:
        code = session.scalar(select(PriceList.code).where(PriceList.id == identity))
    return code or key


def stored_choices[RowT: LineOfferMixin](
    rows: Sequence[RowT], *, line_of: Callable[[RowT], UUID | None]
) -> dict[UUID, OfferChoice]:
    """Read back, by line id, the choices a document's chosen rows record.

    The rows marked chosen are the whole record of a choice (no column holds
    it): the offers chosen by their lasting identity, and the standing
    arrangement the discount was taken from. A line whose choice took no
    offer reads back as choosing none.
    """
    found: dict[UUID, tuple[str | None, list[str]]] = {}
    for row in sorted(rows, key=lambda item: item.sequence):
        line_id = line_of(row)
        if line_id is None or not row.chosen:
            continue
        discount_from, offers = found.setdefault(line_id, (None, []))
        if row.source == "promotion" and row.promotion_group_id is not None:
            offers.append(str(row.promotion_group_id))
        elif row.source == "price_list" and row.price_list_id is not None:
            discount_from = str(row.price_list_id)
        elif row.source == "customer":
            discount_from = CHOSEN_CUSTOMER
        elif row.source == "customer_group":
            discount_from = CHOSEN_CUSTOMER_GROUP
        found[line_id] = (discount_from, offers)
    return {
        line_id: OfferChoice(discount_from=discount_from, offers=offers)
        for line_id, (discount_from, offers) in found.items()
    }
