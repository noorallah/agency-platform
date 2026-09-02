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

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
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
    #: COLLECTED or INVOICED -- what the percentage is *of*. Defaults to what
    #: this module has always paid on, so no existing rule changes meaning.
    basis: Mapped[str] = mapped_column(
        String(20), nullable=False, default="COLLECTED", server_default="COLLECTED"
    )
    #: How this rule's slabs read, if it has any. Meaningless on a flat rule.
    slab_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MARGINAL", server_default="MARGINAL"
    )
    #: The most this rule pays one salesman for one period, or NULL for no
    #: ceiling. A cap belongs on the rule rather than on a slab because it is a
    #: limit on the arrangement, not on a band within it -- and it is applied
    #: after the ladder, so it caps what was earned rather than what was sold.
    max_commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))


class CommissionBasis(StrEnum):
    """What a rule is a percentage *of*.

    COLLECTED is what this module has always paid on and stays the default: a
    salesman earns when the money arrives, which is the arrangement most
    distribution firms actually run because it puts the collection risk on the
    person who agreed the sale.

    INVOICED pays on approved invoice value in the period instead, which some
    firms prefer for a salaried team who do not do the collecting. It is a
    different arrangement, not an addition -- see the overlap guard, which
    deliberately refuses a second rule covering the same person and dates
    whatever its basis, so a firm switching over replaces the rule rather than
    quietly paying twice for one sale.
    """

    COLLECTED = "COLLECTED"
    INVOICED = "INVOICED"


class CommissionSlabMode(StrEnum):
    """How a ladder of rates reads.

    Both are in ordinary use and they pay very differently, so this is the
    firm's arrangement to declare rather than an interpretation to hard-code.

    MARGINAL charges each portion at its own rate, the way income tax reads:
    120,000 against slabs of 2% to 100,000 and 3% above pays 2,000 + 600.

    WHOLE_AMOUNT charges the whole subtotal at the rate of the highest slab it
    reaches: the same 120,000 pays 3,600. It is the more common incentive
    scheme and the more motivating one, because crossing a threshold lifts
    everything already earned.
    """

    MARGINAL = "MARGINAL"
    WHOLE_AMOUNT = "WHOLE_AMOUNT"


class CommissionRuleSlab(BaseEntity):
    """One rung of a rule's ladder: a band of value, and its rate.

    A rule with no slabs pays its flat `percentage`, which is what every rule
    written before this table existed does and keeps doing. A rule *with* slabs
    ignores that column entirely -- there is one answer to "what does this
    rule pay", and a flat rate sitting beside a ladder that overrides it is a
    number somebody will eventually read as the arrangement.
    """

    __tablename__ = "commission_rule_slabs"
    __table_args__ = (
        CheckConstraint(
            "percentage >= 0 AND percentage <= 100",
            name="CK_commission_rule_slabs_percentage_range",
        ),
        CheckConstraint(
            "from_amount >= 0", name="CK_commission_rule_slabs_from_amount"
        ),
        CheckConstraint(
            "to_amount IS NULL OR to_amount > from_amount",
            name="CK_commission_rule_slabs_band",
        ),
        Index(
            "IX_commission_rule_slabs_rule",
            "commission_rule_id",
            "from_amount",
        ),
    )

    commission_rule_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("commission_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Position in the ladder, held so a stored order survives a re-save. The
    #: bands are still resolved by `from_amount`, because that is what decides
    #: which rung an amount falls in and a sequence that disagreed with the
    #: numbers would be the thing believed.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Inclusive lower bound of the band.
    from_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Exclusive upper bound. NULL is the open-ended top rung, and only the
    #: last rung may have one.
    to_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
