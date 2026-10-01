"""How a firm decides what to reorder (backlog 69 row 12, decision A39).

* ``reorder_planning_settings``: one row per firm -- ``basis`` LEVELS (typed
  levels, as before) or SALES (levels derived from net sales over
  ``sales_window_days``), with ``lead_time_days``, ``safety_days`` and
  ``cover_days``. A firm with no row plans on LEVELS.

No permission codes: reading takes ``PURCHASE_VIEW`` or ``REPORT_VIEW``,
writing ``PURCHASE_MANAGE_SETTINGS``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261002_0215
Revises: 20261002_0214
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0215"
down_revision: str | Sequence[str] | None = "20261002_0214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def _days(name: str, default: int) -> sa.Column:  # type: ignore[type-arg]
    """Return a whole number of days with its default."""
    return sa.Column(name, sa.Integer(), nullable=False, server_default=str(default))


def upgrade() -> None:
    """Create the table where this store holds purchase orders."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("purchase_orders"):
        return
    if inspector.has_table("reorder_planning_settings"):
        return
    op.create_table(
        "reorder_planning_settings",
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "basis", sa.String(length=10), nullable=False, server_default="LEVELS"
        ),
        _days("sales_window_days", 90),
        _days("lead_time_days", 7),
        _days("safety_days", 7),
        _days("cover_days", 30),
        sa.UniqueConstraint("firm_id", name="UQ_reorder_planning_settings_firm"),
    )
    op.create_index(
        "IX_reorder_planning_settings_firm_id",
        "reorder_planning_settings",
        ["firm_id"],
    )


def downgrade() -> None:
    """Drop the table where it exists."""
    if sa.inspect(op.get_bind()).has_table("reorder_planning_settings"):
        op.drop_table("reorder_planning_settings")
