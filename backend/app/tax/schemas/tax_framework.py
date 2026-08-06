"""Validated request and response contracts for enterprise tax framework."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaxStatus(StrEnum):
    """Supported status values for tax entities."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class TaxRuleConditionOperator(StrEnum):
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


class TaxRuleActionType(StrEnum):
    APPLY_TAX_PROFILE = "APPLY_TAX_PROFILE"
    APPLY_TAX_COMPONENT = "APPLY_TAX_COMPONENT"
    EXEMPT_TAX = "EXEMPT_TAX"
    ZERO_RATED = "ZERO_RATED"
    REVERSE_CHARGE = "REVERSE_CHARGE"
    INPUT_CREDIT_ALLOWED = "INPUT_CREDIT_ALLOWED"
    INPUT_CREDIT_BLOCKED = "INPUT_CREDIT_BLOCKED"
    OVERRIDE_COMPONENT_PERCENTAGE = "OVERRIDE_COMPONENT_PERCENTAGE"


class TaxFrameworkSchema(BaseModel):
    """Apply strict validation and ORM serialization behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class EffectiveDatedSchema(TaxFrameworkSchema):
    """Base schema carrying effective date validation."""

    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_effective_window(self) -> "EffectiveDatedSchema":
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_from > self.effective_to
        ):
            raise ValueError("effective_from cannot be after effective_to.")
        return self


class TaxSystemWrite(EffectiveDatedSchema):
    """Create or update one tax system."""

    country_id: UUID | None = None
    business_profile_id: UUID | None = None
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=120)
    description: str | None = None
    status: TaxStatus = TaxStatus.ACTIVE
    display_order: int = Field(default=0, ge=0, le=100000)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name", "display_name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def default_display_name(self) -> "TaxSystemWrite":
        if not self.display_name:
            self.display_name = self.name
        return self


class TaxComponentWrite(EffectiveDatedSchema):
    """Create or update one configurable tax component."""

    tax_system_id: UUID
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    label: str | None = Field(default=None, max_length=120)
    short_label: str | None = Field(default=None, max_length=40)
    display_order: int = Field(default=0, ge=0, le=100000)
    calculation_order: int = Field(default=0, ge=0, le=100000)
    percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    included_in_price: bool = False
    recoverable: bool = False
    status: TaxStatus = TaxStatus.ACTIVE

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name", "label", "short_label", mode="before")
    @classmethod
    def normalize_labels(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def default_labels(self) -> "TaxComponentWrite":
        if not self.label:
            self.label = self.name
        if not self.short_label:
            self.short_label = self.code
        return self


class TaxProfileComponentInput(TaxFrameworkSchema):
    """One tax profile component assignment."""

    tax_component_id: UUID
    label: str | None = Field(default=None, max_length=120)
    short_label: str | None = Field(default=None, max_length=40)
    calculation_order: int = Field(default=0, ge=0, le=100000)
    percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    included_in_price: bool = False
    recoverable: bool = False


class TaxProfileWrite(EffectiveDatedSchema):
    """Create or update one tax profile."""

    tax_system_id: UUID
    business_profile_id: UUID | None = None
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    label: str | None = Field(default=None, max_length=120)
    description: str | None = None
    status: TaxStatus = TaxStatus.ACTIVE
    display_order: int = Field(default=0, ge=0, le=100000)
    is_historical: bool = False
    components: list[TaxProfileComponentInput] = Field(default_factory=list, max_length=50)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name", "label", mode="before")
    @classmethod
    def normalize_labels(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def default_label(self) -> "TaxProfileWrite":
        if not self.label:
            self.label = self.name
        return self


class TaxCountryMappingWrite(EffectiveDatedSchema):
    """Create or update country-to-tax-system mapping."""

    country_id: UUID
    business_profile_id: UUID | None = None
    tax_system_id: UUID
    status: TaxStatus = TaxStatus.ACTIVE
    is_default: bool = True


class TaxMigrationMappingWrite(TaxFrameworkSchema):
    """Create or update legacy tax migration mapping."""

    legacy_tax_code: str = Field(min_length=1, max_length=50)
    legacy_tax_name: str = Field(min_length=1, max_length=120)
    source_system: str | None = Field(default=None, max_length=120)
    legacy_rate: Decimal | None = Field(default=None, ge=0, le=100)
    target_tax_profile_id: UUID | None = None
    keep_historical: bool = True
    status: TaxStatus = TaxStatus.ACTIVE
    notes: str | None = None

    @field_validator("legacy_tax_code", mode="before")
    @classmethod
    def normalize_legacy_code(cls, value: str) -> str:
        return value.strip().upper()


class TaxSettingsWrite(TaxFrameworkSchema):
    """Create or update tax settings and configurable labels."""

    primary_label: str = Field(default="Tax", min_length=1, max_length=50)
    component_label: str = Field(default="Component", min_length=1, max_length=50)
    profile_label: str = Field(default="Profile", min_length=1, max_length=50)
    report_label: str = Field(default="Tax", min_length=1, max_length=80)
    allow_mixed_historical: bool = True
    additional_settings: dict[str, object] = Field(default_factory=dict)


class TaxRuleConditionWrite(TaxFrameworkSchema):
    sequence: int = Field(default=1, ge=1, le=100000)
    field_key: str = Field(min_length=1, max_length=80)
    operator: TaxRuleConditionOperator
    value_text: str | None = None
    value_number: Decimal | None = Field(default=None, ge=0)
    value_date: date | None = None
    value_boolean: bool | None = None
    value_json: dict[str, object] | list[object] | None = None

    @field_validator("field_key", mode="before")
    @classmethod
    def normalize_field_key(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_value_presence(self) -> "TaxRuleConditionWrite":
        if self.operator in {
            TaxRuleConditionOperator.EXISTS,
            TaxRuleConditionOperator.NOT_EXISTS,
        }:
            return self
        if (
            self.value_text is None
            and self.value_number is None
            and self.value_date is None
            and self.value_boolean is None
            and self.value_json is None
        ):
            raise ValueError("At least one condition value must be supplied.")
        return self


class TaxRuleActionWrite(TaxFrameworkSchema):
    sequence: int = Field(default=1, ge=1, le=100000)
    action_type: TaxRuleActionType
    target_tax_profile_id: UUID | None = None
    target_tax_component_id: UUID | None = None
    percentage_override: Decimal | None = Field(default=None, ge=0, le=100)
    parameters: dict[str, object] = Field(default_factory=dict)


class TaxRuleWrite(EffectiveDatedSchema):
    country_id: UUID | None = None
    business_profile_id: UUID | None = None
    tax_profile_id: UUID | None = None
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    priority: int = Field(default=100, ge=1, le=100000)
    status: TaxStatus = TaxStatus.DRAFT
    conditions: list[TaxRuleConditionWrite] = Field(default_factory=list, max_length=100)
    actions: list[TaxRuleActionWrite] = Field(default_factory=list, max_length=50)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_rule_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name", mode="before")
    @classmethod
    def normalize_rule_name(cls, value: str) -> str:
        return value.strip()


class TaxRuleSimulationRequest(TaxFrameworkSchema):
    transaction_type: str = Field(min_length=1, max_length=40)
    transaction_date: date | None = None
    country_id: UUID | None = None
    business_profile_id: UUID | None = None
    tax_profile_id: UUID | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    customer_id: UUID | None = None
    vendor_id: UUID | None = None
    customer_type: str | None = None
    vendor_type: str | None = None
    customer_category: str | None = None
    vendor_category: str | None = None
    currency_code: str | None = Field(default=None, max_length=10)
    origin: str | None = None
    destination: str | None = None
    state: str | None = None
    district: str | None = None
    city: str | None = None
    product_id: UUID | None = None
    product_category_id: UUID | None = None
    product_type: str | None = None
    invoice_value: Decimal | None = Field(default=None, ge=0)
    quantity: Decimal | None = Field(default=None, ge=0)
    additional_context: dict[str, object] = Field(default_factory=dict)

    @field_validator("transaction_type", "customer_type", "vendor_type", mode="before")
    @classmethod
    def normalize_upper_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized.upper() or None

    @field_validator(
        "currency_code",
        "origin",
        "destination",
        "state",
        "district",
        "city",
        "customer_category",
        "vendor_category",
        "product_type",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class TaxSystemResponse(TaxFrameworkSchema):
    id: UUID
    firm_id: UUID
    country_id: UUID | None
    business_profile_id: UUID | None
    code: str
    name: str
    display_name: str
    description: str | None
    status: TaxStatus
    display_order: int
    effective_from: date | None
    effective_to: date | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class TaxComponentResponse(TaxFrameworkSchema):
    id: UUID
    firm_id: UUID
    tax_system_id: UUID
    code: str
    name: str
    label: str
    short_label: str | None
    display_order: int
    calculation_order: int
    percentage: Decimal
    included_in_price: bool
    recoverable: bool
    status: TaxStatus
    effective_from: date | None
    effective_to: date | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class TaxProfileComponentResponse(TaxFrameworkSchema):
    id: UUID
    tax_component_id: UUID
    label: str | None
    short_label: str | None
    calculation_order: int
    percentage: Decimal
    included_in_price: bool
    recoverable: bool


class TaxProfileResponse(TaxFrameworkSchema):
    id: UUID
    firm_id: UUID
    tax_system_id: UUID
    business_profile_id: UUID | None
    code: str
    name: str
    label: str
    description: str | None
    status: TaxStatus
    display_order: int
    is_historical: bool
    effective_from: date | None
    effective_to: date | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    components: list[TaxProfileComponentResponse] = Field(default_factory=list)


class TaxRuleConditionResponse(TaxFrameworkSchema):
    id: UUID
    tax_rule_id: UUID
    sequence: int
    field_key: str
    operator: TaxRuleConditionOperator
    value_text: str | None
    value_number: Decimal | None
    value_date: date | None
    value_boolean: bool | None
    value_json: dict[str, object] | list[object] | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class TaxRuleActionResponse(TaxFrameworkSchema):
    id: UUID
    tax_rule_id: UUID
    sequence: int
    action_type: TaxRuleActionType
    target_tax_profile_id: UUID | None
    target_tax_component_id: UUID | None
    percentage_override: Decimal | None
    parameters: dict[str, object]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class TaxRuleResponse(TaxFrameworkSchema):
    id: UUID
    firm_id: UUID
    country_id: UUID | None
    business_profile_id: UUID | None
    tax_profile_id: UUID | None
    code: str
    name: str
    description: str | None
    priority: int
    status: TaxStatus
    version_group_id: UUID
    version_number: int
    supersedes_rule_id: UUID | None
    effective_from: date | None
    effective_to: date | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    conditions: list[TaxRuleConditionResponse] = Field(default_factory=list)
    actions: list[TaxRuleActionResponse] = Field(default_factory=list)


class TaxCountryMappingResponse(TaxFrameworkSchema):
    id: UUID
    firm_id: UUID
    country_id: UUID
    business_profile_id: UUID | None
    tax_system_id: UUID
    status: TaxStatus
    is_default: bool
    effective_from: date | None
    effective_to: date | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class TaxMigrationMappingResponse(TaxFrameworkSchema):
    id: UUID
    firm_id: UUID
    legacy_tax_code: str
    legacy_tax_name: str
    source_system: str | None
    legacy_rate: Decimal | None
    target_tax_profile_id: UUID | None
    keep_historical: bool
    status: TaxStatus
    notes: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class TaxSettingsResponse(TaxFrameworkSchema):
    id: UUID
    firm_id: UUID
    primary_label: str
    component_label: str
    profile_label: str
    report_label: str
    allow_mixed_historical: bool
    additional_settings: dict[str, object]
    created_at: datetime
    updated_at: datetime


class EffectiveDateRecord(TaxFrameworkSchema):
    entity_type: str
    entity_id: UUID
    code: str
    name: str
    status: TaxStatus
    effective_from: date | None
    effective_to: date | None


class TaxHistoryRecord(TaxFrameworkSchema):
    id: UUID
    action: str
    entity_type: str
    entity_id: UUID
    actor_id: UUID | None
    created_at: datetime


class TaxRulePriorityRecord(TaxFrameworkSchema):
    id: UUID
    code: str
    name: str
    priority: int
    status: TaxStatus
    version_number: int
    effective_from: date | None
    effective_to: date | None
    condition_count: int
    action_count: int


class TaxRuleComponentPreview(TaxFrameworkSchema):
    tax_component_id: UUID | None
    code: str
    label: str
    percentage: Decimal
    amount: Decimal
    included_in_price: bool
    recoverable: bool
    source: str


class TaxRuleEvaluationDecision(TaxFrameworkSchema):
    rule_id: UUID
    code: str
    name: str
    priority: int
    version_number: int
    matched: bool
    reasons: list[str] = Field(default_factory=list)


class TaxRuleSimulationResponse(TaxFrameworkSchema):
    transaction_type: str
    transaction_date: date
    matched_rule_id: UUID | None
    applied_tax_profile_id: UUID | None
    applied_components: list[TaxRuleComponentPreview] = Field(default_factory=list)
    total_tax_amount: Decimal
    base_amount: Decimal
    exempt: bool = False
    zero_rated: bool = False
    reverse_charge: bool = False
    input_credit_allowed: bool | None = None
    matched_rule_reason: str | None = None
    decisions: list[TaxRuleEvaluationDecision] = Field(default_factory=list)


class TaxRuleExecutionLogResponse(TaxFrameworkSchema):
    id: UUID
    firm_id: UUID
    execution_mode: str
    transaction_type: str
    country_id: UUID | None
    business_profile_id: UUID | None
    tax_profile_id: UUID | None
    matched_rule_id: UUID | None
    applied_tax_profile_id: UUID | None
    input_payload: dict[str, object]
    evaluation_trace: dict[str, object]
    result_payload: dict[str, object]
    created_at: datetime
    updated_at: datetime


class TaxRuleImportRequest(TaxFrameworkSchema):
    rules: list[TaxRuleWrite] = Field(min_length=1, max_length=1000)


class BulkUuidRequest(TaxFrameworkSchema):
    ids: list[UUID] = Field(min_length=1, max_length=5000)


class BulkTaxStatusRequest(BulkUuidRequest):
    status: TaxStatus


class TaxImportSystemsRequest(TaxFrameworkSchema):
    systems: list[TaxSystemWrite] = Field(min_length=1, max_length=1000)
