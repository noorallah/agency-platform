"""Rule 42 common credit reversal (GST-4, decision A84).

* ``gst_compliance_settings.rule42_mode`` (REPORT).
* ``itc_common_reversals``: a period's rule 42 reversal, or a year's true-up,
  with the turnover and common credit it was worked from.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0256
Revises: 20261003_0255
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0256"
down_revision: str | Sequence[str] | None = "20261003_0255"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "itc_common_reversals"
_HEADS = ("igst", "cgst", "sgst", "cess")


def _money(name: str) -> sa.Column[object]:
    """Return a NOT NULL money column defaulting to zero."""
    return sa.Column(
        name, sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False
    )


def upgrade() -> None:
    """Add the setting and the reversal table where missing."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("gst_compliance_settings"):
        have = {c["name"] for c in inspector.get_columns("gst_compliance_settings")}
        if "rule42_mode" not in have:
            op.add_column(
                "gst_compliance_settings",
                sa.Column(
                    "rule42_mode",
                    sa.String(10),
                    server_default=sa.text("'REPORT'"),
                    nullable=False,
                ),
            )
    if inspector.has_table(_TABLE) or not inspector.has_table("journal_entries"):
        return
    op.create_table(
        _TABLE,
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
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("movement_date", sa.Date(), nullable=False),
        _money("exempt_turnover"),
        _money("total_turnover"),
        *(_money(f"common_{head}") for head in _HEADS),
        *(_money(f"reversed_{head}") for head in _HEADS),
        sa.Column(
            "status", sa.String(20), server_default=sa.text("'POSTED'"), nullable=False
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=False),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by", UUIDType(), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_itc_common_reversals"),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name="FK_itc_common_reversals_journal_entry_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_journal_entry_id"],
            ["journal_entries.id"],
            name="FK_itc_common_reversals_reversal_journal_entry_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_itc_common_reversals_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "UQ_itc_common_reversals_firm_kind_period_posted",
        _TABLE,
        ["firm_id", "kind", "period_from"],
        unique=True,
        postgresql_where=sa.text("status = 'POSTED' AND is_deleted = false"),
    )


def downgrade() -> None:
    """Drop the table and the setting."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if inspector.has_table("gst_compliance_settings"):
        have = {c["name"] for c in inspector.get_columns("gst_compliance_settings")}
        if "rule42_mode" in have:
            op.drop_column("gst_compliance_settings", "rule42_mode")
