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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.utils.dates import as_utc, utc_now
from app.core.utils.money import quantize_ledger, quantize_money
from app.core.utils.pricing import apportion
from app.products.models import Product
from app.promotions.models import (
    Promotion,
    PromotionCoupon,
    PromotionExecutionLog,
    PromotionRedemption,
)
from app.promotions.schemas import (
    PromotionActionType,
    PromotionApplication,
    PromotionConditionOperator,
    PromotionDecision,
    PromotionEvaluationRequest,
    PromotionEvaluationResponse,
    PromotionField,
    PromotionGift,
    PromotionLineOutcome,
    PromotionStatus,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


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
    quantity: Decimal
    discount: Decimal = ZERO
    #: What the line sells, for an offer about a set of products (SEL-3).
    product_id: UUID | None = None
    free_quantity: Decimal = ZERO
    #: Somebody typed this line's free quantity, so no offer adds to it.
    free_typed: bool = False
    #: The offer that gave this line's free units: the last, if two did.
    free_promotion_id: UUID | None = None
    codes: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> Decimal:
        """What is still discountable on this line."""
        return self.gross - self.discount


class PromotionService:
    """Evaluate a firm's promotions against one document."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def evaluate(
        self, data: PromotionEvaluationRequest, *, firm_scope: UUID
    ) -> PromotionEvaluationResponse:
        """Apply every matching promotion, in order, and report what happened.

        Never commits: the caller is mid-document. The `/simulate` endpoint
        owns the transaction, exactly as it does for tax.
        """
        states = [
            _LineState(
                line_number=line.line_number,
                gross=quantize_money(line.gross),
                quantity=Decimal(str(line.quantity)),
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
        best_only, line_cap = self._promotion_policy(firm_scope)
        candidates: list[tuple[Promotion, list[_LineState]]] = []
        # Which offer added how much to which line, in the order applied, so a
        # combined cap can take back the last slice first (backlog 59 item 3).
        slices: list[list[tuple[int, Decimal]]] = [[] for _ in states]
        applied_promotions: list[Promotion] = []
        # What each budgeted offer still has to give, read once per offer.
        room: dict[UUID, BudgetRoom] = {}

        def apply_one(
            promotion: Promotion, matched_lines: list[_LineState]
        ) -> bool | None:
            """Apply one offer to the document; True when evaluation must stop.

            None when the offer was not applied after all: what it would give
            this document is more than its budget has left. Everything it
            did is undone, so the document is priced as if it had not matched.
            """
            nonlocal bill_discount, freight_waived
            before_each = [state.discount for state in states]
            before_free = [state.free_quantity for state in states]
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
            free_given = sum((state.free_quantity for state in states), ZERO) - sum(
                before_free, ZERO
            )
            free_given += sum((gift.quantity for gift in gifts[before_gifts:]), ZERO)
            overrun = room[promotion.id].overrun(worth, free_given)
            if overrun is not None:
                # Whole or not at all, as approval refuses it: part of a
                # scheme is a price nobody published.
                for state, discount, free in zip(
                    states, before_each, before_free, strict=True
                ):
                    state.discount = discount
                    state.free_quantity = free
                del gifts[before_gifts:]
                decisions.append(
                    self._decision(promotion, False, f"This offer {overrun}")
                )
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
                    free_quantity=free_given,
                )
            )
            applied_promotions.append(promotion)
            for index, state in enumerate(states):
                delta = state.discount - before_each[index]
                if delta > ZERO:
                    slices[index].append((len(applications) - 1, delta))
                if state.free_quantity > before_free[index]:
                    # Named on the line, so the document can say whose free
                    # goods these are when a principal is asked to pay.
                    state.free_promotion_id = promotion.id
            for state in matched_lines:
                state.codes.append(promotion.code)
            decisions.append(self._decision(promotion, True, "Applied."))
            if not promotion.allow_stacking:
                decisions.append(
                    self._decision(
                        promotion,
                        True,
                        "This promotion does not stack, so evaluation stopped.",
                    )
                )
                return True
            return False

        for promotion in self._active_promotions(
            firm_scope=firm_scope, on=data.transaction_date
        ):
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
                promotion, coupon=coupon, data=data, firm_scope=firm_scope
            )
            if refusal is not None:
                decisions.append(self._decision(promotion, False, refusal))
                continue
            # A budget is counted like the number of claims, from the ledger:
            # one that is spent is not quoted, and one that cannot cover this
            # document is found out when the offer is applied below.
            room[promotion.id] = budget_room(
                self._session, promotion, firm_id=firm_scope
            )
            spent = room[promotion.id].spent()
            if spent is not None:
                decisions.append(self._decision(promotion, False, spent))
                continue
            matched_lines = [
                state
                for state, line in zip(states, data.lines, strict=True)
                # A line somebody priced by hand is left alone entirely. The
                # shared rule would discard the promotion downstream anyway;
                # skipping here is what stops the trace claiming a benefit the
                # line never received, which is the question this log exists to
                # answer.
                if not line.caller_priced
                and self._matches(
                    promotion,
                    context=self._context(
                        data,
                        line=line,
                        state=state,
                        document_gross=document_gross,
                        products=products,
                        history=history,
                    ),
                )
            ]
            if not matched_lines:
                decisions.append(
                    self._decision(
                        promotion,
                        False,
                        (
                            "Every line was priced by hand."
                            if all(line.caller_priced for line in data.lines)
                            else "No line met the conditions."
                        ),
                    )
                )
                continue

            if best_only:
                candidates.append((promotion, matched_lines))
                continue
            if apply_one(promotion, matched_lines):
                break

        if best_only and candidates:
            self._apply_best(candidates, states, data, decisions, apply_one)
        elif line_cap is not None:
            self._cap_lines(
                line_cap,
                states=states,
                slices=slices,
                applications=applications,
                applied_promotions=applied_promotions,
                decisions=decisions,
            )

        response = PromotionEvaluationResponse(
            lines=[
                PromotionLineOutcome(
                    line_number=state.line_number,
                    discount_amount=quantize_money(state.discount),
                    free_quantity=state.free_quantity,
                    free_promotion_id=state.free_promotion_id,
                    applied_promotion_codes=state.codes,
                )
                for state in states
            ],
            bill_discount_amount=quantize_money(bill_discount),
            freight_waived=freight_waived,
            applied_promotion_codes=applied,
            gifts=gifts,
            applied=applications,
            decisions=decisions,
        )
        self._log(data, response, firm_scope=firm_scope)
        return response

    def _active_promotions(self, *, firm_scope: UUID, on: date) -> list[Promotion]:
        """Return the promotions in force on that date, in application order.

        Ordered exactly as the tax engine orders its rules. The window is
        judged against the **document's** date rather than today's, so an offer
        that ran in April still explains an April order in September.
        """
        rows = self._session.scalars(
            select(Promotion)
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
    ) -> str | None:
        """Say why this promotion is out of reach, or nothing if it is not.

        Checked before the conditions, because "you did not present the code"
        and "your order does not qualify" are different answers and a firm
        chasing an offer that did not fire needs to know which.

        A limit is counted from the redemption ledger rather than from a
        counter on the promotion. A counter would have to be written while the
        document is priced, and pricing must never commit -- so it would either
        publish a half-written order or count a draft that is edited five more
        times and never approved.
        """
        if promotion.requires_coupon and (
            coupon is None
            or not self._coupon_reaches(coupon, promotion, firm_scope=firm_scope)
        ):
            return "This offer is claimed with a coupon, and none was presented."
        claimed = self._claimed(promotion, firm_scope=firm_scope)
        if (
            promotion.max_redemptions is not None
            and claimed >= promotion.max_redemptions
        ):
            return "This offer has been claimed as often as it allows."
        if promotion.max_redemptions_per_customer is not None and data.customer_id:
            by_customer = self._claimed(
                promotion, firm_scope=firm_scope, customer_id=data.customer_id
            )
            if by_customer >= promotion.max_redemptions_per_customer:
                return "This customer has claimed this offer as often as they may."
        if coupon is not None and self._coupon_reaches(
            coupon, promotion, firm_scope=firm_scope
        ):
            coupon_claimed = self._claimed(
                promotion, firm_scope=firm_scope, coupon_id=coupon.id
            )
            if (
                coupon.max_redemptions is not None
                and coupon_claimed >= coupon.max_redemptions
            ):
                return "This coupon has been used as often as it allows."
            if coupon.max_redemptions_per_customer is not None and data.customer_id:
                mine = self._claimed(
                    promotion,
                    firm_scope=firm_scope,
                    coupon_id=coupon.id,
                    customer_id=data.customer_id,
                )
                if mine >= coupon.max_redemptions_per_customer:
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

    def _claimed(
        self,
        promotion: Promotion,
        *,
        firm_scope: UUID,
        customer_id: UUID | None = None,
        coupon_id: UUID | None = None,
    ) -> int:
        """Count live claims on one offer. A reversal does not count.

        Counted across the offer's whole **version group**, not against the
        row that happens to be live. A published promotion is superseded
        rather than edited, so counting by row id gave the successor a claim
        count of zero -- an exhausted campaign became fully available again
        on a one-character edit, which is money given away.
        """
        statement = (
            select(func.count())
            .select_from(PromotionRedemption)
            .where(
                PromotionRedemption.firm_id == firm_scope,
                PromotionRedemption.promotion_id.in_(
                    select(Promotion.id).where(
                        Promotion.firm_id == firm_scope,
                        Promotion.version_group_id == promotion.version_group_id,
                    )
                ),
                PromotionRedemption.is_deleted.is_(False),
                PromotionRedemption.status == "CLAIMED",
            )
        )
        if customer_id is not None:
            statement = statement.where(PromotionRedemption.customer_id == customer_id)
        if coupon_id is not None:
            statement = statement.where(PromotionRedemption.coupon_id == coupon_id)
        return int(self._session.scalar(statement) or 0)

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

    def _apply_best(
        self,
        candidates: list[tuple[Promotion, list[_LineState]]],
        states: list[_LineState],
        data: PromotionEvaluationRequest,
        decisions: list[PromotionDecision],
        apply_one: Callable[[Promotion, list[_LineState]], bool | None],
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

    def _promotion_policy(self, firm_scope: UUID) -> tuple[bool, Decimal | None]:
        """Return (best offer only, combined line cap %) for the firm (backlog 59).

        A firm with no settings row combines with no cap, as offers always
        have. The cap is read only in Combine mode: a single best offer is
        already one offer.
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
            return False, None
        mode, cap = row
        if mode == "BEST_OFFER":
            return True, None
        return False, (None if cap is None else Decimal(str(cap)))

    def _cap_lines(
        self,
        cap_percent: Decimal,
        *,
        states: list[_LineState],
        slices: list[list[tuple[int, Decimal]]],
        applications: list[PromotionApplication],
        applied_promotions: list[Promotion],
        decisions: list[PromotionDecision],
    ) -> None:
        """Hold each line's combined offer discount to the firm's cap.

        Backlog 59 item 3. Offers compound, so the one applied last added the
        last slice; it is trimmed first, then the one before it. Each trimmed
        offer's ``benefit_amount`` falls by what was taken back, so a
        campaign is costed at what it actually gave. The bill discount is not
        a line discount and is left alone.
        """
        for index, state in enumerate(states):
            limit = quantize_money(state.gross * cap_percent / HUNDRED)
            excess = state.discount - limit
            if excess <= ZERO:
                continue
            trimmed_from: list[str] = []
            for application_index, slice_amount in reversed(slices[index]):
                if excess <= ZERO:
                    break
                take = min(slice_amount, excess)
                state.discount -= take
                excess -= take
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
            if state.free_quantity > ZERO and state.quantity > ZERO:
                value += state.free_quantity * state.gross / state.quantity
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
                        times = int(state.quantity // buy)
                        if times > 0 and not state.free_typed:
                            state.free_quantity += free * times
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
                free = Decimal(str(params.get("free_quantity", 0) or 0))
                if gifts is None or gift_id in (None, "None") or free <= ZERO:
                    continue
                threshold = Decimal(str(params.get("buy_quantity", 0) or 0))
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
                        product_id=UUID(str(gift_id)),
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
                result_payload=response.model_dump(mode="json"),
            )
        )
        self._session.flush()


@dataclass(frozen=True, slots=True)
class BudgetRoom:
    """What is left of an offer's budget in money and in free units.

    One answer for pricing and for approval, so the two cannot disagree about
    whether a document fits. Counted from CLAIMED redemptions across the
    offer's version group, as the number of claims is: a draft has taken
    nothing, a cancelled document gave its part back, and an edit does not
    refill a budget.
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
    value = Decimal(str(quantity or 0)).normalize()
    return f"{value:f}"


def budget_rooms(
    session: Session, promotions: Sequence[Promotion], *, firm_id: UUID
) -> dict[UUID, BudgetRoom]:
    """Return what each offer's budget has left, keyed by promotion id.

    One statement for the whole list, never one per offer: a page of offers
    asks once. What was claimed is counted whether or not there is a budget,
    because "how much has this offer given" is worth showing either way.
    """
    budgeted = {row.version_group_id for row in promotions}
    claimed: dict[UUID, tuple[Decimal, Decimal]] = {}
    if budgeted:
        for group, amount, free in session.execute(
            select(
                Promotion.version_group_id,
                func.coalesce(func.sum(PromotionRedemption.benefit_amount), 0),
                func.coalesce(func.sum(PromotionRedemption.free_quantity), 0),
            )
            .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
            .where(
                PromotionRedemption.firm_id == firm_id,
                Promotion.firm_id == firm_id,
                Promotion.version_group_id.in_(budgeted),
                PromotionRedemption.status == "CLAIMED",
                PromotionRedemption.is_deleted.is_(False),
            )
            .group_by(Promotion.version_group_id)
        ):
            claimed[group] = (Decimal(str(amount)), Decimal(str(free)))
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


def _cap(params: dict[str, object]) -> Decimal | None:
    """Return a percent action's cap on the document, or None for no cap."""
    raw = params.get("max_amount")
    if raw in (None, "", "None"):
        return None
    return quantize_money(Decimal(str(raw)))
