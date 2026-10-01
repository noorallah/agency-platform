"""Selling below cost or below a minimum price (BACKLOG 64 row 2)."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.sales_order.schemas.sales_order import SalesOrderSchema

PriceFloorEnforcement = Literal["OFF", "WARN", "BLOCK"]


class PriceFloorSettingsResponse(SalesOrderSchema):
    """The firm's policy, and whether the firm actually chose it."""

    enforcement: PriceFloorEnforcement
    include_cost: bool
    is_configured: bool


class PriceFloorSettingsWrite(SalesOrderSchema):
    """Replace the firm's policy. Both fields are sent every time."""

    enforcement: PriceFloorEnforcement
    include_cost: bool


class PriceFloorFinding(SalesOrderSchema):
    """One line sold below its floor."""

    line_number: int
    product_id: UUID
    product_code: str | None
    product_name: str | None
    #: What one stock unit was sold for, after every discount.
    net_rate: Decimal
    #: ``minimum`` or ``cost``; when both, the higher floor is named.
    floor: Literal["minimum", "cost"]
    #: The minimum price, when that is the floor. Never the cost: whoever
    #: sells may not be allowed to see what the goods cost.
    minimum_price: Decimal | None
    message: str


class PriceFloorCheckResponse(SalesOrderSchema):
    """What approving this document would meet."""

    enforcement: PriceFloorEnforcement
    findings: list[PriceFloorFinding]
    #: True when the policy is BLOCK and a line is below its floor: approving
    #: then needs SALES_PRICE_OVERRIDE and a reason.
    would_block: bool
    message: str | None


class RoleDiscountLimitItem(SalesOrderSchema):
    """The largest discount one role may give on its own (backlog 64 row 3)."""

    role_code: str = Field(min_length=1, max_length=100)
    max_discount_percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class RoleDiscountLimitsWrite(SalesOrderSchema):
    """Replace the firm's whole list; a role left out has no limit."""

    limits: list[RoleDiscountLimitItem]


class RoleDiscountLimitsResponse(SalesOrderSchema):
    """The firm's limits, by role code."""

    limits: list[RoleDiscountLimitItem]
