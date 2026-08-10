"""Firm-scoped enterprise tax framework persistence models."""

from datetime import date
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
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

from app.business.models import AttributeEntityType, AttributeValueBase
from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class TaxSystem(BaseEntity):
    """Store one configurable tax system per firm and country."""

    __tablename__ = "tax_systems"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_tax_systems_firm_code"),
        Index("IX_tax_systems_firm_country", "firm_id", "country_id"),
        Index("IX_tax_systems_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    country_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_countries.id", ondelete="RESTRICT"), index=True
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    components: Mapped[list["TaxComponent"]] = relationship(
        back_populates="tax_system",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            TaxSystem.id == TaxComponent.tax_system_id,
            TaxComponent.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="TaxComponent.calculation_order",
    )


class TaxComponent(BaseEntity):
    """Store one configurable tax component for a tax system."""

    __tablename__ = "tax_components"
    __table_args__ = (
        UniqueConstraint("tax_system_id", "code", name="UQ_tax_components_system_code"),
        Index("IX_tax_components_firm_system", "firm_id", "tax_system_id"),
        Index("IX_tax_components_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    tax_system_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tax_systems.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    short_label: Mapped[str | None] = mapped_column(String(40))
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    calculation_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0, server_default="0"
    )
    included_in_price: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    recoverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    tax_system: Mapped[TaxSystem] = relationship(back_populates="components")


class TaxProfile(BaseEntity):
    """Store one reusable tax profile applied by products."""

    __tablename__ = "tax_profiles"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_tax_profiles_firm_code"),
        Index("IX_tax_profiles_firm_system", "firm_id", "tax_system_id"),
        Index("IX_tax_profiles_firm_status", "firm_id", "status"),
        Index("IX_tax_profiles_firm_group_code", "firm_id", "group_code"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    tax_system_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tax_systems.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_historical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    group_code: Mapped[str | None] = mapped_column(String(50))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    tax_system: Mapped[TaxSystem] = relationship(lazy="selectin")
    components: Mapped[list["TaxProfileComponent"]] = relationship(
        back_populates="tax_profile",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            TaxProfile.id == TaxProfileComponent.tax_profile_id,
            TaxProfileComponent.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="TaxProfileComponent.calculation_order",
    )


class TaxProfileComponent(BaseEntity):
    """Store component composition and percentages for one tax profile."""

    __tablename__ = "tax_profile_components"
    __table_args__ = (
        UniqueConstraint(
            "tax_profile_id",
            "tax_component_id",
            name="UQ_tax_profile_components_profile_component",
        ),
        Index("IX_tax_profile_components_firm_profile", "firm_id", "tax_profile_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    tax_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tax_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tax_component_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tax_components.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String(120))
    short_label: Mapped[str | None] = mapped_column(String(40))
    calculation_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0, server_default="0"
    )
    included_in_price: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    recoverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    tax_profile: Mapped[TaxProfile] = relationship(back_populates="components")
    tax_component: Mapped[TaxComponent] = relationship(lazy="selectin")


class TaxCountryMapping(BaseEntity):
    """Store default tax system mapping per country and profile context."""

    __tablename__ = "tax_country_mappings"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "country_id",
            "business_profile_id",
            "tax_system_id",
            name="UQ_tax_country_mappings_unique",
        ),
        Index("IX_tax_country_mappings_firm_country", "firm_id", "country_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    country_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("geo_countries.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    tax_system_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tax_systems.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class TaxMigrationMapping(BaseEntity):
    """Store migration mapping from legacy tax definitions."""

    __tablename__ = "tax_migration_mappings"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "legacy_tax_code",
            "legacy_tax_name",
            name="UQ_tax_migration_mappings_legacy",
        ),
        Index(
            "IX_tax_migration_mappings_firm_historical", "firm_id", "keep_historical"
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    legacy_tax_code: Mapped[str] = mapped_column(String(50), nullable=False)
    legacy_tax_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(120))
    legacy_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    target_tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT")
    )
    keep_historical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    notes: Mapped[str | None] = mapped_column(Text)


class TaxSettings(BaseEntity):
    """Store configurable enterprise tax labels and behavior per firm."""

    __tablename__ = "tax_settings"
    __table_args__ = (UniqueConstraint("firm_id", name="UQ_tax_settings_firm"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    primary_label: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Tax", server_default="Tax"
    )
    component_label: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Component", server_default="Component"
    )
    profile_label: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Profile", server_default="Profile"
    )
    report_label: Mapped[str] = mapped_column(
        String(80), nullable=False, default="Tax", server_default="Tax"
    )
    allow_mixed_historical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    additional_settings: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class TaxRule(BaseEntity):
    """Store versioned tax rule masters evaluated by the tax engine."""

    __tablename__ = "tax_rules"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "code",
            "version_number",
            name="UQ_tax_rules_firm_code_version",
        ),
        Index("IX_tax_rules_firm_priority", "firm_id", "priority"),
        Index("IX_tax_rules_firm_status", "firm_id", "status"),
        Index("IX_tax_rules_firm_version_group", "firm_id", "version_group_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    country_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_countries.id", ondelete="RESTRICT"), index=True
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    version_group_id: Mapped[UUID] = mapped_column(
        UUIDType(), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    supersedes_rule_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_rules.id", ondelete="RESTRICT")
    )
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    tax_profile: Mapped[TaxProfile | None] = relationship(lazy="selectin")
    conditions: Mapped[list["TaxRuleCondition"]] = relationship(
        back_populates="rule",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            TaxRule.id == TaxRuleCondition.tax_rule_id,
            TaxRuleCondition.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="TaxRuleCondition.sequence",
    )
    actions: Mapped[list["TaxRuleAction"]] = relationship(
        back_populates="rule",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            TaxRule.id == TaxRuleAction.tax_rule_id,
            TaxRuleAction.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="TaxRuleAction.sequence",
    )
    superseded_rule: Mapped["TaxRule | None"] = relationship(remote_side="TaxRule.id")


class TaxRuleCondition(BaseEntity):
    """Store one configurable condition attached to a tax rule."""

    __tablename__ = "tax_rule_conditions"
    __table_args__ = (
        Index("IX_tax_rule_conditions_firm_rule", "firm_id", "tax_rule_id"),
        Index("IX_tax_rule_conditions_firm_field", "firm_id", "field_key"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    tax_rule_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tax_rules.id", ondelete="RESTRICT"),
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

    rule: Mapped[TaxRule] = relationship(back_populates="conditions")


class TaxRuleAction(BaseEntity):
    """Store one action performed when a tax rule matches."""

    __tablename__ = "tax_rule_actions"
    __table_args__ = (
        Index("IX_tax_rule_actions_firm_rule", "firm_id", "tax_rule_id"),
        Index("IX_tax_rule_actions_firm_type", "firm_id", "action_type"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    tax_rule_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tax_rules.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT")
    )
    target_tax_component_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_components.id", ondelete="RESTRICT")
    )
    percentage_override: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    parameters: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    rule: Mapped[TaxRule] = relationship(back_populates="actions")
    target_tax_profile: Mapped[TaxProfile | None] = relationship(
        foreign_keys=[target_tax_profile_id],
        lazy="selectin",
    )
    target_tax_component: Mapped[TaxComponent | None] = relationship(
        foreign_keys=[target_tax_component_id],
        lazy="selectin",
    )


class TaxRuleExecutionLog(BaseEntity):
    """Persist simulation and preview runs with immutable explanations."""

    __tablename__ = "tax_rule_execution_logs"
    __table_args__ = (
        Index("IX_tax_rule_execution_logs_firm_mode", "firm_id", "execution_mode"),
        Index("IX_tax_rule_execution_logs_firm_rule", "firm_id", "matched_rule_id"),
        Index("IX_tax_rule_execution_logs_firm_created", "firm_id", "created_at"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    execution_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    country_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_countries.id", ondelete="RESTRICT")
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT")
    )
    matched_rule_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_rules.id", ondelete="RESTRICT")
    )
    applied_tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT")
    )
    input_payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    evaluation_trace: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    result_payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    matched_rule: Mapped[TaxRule | None] = relationship(
        foreign_keys=[matched_rule_id],
        lazy="selectin",
    )


class TaxProfileAttributeValue(AttributeValueBase):
    """Store one configurable attribute value for a tax profile."""

    __tablename__ = "tax_profile_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "tax_profile_id",
            "attribute_definition_id",
            name="UQ_tax_profile_attribute_values_owner_attribute",
        ),
        Index("IX_tax_profile_attribute_values_firm_text", "firm_id", "value_text"),
        Index("IX_tax_profile_attribute_values_firm_number", "firm_id", "value_number"),
        Index("IX_tax_profile_attribute_values_firm_date", "firm_id", "value_date"),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.TAX_PROFILE
    OWNER_COLUMN: ClassVar[str] = "tax_profile_id"

    tax_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tax_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
