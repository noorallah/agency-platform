"""SQLAlchemy models for the multi-industry business profile framework."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar, cast
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class BusinessProfile(BaseEntity):
    """Define one industry/business operating profile."""

    __tablename__ = "business_profiles"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    industry_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    default_settings: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class BusinessFeature(BaseEntity):
    """Define one configurable framework feature flag."""

    __tablename__ = "business_features"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    default_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: Whether anything in the codebase actually implements this feature.
    #:
    #: Distinct from ``is_active``, which is a choice an administrator makes.
    #: This is a statement of fact: seven catalogue entries had no backing code
    #: in either application, so enabling one promised a customer something
    #: that could never happen. They stay in the catalogue as roadmap, and this
    #: flag stops them being switched on.
    #:
    #: Six remain -- IMEI, PRESCRIPTION_REQUIRED, RECIPE_MANAGEMENT,
    #: KITCHEN_MANAGEMENT, SERVICE_CONTRACTS and PROJECT_MANAGEMENT.
    #: ``COMMISSION`` came off the list on 2026-09-03, because `app/commission`
    #: shipped on 2026-08-23 and the flag outlived the fact. **A flag recording
    #: what the codebase does has to be revisited when the codebase does it**,
    #: or it goes on refusing a feature the platform has.
    is_implemented: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class BusinessModule(BaseEntity):
    """Define one configurable module in the ERP workspace."""

    __tablename__ = "business_modules"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ui_route: Mapped[str | None] = mapped_column(String(100))
    default_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class ProfileFeature(BaseEntity):
    """Store per-profile feature enablement and optional configuration."""

    __tablename__ = "profile_features"
    __table_args__ = (UniqueConstraint("business_profile_id", "feature_id"),)

    business_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id"), nullable=False
    )
    feature_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_features.id"), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    configuration: Mapped[dict[str, object] | None] = mapped_column(JSON)


class ProfileModule(BaseEntity):
    """Store per-profile module visibility and workflow configuration."""

    __tablename__ = "profile_modules"
    __table_args__ = (UniqueConstraint("business_profile_id", "module_id"),)

    business_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id"), nullable=False
    )
    module_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_modules.id"), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    configuration: Mapped[dict[str, object] | None] = mapped_column(JSON)


class AttributeEntityType(StrEnum):
    """Name the records a custom attribute can extend.

    Adding a member here plus a call to ``AttributeService`` is all a module
    needs to gain configurable fields; no schema change is required.
    """

    PRODUCT = "PRODUCT"
    CUSTOMER = "CUSTOMER"
    VENDOR = "VENDOR"
    BRANCH = "BRANCH"
    WAREHOUSE = "WAREHOUSE"
    TAX_PROFILE = "TAX_PROFILE"
    #: Units are a shared catalogue: one row serves every firm in a shared
    #: store, so unlike the others its values must be read firm-scoped.
    UOM = "UOM"
    #: Documents (MST-6): a firm's own fields on its orders, notes and
    #: invoices -- a site name, the buyer's PO reference.
    QUOTATION = "QUOTATION"
    SALES_ORDER = "SALES_ORDER"
    DELIVERY_NOTE = "DELIVERY_NOTE"
    SALES_INVOICE = "SALES_INVOICE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    PURCHASE_INVOICE = "PURCHASE_INVOICE"


class AttributeDataType(StrEnum):
    """Supported value types for a custom attribute."""

    TEXT = "TEXT"
    NUMBER = "NUMBER"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"


class AttributeDefinition(BaseEntity):
    """Define one configurable field that extends a record for some industry.

    A definition is scoped by ``entity_type`` (which record it extends). A
    shared one is offered to every firm unless that firm switched it off
    (``firm_attribute_switches``), and a rule naming a kind of record --
    a goods type, a customer group, a supplier type -- ties it to records of
    that kind (``category_attribute_rules``). The firm's business profile has
    no say (backlog 89).
    """

    __tablename__ = "attribute_definitions"
    __table_args__ = (
        # A firm's code is its own (MST-8); the shared catalogue's codes are
        # unique among themselves. The service also keeps a firm's code clear
        # of the shared ones, which no single index can say.
        Index(
            "UQ_attribute_definitions_firm_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false AND firm_id IS NOT NULL"),
            sqlite_where=text("is_deleted = 0 AND firm_id IS NOT NULL"),
        ),
        Index(
            "UQ_attribute_definitions_shared_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false AND firm_id IS NULL"),
            sqlite_where=text("is_deleted = 0 AND firm_id IS NULL"),
        ),
    )

    #: The firm whose own field this is (MST-8); null for the platform's
    #: shared catalogue, offered to every firm.
    firm_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=AttributeEntityType.PRODUCT.value,
        server_default=AttributeEntityType.PRODUCT.value,
        index=True,
    )
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Whether the field prints on a document it is filled on (MST-6).
    show_on_print: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    default_value: Mapped[str | None] = mapped_column(Text)
    validation_rule: Mapped[dict[str, object] | None] = mapped_column(JSON)

    @property
    def allowed_values(self) -> list[str]:
        """The fixed choices a TEXT field is limited to, or none.

        Read off ``validation_rule["allowed_values"]``, which is where the
        rule lives; the column existed unused since the framework was written
        and this is its first meaning. Empty means free text.
        """
        rule = self.validation_rule or {}
        raw = rule.get("allowed_values")
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw if str(item).strip()]

    applicable_category: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


#: The columns of a rule that name a kind of record, and the entity type
#: each one belongs to. A field with a rule on one of them is *tied*: it is
#: offered only on records of the kinds its rules name.
RULE_KIND_COLUMNS: dict[str, str] = {
    "goods_type_id": "PRODUCT",
    "customer_group_id": "CUSTOMER",
    "vendor_type_id": "VENDOR",
}


def _rule_key(column: str) -> Index:
    """Return the key holding one live rule per firm, kind and field."""
    return Index(
        f"UQ_category_attribute_rules_{column.removesuffix('_id')}_active",
        "firm_id",
        column,
        "attribute_definition_id",
        unique=True,
        postgresql_where=text(f"is_deleted = false AND {column} IS NOT NULL"),
        sqlite_where=text(f"is_deleted = 0 AND {column} IS NOT NULL"),
    )


class CategoryAttributeRule(BaseEntity):
    """Say which records a field belongs to, and where it is compulsory.

    A rule names exactly one thing: a product category by its code, a goods
    type, a customer group or a supplier type. A category rule only makes the
    field compulsory there. A rule on one of the three kinds also ties the
    field to that kind -- it is offered on records of the kinds its rules
    name and on no other -- and ``is_mandatory`` says whether it must be
    filled. The business profile no longer takes part (backlog 89).

    The keys guard a firm's own rules. A shared rule has no ``firm_id``, which
    no unique index compares, so the service refuses its duplicate.
    """

    __tablename__ = "category_attribute_rules"
    __table_args__ = (
        _rule_key("category_code"),
        _rule_key("goods_type_id"),
        _rule_key("customer_group_id"),
        _rule_key("vendor_type_id"),
    )

    #: The firm whose own rule this is (MST-8); null for a shared rule.
    firm_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    category_code: Mapped[str | None] = mapped_column(String(100))
    goods_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "goods_types.id",
            name="FK_category_attribute_rules_goods_type_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    customer_group_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "customer_groups.id",
            name="FK_category_attribute_rules_customer_group_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    vendor_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "vendor_types.id",
            name="FK_category_attribute_rules_vendor_type_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    attribute_definition_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("attribute_definitions.id"), nullable=False
    )
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    validation_override: Mapped[dict[str, object] | None] = mapped_column(JSON)


class FirmAttributeSwitch(BaseEntity):
    """One firm's on or off for a field of the shared catalogue.

    No row means on. Switching a shared field off hides it from that firm's
    forms and keeps every value already stored; a firm's own field has its
    ``is_active`` for the same purpose and never a row here.
    """

    __tablename__ = "firm_attribute_switches"
    __table_args__ = (
        Index(
            "UQ_firm_attribute_switches_firm_field_active",
            "firm_id",
            "attribute_definition_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    attribute_definition_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "attribute_definitions.id",
            name="FK_firm_attribute_switches_attribute_definition_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class FirmBusinessProfile(BaseEntity):
    """Assign exactly one active business profile to a firm."""

    __tablename__ = "firm_business_profiles"
    # One profile per **live** assignment, not per row ever written. The
    # table-wide UNIQUE this replaces would have let a soft-deleted row block
    # its firm from ever being assigned again: the row is invisible to every
    # query here -- all of them filter `is_deleted` -- while still holding the
    # key. Nothing soft-deletes one today, so this closes the trap before the
    # first "unassign" action opens it rather than after. Mirrors
    # UQ_firms_code_active. MySQL ignores the predicate, so the service check
    # in `assign_profile_to_firm`, which updates in place, stays authoritative
    # there.
    __table_args__ = (
        Index(
            "UQ_firm_business_profiles_firm_active",
            "firm_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False
    )
    business_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class AttributeValueBase(BaseEntity):
    """Shared columns for a module's custom attribute values.

    Each module owns a small concrete table (``product_attribute_values``,
    ``customer_attribute_values``, …) so the value carries a real foreign key to
    its record and gets its own indexes. The behaviour stays generic:
    ``AttributeService`` is parameterised by the model, so there is still one
    implementation, one set of tests, and one form renderer.

    Values live in typed columns rather than a serialized blob so that list
    filters and reports can index and query them.
    """

    __abstract__ = True

    #: Which catalogue entries apply to this table.
    ENTITY_TYPE: ClassVar[AttributeEntityType]
    #: Name of the foreign-key column pointing at the owning record.
    OWNER_COLUMN: ClassVar[str]

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    attribute_definition_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("attribute_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    value_date: Mapped[date | None] = mapped_column(Date)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)

    @classmethod
    def owner_column(cls) -> Mapped[UUID]:
        """Return the mapped foreign-key column pointing at the owning record."""
        return cast("Mapped[UUID]", getattr(cls, cls.OWNER_COLUMN))
