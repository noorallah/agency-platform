"""Request and response contracts for business profile framework APIs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_BUSINESS_PROFILE_STATUSES = frozenset({"ACTIVE", "INACTIVE", "ARCHIVED"})


class BusinessFrameworkSchema(BaseModel):
    """Base schema behavior for business framework APIs."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class IdentifierList(BusinessFrameworkSchema):
    """Reusable list of entity identifiers."""

    ids: list[UUID] = Field(default_factory=list)


class BusinessProfileCreate(BusinessFrameworkSchema):
    """Payload for creating a business profile."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    industry_type: str = Field(min_length=2, max_length=100)
    status: str = Field(default="ACTIVE", min_length=2, max_length=20)
    is_default: bool = False
    default_settings: dict[str, object] = Field(default_factory=dict)

    @field_validator("code", "industry_type", "status", mode="before")
    @classmethod
    def _normalize_upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in _BUSINESS_PROFILE_STATUSES:
            raise ValueError("Status must be ACTIVE, INACTIVE, or ARCHIVED.")
        return value


class BusinessProfileUpdate(BusinessProfileCreate):
    """Payload for replacing a business profile."""


class BusinessProfileResponse(BusinessFrameworkSchema):
    """Business profile API response."""

    id: UUID
    code: str
    name: str
    description: str | None
    industry_type: str
    status: str
    is_default: bool
    default_settings: dict[str, object]
    created_at: datetime
    updated_at: datetime


class BusinessFeatureCreate(BusinessFrameworkSchema):
    """Payload for creating a feature definition."""

    code: str = Field(min_length=2, max_length=100, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    default_enabled: bool = False
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class BusinessFeatureUpdate(BusinessFeatureCreate):
    """Payload for replacing a feature definition."""


class BusinessFeatureResponse(BusinessFrameworkSchema):
    """Feature definition API response."""

    id: UUID
    code: str
    name: str
    description: str | None
    category: str | None
    default_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BusinessModuleCreate(BusinessFrameworkSchema):
    """Payload for creating a module definition."""

    code: str = Field(min_length=2, max_length=100, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    ui_route: str | None = Field(default=None, max_length=100)
    default_enabled: bool = True
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class BusinessModuleUpdate(BusinessModuleCreate):
    """Payload for replacing a module definition."""


class BusinessModuleResponse(BusinessFrameworkSchema):
    """Module definition API response."""

    id: UUID
    code: str
    name: str
    description: str | None
    ui_route: str | None
    default_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AttributeDefinitionCreate(BusinessFrameworkSchema):
    """Payload for creating a reusable attribute definition."""

    code: str = Field(min_length=2, max_length=100, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    data_type: str = Field(min_length=2, max_length=50)
    mandatory: bool = False
    default_value: str | None = None
    validation_rule: dict[str, object] | None = None
    applicable_category: str | None = Field(default=None, max_length=100)
    applicable_business_profile_id: UUID | None = None
    is_active: bool = True

    @field_validator("code", "data_type", mode="before")
    @classmethod
    def _normalize_upper(cls, value: str) -> str:
        return value.strip().upper()


class AttributeDefinitionUpdate(AttributeDefinitionCreate):
    """Payload for replacing an attribute definition."""


class AttributeDefinitionResponse(BusinessFrameworkSchema):
    """Attribute definition API response."""

    id: UUID
    code: str
    name: str
    description: str | None
    data_type: str
    mandatory: bool
    default_value: str | None
    validation_rule: dict[str, object] | None
    applicable_category: str | None
    applicable_business_profile_id: UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryAttributeRuleCreate(BusinessFrameworkSchema):
    """Payload for creating one category attribute rule."""

    business_profile_id: UUID | None = None
    category_code: str = Field(min_length=2, max_length=100)
    attribute_definition_id: UUID
    is_mandatory: bool = True
    validation_override: dict[str, object] | None = None

    @field_validator("category_code", mode="before")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class CategoryAttributeRuleUpdate(CategoryAttributeRuleCreate):
    """Payload for replacing one category attribute rule."""


class CategoryAttributeRuleResponse(BusinessFrameworkSchema):
    """Category attribute rule API response."""

    id: UUID
    business_profile_id: UUID | None
    category_code: str
    attribute_definition_id: UUID
    is_mandatory: bool
    validation_override: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


class FirmBusinessProfileAssign(BusinessFrameworkSchema):
    """Assign one business profile to a firm."""

    business_profile_id: UUID
    is_active: bool = True
    notes: str | None = None


class FirmBusinessProfileResponse(BusinessFrameworkSchema):
    """Firm-to-profile assignment API response."""

    id: UUID
    firm_id: UUID
    business_profile_id: UUID
    is_active: bool
    effective_from: datetime
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ActiveFeatureResponse(BusinessFrameworkSchema):
    """One active feature resolved for a firm/profile context."""

    id: UUID
    code: str
    name: str
    category: str | None
    configuration: dict[str, object]


class ActiveModuleResponse(BusinessFrameworkSchema):
    """One active module resolved for a firm/profile context."""

    id: UUID
    code: str
    name: str
    ui_route: str | None
    display_order: int


class BusinessProfileConfigurationResponse(BusinessFrameworkSchema):
    """Assignment state used by desktop configuration forms."""

    feature_ids: list[UUID]
    module_ids: list[UUID]
