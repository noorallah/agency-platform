"""Approval rules and the decisions taken under them (PLT-1)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class ApprovalRule(BaseEntity):
    """One role's sign-off at one level, for documents from an amount up.

    A document whose total reaches ``min_amount`` needs a sign-off at
    ``level`` (1 to 3) by a person holding ``role_code``; several roles at one
    level are alternatives. Levels are signed in order (decision A131).
    """

    __tablename__ = "approval_rules"
    __table_args__ = (Index("IX_approval_rules_firm_type", "firm_id", "document_type"),)

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: ``SALES_ORDER``, ``SALES_INVOICE``, ``PURCHASE_ORDER`` or
    #: ``PURCHASE_INVOICE``.
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    min_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    role_code: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class ApprovalDecision(BaseEntity):
    """A sign-off or a rejection of one document at one level.

    A rejection clears the sign-offs before it (soft-deleted), so the chain
    starts again once the document is corrected. A sign-off counts only while
    the document's total is no more than the amount it was signed at.
    """

    __tablename__ = "approval_decisions"
    __table_args__ = (
        Index(
            "IX_approval_decisions_document",
            "firm_id",
            "document_type",
            "document_id",
        ),
        Index(
            "UQ_approval_decisions_level_active",
            "document_type",
            "document_id",
            "level",
            unique=True,
            postgresql_where=text("is_deleted = false AND decision = 'APPROVED'"),
            sqlite_where=text("is_deleted = 0 AND decision = 'APPROVED'"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    #: No foreign key: four document tables, named by ``document_type``.
    document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    #: ``APPROVED`` or ``REJECTED``.
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The document's total when it was decided.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    decided_by: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)
