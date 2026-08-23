"""Commission rule persistence: the rate, who it applies to, and from when.

One table serves both scopes. `salesman_id` names one person; NULL is the
firm's own standing rate, used for anyone with no rule of their own. Two
nullable-key scopes rather than a type-and-id pair is the shape `price_lists`
uses, and it makes "the rules that could apply here" two equality tests with
the specificity order falling out of which key is filled.

Effective-dated for the reason `uom_conversion_rules` and `tax_profiles` are: a
rate agreed in April has to keep explaining an April payout after the
arrangement changes in September. A rate is superseded by dating it, never by
editing the row that paid somebody last quarter.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class CommissionRuleStatus(StrEnum):
    """Whether a rule is in force at all.

    Separate from the effective window on purpose: a window says *when* a rate
    applied and is history, while the status is an administrator's switch. A
    rule taken out of use is deactivated, and it still explains the payouts it
    already produced.
    """

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CommissionRule(BaseEntity):
    """Store one flat commission percentage, scoped and effective-dated."""

    __tablename__ = "commission_rules"
    __table_args__ = (
        # A rate outside 0..100 is a typo, not an arrangement. The service says
        # so in the language of the request; this is the backstop for anything
        # that reaches the table another way.
        CheckConstraint(
            "percentage >= 0 AND percentage <= 100",
            name="CK_commission_rules_percentage_range",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="CK_commission_rules_effective_window",
        ),
        Index("IX_commission_rules_firm_salesman", "firm_id", "salesman_id"),
        Index("IX_commission_rules_firm_status", "firm_id", "status"),
    )

    #: No foreign key: `firms` lives only in the platform schema and this table
    #: lives in every firm store, which is the rule every firm-owned table in
    #: `firm_shared` follows.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: NULL means the firm-wide default rate. The reference matches
    #: `sales_invoices.salesman_id`, which is what attribution reads.
    salesman_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    #: NULL means "until further notice".
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CommissionRuleStatus.ACTIVE.value,
        server_default=CommissionRuleStatus.ACTIVE.value,
    )
