"""Decide what benefits a sales document earns, and why.

The engine is `app/tax`'s with one deliberate difference. Tax stops at the
first matching rule, because two rules both applying would tax a line twice.
Promotions **stack**: every matching promotion applies, in priority order,
until one that refuses further stacking is reached.

Two rules make that safe.

**The order is total.** `priority ASC, code ASC, version_number DESC,
created_at ASC` -- the same document must always price the same, and two
promotions of equal priority must never swap places between runs.

**Percentages compound on what is left, never add on the gross.** Two stacked
ten percent offers take nineteen percent, not twenty. That is what a shop
means by it, and it also makes it arithmetically impossible for stacked
benefits to exceed the line -- which matters, because `resolve_line_discount`
refuses a discount larger than the line, and a promotion nobody can configure
their way out of would make a document unsaveable rather than cheap.

Like `TaxRuleService.simulate`, this **never commits**. It runs while a
document is being built, on the caller's session; committing here would
publish a half-written order.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, false, func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.utils.dates import as_utc, utc_now
from app.core.utils.money import quantize_ledger, quantize_money
from app.core.utils.pricing import apportion
from app.core.utils.quantities import at_quantity_scale, plain_quantity
from app.products.models import Product
from app.promotions.models import (
    Promotion,
    PromotionCoupon,
    PromotionExecutionLog,
    PromotionRedemption,
)
from app.promotions.schemas import (
    OfferCandidate,
    OfferGives,
    PromotionActionType,
    PromotionApplication,
    PromotionConditionOperator,
    PromotionDecision,
    PromotionEvaluationRequest,
    PromotionEvaluationResponse,
    PromotionField,
    PromotionGift,
    PromotionLineOutcome,
    PromotionLineShare,
    PromotionStatus,
)
from app.promotions.services.line_offers import in_line_units, nearest_hints
from app.promotions.services.offer_use import claims_given
from app.promotions.services.references import live_row_ids

ZERO = Decimal("0")
HUNDRED = Decimal("100")

#: The actions that change a line, so an offer carrying one is listed beside
#: each line its conditions hold on (L7 step 3).
_LINE_ACTIONS = frozenset(
    {
        PromotionActionType.LINE_DISCOUNT_PERCENT.value,
        PromotionActionType.LINE_DISCOUNT_AMOUNT.value,
        PromotionActionType.FREE_QUANTITY.value,
        PromotionActionType.BUY_X_GET_Y_DISCOUNT.value,
        PromotionActionType.COMBO_PRICE.value,
    }
)
#: The actions on the whole bill, so an offer carrying one is listed under
#: the totals.
_BILL_ACTIONS = frozenset(
    {
        PromotionActionType.BILL_DISCOUNT_PERCENT.value,
        PromotionActionType.BILL_DISCOUNT_AMOUNT.value,
        PromotionActionType.FREE_SHIPPING.value,
        PromotionActionType.FREE_PRODUCT.value,
    }
)
#: The actions judged line by line under "best one only": each gives one
#: line its own benefit. A combo across lines, a gift counted over several
#: and anything on the whole bill are judged among themselves (decision 2
#: of the L7 design).
_PER_LINE_ACTIONS = frozenset(
    {
        PromotionActionType.LINE_DISCOUNT_PERCENT.value,
        PromotionActionType.LINE_DISCOUNT_AMOUNT.value,
        PromotionActionType.FREE_QUANTITY.value,
        PromotionActionType.BUY_X_GET_Y_DISCOUNT.value,
    }
)
_BILL_DISCOUNTS = frozenset(
    {
        PromotionActionType.BILL_DISCOUNT_PERCENT.value,
        PromotionActionType.BILL_DISCOUNT_AMOUNT.value,
    }
)


#: India Standard Time. The product sells in India and keeps one zone; an
#: offer for "4 to 6 pm" means the shop's clock, not the server's.
INDIA = timezone(timedelta(hours=5, minutes=30), "IST")


def minutes_of_day_in_india(moment: datetime | None) -> int:
    """Return minutes after midnight in India for ``moment``, or for now.

    A naive moment is read as UTC, as every stored timestamp here is.
    """
    when = as_utc(moment) if moment is not None else utc_now()
    local = when.astimezone(INDIA)
    return local.hour * 60 + local.minute


def is_points_offer(promotion: Promotion) -> bool:
    """Say whether an offer gives bonus loyalty points rather than a price."""
    kinds = {
        action.action_type for action in promotion.actions if not action.is_deleted
    }
    return kinds == {PromotionActionType.LOYALTY_MULTIPLIER.value}


@dataclass(slots=True)
class _LineState:
    """What one line has earned so far as promotions are applied."""

    line_number: int
    gross: Decimal
    #: The line's quantity in **stock units**: an offer names products, a
    #: product has one stock unit, and every count an offer makes -- a
    #: quantity condition, "buy X", a combo's set -- is of those (D-PRC-39).
    quantity: Decimal
    discount: Decimal = ZERO
    #: The quantity as the line states it, in the line's own unit.
    entered_quantity: Decimal = ZERO
    #: The stock units one of the line's units holds: 12 for a box of twelve.
    stock_factor: Decimal = Decimal("1")
    #: What the line sells, for an offer about a set of products (SEL-3).
    product_id: UUID | None = None
    #: Free units put on this line, in the line's own unit.
    free_quantity: Decimal = ZERO
    #: The same free units in stock units, which is what a claim counts.
    free_stock: Decimal = ZERO
    #: Somebody typed this line's free quantity, so no offer adds to it.
    free_typed: bool = False
    #: The offer that gave this line's free units: the last, if two did.
    free_promotion_id: UUID | None = None
    codes: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> Decimal:
        """What is still discountable on this line."""
        return self.gross - self.discount

    def fresh(self) -> "_LineState":
        """Return a copy with nothing given yet, to value one offer alone."""
        return replace(
            self,
            discount=ZERO,
            free_quantity=ZERO,
            free_stock=ZERO,
            free_promotion_id=None,
            codes=[],
        )


@dataclass(slots=True)
class _Considered:
    """One offer the engine looked at, kept to list it beside the lines (L7)."""

    promotion: Promotion
    #: The indexes of the lines its conditions hold on, typed lines included.
    lines: list[int]
    #: False where nothing the bill maker does on this document reaches it.
    available: bool = True
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class _OfferUse:
    """What one offer's claims add up to, read with every other offer's."""

    claims: int = 0
    by_customer: int = 0
    by_coupon: int = 0
    by_coupon_customer: int = 0
    amount: Decimal = ZERO
    free: Decimal = ZERO


class PromotionService:
    """Evaluate a firm's promotions against one document."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        #: Each product an offer gives away, and whether the firm holds it.
        self._gift_products: dict[str, UUID | None] = {}
        #: The offers whose gift was passed over, for the trace.
        self._gifts_passed_over: dict[UUID, Promotion] = {}

    def evaluate(
        self,
        data: PromotionEvaluationRequest,
        *,
        firm_scope: UUID,
        record: bool = True,
    ) -> PromotionEvaluationResponse:
        """Apply every matching promotion, in order, and report what happened.

        Never commits: the caller is mid-document. The `/simulate` endpoint
        owns the transaction, exactly as it does for tax. ``record`` False
        writes no execution log, for a caller weighing a person's choice
        against the start (L7 step 5) that logs the answer it keeps with
        `record`.
        """
        states = [
            _LineState(
                line_number=line.line_number,
                gross=quantize_money(line.gross),
                quantity=quantize_money(
                    Decimal(str(line.quantity)) * Decimal(str(line.stock_factor))
                ),
                entered_quantity=Decimal(str(line.quantity)),
                stock_factor=Decimal(str(line.stock_factor)),
                product_id=getattr(line, "product_id", None),
                free_typed=line.free_typed,
            )
            for line in data.lines
        ]
        document_gross = quantize_money(sum((s.gross for s in states), ZERO))
        products = self._products_for(data)
        history = self._customer_history(data)
        bill_discount = ZERO
        # What was charged for delivery is either waived whole or not at all,
        # so this is a flag rather than a running total: a second offer cannot
        # waive an already-waived charge twice.
        freight_waived = ZERO
        gifts: list[PromotionGift] = []
        applied: list[str] = []
        applications: list[PromotionApplication] = []
        decisions: list[PromotionDecision] = []

        coupon = self._coupon_for(data, firm_scope=firm_scope)
        mode, line_cap = self._promotion_policy(firm_scope)
        best_only = mode in ("BEST_OFFER", "ASK")
        # Why an offer is not on one line, where that is the line's own
        # business: not chosen there, or another worth more there (L7 step 5).
        line_reasons: dict[tuple[UUID, int], str] = {}
        candidates: list[tuple[Promotion, list[_LineState]]] = []
        # Which offer added how much to which line, in the order applied, so a
        # combined cap can take back the last slice first (backlog 59 item 3).
        slices: list[list[tuple[int, Decimal]]] = [[] for _ in states]
        # The same for free units, in each line's own unit, so a line can say
        # whose free goods it carries (L7 step 2). A cap never trims these.
        free_slices: list[list[tuple[int, Decimal]]] = [[] for _ in states]
        # What each offer took off the whole bill, in the order applied.
        bill_slices: list[tuple[int, Decimal]] = []
        applied_promotions: list[Promotion] = []
        # What each budgeted offer still has to give.
        room: dict[UUID, BudgetRoom] = {}
        active = self._active_promotions(
            firm_scope=firm_scope, on=data.transaction_date
        )
        # Every offer's claims and budget, read in one statement for the
        # document rather than once per offer (L7 step 3).
        uses = self._offer_uses(
            [row for row in active if not is_points_offer(row)],
            firm_scope=firm_scope,
            customer_id=data.customer_id,
            coupon_id=None if coupon is None else coupon.id,
        )
        # Every offer looked at, in the order looked at, to list beside the
        # lines its conditions hold on (L7 step 3).
        considered: dict[UUID, _Considered] = {}
        # The offer that does not combine and ended evaluation, if one did.
        stopped_by: Promotion | None = None

        # What each line is matched against, built once: nothing in it moves
        # as offers are applied, and the hint (L7 step 4) reads it again.
        contexts = [
            self._context(
                data,
                line=line,
                state=state,
                document_gross=document_gross,
                products=products,
                history=history,
            )
            for state, line in zip(states, data.lines, strict=True)
        ]

        def holding(promotion: Promotion) -> list[int]:
            """Return the lines this offer's conditions hold on, typed or not."""
            return [
                index
                for index, context in enumerate(contexts)
                if self._matches(promotion, context=context)
            ]

        def apply_one(
            promotion: Promotion,
            matched_lines: list[_LineState],
            stops: bool = True,
        ) -> bool | None:
            """Apply one offer to the document; True when evaluation must stop.

            None when the offer was not applied after all: what it would give
            this document is more than its budget has left, or it gave the
            document nothing. Everything it did is undone, so the document is
            priced as if it had not matched.
            """
            nonlocal bill_discount, freight_waived
            before_each = [state.discount for state in states]
            before_free = [state.free_quantity for state in states]
            before_stock = [state.free_stock for state in states]
            before_gifts = len(gifts)
            before_lines = sum(before_each, ZERO)
            added_bill, waives_freight = self._apply(
                promotion,
                matched=matched_lines,
                states=states,
                bill_discount=bill_discount,
                allow_bill=not data.caller_priced_bill,
                gifts=gifts,
            )
            worth = quantize_money(
                sum((state.discount for state in states), ZERO)
                - before_lines
                + added_bill
                + (quantize_money(data.freight_amount) if waives_freight else ZERO)
            )
            # Counted in stock units, whatever unit each line is sold in:
            # a budget of 500 free units is 500 of the product's own unit.
            free_given = sum((state.free_stock for state in states), ZERO) - sum(
                before_stock, ZERO
            )
            free_given += sum((gift.quantity for gift in gifts[before_gifts:]), ZERO)
            if worth <= ZERO and free_given <= ZERO:
                # It matched and gave nothing: its free goods were typed over
                # by hand, its gift is not a product any more, there was no
                # delivery charge to waive. An offer that gave nothing is not
                # applied, so no claim is staged and no "one per customer" is
                # used up for it (D-PRC-32).
                decisions.append(
                    self._decision(
                        promotion,
                        False,
                        (
                            "A free quantity was typed on the line this offer "
                            "matched, so the offer's own was not given and "
                            "nothing is claimed."
                            if any(state.free_typed for state in matched_lines)
                            else "This offer gave nothing on this document, so "
                            "nothing is claimed."
                        ),
                    )
                )
                return None
            overrun = room[promotion.id].overrun(worth, free_given)
            if overrun is not None:
                # Whole or not at all, as approval refuses it: part of a
                # scheme is a price nobody published.
                for state, discount, free, stock in zip(
                    states, before_each, before_free, before_stock, strict=True
                ):
                    state.discount = discount
                    state.free_quantity = free
                    state.free_stock = stock
                del gifts[before_gifts:]
                decisions.append(
                    self._decision(promotion, False, f"This offer {overrun}")
                )
                if promotion.id in considered:
                    considered[promotion.id].available = False
                return None
            bill_discount += added_bill
            if waives_freight:
                freight_waived = quantize_money(data.freight_amount)
            applied.append(promotion.code)
            applications.append(
                PromotionApplication(
                    promotion_id=promotion.id,
                    code=promotion.code,
                    coupon_id=(
                        coupon.id
                        if coupon is not None
                        and self._coupon_reaches(
                            coupon, promotion, firm_scope=firm_scope
                        )
                        else None
                    ),
                    # What this offer alone took off, line and bill together --
                    # so a campaign can be costed without re-pricing every
                    # document it touched.
                    # The waived delivery counts: a campaign that gave away
                    # shipping cost the firm exactly that, and a cost report
                    # that left it out would understate it.
                    benefit_amount=worth,
                    name=promotion.name,
                    promotion_group_id=promotion.version_group_id,
                    free_quantity=free_given,
                )
            )
            applied_promotions.append(promotion)
            if added_bill > ZERO:
                bill_slices.append((len(applications) - 1, added_bill))
            for index, state in enumerate(states):
                delta = state.discount - before_each[index]
                if delta > ZERO:
                    slices[index].append((len(applications) - 1, delta))
                if state.free_quantity > before_free[index]:
                    free_slices[index].append(
                        (
                            len(applications) - 1,
                            state.free_quantity - before_free[index],
                        )
                    )
                    # Named on the line, so the document can say whose free
                    # goods these are when a principal is asked to pay.
                    state.free_promotion_id = promotion.id
            for state in matched_lines:
                state.codes.append(promotion.code)
            decisions.append(self._decision(promotion, True, "Applied."))
            if not promotion.allow_stacking and stops:
                decisions.append(
                    self._decision(
                        promotion,
                        True,
                        "This promotion does not stack, so evaluation stopped.",
                    )
                )
                return True
            return False

        for promotion in active:
            if stopped_by is not None:
                # Evaluation has stopped: the rest are listed, never applied,
                # and leave the trace as it always was.
                if not is_points_offer(promotion):
                    considered[promotion.id] = _Considered(
                        promotion,
                        holding(promotion),
                        available=False,
                        reason=f"Does not combine with {stopped_by.code}.",
                    )
                continue
            if is_points_offer(promotion):
                # Earned when the bill is approved, not given while it is
                # priced: passing it here keeps it off the claim count and
                # stops a non-stacking points offer ending evaluation.
                decisions.append(
                    self._decision(
                        promotion,
                        False,
                        "A bonus-points offer: its points are earned when the "
                        "bill is approved.",
                    )
                )
                continue
            refusal = self._unavailable(
                promotion,
                coupon=coupon,
                data=data,
                firm_scope=firm_scope,
                use=uses.get(promotion.version_group_id, _OfferUse()),
            )
            if refusal is not None:
                decisions.append(self._decision(promotion, False, refusal))
                considered[promotion.id] = _Considered(
                    promotion, holding(promotion), available=False, reason=refusal
                )
                continue
            # A budget is counted like the number of claims, from the ledger:
            # one that is spent is not quoted, and one that cannot cover this
            # document is found out when the offer is applied below.
            use = uses.get(promotion.version_group_id, _OfferUse())
            room[promotion.id] = BudgetRoom(
                max_amount=promotion.max_benefit_amount,
                amount_claimed=use.amount,
                max_free=promotion.max_free_quantity,
                free_claimed=use.free,
            )
            spent = room[promotion.id].spent()
            if spent is not None:
                decisions.append(self._decision(promotion, False, spent))
                considered[promotion.id] = _Considered(
                    promotion, holding(promotion), available=False, reason=spent
                )
                continue
            holds = holding(promotion)
            considered[promotion.id] = _Considered(promotion, holds)
            # A line somebody priced by hand is left alone entirely. The
            # shared rule would discard the promotion downstream anyway;
            # skipping here is what stops the trace claiming a benefit the
            # line never received, which is the question this log exists to
            # answer.
            matched_lines = []
            for index in holds:
                if data.lines[index].caller_priced:
                    continue
                if not _allowed(data.lines[index].offers, promotion):
                    # A person chose this line's offers and left this one
                    # out (L7 step 5).
                    line_reasons[(promotion.id, index)] = "Not chosen on this line."
                    continue
                matched_lines.append(states[index])
            if not matched_lines:
                decisions.append(
                    self._decision(
                        promotion,
                        False,
                        (
                            "Every line was priced by hand."
                            if all(line.caller_priced for line in data.lines)
                            else (
                                "Not chosen on any line it meets."
                                if any(
                                    (promotion.id, index) in line_reasons
                                    for index in holds
                                )
                                else "No line met the conditions."
                            )
                        ),
                    )
                )
                continue

            if best_only:
                candidates.append((promotion, matched_lines))
                continue
            if apply_one(promotion, matched_lines):
                stopped_by = promotion

        if best_only and candidates:
            self._apply_best_per_line(
                candidates,
                states,
                data,
                decisions,
                apply_one,
                line_reasons=line_reasons,
            )
        if line_cap is not None and (mode == "ASK" or not best_only):
            # Under "ask" only a line whose offers a person ticked can carry
            # more than one, and the cap holds them (design 3.5).
            self._cap_lines(
                line_cap,
                states=states,
                slices=slices,
                applications=applications,
                applied_promotions=applied_promotions,
                decisions=decisions,
                only=(
                    None
                    if mode != "ASK"
                    else {
                        index
                        for index, line in enumerate(data.lines)
                        if line.offers is not None
                    }
                ),
            )
        for passed_over in self._gifts_passed_over.values():
            decisions.append(
                self._decision(
                    passed_over,
                    False,
                    "The product this offer gives away is not one of this "
                    "firm's products any more, so nothing was given.",
                )
            )
        self._gifts_passed_over = {}
        line_candidates, bill_candidates = self._candidates(
            list(considered.values()),
            states=states,
            data=data,
            decisions=decisions,
            applied_promotions=applied_promotions,
            slices=slices,
            free_slices=free_slices,
            bill_slices=bill_slices,
            gifts=gifts,
            freight_waived=freight_waived,
            contexts=contexts,
            line_reasons=line_reasons,
        )

        response = PromotionEvaluationResponse(
            lines=[
                PromotionLineOutcome(
                    line_number=state.line_number,
                    discount_amount=quantize_money(state.discount),
                    free_quantity=state.free_quantity,
                    free_promotion_id=state.free_promotion_id,
                    applied_promotion_codes=state.codes,
                    offers=_line_shares(
                        state,
                        slices=slices[index],
                        free_slices=free_slices[index],
                        applied_promotions=applied_promotions,
                    ),
                    candidates=line_candidates[index],
                )
                for index, state in enumerate(states)
            ],
            bill_discount_amount=quantize_money(bill_discount),
            bill_offers=[
                _share(applied_promotions[at], discount=quantize_money(amount))
                for at, amount in bill_slices
            ],
            freight_waived=freight_waived,
            applied_promotion_codes=applied,
            gifts=gifts,
            applied=applications,
            decisions=decisions,
            bill_candidates=bill_candidates,
        )
        if record:
            self._log(data, response, firm_scope=firm_scope)
        return response

    def record(
        self,
        data: PromotionEvaluationRequest,
        response: PromotionEvaluationResponse,
        *,
        firm_scope: UUID,
    ) -> None:
        """Log an answer `evaluate` was asked not to log (L7 step 5)."""
        self._log(data, response, firm_scope=firm_scope)

    def _candidates(
        self,
        considered: list[_Considered],
        *,
        states: list[_LineState],
        data: PromotionEvaluationRequest,
        decisions: list[PromotionDecision],
        applied_promotions: list[Promotion],
        slices: list[list[tuple[int, Decimal]]],
        free_slices: list[list[tuple[int, Decimal]]],
        bill_slices: list[tuple[int, Decimal]],
        gifts: list[PromotionGift],
        freight_waived: Decimal,
        contexts: list[dict[str, object]],
        line_reasons: dict[tuple[UUID, int], str] | None = None,
    ) -> tuple[list[list[OfferCandidate]], list[OfferCandidate]]:
        """List every offer looked at beside the lines, and under the bill (L7).

        Section 3.2 of the design. Worked out in memory from what evaluation
        already read: each offer is valued **alone** on fresh copies of the
        lines, free pieces at the line's own rate, so the list compares offers
        on one footing whatever was applied before them. The only statement
        is one read of the selling prices of the products offers give away,
        and only where an offer on the bill gives one.

        The "buy N more" hint (section 3.6, L7 step 4) is worked out here
        too, from the same contexts: an offer whose next round a line is
        short of carries it on its candidate, and one whose other conditions
        hold on a line short of its minimum quantity is listed there for the
        hint alone. Each line keeps its two nearest (`nearest_hints`).
        """
        applied_at = {row.id: at for at, row in enumerate(applied_promotions)}
        # The last reason the trace gave for not applying each offer.
        refused: dict[UUID, str] = {}
        for decision in decisions:
            if not decision.matched:
                refused[decision.promotion_id] = decision.reason
        per_line: list[list[OfferCandidate]] = [[] for _ in states]
        on_bill: list[tuple[Promotion, _Considered, Decimal, list[PromotionGift]]] = []
        for item in considered:
            promotion = item.promotion
            kinds = _action_kinds(promotion)
            gives = offer_gives(promotion)
            at = applied_at.get(promotion.id)
            reason = item.reason or (
                None if at is not None else refused.get(promotion.id)
            )
            if kinds & _LINE_ACTIONS:
                worths = self._worth_on_lines(promotion, item.lines, states)
                for index in item.lines:
                    state = states[index]
                    gave = at is not None and (
                        any(i == at and v > ZERO for i, v in slices[index])
                        or any(i == at and v > ZERO for i, v in free_slices[index])
                        or any(
                            gift.promotion_id == promotion.id
                            and gift.for_line_number == state.line_number
                            for gift in gifts
                        )
                    )
                    available, why = _line_reason(
                        item,
                        gave=gave,
                        applied=at is not None,
                        typed=data.lines[index].caller_priced,
                        free_typed=state.free_typed
                        and PromotionActionType.FREE_QUANTITY.value in kinds,
                        worth=worths[index],
                        reason=reason,
                        line_reason=(line_reasons or {}).get((promotion.id, index)),
                    )
                    hint = (
                        _hint(promotion, state, floor=None)
                        if available
                        and item.available
                        and not data.lines[index].caller_priced
                        else None
                    )
                    per_line[index].append(
                        _offer_candidate(
                            promotion,
                            gives=gives,
                            worth=worths[index],
                            applied=gave,
                            available=available,
                            reason=why,
                            hint=hint,
                        )
                    )
                if item.available:
                    for index, state in enumerate(states):
                        if index in item.lines or data.lines[index].caller_priced:
                            continue
                        floor = self._quantity_floor(promotion, contexts[index])
                        hint = (
                            None
                            if floor is None
                            else _hint(promotion, state, floor=floor)
                        )
                        if hint is None:
                            continue
                        # Listed for the hint alone: a hint cannot be chosen.
                        per_line[index].append(
                            _offer_candidate(
                                promotion,
                                gives=gives,
                                worth=ZERO,
                                applied=False,
                                available=False,
                                reason=f"{_units(hint[0])} more to earn it.",
                                hint=hint,
                            )
                        )
            if kinds & _BILL_ACTIONS and item.lines:
                value, given = self._worth_on_bill(promotion, item.lines, states, data)
                on_bill.append((promotion, item, value, given))
        # Valuing a gift asks whether the firm still holds it, which notes an
        # offer whose gift it does not; the trace has been written already.
        self._gifts_passed_over = {}
        prices = self._selling_prices(
            {gift.product_id for *_, given in on_bill for gift in given}
        )
        bill: list[OfferCandidate] = []
        for promotion, item, value, given in on_bill:
            kinds = _action_kinds(promotion)
            worth = quantize_money(
                value
                + sum(
                    (
                        gift.quantity * prices.get(gift.product_id, ZERO)
                        for gift in given
                        if gift.for_line_number is None
                    ),
                    ZERO,
                )
            )
            at = applied_at.get(promotion.id)
            gave = at is not None and (
                any(i == at and v > ZERO for i, v in bill_slices)
                or any(
                    gift.promotion_id == promotion.id and gift.for_line_number is None
                    for gift in gifts
                )
                or (
                    PromotionActionType.FREE_SHIPPING.value in kinds
                    and freight_waived > ZERO
                )
            )
            if gave:
                available, why = True, None
            elif not item.available:
                available, why = False, item.reason
            elif data.caller_priced_bill and kinds <= _BILL_DISCOUNTS:
                available, why = False, "A discount is typed on the whole bill."
            elif worth <= ZERO:
                available, why = True, "Nothing earned on this bill yet."
            else:
                available = True
                why = item.reason or refused.get(promotion.id) or "Not applied."
            bill.append(
                _offer_candidate(
                    promotion,
                    gives=offer_gives(promotion),
                    worth=worth,
                    applied=gave,
                    available=available,
                    reason=why,
                )
            )
        return [
            nearest_hints(listed, state.entered_quantity)
            for listed, state in zip(per_line, states, strict=True)
        ], bill

    def _quantity_floor(
        self, promotion: Promotion, context: dict[str, object]
    ) -> Decimal | None:
        """Return the stock quantity that would earn an offer a line misses.

        Only where the line's quantity is what it misses (L7 step 4): every
        other condition holds, and every quantity condition holds at the
        quantity returned -- the least that meets each "at least", "more
        than", "equal to" or "between". None where more of the same would
        not help, or where the offer states no quantity at all. A "more
        than" asks one whole unit more, as quantities are counted.
        """
        key = PromotionField.LINE_QUANTITY.value
        quantity = Decimal(str(context.get(key) or 0))
        floor: Decimal | None = None
        for condition in promotion.conditions:
            if str(getattr(condition, "field_key", "")) != key:
                if not self._condition_holds(condition, context):
                    return None
                continue
            if self._condition_holds(condition, context):
                continue
            least = _least_quantity(condition, self._expected(condition))
            if least is None or least <= quantity:
                return None
            floor = least if floor is None else max(floor, least)
        if floor is None:
            return None
        reached = {**context, key: floor}
        if not all(
            self._condition_holds(condition, reached)
            for condition in promotion.conditions
            if str(getattr(condition, "field_key", "")) == key
        ):
            return None
        return floor

    def _worth_on_lines(
        self, promotion: Promotion, lines: list[int], states: list[_LineState]
    ) -> dict[int, Decimal]:
        """Return what this offer alone takes off each line it holds on.

        Applied to fresh copies, with nothing given yet and nothing on the
        bill: free units at the line's own rate, a free product never (that
        is the bill's). No statement is made.
        """
        fresh = [state.fresh() for state in states]
        self._apply(
            promotion,
            matched=[fresh[index] for index in lines],
            states=fresh,
            bill_discount=ZERO,
            allow_bill=False,
            gifts=None,
        )
        worth: dict[int, Decimal] = {}
        for index in lines:
            state = fresh[index]
            value = state.discount
            if state.free_quantity > ZERO and state.entered_quantity > ZERO:
                value += state.free_quantity * state.gross / state.entered_quantity
            worth[index] = quantize_money(value)
        return worth

    def _worth_on_bill(
        self,
        promotion: Promotion,
        lines: list[int],
        states: list[_LineState],
        data: PromotionEvaluationRequest,
    ) -> tuple[Decimal, list[PromotionGift]]:
        """Return what this offer alone takes off the bill, and what it gives.

        The bill discount and the waived delivery in money; the products it
        gives away are returned for the caller to price in one read.
        """
        fresh = [state.fresh() for state in states]
        given: list[PromotionGift] = []
        added_bill, waives = self._apply(
            promotion,
            matched=[fresh[index] for index in lines],
            states=fresh,
            bill_discount=ZERO,
            allow_bill=not data.caller_priced_bill,
            gifts=given,
        )
        value = added_bill + (quantize_money(data.freight_amount) if waives else ZERO)
        return value, given

    def _selling_prices(self, product_ids: set[UUID]) -> dict[UUID, Decimal]:
        """Read the selling price of each product given away, in one statement."""
        if not product_ids:
            return {}
        return {
            product_id: Decimal(str(price or 0))
            for product_id, price in self._session.execute(
                select(Product.id, Product.selling_price).where(
                    Product.id.in_(product_ids)
                )
            ).all()
        }

    def _offer_uses(
        self,
        promotions: Sequence[Promotion],
        *,
        firm_scope: UUID,
        customer_id: UUID | None,
        coupon_id: UUID | None,
    ) -> dict[UUID, _OfferUse]:
        """Read every offer's claims and budget use in one statement (L7 step 3).

        Keyed by version group: an offer's claims are counted across every
        revision of it, so an edit cannot make a spent campaign new again.
        Counted from CLAIMED rows only, through `claims_given`, the statement
        every reader of an offer's use shares -- so the figures here are the
        ones its budget and its reports state. A document with no offer in
        force asks nothing.
        """
        groups = {row.version_group_id for row in promotions}
        if not groups:
            return {}
        given = claims_given(
            firm_scope, PromotionRedemption.status == "CLAIMED", groups=groups
        ).subquery()
        mine = (
            given.c.customer_id == customer_id if customer_id is not None else false()
        )
        coupon = given.c.coupon_id == coupon_id if coupon_id is not None else false()

        def counted(condition: ColumnElement[bool]) -> ColumnElement[int]:
            """Count the claims a condition holds for, as a column."""
            return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)

        uses: dict[UUID, _OfferUse] = {}
        for (
            group,
            claims,
            by_customer,
            by_coupon,
            both,
            amount,
            free,
        ) in self._session.execute(
            select(
                given.c.version_group_id,
                func.count(),
                counted(mine),
                counted(coupon),
                counted(and_(mine, coupon)),
                func.coalesce(func.sum(given.c.benefit_given), 0),
                func.coalesce(func.sum(given.c.free_given), 0),
            ).group_by(given.c.version_group_id)
        ).all():
            uses[group] = _OfferUse(
                claims=int(claims or 0),
                by_customer=int(by_customer or 0),
                by_coupon=int(by_coupon or 0),
                by_coupon_customer=int(both or 0),
                amount=Decimal(str(amount)),
                # At the four places a quantity holds (D-PRC-57).
                free=at_quantity_scale(free),
            )
        return uses

    def _active_promotions(self, *, firm_scope: UUID, on: date) -> list[Promotion]:
        """Return the promotions in force on that date, in application order.

        Ordered exactly as the tax engine orders its rules. The window is
        judged against the **document's** date rather than today's, so an offer
        that ran in April still explains an April order in September.
        """
        rows = self._session.scalars(
            select(Promotion)
            # Every offer's conditions and actions in two statements, not two
            # per offer: each is matched against every line (L7 step 3).
            .options(
                selectinload(Promotion.conditions), selectinload(Promotion.actions)
            )
            .where(
                Promotion.firm_id == firm_scope,
                Promotion.is_deleted.is_(False),
                Promotion.status == PromotionStatus.ACTIVE.value,
            )
            .order_by(
                Promotion.priority.asc(),
                Promotion.code.asc(),
                Promotion.version_number.desc(),
                Promotion.created_at.asc(),
            )
        ).all()
        in_force = [
            row
            for row in rows
            if (row.effective_from is None or on >= row.effective_from)
            and (row.effective_to is None or on <= row.effective_to)
        ]
        # One offer, however many revisions it has had. Superseding retires the
        # predecessor, but a store that ends up with two live versions of one
        # promotion must still give the benefit once -- the tax engine survives
        # that state only because it stops at the first match, and a stacking
        # engine would hand the customer the same offer twice.
        #
        # The window filter runs first on purpose: a document dated inside the
        # old version's window and outside the new one's keeps the old version,
        # which is what stops an edit repricing a document already dated.
        newest: dict[UUID, Promotion] = {}
        for row in in_force:
            seen = newest.get(row.version_group_id)
            if seen is None or row.version_number > seen.version_number:
                newest[row.version_group_id] = row
        return [row for row in in_force if newest[row.version_group_id] is row]

    def _coupon_for(
        self, data: PromotionEvaluationRequest, *, firm_scope: UUID
    ) -> PromotionCoupon | None:
        """Return the live coupon the document presented, if it presented one.

        A code that names nothing, or names something out of its window, is not
        an error here: the promotion it would have reached simply does not
        apply, and the trace says which. Refusing the whole document would stop
        an order being saved because of a typo in a field that gives money
        away.
        """
        code = (data.coupon_code or "").strip().upper()
        if not code:
            return None
        row = self._session.scalar(
            select(PromotionCoupon).where(
                PromotionCoupon.firm_id == firm_scope,
                PromotionCoupon.code == code,
                PromotionCoupon.is_deleted.is_(False),
                PromotionCoupon.status == PromotionStatus.ACTIVE.value,
            )
        )
        if row is None:
            return None
        on = data.transaction_date
        if row.effective_from is not None and on < row.effective_from:
            return None
        if row.effective_to is not None and on > row.effective_to:
            return None
        return row

    def _unavailable(
        self,
        promotion: Promotion,
        *,
        coupon: PromotionCoupon | None,
        data: PromotionEvaluationRequest,
        firm_scope: UUID,
        use: _OfferUse,
    ) -> str | None:
        """Say why this promotion is out of reach, or nothing if it is not.

        Checked before the conditions, because "you did not present the code"
        and "your order does not qualify" are different answers and a firm
        chasing an offer that did not fire needs to know which.

        A limit is counted from the redemption ledger rather than from a
        counter on the promotion. A counter would have to be written while the
        document is priced, and pricing must never commit -- so it would either
        publish a half-written order or count a draft that is edited five more
        times and never approved. The counts were read for every offer at
        once (`_offer_uses`), across each offer's whole version group: counting
        by row id gave a successor a count of zero, and an exhausted campaign
        became available again on a one-character edit.
        """
        reaches = coupon is not None and self._coupon_reaches(
            coupon, promotion, firm_scope=firm_scope
        )
        if promotion.requires_coupon and not reaches:
            return "This offer is claimed with a coupon, and none was presented."
        if (
            promotion.max_redemptions is not None
            and use.claims >= promotion.max_redemptions
        ):
            return "This offer has been claimed as often as it allows."
        if (
            promotion.max_redemptions_per_customer is not None
            and data.customer_id
            and use.by_customer >= promotion.max_redemptions_per_customer
        ):
            return "This customer has claimed this offer as often as they may."
        if coupon is not None and reaches:
            if (
                coupon.max_redemptions is not None
                and use.by_coupon >= coupon.max_redemptions
            ):
                return "This coupon has been used as often as it allows."
            if (
                coupon.max_redemptions_per_customer is not None
                and data.customer_id
                and use.by_coupon_customer >= coupon.max_redemptions_per_customer
            ):
                return "This customer has used this coupon as often as they may."
        return None

    def _coupon_reaches(
        self,
        coupon: PromotionCoupon,
        promotion: Promotion,
        *,
        firm_scope: UUID,
    ) -> bool:
        """Whether this code is one that claims this offer.

        A coupon names a promotion **row**, and a published promotion is
        superseded rather than edited -- so comparing row ids meant every
        edit to a coupon-gated offer silently orphaned every code in
        circulation, while the coupon list went on showing them ACTIVE. The
        offer's identity is its version group, so that is what a code has to
        match.
        """
        if coupon.promotion_id == promotion.id:
            return True
        group = self._session.scalar(
            select(Promotion.version_group_id).where(
                Promotion.id == coupon.promotion_id,
                Promotion.firm_id == firm_scope,
            )
        )
        return group is not None and group == promotion.version_group_id

    def _customer_history(
        self, data: PromotionEvaluationRequest
    ) -> tuple[int, int | None]:
        """Return the customer's approved bills by the date, and days since the last.

        SEL-6, read once per document. Only approved and closed bills count:
        a draft is not an order, and a cancelled bill was undone.
        """
        if data.customer_id is None:
            return 0, None
        from sqlalchemy import func

        from app.sales_invoice.models import SalesInvoice

        count, last = self._session.execute(
            select(
                func.count(SalesInvoice.id), func.max(SalesInvoice.invoice_date)
            ).where(
                SalesInvoice.customer_id == data.customer_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status.in_(("APPROVED", "CLOSED")),
                SalesInvoice.invoice_date <= data.transaction_date,
            )
        ).one()
        days = None if last is None else (data.transaction_date - last).days
        return int(count or 0), days

    def _products_for(
        self, data: PromotionEvaluationRequest
    ) -> dict[UUID, tuple[UUID | None, str | None]]:
        """Read every line's category and type in one query, never per line."""
        ids = {line.product_id for line in data.lines if line.product_id is not None}
        if not ids:
            return {}
        rows = self._session.execute(
            select(Product.id, Product.category_id, Product.product_type).where(
                Product.id.in_(ids)
            )
        ).all()
        return {row[0]: (row[1], row[2]) for row in rows}

    def _context(
        self,
        data: PromotionEvaluationRequest,
        *,
        line: object,
        state: _LineState,
        document_gross: Decimal,
        products: dict[UUID, tuple[UUID | None, str | None]],
        history: tuple[int, int | None] = (0, None),
    ) -> dict[str, object]:
        """Build what one line is matched against.

        Header keys and line keys together, so a promotion scoped only to a
        customer matches every line, and one scoped to a product matches the
        lines carrying it.
        """
        product_id: UUID | None = getattr(line, "product_id", None)
        missing: tuple[UUID | None, str | None] = (None, None)
        category_id, product_type = (
            products.get(product_id, missing) if product_id is not None else missing
        )
        return {
            PromotionField.CUSTOMER_ID.value: data.customer_id,
            PromotionField.CUSTOMER_GROUP_ID.value: data.customer_group_id,
            PromotionField.BRANCH_ID.value: data.branch_id,
            PromotionField.TERRITORY_ID.value: data.territory_id,
            PromotionField.ROUTE_ID.value: data.route_id,
            PromotionField.SALESMAN_ID.value: data.salesman_id,
            PromotionField.PRODUCT_ID.value: product_id,
            PromotionField.PRODUCT_CATEGORY_ID.value: category_id,
            PromotionField.PRODUCT_TYPE.value: product_type,
            PromotionField.LINE_QUANTITY.value: state.quantity,
            PromotionField.LINE_GROSS.value: state.gross,
            PromotionField.DOCUMENT_GROSS.value: document_gross,
            PromotionField.TRANSACTION_TYPE.value: data.transaction_type,
            PromotionField.TRANSACTION_DATE.value: data.transaction_date,
            PromotionField.WEEKDAY.value: data.transaction_date.isoweekday(),
            PromotionField.TIME_OF_DAY.value: minutes_of_day_in_india(
                data.transaction_time
            ),
            PromotionField.CUSTOMER_ORDER_COUNT.value: (
                history[0] if data.customer_id is not None else None
            ),
            PromotionField.DAYS_SINCE_LAST_ORDER.value: history[1],
        }

    def _matches(self, promotion: Promotion, *, context: dict[str, object]) -> bool:
        """Report whether every condition holds. No conditions means always."""
        return all(
            self._condition_holds(condition, context)
            for condition in promotion.conditions
        )

    def _condition_holds(self, condition: object, context: dict[str, object]) -> bool:
        """Compare one context value against one stored condition."""
        actual = context.get(str(getattr(condition, "field_key", "")))
        operator = str(getattr(condition, "operator", ""))
        if operator == PromotionConditionOperator.EXISTS.value:
            return actual is not None
        if operator == PromotionConditionOperator.NOT_EXISTS.value:
            return actual is None
        if actual is None:
            return False
        if operator in {
            PromotionConditionOperator.IN.value,
            PromotionConditionOperator.NOT_IN.value,
        }:
            listed = {
                str(item) for item in (getattr(condition, "value_json", None) or [])
            }
            inside = str(actual) in listed
            return (
                inside
                if operator == PromotionConditionOperator.IN.value
                else not inside
            )
        if operator == PromotionConditionOperator.BETWEEN.value:
            bounds = getattr(condition, "value_json", None) or []
            if len(bounds) != 2:
                return False
            low, high = (Decimal(str(bounds[0])), Decimal(str(bounds[1])))
            return low <= Decimal(str(actual)) <= high

        expected = self._expected(condition)
        if expected is None:
            return False
        if operator in {
            PromotionConditionOperator.EQUALS.value,
            PromotionConditionOperator.NOT_EQUALS.value,
        }:
            # A count or a quantity is equal as a number: 0 is 0.0000 (SEL-6).
            if isinstance(actual, int | Decimal) and not isinstance(actual, bool):
                try:
                    same = Decimal(str(actual)) == Decimal(str(expected))
                except (ArithmeticError, TypeError, ValueError):
                    same = False
            else:
                same = str(actual) == str(expected)
            return (
                same
                if operator == PromotionConditionOperator.EQUALS.value
                else (not same)
            )
        # The four comparisons are numeric or date; anything else cannot be
        # ordered and is treated as not matching rather than raising, because a
        # bad condition must not make a document unsaveable.
        try:
            left = actual if isinstance(actual, date) else Decimal(str(actual))
            right = expected if isinstance(expected, date) else Decimal(str(expected))
        except (ArithmeticError, TypeError, ValueError):
            return False
        if type(left) is not type(right):
            return False
        if operator == PromotionConditionOperator.GREATER_THAN.value:
            return left > right  # type: ignore[operator]
        if operator == PromotionConditionOperator.GREATER_OR_EQUAL.value:
            return left >= right  # type: ignore[operator]
        if operator == PromotionConditionOperator.LESS_THAN.value:
            return left < right  # type: ignore[operator]
        if operator == PromotionConditionOperator.LESS_OR_EQUAL.value:
            return left <= right  # type: ignore[operator]
        return False

    @staticmethod
    def _expected(condition: object) -> object | None:
        """Return whichever typed value column this condition filled in."""
        for name in ("value_text", "value_number", "value_date", "value_boolean"):
            value: object | None = getattr(condition, name, None)
            if value is not None:
                return value
        return None

    def _apply_best_per_line(
        self,
        candidates: list[tuple[Promotion, list[_LineState]]],
        states: list[_LineState],
        data: PromotionEvaluationRequest,
        decisions: list[PromotionDecision],
        apply_one: Callable[..., bool | None],
        *,
        line_reasons: dict[tuple[UUID, int], str],
    ) -> None:
        """Give each line the one offer worth most on it (L7 decision 2).

        Judged **per line**: an offer on a line's own goods is valued on
        that line alone, and the most valuable applied there, a tie going
        to the one earlier in "Applies at" order. Each winner is applied
        once, to every line it won. Offers on the whole bill -- a bill
        discount, free delivery, a gift, a combo across lines -- are then
        judged among themselves (`_apply_best`), after the lines.

        A line whose offers a person named takes every one named, combined
        as each allows: one that does not stack closes the line to the
        offers after it. An offer whose budget cannot cover this document
        is passed over and its lines fall to their next best -- among the
        offers not yet applied elsewhere, since an offer is applied once.
        """
        per_line = [
            (promotion, matched)
            for promotion, matched in candidates
            if _action_kinds(promotion) <= _PER_LINE_ACTIONS
        ]
        whole = [
            (promotion, matched)
            for promotion, matched in candidates
            if not _action_kinds(promotion) <= _PER_LINE_ACTIONS
        ]
        position = {id(state): index for index, state in enumerate(states)}
        worths: dict[tuple[UUID, int], Decimal] = {
            (promotion.id, position[id(state)]): self._worth_alone(
                promotion, [state], states, data
            )
            for promotion, matched in per_line
            for state in matched
        }
        lost: dict[UUID, str] = {}
        done: set[UUID] = set()
        given: set[UUID] = set()
        closed_by: dict[int, Promotion] = {}

        def plan(lines: list[int]) -> dict[UUID, list[int]]:
            """Return, by offer, the lines it is to be applied to."""
            taken: dict[UUID, list[int]] = {}
            for index in lines:
                offers = [
                    (promotion, worths[(promotion.id, index)])
                    for promotion, _ in per_line
                    if (promotion.id, index) in worths and promotion.id not in done
                ]
                if not offers:
                    continue
                if data.lines[index].offers is not None:
                    for promotion, _ in offers:
                        taken.setdefault(promotion.id, []).append(index)
                    continue
                top = max(value for _, value in offers)
                winner = next(promotion for promotion, value in offers if value == top)
                taken.setdefault(winner.id, []).append(index)
                for promotion, value in offers:
                    if promotion is winner:
                        continue
                    reason = (
                        f"Best offer only: {winner.code} was worth more "
                        f"({quantize_ledger(top)} against {quantize_ledger(value)}) "
                        f"on line {states[index].line_number}."
                    )
                    line_reasons[(promotion.id, index)] = reason
                    lost[promotion.id] = reason
            return taken

        lines = list(range(len(states)))
        while lines:
            taken = plan(lines)
            orphans: list[int] = []
            for promotion, _ in per_line:
                if promotion.id not in taken:
                    continue
                targets: list[int] = []
                for index in taken[promotion.id]:
                    closer = closed_by.get(index)
                    if closer is None:
                        targets.append(index)
                    else:
                        line_reasons[(promotion.id, index)] = (
                            f"Does not combine with {closer.code}."
                        )
                done.add(promotion.id)
                if not targets:
                    continue
                result = apply_one(
                    promotion, [states[index] for index in targets], stops=False
                )
                if result is None:
                    orphans += [
                        index for index in targets if data.lines[index].offers is None
                    ]
                    continue
                given.add(promotion.id)
                if not promotion.allow_stacking:
                    for index in targets:
                        closed_by.setdefault(index, promotion)
            lines = orphans
        for promotion, _ in per_line:
            if promotion.id not in given and promotion.id in lost:
                decisions.append(self._decision(promotion, False, lost[promotion.id]))
        if whole:
            self._apply_best(whole, states, data, decisions, apply_one)

    def _apply_best(
        self,
        candidates: list[tuple[Promotion, list[_LineState]]],
        states: list[_LineState],
        data: PromotionEvaluationRequest,
        decisions: list[PromotionDecision],
        apply_one: Callable[..., bool | None],
    ) -> None:
        """Give only the single offer worth most (backlog 59).

        Each candidate is valued on its own; the most valuable is applied,
        a tie going to the one earlier in "Applies at" order, and every other
        candidate is recorded with what it was worth against the winner. An
        offer whose budget cannot cover this document is passed over, and the
        next most valuable is then the best there is.
        """
        worth = [
            (promotion, matched, self._worth_alone(promotion, matched, states, data))
            for promotion, matched in candidates
        ]
        while True:
            top = max(value for _, _, value in worth)
            winner = next(item for item in worth if item[2] == top)
            if apply_one(winner[0], winner[1]) is not None:
                break
            worth.remove(winner)
            if not worth:
                return
        for promotion, _matched, value in worth:
            if promotion is winner[0]:
                continue
            decisions.append(
                self._decision(
                    promotion,
                    False,
                    f"Best offer only: {winner[0].code} was worth more "
                    f"({quantize_ledger(top)} against {quantize_ledger(value)}).",
                )
            )

    def promotion_mode(self, firm_scope: UUID) -> str:
        """Return the firm's ``promotion_mode``; COMBINE where none is set."""
        return self._promotion_policy(firm_scope)[0]

    def _promotion_policy(self, firm_scope: UUID) -> tuple[str, Decimal | None]:
        """Return (promotion mode, combined line cap %) for the firm (backlog 59).

        A firm with no settings row combines with no cap, as offers always
        have. The cap is read in Combine mode, and in Ask mode for the lines
        a person ticked more than one on: a single best offer is already
        one offer.
        """
        from app.sales_order.models import SalesWorkflowSettings

        row = self._session.execute(
            select(
                SalesWorkflowSettings.promotion_mode,
                SalesWorkflowSettings.max_line_discount_percent,
            ).where(
                SalesWorkflowSettings.firm_id == firm_scope,
                SalesWorkflowSettings.is_deleted.is_(False),
            )
        ).first()
        if row is None:
            return "COMBINE", None
        mode = str(row[0] or "COMBINE")
        cap = row[1]
        # ASK (L7) starts a line where best one only does; what the bill
        # maker ticks beyond that is a choice, held to the cap.
        if mode == "BEST_OFFER":
            return mode, None
        return mode, (None if cap is None else Decimal(str(cap)))

    def _cap_lines(
        self,
        cap_percent: Decimal,
        *,
        states: list[_LineState],
        slices: list[list[tuple[int, Decimal]]],
        applications: list[PromotionApplication],
        applied_promotions: list[Promotion],
        decisions: list[PromotionDecision],
        only: set[int] | None = None,
    ) -> None:
        """Hold each line's combined offer discount to the firm's cap.

        Backlog 59 item 3. Offers compound, so the one applied last added the
        last slice; it is trimmed first, then the one before it. Each trimmed
        offer's ``benefit_amount`` falls by what was taken back, so a
        campaign is costed at what it actually gave. The bill discount is not
        a line discount and is left alone.
        """
        for index, state in enumerate(states):
            if only is not None and index not in only:
                continue
            limit = quantize_money(state.gross * cap_percent / HUNDRED)
            excess = state.discount - limit
            if excess <= ZERO:
                continue
            trimmed_from: list[str] = []
            for position in reversed(range(len(slices[index]))):
                application_index, slice_amount = slices[index][position]
                if excess <= ZERO:
                    break
                take = min(slice_amount, excess)
                state.discount -= take
                excess -= take
                # Kept trimmed, so each offer's share of the line is what it
                # gave after the cap (L7 step 2).
                slices[index][position] = (application_index, slice_amount - take)
                application = applications[application_index]
                application.benefit_amount = quantize_money(
                    application.benefit_amount - take
                )
                trimmed_from.append(application.code)
            if not trimmed_from:
                continue
            last = applied_promotions[next(i for i, _ in reversed(slices[index]))]
            decisions.append(
                self._decision(
                    last,
                    True,
                    f"Line {state.line_number}: offers combined past the "
                    f"firm's cap of {cap_percent.normalize():f}% of the line, so "
                    f"its discount was held at {quantize_ledger(limit)} "
                    f"(trimmed from {', '.join(trimmed_from)}).",
                )
            )

    def _worth_alone(
        self,
        promotion: Promotion,
        matched: list[_LineState],
        states: list[_LineState],
        data: PromotionEvaluationRequest,
    ) -> Decimal:
        """Return what this offer would take off the document on its own.

        Applied to a fresh copy of the lines, so candidates are compared on
        the same footing. Free goods are worth what they would have been
        charged -- free units of a line at that line's own rate, a free
        product at its selling price -- and a waived delivery at its charge.
        """
        copies = {id(state): replace(state, codes=[]) for state in states}
        fresh = [copies[id(state)] for state in states]
        gifts: list[PromotionGift] = []
        added_bill, waives = self._apply(
            promotion,
            matched=[copies[id(state)] for state in matched],
            states=fresh,
            bill_discount=ZERO,
            allow_bill=not data.caller_priced_bill,
            gifts=gifts,
        )
        value = sum((state.discount for state in fresh), ZERO) + added_bill
        for state in fresh:
            if state.free_quantity > ZERO and state.entered_quantity > ZERO:
                value += state.free_quantity * state.gross / state.entered_quantity
        if gifts:
            prices: dict[UUID, Decimal | None] = {
                product_id: price
                for product_id, price in self._session.execute(
                    select(Product.id, Product.selling_price).where(
                        Product.id.in_([gift.product_id for gift in gifts])
                    )
                ).all()
            }
            for gift in gifts:
                value += gift.quantity * Decimal(str(prices.get(gift.product_id) or 0))
        if waives:
            value += data.freight_amount
        return value

    def _apply(
        self,
        promotion: Promotion,
        *,
        matched: list[_LineState],
        states: list[_LineState],
        bill_discount: Decimal,
        allow_bill: bool = True,
        gifts: list[PromotionGift] | None = None,
    ) -> tuple[Decimal, bool]:
        """Give this promotion's benefits, and return what it took off the bill.

        Every percentage is taken off what is **left**, which is what stops
        stacked benefits from ever exceeding the line.
        """
        added_bill = ZERO
        waives_freight = False
        for action in promotion.actions:
            params = action.parameters or {}
            kind = action.action_type
            if kind == PromotionActionType.LINE_DISCOUNT_PERCENT.value:
                rate = Decimal(str(params.get("percent", 0)))
                shares = [
                    quantize_money(state.remaining * rate / HUNDRED)
                    for state in matched
                ]
                cap = _cap(params)
                if cap is not None and sum(shares, ZERO) > cap:
                    # "20% off, up to 500" caps the offer on the document,
                    # not on each line: the cap is spread over the lines in
                    # proportion to what each would have had, so the shares
                    # still sum exactly to it.
                    shares = apportion(cap, shares)
                for state, share in zip(matched, shares, strict=True):
                    state.discount += share
            elif kind == PromotionActionType.LINE_DISCOUNT_AMOUNT.value:
                amount = Decimal(str(params.get("amount", 0)))
                for state in matched:
                    state.discount += min(quantize_money(amount), state.remaining)
            elif kind == PromotionActionType.FREE_QUANTITY.value:
                buy = Decimal(str(params.get("buy_quantity", 0)))
                free = Decimal(str(params.get("free_quantity", 0)))
                if buy > ZERO:
                    for state in matched:
                        # Whole multiples only: buying nineteen on a "ten get
                        # one" earns one free unit, not one and nine tenths.
                        # Counted in stock units: 2 BOX of 12 are 24 bought.
                        times = int(state.quantity // buy)
                        if times > 0 and not state.free_typed:
                            self._give_free(
                                state, free * times, promotion=promotion, gifts=gifts
                            )
            elif kind == PromotionActionType.BUY_X_GET_Y_DISCOUNT.value:
                buy = Decimal(str(params.get("buy_quantity", 0) or 0))
                get = Decimal(str(params.get("free_quantity", 0) or 0))
                rate = Decimal(str(params.get("percent", 0) or 0))
                if buy <= ZERO or get <= ZERO or rate <= ZERO:
                    continue
                shares = []
                for state in matched:
                    # Whole groups only, per line, as FREE_QUANTITY counts:
                    # three bought on "buy 1 get 1" is one group and a spare.
                    times = int(state.quantity // (buy + get))
                    if times <= 0 or state.quantity <= ZERO:
                        shares.append(ZERO)
                        continue
                    # At what each unit has left after earlier benefits, so
                    # stacked offers still cannot take more than the line.
                    unit = state.remaining / state.quantity
                    shares.append(
                        min(
                            quantize_money(get * times * unit * rate / HUNDRED),
                            state.remaining,
                        )
                    )
                cap = _cap(params)
                if cap is not None and sum(shares, ZERO) > cap:
                    shares = apportion(cap, shares)
                for state, share in zip(matched, shares, strict=True):
                    state.discount += share
            elif kind == PromotionActionType.COMBO_PRICE.value:
                for state, share in _combo_saving(params, matched):
                    state.discount += share
            elif kind == PromotionActionType.FREE_PRODUCT.value:
                gift_id = params.get("free_product_id")
                free = _number(params, "free_quantity")
                if gifts is None or gift_id in (None, "None") or free <= ZERO:
                    continue
                gift_product = self._gift_product(gift_id, promotion)
                if gift_product is None:
                    continue
                # No threshold is stored as the text "None": give it once.
                threshold = _number(params, "buy_quantity")
                if threshold > ZERO:
                    # Counted across the lines the offer matched, not per line:
                    # "buy ten of these, get one of those" is a statement about
                    # the order, and ten bought as two lines of five is still
                    # ten. Whole multiples only, as `FREE_QUANTITY` does.
                    bought = sum((state.quantity for state in matched), ZERO)
                    times = int(bought // threshold)
                    if times <= 0:
                        continue
                    free = free * times
                gifts.append(
                    PromotionGift(
                        product_id=gift_product,
                        quantity=free,
                        promotion_code=promotion.code,
                        promotion_id=promotion.id,
                    )
                )
            elif allow_bill and kind in {
                PromotionActionType.BILL_DISCOUNT_PERCENT.value,
                PromotionActionType.BILL_DISCOUNT_AMOUNT.value,
            }:
                taxable = sum((s.remaining for s in states), ZERO) - (
                    bill_discount + added_bill
                )
                if taxable <= ZERO:
                    continue
                if kind == PromotionActionType.BILL_DISCOUNT_PERCENT.value:
                    rate = Decimal(str(params.get("percent", 0)))
                    off = quantize_money(taxable * rate / HUNDRED)
                    cap = _cap(params)
                    added_bill += off if cap is None else min(off, cap)
                else:
                    amount = Decimal(str(params.get("amount", 0)))
                    added_bill += min(quantize_money(amount), taxable)
            elif kind == PromotionActionType.FREE_SHIPPING.value:
                # Nothing to compute: the charge is waived whole or not at
                # all, and how much it was is the document's business rather
                # than the offer's.
                waives_freight = True
        return added_bill, waives_freight

    @staticmethod
    def _give_free(
        state: _LineState,
        earned: Decimal,
        *,
        promotion: Promotion,
        gifts: list[PromotionGift] | None,
    ) -> None:
        """Give a line the free units it earned, losing and inventing none.

        ``earned`` is in stock units, as the offer states it. Where that is a
        whole number of the line's own unit it goes on the line -- 24 pieces
        on a line sold by the box of 12 are 2 BOX free -- and where it is not
        (2 pieces on that line) it is a **free line of the same product in
        the stock unit**, handed to the document the way a gift of another
        product is. A line sold in its stock unit takes the figure as it is.
        """
        factor = state.stock_factor
        if factor == Decimal("1"):
            state.free_quantity += earned
            state.free_stock += earned
            return
        in_line = quantize_money(earned / factor)
        whole = in_line == in_line.to_integral_value() and in_line > ZERO
        if whole or gifts is None or state.product_id is None:
            state.free_quantity += in_line
            state.free_stock += earned
            return
        gifts.append(
            PromotionGift(
                product_id=state.product_id,
                quantity=earned,
                promotion_code=promotion.code,
                promotion_id=promotion.id,
                for_line_number=state.line_number,
            )
        )

    def _gift_product(self, gift_id: object, promotion: Promotion) -> UUID | None:
        """Return the product an offer gives away, if the firm still has it.

        An offer is checked when it is written (`assert_offer_references`),
        but a product can be retired afterwards and a row can reach the store
        some other way. A gift of a product the firm does not hold used to be
        handed to the document, which then failed with a 500 on every
        matching order (D-PRC-5); it is passed over instead, and the trace
        says so. Asked once per product for the evaluation.
        """
        key = str(gift_id)
        if key not in self._gift_products:
            found = live_row_ids(
                self._session, Product, [key], firm_id=promotion.firm_id
            )
            self._gift_products[key] = next(iter(found), None)
        product_id = self._gift_products[key]
        if product_id is None:
            self._gifts_passed_over[promotion.id] = promotion
        return product_id

    @staticmethod
    def _decision(
        promotion: Promotion, matched: bool, reason: str
    ) -> PromotionDecision:
        """Record why one promotion did or did not apply."""
        return PromotionDecision(
            promotion_id=promotion.id,
            code=promotion.code,
            priority=promotion.priority,
            matched=matched,
            reason=reason,
        )

    def _log(
        self,
        data: PromotionEvaluationRequest,
        response: PromotionEvaluationResponse,
        *,
        firm_scope: UUID,
    ) -> None:
        """Record what was asked, what was considered, and what was given.

        Staged, never committed -- the caller's transaction owns it, so a
        document that is refused leaves no log claiming it was priced.
        """
        self._session.add(
            PromotionExecutionLog(
                firm_id=firm_scope,
                transaction_type=data.transaction_type,
                document_date=data.transaction_date,
                customer_id=data.customer_id,
                input_payload=data.model_dump(mode="json"),
                evaluation_trace={
                    "decisions": [
                        item.model_dump(mode="json") for item in response.decisions
                    ]
                },
                # The candidates are the screen's, not the trace's: what
                # was decided is in the decisions above.
                result_payload=response.model_dump(
                    mode="json",
                    exclude={
                        "bill_candidates": True,
                        "lines": {"__all__": {"candidates"}},
                    },
                ),
            )
        )
        self._session.flush()


@dataclass(frozen=True, slots=True)
class BudgetRoom:
    """What is left of an offer's budget in money and in free units.

    One answer for pricing and for approval, so the two cannot disagree about
    whether a document fits. Counted from CLAIMED redemptions across the
    offer's version group, as the number of claims is: a draft has taken
    nothing, a cancelled document gave its part back, an order closed short
    gave back what it never delivered, and an edit does not refill a budget.
    """

    max_amount: Decimal | None
    amount_claimed: Decimal
    max_free: Decimal | None
    free_claimed: Decimal

    @property
    def amount_left(self) -> Decimal | None:
        """What the money budget still has, never below zero; None if none."""
        if self.max_amount is None:
            return None
        return max(self.max_amount - self.amount_claimed, ZERO)

    @property
    def free_left(self) -> Decimal | None:
        """How many free units are still to give; None if there is no budget."""
        if self.max_free is None:
            return None
        return max(self.max_free - self.free_claimed, ZERO)

    def spent(self) -> str | None:
        """Say which budget has nothing left, or nothing if both have room."""
        if self.max_amount is not None and self.amount_left == ZERO:
            return (
                f"This offer's budget of {quantize_ledger(self.max_amount)} has "
                "all been given."
            )
        if self.max_free is not None and self.free_left == ZERO:
            return (
                f"This offer's budget of {_units(self.max_free)} free units has "
                "all been given."
            )
        return None

    def overrun(self, amount: Decimal, free: Decimal) -> str | None:
        """Say which budget this much would overrun, or nothing if it fits.

        The answer is the rest of a sentence about the offer: "has 20.00 left
        of its budget of 50.00, and this document would take 40.00." A claim
        fits whole or not at all -- giving only the part that is left would
        price the document at a discount no offer states.
        """
        left = self.amount_left
        if left is not None and (left == ZERO or amount > left):
            return (
                f"has {quantize_ledger(left)} left of its budget of "
                f"{quantize_ledger(self.max_amount)}, and this document would "
                f"take {quantize_ledger(amount)}."
            )
        free_left = self.free_left
        if free_left is not None and (free_left == ZERO or free > free_left):
            return (
                f"has {_units(free_left)} left of its budget of "
                f"{_units(self.max_free)} free units, and this document would "
                f"take {_units(free)}."
            )
        return None


def _units(quantity: Decimal | None) -> str:
    """Spell a quantity without trailing zeroes: 500, not 500.0000."""
    return plain_quantity(quantity)


def budget_rooms(
    session: Session, promotions: Sequence[Promotion], *, firm_id: UUID
) -> dict[UUID, BudgetRoom]:
    """Return what each offer's budget has left, keyed by promotion id.

    One statement for the whole list, never one per offer: a page of offers
    asks once. What was given is counted whether or not there is a budget,
    because "how much has this offer given" is worth showing either way.

    Summed from `claims_given`, the one statement every reader of an offer's
    use shares: what each claim took, less what an order closed short gave
    back (D-PRC-28), less the free units a completed return brought back
    (D-PRC-8) and the discount on goods that came back or were credited
    (D-PRC-45).
    """
    budgeted = {row.version_group_id for row in promotions}
    claimed: dict[UUID, tuple[Decimal, Decimal]] = {}
    if budgeted:
        given = claims_given(
            firm_id, PromotionRedemption.status == "CLAIMED", groups=budgeted
        ).subquery()
        for group, amount, free in session.execute(
            select(
                given.c.version_group_id,
                func.coalesce(func.sum(given.c.benefit_given), 0),
                func.coalesce(func.sum(given.c.free_given), 0),
            ).group_by(given.c.version_group_id)
        ):
            # At the four places a quantity holds: the sum comes back at
            # the scale of quantity times factor, and one free unit read
            # 1.00000000000000 (D-PRC-57).
            claimed[group] = (Decimal(str(amount)), at_quantity_scale(free))
    rooms: dict[UUID, BudgetRoom] = {}
    for row in promotions:
        amount, free = claimed.get(row.version_group_id, (ZERO, ZERO))
        rooms[row.id] = BudgetRoom(
            max_amount=row.max_benefit_amount,
            amount_claimed=amount,
            max_free=row.max_free_quantity,
            free_claimed=free,
        )
    return rooms


def budget_room(session: Session, promotion: Promotion, *, firm_id: UUID) -> BudgetRoom:
    """Return what one offer's budget has left.

    An offer with no budget is answered without a read: this runs for every
    offer on every document priced, and most offers have none.
    """
    if promotion.max_benefit_amount is None and promotion.max_free_quantity is None:
        return BudgetRoom(None, ZERO, None, ZERO)
    return budget_rooms(session, [promotion], firm_id=firm_id)[promotion.id]


def _combo_saving(
    params: dict[str, object], matched: list[_LineState]
) -> list[tuple[_LineState, Decimal]]:
    """Return what a combo price takes off each line of its complete sets.

    SEL-3. The set is the products and quantities the offer names; the
    document holds as many complete sets as its scarcest member allows,
    counted across lines. One set at its own rates costs what each unit has
    left after earlier offers; the saving is that less the combo price, times
    the sets, and it is spread over the lines the sets used by the value each
    contributed -- the way a bill discount is -- so each line keeps its own
    GST. A combo dearer than its parts saves nothing.
    """
    raw = params.get("items")
    items = raw if isinstance(raw, list) else []
    price = Decimal(str(params.get("price", 0) or 0))
    wanted: dict[str, Decimal] = {}
    for item in items:
        if isinstance(item, dict) and item.get("product_id"):
            wanted[str(item["product_id"])] = Decimal(str(item.get("quantity", 0)))
    if len(wanted) < 2 or price <= ZERO or any(q <= ZERO for q in wanted.values()):
        return []
    lines: dict[str, list[_LineState]] = {key: [] for key in wanted}
    for state in matched:
        key = str(state.product_id) if state.product_id is not None else ""
        if key in lines and state.quantity > ZERO:
            lines[key].append(state)
    held = {
        key: sum((state.quantity for state in found), ZERO)
        for key, found in lines.items()
    }
    sets = min(int(held[key] // wanted[key]) for key in wanted)
    if sets <= 0:
        return []
    # What one unit of each product has left, across the lines that hold it.
    unit = {
        key: sum((state.remaining for state in lines[key]), ZERO) / held[key]
        for key in wanted
    }
    worth = sum((unit[key] * wanted[key] for key in wanted), ZERO)
    saving = quantize_money((worth - price) * sets)
    if saving <= ZERO:
        return []
    # Each line's part of the sets: its share of its product's units used.
    weights: list[Decimal] = []
    targets: list[_LineState] = []
    for key in wanted:
        used = wanted[key] * sets
        for state in lines[key]:
            take = min(state.quantity, used)
            used -= take
            if take <= ZERO:
                continue
            targets.append(state)
            weights.append(take * unit[key])
    shares = apportion(saving, weights)
    return [
        (state, min(share, state.remaining))
        for state, share in zip(targets, shares, strict=True)
    ]


def _number(params: dict[str, object], key: str) -> Decimal:
    """Read one stored parameter as a number, nothing where it holds none.

    `PromotionCrudService._parameters` writes an absent figure as the text
    "None", so a `FREE_PRODUCT` offer with no buy quantity -- "spend ten
    thousand, get one" -- stores exactly that, and reading it as a number
    raised on every document the offer matched (D-PRC-5).
    """
    try:
        return Decimal(str(params.get(key) or 0))
    except ArithmeticError:
        return ZERO


def _share(
    promotion: Promotion,
    *,
    discount: Decimal = ZERO,
    free_quantity: Decimal = ZERO,
) -> PromotionLineShare:
    """Return what one offer gave, named as the document will keep it."""
    return PromotionLineShare(
        promotion_id=promotion.id,
        promotion_group_id=promotion.version_group_id,
        code=promotion.code,
        name=promotion.name,
        discount_amount=discount,
        free_quantity=free_quantity,
    )


def _line_shares(
    state: _LineState,
    *,
    slices: list[tuple[int, Decimal]],
    free_slices: list[tuple[int, Decimal]],
    applied_promotions: list[Promotion],
) -> list[PromotionLineShare]:
    """Return each offer's part of one line, in the order applied (L7 step 2).

    Read after the cap and after "best offer only", so the discounts add up
    to the line's quantized discount exactly: any rounding residual goes on
    the last offer that took something off, as the cap takes from it first.
    """
    discount: dict[int, Decimal] = {}
    free: dict[int, Decimal] = {}
    for at, amount in slices:
        discount[at] = discount.get(at, ZERO) + amount
    for at, quantity in free_slices:
        free[at] = free.get(at, ZERO) + quantity
    shares: list[PromotionLineShare] = []
    for at in sorted(set(discount) | set(free)):
        amount = quantize_money(discount.get(at, ZERO))
        quantity = free.get(at, ZERO)
        if amount <= ZERO and quantity <= ZERO:
            # The cap took back all it gave, and it gave no free goods.
            continue
        shares.append(
            _share(applied_promotions[at], discount=amount, free_quantity=quantity)
        )
    residual = quantize_money(state.discount) - sum(
        (share.discount_amount for share in shares), ZERO
    )
    if residual != ZERO:
        last = next(
            (share for share in reversed(shares) if share.discount_amount > ZERO),
            None,
        )
        if last is not None:
            last.discount_amount += residual
    return shares


def _cap(params: dict[str, object]) -> Decimal | None:
    """Return a percent action's cap on the document, or None for no cap."""
    raw = params.get("max_amount")
    if raw in (None, "", "None"):
        return None
    return quantize_money(Decimal(str(raw)))


def _action_kinds(promotion: Promotion) -> set[str]:
    """Return the kinds of benefit an offer gives."""
    return {action.action_type for action in promotion.actions if not action.is_deleted}


def _figure(params: dict[str, object], key: str) -> Decimal | None:
    """Read one stored figure, or None where the offer states none."""
    raw = params.get(key)
    if raw in (None, "", "None"):
        return None
    try:
        return Decimal(str(raw))
    except ArithmeticError:
        return None


def _money(value: Decimal | None) -> str:
    """Spell a sum of money as the documents print it: 10.00."""
    return f"{quantize_ledger(value or ZERO)}"


def _action_sentence(kind: str, params: dict[str, object]) -> str:
    """Say what one action gives, in the words the bill maker reads."""
    percent = _units(_figure(params, "percent"))
    buy = _units(_figure(params, "buy_quantity"))
    free = _units(_figure(params, "free_quantity"))
    cap = _figure(params, "max_amount")
    capped = "" if cap is None else f", up to {_money(cap)}"
    if kind == PromotionActionType.LINE_DISCOUNT_PERCENT.value:
        return f"{percent}% off{capped}"
    if kind == PromotionActionType.LINE_DISCOUNT_AMOUNT.value:
        return f"{_money(_figure(params, 'amount'))} off the line"
    if kind == PromotionActionType.FREE_QUANTITY.value:
        return f"{buy} + {free} free"
    if kind == PromotionActionType.BUY_X_GET_Y_DISCOUNT.value:
        return f"buy {buy}, get {free} at {percent}% off{capped}"
    if kind == PromotionActionType.COMBO_PRICE.value:
        return f"a set for {_money(_figure(params, 'price'))}"
    if kind == PromotionActionType.FREE_PRODUCT.value:
        if _figure(params, "buy_quantity"):
            return f"buy {buy}, get {free} of another product free"
        return f"{free} of another product free"
    if kind == PromotionActionType.BILL_DISCOUNT_PERCENT.value:
        return f"{percent}% off the bill{capped}"
    if kind == PromotionActionType.BILL_DISCOUNT_AMOUNT.value:
        return f"{_money(_figure(params, 'amount'))} off the bill"
    if kind == PromotionActionType.FREE_SHIPPING.value:
        return "free delivery"
    return kind.replace("_", " ").lower()


def offer_gives(promotion: Promotion) -> OfferGives:
    """Return what an offer gives, in figures and in one sentence (L7 step 3).

    One action gives its own kind and figures; several are ``MIXED``, and the
    sentence names each in the order the offer applies them.
    """
    actions = [action for action in promotion.actions if not action.is_deleted]
    sentence = ", ".join(
        _action_sentence(action.action_type, action.parameters or {})
        for action in actions
    )
    if len(actions) != 1:
        return OfferGives(kind="MIXED", sentence=sentence)
    params = actions[0].parameters or {}
    return OfferGives(
        kind=actions[0].action_type,
        percent=_figure(params, "percent"),
        amount=_figure(params, "amount") or _figure(params, "price"),
        buy_quantity=_figure(params, "buy_quantity"),
        free_quantity=_figure(params, "free_quantity"),
        sentence=sentence,
    )


def _allowed(offers: Sequence[UUID] | None, promotion: Promotion) -> bool:
    """Return whether a line whose offers a person named may take this one."""
    return offers is None or promotion.version_group_id in offers


def _line_reason(
    item: _Considered,
    *,
    gave: bool,
    applied: bool,
    typed: bool,
    free_typed: bool,
    worth: Decimal,
    reason: str | None,
    line_reason: str | None = None,
) -> tuple[bool, str | None]:
    """Return whether an offer is available on one line, and why it is not in.

    The line's own reason first -- a discount typed on it -- then the offer's
    on the whole document, then what the line itself has not yet earned.
    """
    if gave:
        return True, None
    if typed:
        return False, "A discount is typed on this line."
    if not item.available:
        return False, item.reason
    if line_reason is not None:
        return True, line_reason
    if free_typed and worth <= ZERO:
        return False, "A free quantity is typed on this line."
    if worth <= ZERO:
        return True, "Nothing earned on this line yet."
    if applied:
        return True, "The firm's cap on a line's discount took this offer's part back."
    return True, reason or "Not applied."


def _offer_candidate(
    promotion: Promotion,
    *,
    gives: OfferGives,
    worth: Decimal,
    applied: bool,
    available: bool,
    reason: str | None,
    hint: tuple[Decimal, str] | None = None,
) -> OfferCandidate:
    """Return one offer as a candidate, keyed by its lasting identity."""
    return OfferCandidate(
        key=str(promotion.version_group_id),
        source="promotion",
        code=promotion.code,
        name=promotion.name,
        gives=gives,
        worth=worth,
        applied=applied,
        combines=bool(promotion.allow_stacking),
        available=available,
        reason=reason,
        needs_more=None if hint is None else hint[0],
        then_gives=None if hint is None else hint[1],
    )


#: The actions earned in whole rounds: "buy 11, get 1".
_ROUND_ACTIONS = frozenset(
    {
        PromotionActionType.FREE_QUANTITY.value,
        PromotionActionType.BUY_X_GET_Y_DISCOUNT.value,
    }
)
#: The line actions that give their whole benefit once a line qualifies.
_FLAT_LINE_ACTIONS = frozenset(
    {
        PromotionActionType.LINE_DISCOUNT_PERCENT.value,
        PromotionActionType.LINE_DISCOUNT_AMOUNT.value,
        PromotionActionType.COMBO_PRICE.value,
    }
)


def _least_quantity(condition: object, expected: object | None) -> Decimal | None:
    """Return the least quantity one quantity condition holds at, if any."""
    operator = str(getattr(condition, "operator", ""))
    try:
        if operator == PromotionConditionOperator.BETWEEN.value:
            bounds = getattr(condition, "value_json", None) or []
            return Decimal(str(bounds[0])) if len(bounds) == 2 else None
        if expected is None:
            return None
        figure = Decimal(str(expected))
    except (ArithmeticError, TypeError, ValueError):
        return None
    if operator in {
        PromotionConditionOperator.GREATER_OR_EQUAL.value,
        PromotionConditionOperator.EQUALS.value,
    }:
        return figure
    if operator == PromotionConditionOperator.GREATER_THAN.value:
        return figure + 1
    return None


def _rounds(promotion: Promotion) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    """Return each round an offer gives: its kind, step, units given and rate."""
    rounds: list[tuple[str, Decimal, Decimal, Decimal]] = []
    for action in promotion.actions:
        if action.is_deleted or action.action_type not in _ROUND_ACTIONS:
            continue
        params = action.parameters or {}
        buy = _figure(params, "buy_quantity") or ZERO
        get = _figure(params, "free_quantity") or ZERO
        step = (
            buy
            if action.action_type == PromotionActionType.FREE_QUANTITY.value
            else buy + get
        )
        if step > ZERO and get > ZERO:
            rate = _figure(params, "percent") or ZERO
            rounds.append((action.action_type, step, get, rate))
    return rounds


def _hint(
    promotion: Promotion, state: _LineState, *, floor: Decimal | None
) -> tuple[Decimal, str] | None:
    """Return how many more of the line's units earn what, or None (L7 step 4).

    ``floor`` is the stock quantity meeting the offer's quantity conditions
    on a line short of them (`_quantity_floor`); None on a line they already
    hold on, where only the next round of a "buy X get Y" is hinted. Short of
    the floor, the target is the floor -- raised to the first whole round
    where the offer gives nothing but rounds and the floor earns none. The
    shortfall is in the line's own unit and shown only where it is no more
    than the quantity typed (section 3.6).
    """
    quantity = state.quantity
    rounds = _rounds(promotion)
    if floor is None:
        if not rounds:
            return None
        target = min((int(quantity // step) + 1) * step for _, step, _, _ in rounds)
    else:
        target = floor
        only_rounds = not (_action_kinds(promotion) & _FLAT_LINE_ACTIONS)
        if rounds and only_rounds and all(floor < step for _, step, _, _ in rounds):
            target = min(step for _, step, _, _ in rounds)
    if target <= quantity:
        return None
    parts: list[str] = []
    for kind, step, get, rate in rounds:
        now = int(quantity // step)
        more = int(target // step) - now
        if more <= 0:
            continue
        again = "more " if now > 0 else ""
        if kind == PromotionActionType.FREE_QUANTITY.value:
            parts.append(f"{_units(get * more)} {again}free")
        else:
            parts.append(f"{_units(get * more)} {again}at {_units(rate)}% off")
    if floor is not None:
        parts.extend(
            _action_sentence(action.action_type, action.parameters or {})
            for action in promotion.actions
            if not action.is_deleted and action.action_type in _FLAT_LINE_ACTIONS
        )
    if not parts:
        return None
    needs_more = in_line_units(target - quantity, state.stock_factor)
    if needs_more > state.entered_quantity:
        return None
    return needs_more, ", ".join(parts)
