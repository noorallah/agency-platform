"""A GST return the firm says it filed on the portal (backlog 63 item 4).

``gst_return_filings``: one row per firm, return (GSTR1 / GSTR3B) and month,
with the date filed and the portal's ARN, so the tax calendar on Home can tell
a filed return from a late one. One live row per return and month, held by a
partial unique index.

No permission codes: saying a return was filed takes ``JOURNAL_POST``, as
recording the month's GST payment does.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261002_0208
Revises: 20261002_0207
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0208"
down_revision: str | Sequence[str] | None = "20261002_0207"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "gst_return_filings"


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity carries, timestamps defaulted."""
    return [
        sa.Column("id", UUIDType(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def upgrade() -> None:
    """Create the table where a firm store lacks it."""
    inspector = sa.inspect(op.get_bind())
    # The calendar sits beside the GST payment; a store without that table is
    # not a firm store.
    if not inspector.has_table("gst_payments") or inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("return_type", sa.String(length=10), nullable=False),
        sa.Column("return_period", sa.String(length=7), nullable=False),
        sa.Column("filed_on", sa.Date(), nullable=False),
        sa.Column("arn", sa.String(length=30), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
    )
    op.create_index("IX_gst_return_filings_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "UQ_gst_return_filings_firm_type_period_active",
        _TABLE,
        ["firm_id", "return_type", "return_period"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        sqlite_where=sa.text("is_deleted = 0"),
    )


def downgrade() -> None:
    """Drop the table where it exists."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
