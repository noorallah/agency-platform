"""Approval rules by amount in up to three levels (PLT-1, decision A131).

* ``approval_rules``: per document type, a role's sign-off at a level from
  an amount up.
* ``approval_decisions``: each sign-off and rejection.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0293
Revises: 20261003_0292
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0293"
down_revision: str | Sequence[str] | None = "20261003_0292"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity carries, timestamps defaulted."""
    return [
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    ]


def upgrade() -> None:
    """Create both tables where a firm store lacks them."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no documents.
    if not inspector.has_table("sales_orders"):
        return
    if not inspector.has_table("approval_rules"):
        op.create_table(
            "approval_rules",
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("document_type", sa.String(30), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False),
            sa.Column("min_amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("role_code", sa.String(100), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_approval_rules"),
        )
        op.create_index("IX_approval_rules_firm_id", "approval_rules", ["firm_id"])
        op.create_index(
            "IX_approval_rules_firm_type",
            "approval_rules",
            ["firm_id", "document_type"],
        )
    if not inspector.has_table("approval_decisions"):
        op.create_table(
            "approval_decisions",
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("document_type", sa.String(30), nullable=False),
            sa.Column("document_id", UUIDType(), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False),
            sa.Column("decision", sa.String(20), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("decided_by", UUIDType(), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_approval_decisions"),
        )
        op.create_index(
            "IX_approval_decisions_firm_id", "approval_decisions", ["firm_id"]
        )
        op.create_index(
            "IX_approval_decisions_document",
            "approval_decisions",
            ["firm_id", "document_type", "document_id"],
        )
        op.create_index(
            "UQ_approval_decisions_level_active",
            "approval_decisions",
            ["document_type", "document_id", "level"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false AND decision = 'APPROVED'"),
        )


def downgrade() -> None:
    """Drop both tables."""
    inspector = sa.inspect(op.get_bind())
    for table in ("approval_decisions", "approval_rules"):
        if inspector.has_table(table):
            op.drop_table(table)
