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
from app.core.utils.quantities import at_quantity_scale
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
    APPLIED,
    REFUSED,
    OfferRow,
    StandingArrangement,
    line_offer_rows,
)
from app.promotions.services.promotion_service import PromotionService

ZERO = Decimal("0")
#: The permission a real choice needs (design 3.8).
CHOOSE_PERMISSION = "SALES_OFFER_CHOOSE"
_NOT_COMBINING = "Does not combine with "
#: How long a row's ``name`` may be (``LineOfferMixin``).
_NAME_LENGTH = 120


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
    #: True where a choice that no longer holds is dropped and reported
    #: rather than refused: one handed over by a quotation, checked again on
    #: the order's own date (L7 step 6).
    forgiving: bool = False
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
    #: The key of the offer taken as a part share (L7 step 7), if one is.
    part_share: str | None = None
    #: The arrangements the start applied that the choice did not take, as
    #: the start gave them: free goods in the line's own unit (L7 step 9).
    passed_over: tuple[OfferRow, ...] = ()

    def keys(self) -> frozenset[str]:
        """Return every key the person chose on the line."""
        named = set(self.offers)
        if self.discount_from not in (None, CHOSEN_OFFERS):
            named.add(str(self.discount_from))
        return frozenset(named)

    def mark_rows(
        self,
        rows: Sequence[OfferRow],
        *,
        stock_factor: Decimal,
        standing: StandingArrangement | None = None,
    ) -> list[OfferRow]:
        """Return the line's rows with the chosen ones marked so.

        Each arrangement the choice passed over follows the applied rows as a
        REFUSED row (L7 step 9), holding what the start gave: its discount,
        and its free goods in stock units (``stock_factor`` is the stock
        units one of the line's units holds). A REFUSED row is never chosen
        and adds to nothing: only the APPLIED rows add up to the line.
        """
        keys = self.keys()
        marked = [replace(row, chosen=row.key in keys) for row in rows]
        for row in self.passed_over:
            if row.source == "customer_group" and standing is not None:
                # The start named the group generically; the caller knows it.
                row = replace(
                    row,
                    code=standing.group_code or row.code,
                    name=(standing.group_name or row.name)[:_NAME_LENGTH],
                )
            marked.append(
                replace(
                    row,
                    state=REFUSED,
                    chosen=False,
                    part_share=False,
                    free_quantity=at_quantity_scale(row.free_quantity * stock_factor),
                )
            )
        return marked

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
            "part_share": self.part_share,
        }


@dataclass(slots=True)
class SettledChoices:
    """The engine's answer for a document, and the choices it honours."""

    request: PromotionEvaluationRequest
    outcome: PromotionEvaluationResponse
    #: The real choices, by the line's position among the lines asked.
    choices: dict[int, SettledChoice] = field(default_factory=dict)
    #: What a preview, or a forgiving line, refused, by line number.
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
        lenient: A preview: refusals are reported, not raised. A line marked
            ``forgiving`` is treated so on a save too.

    Returns:
        The answer to price the document by, logged as the engine logs it,
        with each real choice and what a preview refused.

    Raises:
        ValidationError: A choice the line cannot take, on a save.
        AuthorizationError: A real choice without the permission, on a save.

    """
    engine = PromotionService(session)
    active = {
        index: _with_part_share_offer(item)
        for index, item in enumerate(terms)
        if item.choice is not None
        and (
            item.choice.discount_from is not None
            or item.choice.offers is not None
            or item.choice.part_share is not None
        )
    }
    if not active:
        request = build_request({})
        return SettledChoices(
            request=request, outcome=engine.evaluate(request, firm_scope=firm_id)
        )

    refused: dict[int, str] = {}

    def refuse(index: int, problem: _RefusalError) -> None:
        """Raise a refusal on a save; note it and drop the choice on a preview."""
        if not (lenient or terms[index].forgiving):
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
        shares = {
            index: UUID(item.choice.part_share)
            for index, item in active.items()
            if item.choice is not None and item.choice.part_share is not None
        }
        request = (
            _with_part_shares(build_request(limits), shares)
            if limits or shares
            else start_request
        )
        outcome = (
            engine.evaluate(request, firm_scope=firm_id, record=False)
            if limits or shares
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
    if choice.part_share is not None:
        candidate = offered.get(choice.part_share)
        if candidate is not None and not terms.engine_free:
            raise _RefusalError(_cannot_share(number, candidate.code))
        if candidate is None or not candidate.available:
            code = (
                candidate.code
                if candidate is not None
                else _name(session, choice.part_share, standing=standing)
            )
            raise _RefusalError(
                f"Line {number}: offer {code} does not apply to this line any "
                "more. Choose again."
            )
        if candidate.part_share is None:
            raise _RefusalError(_cannot_share(number, candidate.code))
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
    if choice.part_share is not None and not any(
        row.key == choice.part_share and row.part_share for row in rows
    ):
        # Taken in whole rounds or not at all: under "best one only" another
        # offer won the line, or the quantity earns no share of a piece.
        candidate = offered.get(choice.part_share)
        code = candidate.code if candidate is not None else choice.part_share
        reason = None if candidate is None else candidate.reason
        raise _RefusalError(
            f"Line {terms.line_number}: offer {code} gives this line nothing "
            "as a part share" + (f" ({reason.rstrip('.')})." if reason else ".")
        )
    begun = chosen_line_discount(
        terms,
        percent=None,
        amount=None,
        promotion_amount=_promotion_amount(start),
        discount_from=None,
    )
    start_rows = _rows(terms, start, begun)
    if (
        taken == {row.key for row in start_rows}
        and priced.source == begun.source
        # The start never bills a part share, so one is always a choice.
        and choice.part_share is None
    ):
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
        part_share=choice.part_share,
        passed_over=tuple(row for row in start_rows if row.key not in taken),
    )


def _cannot_share(number: int, code: str) -> str:
    """Say why a line cannot take an offer as a part share (L7 step 7)."""
    return (
        f"Line {number}: offer {code} cannot be billed as a part share on this "
        "line. A part share is of an offer that allows one, on a line in the "
        "item's own unit with no free quantity typed."
    )


def _with_part_share_named(choice: OfferChoice) -> OfferChoice:
    """Return a choice whose named offers include its part share (L7 step 7).

    A part share takes its offer whether or not ``offers`` names it, so a
    list that leaves it out is read as naming it.
    """
    if (
        choice.part_share is None
        or choice.offers is None
        or choice.part_share in choice.offers
    ):
        return choice
    return choice.model_copy(update={"offers": [*choice.offers, choice.part_share]})


def _with_part_share_offer(terms: LineTerms) -> LineTerms:
    """Return a line's terms with its part share among the offers it names."""
    if terms.choice is None:
        return terms
    named = _with_part_share_named(terms.choice)
    return terms if named is terms.choice else replace(terms, choice=named)


def _with_part_shares(
    request: PromotionEvaluationRequest, shares: Mapping[int, UUID]
) -> PromotionEvaluationRequest:
    """Return the engine's request with each line's part share, by position."""
    if not shares:
        return request
    return request.model_copy(
        update={
            "lines": [
                (
                    line.model_copy(update={"part_share": shares[index]})
                    if index in shares
                    else line
                )
                for index, line in enumerate(request.lines)
            ]
        }
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
    found: dict[UUID, tuple[str | None, list[str], str | None]] = {}
    for row in sorted(rows, key=lambda item: item.sequence):
        line_id = line_of(row)
        if line_id is None or not row.chosen or row.state != APPLIED:
            continue
        discount_from, offers, part_share = found.setdefault(line_id, (None, [], None))
        if row.source == "promotion" and row.promotion_group_id is not None:
            offers.append(str(row.promotion_group_id))
            if row.part_share:
                part_share = str(row.promotion_group_id)
        elif row.source == "price_list" and row.price_list_id is not None:
            discount_from = str(row.price_list_id)
        elif row.source == "customer":
            discount_from = CHOSEN_CUSTOMER
        elif row.source == "customer_group":
            discount_from = CHOSEN_CUSTOMER_GROUP
        found[line_id] = (discount_from, offers, part_share)
    return {
        line_id: OfferChoice(
            discount_from=discount_from, offers=offers, part_share=part_share
        )
        for line_id, (discount_from, offers, part_share) in found.items()
    }


def same_choice(sent: OfferChoice | None, held: OfferChoice | None) -> bool:
    """Say whether a choice sent back is the one a line already holds (step 6).

    Offers compare as a set. ``discount_from="offers"`` reads as unnamed,
    since the rows a held choice is read back from cannot tell the two apart
    (see `stored_choices`); calling the two different would only raise a
    document again for nothing.
    """

    def shape(
        choice: OfferChoice | None,
    ) -> tuple[str | None, frozenset[str] | None, str | None]:
        """Return the choice in the form two choices compare by."""
        if choice is None:
            return None, None, None
        choice = _with_part_share_named(choice)
        source = None if choice.discount_from == CHOSEN_OFFERS else choice.discount_from
        offers = None if choice.offers is None else frozenset(choice.offers)
        return source, offers, choice.part_share

    return shape(sent) == shape(held)
