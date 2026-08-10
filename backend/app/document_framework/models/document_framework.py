"""Persistence models for the reusable document lifecycle framework."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class DocumentTypeDefinition(BaseEntity):
    """Define one reusable document family."""

    __tablename__ = "document_type_definitions"
    __table_args__ = (UniqueConstraint("firm_id", "code"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    configuration: Mapped[dict[str, object] | None] = mapped_column(JSON)


class DocumentStateDefinition(BaseEntity):
    """Define configurable lifecycle states for one document family."""

    __tablename__ = "document_state_definitions"
    __table_args__ = (UniqueConstraint("firm_id", "document_type_id", "code"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    document_type_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("document_type_definitions.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_terminal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    allows_edit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    allows_print: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    allows_email: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    allows_export_pdf: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    transition_rules: Mapped[dict[str, object] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class DocumentNumberingRule(BaseEntity):
    """Define configurable numbering behavior for one document family."""

    __tablename__ = "document_numbering_rules"
    __table_args__ = (UniqueConstraint("firm_id", "document_type_id", "code"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    document_type_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("document_type_definitions.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prefix: Mapped[str | None] = mapped_column(String(40))
    suffix: Mapped[str | None] = mapped_column(String(40))
    separator: Mapped[str] = mapped_column(
        String(10), nullable=False, default="-", server_default="-"
    )
    include_financial_year: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    include_branch_code: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    include_company_code: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    auto_reset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    manual_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    sequence_padding: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6, server_default="6"
    )
    next_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    last_scope_signature: Mapped[str | None] = mapped_column(String(200))
    format_pattern: Mapped[str | None] = mapped_column(String(200))
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    configuration: Mapped[dict[str, object] | None] = mapped_column(JSON)


class DocumentLifecycleEvent(BaseEntity):
    """Record one append-only lifecycle event for a document instance."""

    __tablename__ = "document_lifecycle_events"

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    document_type_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("document_type_definitions.id"), nullable=False
    )
    source_document_id: Mapped[UUID] = mapped_column(
        UUIDType(), nullable=False, index=True
    )
    source_module_code: Mapped[str | None] = mapped_column(String(80))
    document_number: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(80))
    to_state: Mapped[str | None] = mapped_column(String(80))
    remarks: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    snapshot_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    actor_id: Mapped[UUID | None] = mapped_column(UUIDType())
    approved_by: Mapped[UUID | None] = mapped_column(UUIDType())
    printed_by: Mapped[UUID | None] = mapped_column(UUIDType())
    exported_by: Mapped[UUID | None] = mapped_column(UUIDType())
    email_recipient: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )


class DocumentHeader(BaseEntity):
    """Store a reusable enterprise document header."""

    __tablename__ = "document_headers"
    __table_args__ = (UniqueConstraint("firm_id", "document_number"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    document_type_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("document_type_definitions.id"), nullable=False
    )
    source_document_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    branch_id: Mapped[UUID | None] = mapped_column(UUIDType())
    warehouse_id: Mapped[UUID | None] = mapped_column(UUIDType())
    firm_name: Mapped[str | None] = mapped_column(String(200))
    business_profile_name: Mapped[str | None] = mapped_column(String(200))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(String(80), nullable=False, default="DRAFT")
    remarks: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[UUID | None] = mapped_column(UUIDType())


class DocumentLine(BaseEntity):
    """Store one reusable document line."""

    __tablename__ = "document_lines"
    __table_args__ = (UniqueConstraint("firm_id", "document_header_id", "line_number"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    document_header_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("document_headers.id"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(UUIDType())
    description: Mapped[str | None] = mapped_column(String(500))
    uom_id: Mapped[UUID | None] = mapped_column(UUIDType())
    packaging: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[str | None] = mapped_column(String(40))
    free_quantity: Mapped[str | None] = mapped_column(String(40))
    unit_price: Mapped[str | None] = mapped_column(String(40))
    discount: Mapped[str | None] = mapped_column(String(40))
    tax_profile: Mapped[str | None] = mapped_column(String(120))
    amount: Mapped[str | None] = mapped_column(String(40))
    net_amount: Mapped[str | None] = mapped_column(String(40))
    remarks: Mapped[str | None] = mapped_column(Text)


class DocumentTotal(BaseEntity):
    """Store reusable totals for one document."""

    __tablename__ = "document_totals"
    __table_args__ = (UniqueConstraint("firm_id", "document_header_id"),)

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    document_header_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("document_headers.id"), nullable=False
    )
    subtotal: Mapped[str | None] = mapped_column(String(40))
    discount: Mapped[str | None] = mapped_column(String(40))
    tax: Mapped[str | None] = mapped_column(String(40))
    charges: Mapped[str | None] = mapped_column(String(40))
    round_off: Mapped[str | None] = mapped_column(String(40))
    grand_total: Mapped[str | None] = mapped_column(String(40))
    remarks: Mapped[str | None] = mapped_column(Text)


class DocumentNumberSequence(BaseEntity):
    """Track the next number for one numbering rule in one scope.

    A numbering rule used to carry a single ``next_sequence`` plus the last
    scope it had seen, and reset the counter whenever the scope changed. That
    works only if documents are created in scope order and never revisited:
    enter one document dated in the previous financial year and the counter
    resets, and the next current-year document collides with a number already
    issued. Back-dating a missed invoice is ordinary accounting, so this keeps
    a counter per scope instead of one counter and a memory.

    The scope signature is whatever the rule includes in the number -- the
    financial year, branch and company code -- so two scopes number
    independently and neither disturbs the other.
    """

    __tablename__ = "document_number_sequences"
    __table_args__ = (
        UniqueConstraint(
            "numbering_rule_id",
            "scope_signature",
            name="UQ_document_number_sequences_rule_scope",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    numbering_rule_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("document_numbering_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_signature: Mapped[str] = mapped_column(String(200), nullable=False)
    next_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
