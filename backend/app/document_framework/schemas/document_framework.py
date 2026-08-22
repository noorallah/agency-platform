"""Validated contracts for the reusable document lifecycle framework."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DOCUMENT_STATUS_VALUES = frozenset(
    {
        "DRAFT",
        "PENDING APPROVAL",
        "APPROVED",
        "REJECTED",
        "PARTIALLY PROCESSED",
        "PROCESSED",
        "COMPLETED",
        "CANCELLED",
        "CLOSED",
        "ARCHIVED",
    }
)


class DocumentFrameworkSchema(BaseModel):
    """Shared base behavior for framework contracts."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DocumentTypeCreate(DocumentFrameworkSchema):
    """Create or replace one document type definition."""

    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    configuration: dict[str, object] | None = None

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class DocumentTypeUpdate(DocumentTypeCreate):
    """Replace one document type definition."""


class DocumentTypeResponse(DocumentFrameworkSchema):
    """Expose one document type row."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    category: str | None
    is_active: bool
    configuration: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


class DocumentStateCreate(DocumentFrameworkSchema):
    """Create or replace one lifecycle state."""

    document_type_id: UUID
    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)
    is_default: bool = False
    is_terminal: bool = False
    allows_edit: bool = True
    allows_print: bool = True
    allows_email: bool = True
    allows_export_pdf: bool = True
    transition_rules: dict[str, object] | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class DocumentStateUpdate(DocumentStateCreate):
    """Replace one lifecycle state."""


class DocumentStateResponse(DocumentFrameworkSchema):
    """Expose one lifecycle state row."""

    id: UUID
    firm_id: UUID
    document_type_id: UUID
    code: str
    name: str
    description: str | None
    sort_order: int
    is_default: bool
    is_terminal: bool
    allows_edit: bool
    allows_print: bool
    allows_email: bool
    allows_export_pdf: bool
    transition_rules: dict[str, object] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DocumentNumberingRuleCreate(DocumentFrameworkSchema):
    """Create or replace one numbering rule."""

    document_type_id: UUID
    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    prefix: str | None = Field(default=None, max_length=40)
    suffix: str | None = Field(default=None, max_length=40)
    separator: str = Field(default="-", min_length=1, max_length=10)
    include_financial_year: bool = False
    include_branch_code: bool = False
    include_company_code: bool = False
    auto_reset: bool = True
    manual_allowed: bool = False
    sequence_padding: int = Field(default=6, ge=1, le=12)
    next_sequence: int = Field(default=1, ge=1)
    last_scope_signature: str | None = Field(default=None, max_length=200)
    format_pattern: str | None = Field(default=None, max_length=200)
    is_default: bool = False
    is_active: bool = True
    configuration: dict[str, object] | None = None

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class DocumentNumberingRuleUpdate(DocumentNumberingRuleCreate):
    """Replace one numbering rule."""


class DocumentNumberingRuleResponse(DocumentFrameworkSchema):
    """Expose one numbering rule row."""

    id: UUID
    firm_id: UUID
    document_type_id: UUID
    code: str
    name: str
    prefix: str | None
    suffix: str | None
    separator: str
    include_financial_year: bool
    include_branch_code: bool
    include_company_code: bool
    auto_reset: bool
    manual_allowed: bool
    sequence_padding: int
    next_sequence: int
    last_scope_signature: str | None
    format_pattern: str | None
    is_default: bool
    is_active: bool
    configuration: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


class DocumentLifecycleEventCreate(DocumentFrameworkSchema):
    """Create one lifecycle event entry."""

    document_type_id: UUID
    source_document_id: UUID
    source_module_code: str | None = Field(default=None, max_length=80)
    document_number: str | None = Field(default=None, max_length=80)
    action: str = Field(min_length=1, max_length=50)
    from_state: str | None = Field(default=None, max_length=80)
    to_state: str | None = Field(default=None, max_length=80)
    remarks: str | None = None
    details_json: dict[str, object] | None = None
    snapshot_json: dict[str, object] | None = None
    actor_id: UUID | None = None
    approved_by: UUID | None = None
    printed_by: UUID | None = None
    exported_by: UUID | None = None
    email_recipient: str | None = Field(default=None, max_length=255)

    @field_validator("action", "from_state", "to_state", mode="before")
    @classmethod
    def _normalize_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


class DocumentLifecycleEventResponse(DocumentFrameworkSchema):
    """Expose one timeline row."""

    id: UUID
    firm_id: UUID
    document_type_id: UUID
    source_document_id: UUID
    source_module_code: str | None
    document_number: str | None
    action: str
    from_state: str | None
    to_state: str | None
    remarks: str | None
    details_json: dict[str, object] | None
    snapshot_json: dict[str, object] | None
    actor_id: UUID | None
    approved_by: UUID | None
    printed_by: UUID | None
    exported_by: UUID | None
    email_recipient: str | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class DocumentHeaderContract(DocumentFrameworkSchema):
    """Reusable transaction header contract."""

    document_type_code: str = Field(min_length=1, max_length=80)
    document_number: str = Field(min_length=1, max_length=80)
    document_date: date
    reference: str | None = Field(default=None, max_length=120)
    branch: str | None = Field(default=None, max_length=200)
    warehouse: str | None = Field(default=None, max_length=200)
    firm: str | None = Field(default=None, max_length=200)
    business_profile: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(default=None, gt=0)
    status: str = Field(default="DRAFT", max_length=80)
    remarks: str | None = None
    created_by: str | None = None
    approved_by: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _DOCUMENT_STATUS_VALUES:
            raise ValueError("Unsupported document status.")
        return normalized


class DocumentLineContract(DocumentFrameworkSchema):
    """Reusable transaction line contract."""

    line_number: int = Field(ge=1)
    product: str | None = None
    description: str | None = None
    uom: str | None = None
    packaging: str | None = None
    quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    free_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    unit_price: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    discount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile: str | None = None
    amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    net_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    remarks: str | None = None


class DocumentTotalsContract(DocumentFrameworkSchema):
    """Reusable document totals contract."""

    subtotal: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    discount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    grand_total: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)


class DocumentAttachmentContract(DocumentFrameworkSchema):
    """Reusable attachment placeholder."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    category: str | None = Field(default=None, max_length=80)


class DocumentNoteContract(DocumentFrameworkSchema):
    """Reusable note placeholder."""

    note_type: str = Field(default="INTERNAL", max_length=30)
    note: str = Field(min_length=1)


class DocumentApprovalContract(DocumentFrameworkSchema):
    """Placeholder approval payload for future workflow orchestration."""

    requested: bool = False
    status: str = Field(default="PENDING", max_length=30)
    requested_by: UUID | None = None
    approved_by: UUID | None = None
    rejected_by: UUID | None = None
    remarks: str | None = None


class DocumentPrintContract(DocumentFrameworkSchema):
    """Placeholder print payload."""

    template_code: str | None = Field(default=None, max_length=80)
    printer_name: str | None = Field(default=None, max_length=120)
    copies: int = Field(default=1, ge=1, le=20)


class DocumentEmailContract(DocumentFrameworkSchema):
    """Placeholder email-ready payload."""

    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    subject: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=5000)
    attachments: list[str] = Field(default_factory=list)


class DocumentPdfContract(DocumentFrameworkSchema):
    """Reusable PDF generation placeholder."""

    template_code: str | None = Field(default=None, max_length=80)
    output_name: str | None = Field(default=None, max_length=120)
    include_signature: bool = False


class DocumentTimelineEntry(DocumentFrameworkSchema):
    """One normalized timeline entry for desktop rendering."""

    occurred_at: datetime
    action: str
    from_state: str | None = None
    to_state: str | None = None
    actor: str | None = None
    remarks: str | None = None
    details: dict[str, object] | None = None


class DocumentPrintTemplateWrite(DocumentFrameworkSchema):
    """Everything a firm may change about a printed document.

    Deliberately nothing statutory: the words *Tax Invoice* can be reworded --
    a Bill of Supply is a real document too -- but the parties' GSTINs, the HSN
    per line, the rate and amount per tax component, the tax summary and the
    total in words are what make a tax invoice one, and none of them is here.
    """

    title_text: str = Field(default="TAX INVOICE", min_length=2, max_length=60)
    accent_color: str = Field(default="#0B3D6B", pattern=r"^#[0-9A-Fa-f]{6}$")
    header_note: str | None = None
    show_bank_details: bool = True
    bank_details: str | None = Field(default=None, max_length=1000)
    terms: str | None = Field(default=None, max_length=2000)
    declaration: str | None = Field(default=None, max_length=1000)
    jurisdiction: str | None = Field(default=None, max_length=200)
    footer_note: str | None = Field(default=None, max_length=500)
    signatory_text: str | None = Field(default=None, max_length=200)
    show_discount_column: bool = True
    show_batch_column: bool = False
    show_expiry_column: bool = False
    #: In print order. Empty prints the original alone.
    copy_labels: list[str] = Field(default_factory=list, max_length=4)
    page_size: Literal["A4", "A5"] = "A4"
    margin_mm: Decimal = Field(default=Decimal("12"), ge=5, le=40)


class DocumentPrintTemplateResponse(DocumentPrintTemplateWrite):
    """One firm's template, or the platform default it has not overridden."""

    id: UUID | None = None
    document_type: str
    #: False where no row exists yet and these are the platform defaults.
    is_customised: bool = False
