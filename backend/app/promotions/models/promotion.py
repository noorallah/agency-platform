"""Promotion persistence models.

The shape is `app/tax`'s: a rule row, typed condition child rows, action child
rows, and an execution log. Conditions are rows rather than a JSON blob for the
reason the custom-attribute framework gives -- a blob cannot be filtered or
reported on, and a promotion nobody can query is one nobody can audit.

One thing is deliberately different from tax. Tax stops at the first matching
rule, because two rules both applying would tax a line twice. Promotions
**stack**: every matching promotion applies, in priority order, until one that
refuses further stacking is reached. That is what a firm means by running a
customer discount and a seasonal offer at the same time.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Promotion(BaseEntity):
    """Store one versioned promotion evaluated while a document is priced."""

    __tablename__ = "promotions"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "code",
            "version_number",
            name="UQ_promotions_firm_code_version",
        ),
        Index("IX_promotions_firm_priority", "firm_id", "priority"),
        Index("IX_promotions_firm_status", "firm_id", "status"),
        Index("IX_promotions_firm_version_group", "firm_id", "version_group_id"),
    )

    #: No foreign key: `firms` lives only in the platform schema and this table
    #: lives in every firm store, so a reference would be unresolvable there --
    #: and `Base.metadata.create_all`, which the seed and tenancy-reset scripts
    #: use to build a firm store, would refuse the table outright.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: Lowest number applies first. `code` breaks a tie so two promotions of
    #: equal priority never swap places between runs -- the same document must
    #: always price the same.
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    #: Whether promotions after this one may still apply. False ends the
    #: evaluation once this promotion has been applied, which is how a firm
    #: says "this offer is instead of everything else, not on top of it".
    allow_stacking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: Judged against the document's own date, never the server clock: an offer
    #: that ran in April must still explain an April order in September.
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    #: Whether the customer has to ask for this offer by name. A promotion
    #: requiring a coupon never applies on its own, however well a document
    #: otherwise matches it.
    requires_coupon: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: How many times the campaign may be claimed in total, and by any one
    #: customer. Null is no limit, which is a different answer from zero --
    #: hence nullable rather than a default nobody chose.
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    max_redemptions_per_customer: Mapped[int | None] = mapped_column(Integer)
    #: The promotion's published revision. `version` -- inherited from
    #: `BaseEntity` -- is the optimistic-concurrency counter and must not be
    #: reused for this, which is the trap `uom.ConversionRule` fell into.
    version_group_id: Mapped[UUID] = mapped_column(
        UUIDType(), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    supersedes_promotion_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("promotions.id", ondelete="RESTRICT")
    )

    conditions: Mapped[list["PromotionCondition"]] = relationship(
        back_populates="promotion",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Promotion.id == PromotionCondition.promotion_id,
            PromotionCondition.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="PromotionCondition.sequence",
    )
    actions: Mapped[list["PromotionAction"]] = relationship(
        back_populates="promotion",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Promotion.id == PromotionAction.promotion_id,
            PromotionAction.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="PromotionAction.sequence",
    )
    superseded_promotion: Mapped["Promotion | None"] = relationship(
        remote_side="Promotion.id"
    )


class PromotionCondition(BaseEntity):
    """Store one condition a promotion is matched on."""

    __tablename__ = "promotion_conditions"
    __table_args__ = (
        Index("IX_promotion_conditions_firm_promotion", "firm_id", "promotion_id"),
        Index("IX_promotion_conditions_firm_field", "firm_id", "field_key"),
    )

    #: No foreign key, for the reason `Promotion.firm_id` gives above.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    promotion_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("promotions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    operator: Mapped[str] = mapped_column(String(30), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    value_date: Mapped[date | None] = mapped_column(Date)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_json: Mapped[dict[str, object] | list[object] | None] = mapped_column(JSON)

    promotion: Mapped[Promotion] = relationship(back_populates="conditions")


class PromotionAction(BaseEntity):
    """Store one benefit a promotion gives when it matches."""

    __tablename__ = "promotion_actions"
    __table_args__ = (
        Index("IX_promotion_actions_firm_promotion", "firm_id", "promotion_id"),
        Index("IX_promotion_actions_firm_type", "firm_id", "action_type"),
    )

    #: No foreign key, for the reason `Promotion.firm_id` gives above.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    promotion_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("promotions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    promotion: Mapped[Promotion] = relationship(back_populates="actions")


class PromotionExecutionLog(BaseEntity):
    """Store what the engine was asked, what it considered, and what it gave.

    The answer to "why did this customer get that price", which a discount
    stored on a line cannot give on its own. Same shape and the same growth
    problem as `tax_rule_execution_logs`, so it is pruned by the same retention
    script rather than growing for ever.
    """

    __tablename__ = "promotion_execution_logs"
    __table_args__ = (
        Index("IX_promotion_execution_logs_firm_created", "firm_id", "created_at"),
        Index("IX_promotion_execution_logs_firm_type", "firm_id", "transaction_type"),
    )

    #: No foreign key, for the reason `Promotion.firm_id` gives above.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date)
    customer_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    input_payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    #: Every promotion considered and why it did or did not apply, in the order
    #: they were evaluated -- not only the ones that matched. A trace that shows
    #: the winners alone cannot answer why a promotion the firm expected did
    #: nothing, which is the question support actually gets.
    evaluation_trace: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    result_payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class PromotionCoupon(BaseEntity):
    """A code a customer presents to claim an offer.

    A coupon is a way of *reaching* a promotion, not a second kind of one: the
    benefit, the conditions and the stacking rule all still live on the
    promotion it names. What a coupon adds is that the offer applies only when
    somebody asks for it by name.
    """

    __tablename__ = "promotion_coupons"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_promotion_coupons_firm_code"),
        Index("IX_promotion_coupons_firm_promotion", "firm_id", "promotion_id"),
    )

    #: No foreign key, for the reason `Promotion.firm_id` gives above.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    promotion_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("promotions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    #: How many times this coupon may be claimed in total, and by any one
    #: customer. Null means no limit -- which is different from zero, and the
    #: reason both are nullable rather than defaulting to a number nobody
    #: chose.
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    max_redemptions_per_customer: Mapped[int | None] = mapped_column(Integer)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    promotion: Mapped[Promotion] = relationship(lazy="selectin")


class PromotionRedemption(BaseEntity):
    """One claim on an offer, and what it was worth.

    Written when a document is **approved**, never while it is priced. Pricing
    runs on the caller's session and must never commit -- so a counter
    incremented there would either publish a half-written order or count a
    draft that is edited five more times before anybody approves it.

    Reversed rather than deleted when the document is cancelled: what a
    customer claimed and what they gave back are two facts, and a ledger that
    forgets the first cannot explain the second.
    """

    __tablename__ = "promotion_redemptions"
    __table_args__ = (
        Index("IX_promotion_redemptions_firm_promotion", "firm_id", "promotion_id"),
        Index("IX_promotion_redemptions_firm_customer", "firm_id", "customer_id"),
        Index("IX_promotion_redemptions_document", "firm_id", "document_id"),
    )

    #: No foreign key, for the reason `Promotion.firm_id` gives above.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    promotion_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("promotions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    coupon_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("promotion_coupons.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    #: The document that claimed it. A bare UUID with no foreign key, because
    #: more than one table can hold one -- the same shape
    #: `source_document_line_id` has.
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(60))
    redeemed_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: What the claim was worth, so a campaign can be costed without re-pricing
    #: every document it touched.
    benefit_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: CLAIMED or REVERSED. Only a claim counts against a limit.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="CLAIMED", server_default="CLAIMED"
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
