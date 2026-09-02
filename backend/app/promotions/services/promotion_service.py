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

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.utils.money import quantize_money
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
    PromotionLineOutcome,
    PromotionStatus,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(slots=True)
class _LineState:
    """What one line has earned so far as promotions are applied."""

    line_number: int
    gross: Decimal
    quantity: Decimal
    discount: Decimal = ZERO
    free_quantity: Decimal = ZERO
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
            )
            for line in data.lines
        ]
        document_gross = quantize_money(sum((s.gross for s in states), ZERO))
        products = self._products_for(data)
        bill_discount = ZERO
        applied: list[str] = []
        applications: list[PromotionApplication] = []
        decisions: list[PromotionDecision] = []

        coupon = self._coupon_for(data, firm_scope=firm_scope)
        for promotion in self._active_promotions(
            firm_scope=firm_scope, on=data.transaction_date
        ):
            refusal = self._unavailable(
                promotion, coupon=coupon, data=data, firm_scope=firm_scope
            )
            if refusal is not None:
                decisions.append(self._decision(promotion, False, refusal))
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

            before_lines = sum((state.discount for state in states), ZERO)
            added_bill = self._apply(
                promotion,
                matched=matched_lines,
                states=states,
                bill_discount=bill_discount,
                allow_bill=not data.caller_priced_bill,
            )
            bill_discount += added_bill
            applied.append(promotion.code)
            applications.append(
                PromotionApplication(
                    promotion_id=promotion.id,
                    code=promotion.code,
                    coupon_id=(
                        coupon.id
                        if coupon is not None and coupon.promotion_id == promotion.id
                        else None
                    ),
                    # What this offer alone took off, line and bill together --
                    # so a campaign can be costed without re-pricing every
                    # document it touched.
                    benefit_amount=quantize_money(
                        sum((state.discount for state in states), ZERO)
                        - before_lines
                        + added_bill
                    ),
                )
            )
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
                break

        response = PromotionEvaluationResponse(
            lines=[
                PromotionLineOutcome(
                    line_number=state.line_number,
                    discount_amount=quantize_money(state.discount),
                    free_quantity=state.free_quantity,
                    applied_promotion_codes=state.codes,
                )
                for state in states
            ],
            bill_discount_amount=quantize_money(bill_discount),
            applied_promotion_codes=applied,
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
            coupon is None or coupon.promotion_id != promotion.id
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
        if coupon is not None and coupon.promotion_id == promotion.id:
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

    def _claimed(
        self,
        promotion: Promotion,
        *,
        firm_scope: UUID,
        customer_id: UUID | None = None,
        coupon_id: UUID | None = None,
    ) -> int:
        """Count live claims on one offer. A reversal does not count."""
        statement = (
            select(func.count())
            .select_from(PromotionRedemption)
            .where(
                PromotionRedemption.firm_id == firm_scope,
                PromotionRedemption.promotion_id == promotion.id,
                PromotionRedemption.is_deleted.is_(False),
                PromotionRedemption.status == "CLAIMED",
            )
        )
        if customer_id is not None:
            statement = statement.where(PromotionRedemption.customer_id == customer_id)
        if coupon_id is not None:
            statement = statement.where(PromotionRedemption.coupon_id == coupon_id)
        return int(self._session.scalar(statement) or 0)

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
        if operator == PromotionConditionOperator.EQUALS.value:
            return str(actual) == str(expected)
        if operator == PromotionConditionOperator.NOT_EQUALS.value:
            return str(actual) != str(expected)
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

    def _apply(
        self,
        promotion: Promotion,
        *,
        matched: list[_LineState],
        states: list[_LineState],
        bill_discount: Decimal,
        allow_bill: bool = True,
    ) -> Decimal:
        """Give this promotion's benefits, and return what it took off the bill.

        Every percentage is taken off what is **left**, which is what stops
        stacked benefits from ever exceeding the line.
        """
        added_bill = ZERO
        for action in promotion.actions:
            params = action.parameters or {}
            kind = action.action_type
            if kind == PromotionActionType.LINE_DISCOUNT_PERCENT.value:
                rate = Decimal(str(params.get("percent", 0)))
                for state in matched:
                    state.discount += quantize_money(state.remaining * rate / HUNDRED)
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
                        if times > 0:
                            state.free_quantity += free * times
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
                    added_bill += quantize_money(taxable * rate / HUNDRED)
                else:
                    amount = Decimal(str(params.get("amount", 0)))
                    added_bill += min(quantize_money(amount), taxable)
        return added_bill

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
