"""Validated contracts for promotions."""

from datetime import date
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
        return self


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

    @model_validator(mode="after")
    def _parameters_match_the_action(self) -> "PromotionActionWrite":
        """Refuse an action missing the number it needs to do anything."""
        percent_actions = {
            PromotionActionType.LINE_DISCOUNT_PERCENT,
            PromotionActionType.BILL_DISCOUNT_PERCENT,
        }
        amount_actions = {
            PromotionActionType.LINE_DISCOUNT_AMOUNT,
            PromotionActionType.BILL_DISCOUNT_AMOUNT,
        }
        if self.action_type in percent_actions and self.percent is None:
            raise ValueError("A percentage benefit needs a percent.")
        if self.action_type in amount_actions and self.amount is None:
            raise ValueError("An amount benefit needs an amount.")
        if self.action_type is PromotionActionType.FREE_QUANTITY and (
            self.buy_quantity is None or self.free_quantity is None
        ):
            raise ValueError("Free goods need a buy quantity and a free quantity.")
        if self.action_type is PromotionActionType.FREE_PRODUCT:
            if self.free_product_id is None:
                raise ValueError("Say which product is given away.")
            if self.free_quantity is None:
                raise ValueError("Say how many of it are given away.")
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
    conditions: list[PromotionConditionWrite] = Field(
        default_factory=list, max_length=50
    )
    actions: list[PromotionActionWrite] = Field(min_length=1, max_length=20)

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
    #: True when somebody typed a discount on this line. Promotions are not
    #: evaluated for it -- a person deciding beats a rule -- and the trace says
    #: so, rather than reporting a benefit the line never received.
    caller_priced: bool = False


class PromotionEvaluationRequest(PromotionSchema):
    """Ask what benefits a document earns."""

    transaction_type: str = Field(min_length=1, max_length=40)
    transaction_date: date
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


class PromotionGift(PromotionSchema):
    """Something the document is given that none of its lines asked for.

    A line rather than a field, because no line on the document mentions this
    product. The caller appends it: the engine says what is owed and the
    document service is what writes documents.
    """

    product_id: UUID
    quantity: Decimal
    promotion_code: str


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


class PromotionCouponResponse(PromotionSchema):
    """Expose one stored coupon, and how much of it is left."""

    id: UUID
    promotion_id: UUID
    promotion_code: str
    code: str
    description: str | None
    status: str
    max_redemptions: int | None
    max_redemptions_per_customer: int | None
    effective_from: date | None
    effective_to: date | None
    #: What has actually been claimed, so a screen can say how much is left
    #: rather than only what was allowed.
    redemption_count: int
    version: int
