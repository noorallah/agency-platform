"""Validated contracts for promotions."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PromotionSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PromotionStatus(StrEnum):
    """Supported promotion lifecycle statuses.

    Only ACTIVE promotions are evaluated. DRAFT is editable in place; an ACTIVE
    one is superseded by a new version rather than edited, so a document priced
    under it stays explicable.
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class PromotionConditionOperator(StrEnum):
    """Supported promotion condition operators."""

    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    IN = "IN"
    NOT_IN = "NOT_IN"
    GREATER_THAN = "GREATER_THAN"
    GREATER_OR_EQUAL = "GREATER_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_OR_EQUAL = "LESS_OR_EQUAL"
    BETWEEN = "BETWEEN"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"


class PromotionField(StrEnum):
    """The keys a promotion may be matched on.

    Every one of these is either already on a sales document header or already
    derived per line while the document is priced. That is deliberate: the tax
    review found rules scoped by a country no document ever sent, so those
    rules could never fire and nobody knew. A key nothing can satisfy is worse
    than a key that does not exist.
    """

    CUSTOMER_ID = "customer_id"
    CUSTOMER_GROUP_ID = "customer_group_id"
    BRANCH_ID = "branch_id"
    TERRITORY_ID = "territory_id"
    ROUTE_ID = "route_id"
    SALESMAN_ID = "salesman_id"
    PRODUCT_ID = "product_id"
    PRODUCT_CATEGORY_ID = "product_category_id"
    PRODUCT_TYPE = "product_type"
    LINE_QUANTITY = "line_quantity"
    LINE_GROSS = "line_gross"
    DOCUMENT_GROSS = "document_gross"
    TRANSACTION_TYPE = "transaction_type"
    TRANSACTION_DATE = "transaction_date"
    #: The document date's day of the week, 1 Monday to 7 Sunday (SEL-7):
    #: ``IN [6, 7]`` is "weekends only".
    WEEKDAY = "weekday"
    #: Minutes after midnight, India time, when the document was raised
    #: (SEL-7): ``BETWEEN [960, 1079]`` is "4 to 6 pm".
    TIME_OF_DAY = "time_of_day"
    #: How many approved bills the customer had by the document's date
    #: (SEL-6): ``EQUALS 0`` is "first order only". A draft is not an order.
    CUSTOMER_ORDER_COUNT = "customer_order_count"
    #: Days from the customer's last approved bill to the document's date
    #: (SEL-6): ``GREATER_OR_EQUAL 60`` is "not billed in 60 days". Absent
    #: for a customer never billed, whom the order count catches instead.
    DAYS_SINCE_LAST_ORDER = "days_since_last_order"


class PromotionActionType(StrEnum):
    """The benefits a promotion may give.

    Seven, and each one changes a value the sales documents already store and
    already tax correctly. Nothing here is declared and unread -- the tax review
    recorded two flags that were stored, returned and acted on by nobody, which
    silently produced wrong money.

    `FREE_QUANTITY` and `FREE_PRODUCT` are not the same benefit wearing two
    names. The first gives **more of what was bought** and only ever changes a
    field on a line that already exists. The second gives **something else**,
    which no line on the document mentions, so the engine has to emit a line
    rather than adjust one -- and that line has to survive dispatch and reach
    the bill, which is why it needed the invoice to learn about nil-charge
    lines first.
    """

    LINE_DISCOUNT_PERCENT = "LINE_DISCOUNT_PERCENT"
    LINE_DISCOUNT_AMOUNT = "LINE_DISCOUNT_AMOUNT"
    BILL_DISCOUNT_PERCENT = "BILL_DISCOUNT_PERCENT"
    BILL_DISCOUNT_AMOUNT = "BILL_DISCOUNT_AMOUNT"
    FREE_QUANTITY = "FREE_QUANTITY"
    FREE_PRODUCT = "FREE_PRODUCT"
    #: Waives the delivery charge outright. Not a discount on it: free
    #: shipping means nothing is charged for delivery, so there is nothing to
    #: tax either -- and a document showing a delivery charge beside a
    #: discount cancelling it says something different from one showing no
    #: charge at all. A firm wanting to take only part of it off has
    #: `BILL_DISCOUNT_AMOUNT` already, which is why this takes no parameter.
    FREE_SHIPPING = "FREE_SHIPPING"
    #: Multiplies the loyalty points a bill earns while the offer runs --
    #: "double points for Diwali" (SEL-4). It changes nothing on the document:
    #: the points are earned when the bill is approved, so the pricing engine
    #: passes over it and the loyalty scheme reads it. An offer carrying it
    #: carries nothing else.
    LOYALTY_MULTIPLIER = "LOYALTY_MULTIPLIER"
    #: "Buy 2, the second at 50% off" (SEL-2): on each matched line, every
    #: complete group of ``buy_quantity`` + ``free_quantity`` units takes
    #: ``percent`` off ``free_quantity`` of them, at the line's own rate. A
    #: discount on units already on the line, so tax stays per line.
    BUY_X_GET_Y_DISCOUNT = "BUY_X_GET_Y_DISCOUNT"
    #: A set price for a set of products bought together (SEL-3): ``combo_items``
    #: names the products and quantities of one set, ``amount`` its price.
    #: Complete sets on the document cost that; the saving is spread over
    #: their lines by value, so each line keeps its own tax.
    COMBO_PRICE = "COMBO_PRICE"


class PromotionConditionWrite(PromotionSchema):
    """Carry one promotion condition into a request."""

    sequence: int = Field(default=1, ge=1)
    field_key: PromotionField
    operator: PromotionConditionOperator
    value_text: str | None = Field(default=None, max_length=500)
    value_number: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    value_date: date | None = None
    value_boolean: bool | None = None
    value_json: list[object] | None = None

    @model_validator(mode="after")
    def _value_matches_operator(self) -> "PromotionConditionWrite":
        """Refuse a condition whose operator has nothing to compare against.

        `IN` with no list and `BETWEEN` with one bound are conditions that can
        never be true, which is a configuration nobody would write on purpose
        and one no screen would explain afterwards.
        """
        listed = {
            PromotionConditionOperator.IN,
            PromotionConditionOperator.NOT_IN,
        }
        if self.operator in listed and not self.value_json:
            raise ValueError("IN and NOT_IN need a list of values.")
        if self.operator is PromotionConditionOperator.BETWEEN and (
            not isinstance(self.value_json, list) or len(self.value_json) != 2
        ):
            raise ValueError("BETWEEN needs exactly two values.")
        unary = {
            PromotionConditionOperator.EXISTS,
            PromotionConditionOperator.NOT_EXISTS,
        }
        if (
            self.operator not in unary
            and self.operator not in listed
            and self.operator is not PromotionConditionOperator.BETWEEN
            and self.value_text is None
            and self.value_number is None
            and self.value_date is None
            and self.value_boolean is None
        ):
            raise ValueError("This operator needs a value to compare against.")
        self._day_and_time_are_in_range()
        return self

    def _day_and_time_are_in_range(self) -> None:
        """Refuse a weekday outside 1-7 or a time outside the day (SEL-7).

        A window crossing midnight would need "after 22:00 or before 02:00",
        which one condition cannot say -- every condition must hold -- so it
        is refused with what to do instead rather than saved never to match.
        """
        bounds = {PromotionField.WEEKDAY: (1, 7), PromotionField.TIME_OF_DAY: (0, 1439)}
        if self.field_key not in bounds:
            return
        low, high = bounds[self.field_key]
        values: list[object] = list(self.value_json or [])
        if self.value_number is not None:
            values.append(self.value_number)
        if self.value_text is not None:
            values.append(self.value_text)
        try:
            numbers = [Decimal(str(value)) for value in values]
        except ArithmeticError as error:
            raise ValueError("A day or a time is given as a number.") from error
        if any(n != n.to_integral_value() or not low <= n <= high for n in numbers):
            what = "A weekday is 1 (Monday) to 7 (Sunday)."
            if self.field_key is PromotionField.TIME_OF_DAY:
                what = "A time of day is 0 to 1439 minutes after midnight."
            raise ValueError(what)
        if (
            self.field_key is PromotionField.TIME_OF_DAY
            and self.operator is PromotionConditionOperator.BETWEEN
            and len(numbers) == 2
            and numbers[0] > numbers[1]
        ):
            raise ValueError(
                "A time window cannot cross midnight; make it two offers, "
                "one before and one after."
            )


class ComboItem(PromotionSchema):
    """One product and how many of it make up one combo set (SEL-3)."""

    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class PromotionActionWrite(PromotionSchema):
    """Carry one promotion action into a request."""

    sequence: int = Field(default=1, ge=1)
    action_type: PromotionActionType
    #: A rate, for the two percent actions. Bounded at 100 because a promotion
    #: that takes more than the line is a configuration that would make the
    #: document unsaveable rather than cheap.
    percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    #: For LOYALTY_MULTIPLIER: how many times the usual points, above 1 and
    #: at most 10 (SEL-4).
    multiplier: Decimal | None = Field(
        default=None, gt=1, le=10, max_digits=6, decimal_places=2
    )
    #: For FREE_QUANTITY: how many must be bought, and how many come free.
    buy_quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    free_quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    #: For FREE_PRODUCT: what is given away. It is deliberately not one of the
    #: products the offer matches on -- the whole point is that it is
    #: something else, and the document need never have mentioned it.
    free_product_id: UUID | None = None
    #: For the two percent actions: the most the offer may take off the
    #: whole document -- "20% off, up to 500" (backlog 60 item 1). Blank is
    #: no cap.
    max_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    #: For COMBO_PRICE: the products of one set, two or more (SEL-3).
    combo_items: list[ComboItem] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _parameters_match_the_action(self) -> "PromotionActionWrite":
        """Refuse an action missing the number it needs to do anything."""
        percent_actions = {
            PromotionActionType.LINE_DISCOUNT_PERCENT,
            PromotionActionType.BILL_DISCOUNT_PERCENT,
            PromotionActionType.BUY_X_GET_Y_DISCOUNT,
        }
        amount_actions = {
            PromotionActionType.LINE_DISCOUNT_AMOUNT,
            PromotionActionType.BILL_DISCOUNT_AMOUNT,
            PromotionActionType.COMBO_PRICE,
        }
        if self.action_type in percent_actions and self.percent is None:
            raise ValueError("A percentage benefit needs a percent.")
        if self.max_amount is not None and self.action_type not in percent_actions:
            raise ValueError("Only a percentage benefit can have a cap.")
        if self.action_type in amount_actions and self.amount is None:
            raise ValueError("An amount benefit needs an amount.")
        if self.action_type is PromotionActionType.FREE_QUANTITY and (
            self.buy_quantity is None or self.free_quantity is None
        ):
            raise ValueError("Free goods need a buy quantity and a free quantity.")
        if self.action_type is PromotionActionType.BUY_X_GET_Y_DISCOUNT and (
            self.buy_quantity is None or self.free_quantity is None
        ):
            raise ValueError(
                "Say how many are bought at full price and how many at the "
                "discount, such as buy 1, get 1 at 50%."
            )
        if self.action_type is PromotionActionType.FREE_PRODUCT:
            if self.free_product_id is None:
                raise ValueError("Say which product is given away.")
            if self.free_quantity is None:
                raise ValueError("Say how many of it are given away.")
        combo = self.action_type is PromotionActionType.COMBO_PRICE
        if combo:
            items = self.combo_items or []
            if len(items) < 2:
                raise ValueError("A combo names two or more products.")
            if len({item.product_id for item in items}) != len(items):
                raise ValueError("Name each product of a combo once.")
        elif self.combo_items:
            raise ValueError("Only a combo price names a set of products.")
        points = self.action_type is PromotionActionType.LOYALTY_MULTIPLIER
        if points and self.multiplier is None:
            raise ValueError("Say how many times the usual points, such as 2.")
        if not points and self.multiplier is not None:
            raise ValueError("Only a bonus-points benefit has a multiplier.")
        return self


class PromotionWrite(PromotionSchema):
    """Create or replace one promotion."""

    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    priority: int = Field(default=100, ge=1, le=9999)
    status: PromotionStatus = PromotionStatus.DRAFT
    allow_stacking: bool = True
    effective_from: date | None = None
    effective_to: date | None = None
    #: Whether the customer has to ask for this offer by name.
    requires_coupon: bool = False
    #: Null is no limit, which is a different answer from zero.
    max_redemptions: int | None = Field(default=None, ge=1)
    max_redemptions_per_customer: int | None = Field(default=None, ge=1)
    #: The scheme's budget: the most money it may take off bills, and the
    #: most free units it may give, over its whole life. Null is no budget.
    #: On an edit, leaving one out keeps what the offer has and an explicit
    #: null clears it -- an editor that does not know the field must not
    #: lift a principal's budget by saving a name.
    max_benefit_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    max_free_quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    #: The principal funding the scheme, whose share is claimed back (SEL-11).
    principal_id: UUID | None = None
    principal_share_percent: Decimal = Field(
        default=Decimal("100"), gt=0, le=100, max_digits=7, decimal_places=4
    )
    conditions: list[PromotionConditionWrite] = Field(
        default_factory=list, max_length=50
    )
    actions: list[PromotionActionWrite] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _points_offer_stands_alone(self) -> "PromotionWrite":
        """Keep a bonus-points offer apart from price benefits (SEL-4).

        Its points are earned at approval while a price benefit is given when
        the document is priced, and one offer settled at two moments would be
        claimed once and paid twice -- or the other way round.
        """
        kinds = {action.action_type for action in self.actions}
        points = PromotionActionType.LOYALTY_MULTIPLIER
        if points in kinds and len(kinds) > 1:
            raise ValueError(
                "A bonus-points offer gives nothing else; make the discount a "
                "separate offer."
            )
        return self

    @model_validator(mode="after")
    def _window_is_ordered(self) -> "PromotionWrite":
        """Refuse a window that ends before it starts."""
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("A promotion cannot end before it starts.")
        return self


class PromotionConditionResponse(PromotionSchema):
    """Expose one stored condition."""

    id: UUID
    sequence: int
    field_key: str
    operator: str
    value_text: str | None
    value_number: Decimal | None
    value_date: date | None
    value_boolean: bool | None
    value_json: list[object] | dict[str, object] | None
    #: What the id in `value_text` names -- "CODE — name" for a product,
    #: territory or route, the name for a category or customer -- so a screen
    #: never has to show a bare id. `None` for a field that is not an id, or
    #: an id that no longer resolves.
    value_label: str | None = None


class PromotionActionResponse(PromotionSchema):
    """Expose one stored action."""

    id: UUID
    sequence: int
    action_type: str
    parameters: dict[str, object]


class PromotionResponse(PromotionSchema):
    """Expose one stored promotion."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    priority: int
    status: str
    allow_stacking: bool
    effective_from: date | None
    effective_to: date | None
    requires_coupon: bool
    max_redemptions: int | None
    max_redemptions_per_customer: int | None
    #: The budget in money, what approved documents have taken of it across
    #: every revision of the offer, and what is left. `remaining_*` is null
    #: where there is no budget, and never below zero.
    max_benefit_amount: Decimal | None = None
    benefit_amount_claimed: Decimal = Decimal("0")
    remaining_benefit_amount: Decimal | None = None
    #: The same three for the budget in free units.
    max_free_quantity: Decimal | None = None
    free_quantity_claimed: Decimal = Decimal("0")
    remaining_free_quantity: Decimal | None = None
    principal_id: UUID | None = None
    principal_share_percent: Decimal = Decimal("100")
    version_group_id: UUID
    version_number: int
    supersedes_promotion_id: UUID | None
    conditions: list[PromotionConditionResponse]
    actions: list[PromotionActionResponse]
    version: int


class PromotionLineRequest(PromotionSchema):
    """One line the engine is asked to price."""

    line_number: int = Field(ge=1)
    product_id: UUID | None = None
    quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18)
    gross: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18)
    #: The stock units one unit of this line holds -- 12 for a line sold by
    #: the box of twelve, 1 for a line in the unit the product is kept in.
    #: An offer counts stock units (D-PRC-39): a quantity condition, "buy X"
    #: and a combo's set all read ``quantity`` times this.
    stock_factor: Decimal = Field(default=Decimal("1"), gt=0, max_digits=18)
    #: True when somebody typed a discount on this line. Promotions are not
    #: evaluated for it -- a person deciding beats a rule -- and the trace says
    #: so, rather than reporting a benefit the line never received.
    caller_priced: bool = False
    #: True when somebody typed the line's free quantity, a zero included.
    #: The document keeps the typed figure, so an offer's free goods are not
    #: given on that line -- and are not counted against the offer's budget.
    free_typed: bool = False


class PromotionEvaluationRequest(PromotionSchema):
    """Ask what benefits a document earns."""

    transaction_type: str = Field(min_length=1, max_length=40)
    transaction_date: date
    #: When the document was raised, for an offer on a time of day (SEL-7).
    #: Absent means now; a document passes its own creation time so saving
    #: it again later does not move it out of the window.
    transaction_time: datetime | None = None
    customer_id: UUID | None = None
    #: The segment the customer belongs to, so an offer can be aimed at
    #: wholesalers without naming every one of them.
    customer_group_id: UUID | None = None
    branch_id: UUID | None = None
    territory_id: UUID | None = None
    route_id: UUID | None = None
    salesman_id: UUID | None = None
    #: The code the customer presented, if any. A promotion requiring one
    #: never applies without it.
    coupon_code: str | None = Field(default=None, max_length=40)
    #: True when somebody typed a discount on the whole bill, for the same
    #: reason `PromotionLineRequest.caller_priced` exists.
    caller_priced_bill: bool = False
    #: What the document is charging for delivery, so an offer can waive it.
    #: The engine cannot waive a charge it has not been told about, and a
    #: `FREE_SHIPPING` promotion on a document with no delivery charge gives
    #: nothing rather than claiming to.
    freight_amount: Decimal = Decimal("0")
    lines: list[PromotionLineRequest] = Field(default_factory=list, max_length=1000)


class PromotionLineOutcome(PromotionSchema):
    """What one line earned."""

    line_number: int
    discount_amount: Decimal
    free_quantity: Decimal
    #: The offer that gave `free_quantity`, so the document can keep whose
    #: free goods these are. Null where no offer gave any.
    free_promotion_id: UUID | None = None
    applied_promotion_codes: list[str]


class PromotionDecision(PromotionSchema):
    """Why one promotion did or did not apply."""

    promotion_id: UUID
    code: str
    priority: int
    matched: bool
    reason: str


class PromotionApplication(PromotionSchema):
    """One offer that applied, and what it gave away.

    Carries the id as well as the code, because a claim is recorded against
    the promotion row and a code is only unique among live ones.
    """

    promotion_id: UUID
    code: str
    coupon_id: UUID | None = None
    benefit_amount: Decimal
    #: The free units this offer gave: on its lines and as gifts together.
    free_quantity: Decimal = Decimal("0")


class PromotionGift(PromotionSchema):
    """Something the document is given that none of its lines asked for.

    A line rather than a field, because no line on the document mentions this
    product. The caller appends it: the engine says what is owed and the
    document service is what writes documents.
    """

    product_id: UUID
    #: In the product's stock unit.
    quantity: Decimal
    promotion_code: str
    #: The row behind the code: a code is only unique among live offers.
    promotion_id: UUID | None = None
    #: Set where these are free units of a **line's own product** that are
    #: not a whole number of the line's unit -- 2 pieces earned by a line of
    #: 2 BOX -- so the document adds them as a free line of the same product
    #: in the stock unit. Null for a gift of another product.
    for_line_number: int | None = None


class PromotionEvaluationResponse(PromotionSchema):
    """What the document earned, and why."""

    lines: list[PromotionLineOutcome]
    bill_discount_amount: Decimal
    #: How much of the delivery charge an offer took off. Zero unless a
    #: `FREE_SHIPPING` promotion applied, and never more than was charged.
    freight_waived: Decimal = Decimal("0")
    applied_promotion_codes: list[str]
    applied: list[PromotionApplication] = Field(default_factory=list)
    #: Goods to add to the document. Empty for every offer that only changes
    #: what an existing line costs, which is most of them.
    gifts: list[PromotionGift] = Field(default_factory=list)
    decisions: list[PromotionDecision]


class PromotionCouponWrite(PromotionSchema):
    """Create or replace one coupon."""

    promotion_id: UUID
    code: str = Field(min_length=1, max_length=40)
    description: str | None = None
    status: PromotionStatus = PromotionStatus.ACTIVE
    max_redemptions: int | None = Field(default=None, ge=1)
    max_redemptions_per_customer: int | None = Field(default=None, ge=1)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def _window_is_ordered(self) -> "PromotionCouponWrite":
        """Refuse a window that ends before it starts."""
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("A coupon cannot end before it starts.")
        return self


class PromotionCopyRequest(PromotionSchema):
    """Copy a set of offers as drafts with a new window (SEL-8)."""

    promotion_ids: list[UUID] = Field(min_length=1, max_length=100)
    effective_from: date
    effective_to: date
    #: Added to each code, since a code names one offer for good: DIWALI
    #: becomes DIWALI-26.
    code_suffix: str = Field(min_length=1, max_length=12)


class CouponBatchRequest(PromotionSchema):
    """Mint a campaign's single-use codes against one offer (SEL-5)."""

    count: int = Field(ge=1, le=5000)
    #: Letters and digits printed before each code, such as DIWALI26.
    prefix: str = Field(default="", max_length=12)
    description: str | None = Field(default=None, max_length=200)
    effective_from: date | None = None
    effective_to: date | None = None


class CouponBatchResponse(PromotionSchema):
    """The codes a batch minted, sorted."""

    count: int
    codes: list[str]


class PromotionCouponResponse(PromotionSchema):
    """Expose one stored coupon, and how much of it is left."""

    id: UUID
    promotion_id: UUID
    promotion_code: str
    code: str
    description: str | None
    #: What the code reads as, which follows its offer: a code left ACTIVE
    #: under an offer that is switched off reads as the offer does, because
    #: presenting it gives nothing. Derived on read, never stored.
    status: str
    #: What the code itself is set to, and what an editor sends back. Sending
    #: `status` back instead would switch the code off for good the first
    #: time somebody saved it under a paused offer.
    own_status: str = "ACTIVE"
    #: The status of the offer's current revision.
    offer_status: str = "ACTIVE"
    max_redemptions: int | None
    max_redemptions_per_customer: int | None
    effective_from: date | None
    effective_to: date | None
    #: What has actually been claimed, so a screen can say how much is left
    #: rather than only what was allowed.
    redemption_count: int
    version: int


class PromotionPerformanceRecord(PromotionSchema):
    """What one offer has been claimed, and what it cost.

    Keyed on `version_group_id` rather than on the promotion row, because an
    ACTIVE promotion is superseded rather than edited: the row is only the
    version that happens to be current. Reporting per row would split one
    campaign into a handful of small ones every time somebody corrected a
    typo, and would show a limit as untouched the moment it was edited --
    which is the defect `_claimed` already exists to prevent.

    `code`, `name` and `status` are read off the **latest** version, since
    that is the offer as it now stands.
    """

    version_group_id: UUID
    code: str
    name: str
    status: PromotionStatus
    version_count: int
    #: Only CLAIMED counts against a limit. PENDING is a draft that has been
    #: priced and not approved, and REVERSED is a claim given back; both are
    #: reported because a campaign whose claims are mostly cancelled is a
    #: different thing from one nobody took up, and the totals cannot say so.
    claimed_count: int
    pending_count: int
    reversed_count: int
    #: How many different customers claimed it. A campaign taken up ninety
    #: times by three shops is not one that reached ninety.
    customer_count: int
    benefit_amount: Decimal
    #: The free units its claims gave, lines and gifts together.
    free_quantity: Decimal = Decimal("0")
    max_redemptions: int | None
    #: Null when the campaign is uncapped -- which is a different answer from
    #: zero, and the reason this is not an int with a default.
    remaining_redemptions: int | None
    #: The budget in money and in free units, and what is left of each. Null
    #: where there is none; floored at zero as the count is.
    max_benefit_amount: Decimal | None = None
    remaining_benefit_amount: Decimal | None = None
    max_free_quantity: Decimal | None = None
    remaining_free_quantity: Decimal | None = None


class PromotionRedemptionRecord(PromotionSchema):
    """One claim on an offer, as the register lists it."""

    redemption_id: UUID
    promotion_id: UUID
    promotion_code: str
    promotion_name: str
    coupon_code: str | None
    customer_id: UUID | None
    customer_name: str | None
    document_type: str
    document_id: UUID
    document_number: str | None
    redeemed_on: date
    #: The money the claim gave: what it took off the document, less the part
    #: an order closed short never delivered. The figure the offer's budget
    #: counts; a REVERSED or PENDING row reads what the document claimed.
    benefit_amount: Decimal
    #: The units it gave free, less those released at a short close and those
    #: a completed return brought back. A free-goods offer is costed here and
    #: reads zero above: goods given free are charged nothing, so they take
    #: nothing off the bill, and no worth is stored for them on the claim.
    free_quantity: Decimal = Decimal("0")
    #: What the document claimed when it was approved, before anything was
    #: released or came back. Equal to the two above on most claims.
    claimed_benefit_amount: Decimal = Decimal("0")
    claimed_free_quantity: Decimal = Decimal("0")
    status: str


class PromotionCouponPerformanceRecord(PromotionSchema):
    """What one coupon code has been claimed, and what it cost.

    A coupon is a way of reaching an offer rather than a second kind of one,
    so the benefit and the conditions belong to the promotion. What this
    answers is which codes people actually presented -- the question a
    campaign's own totals cannot, because a promotion reached by ten codes
    reports one number.
    """

    coupon_id: UUID
    code: str
    promotion_id: UUID
    promotion_code: str
    #: Follows the offer, as the coupon list's does.
    status: str
    claimed_count: int
    customer_count: int
    benefit_amount: Decimal
    #: The free units the code's claims gave. Goods given free take nothing
    #: off a bill, so `benefit_amount` is zero for them and this is the only
    #: figure a free-goods code has.
    free_quantity: Decimal = Decimal("0")
    max_redemptions: int | None
    remaining_redemptions: int | None
