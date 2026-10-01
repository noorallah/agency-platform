"""Why a delivery note's goods go out, and the firm's GST document policy (77).

* ``delivery_notes.challan_reason`` (``SALE`` for every note already written,
  which is what each of them was) and ``challan_reason_note``.
* ``gst_compliance_settings``: one row per firm -- the dates e-invoicing and
  the 30-day limit apply from, and whether a sale dispatched before its
  invoice is let through, warned about or refused. A firm with no row warns.

No permission codes: the policy is read on ``TAX_VIEW`` and written on
``TAX_MANAGE_SETTINGS``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261002_0210
Revises: 20261002_0209
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0210"
down_revision: str | Sequence[str] | None = "20261002_0209"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "gst_compliance_settings"


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the names of a table's columns."""
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the columns and the table where this store holds delivery notes."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("delivery_notes"):
        return
    present = _columns(inspector, "delivery_notes")
    if "challan_reason" not in present:
        op.add_column(
            "delivery_notes",
            sa.Column(
                "challan_reason",
                sa.String(length=20),
                nullable=False,
                server_default="SALE",
            ),
        )
    if "challan_reason_note" not in present:
        op.add_column(
            "delivery_notes",
            sa.Column("challan_reason_note", sa.String(length=200), nullable=True),
        )
    if inspector.has_table(_TABLE):
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
        sa.Column("einvoice_applicable_from", sa.Date(), nullable=True),
        sa.Column("thirty_day_rule_from", sa.Date(), nullable=True),
        sa.Column(
            "dispatch_without_invoice",
            sa.String(10),
            server_default="WARN",
            nullable=False,
        ),
        sa.Column(
            "route_sale_needs_invoice",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=f"PK_{_TABLE}"),
    )
    op.create_index(f"IX_{_TABLE}_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        f"UQ_{_TABLE}_firm_active",
        _TABLE,
        ["firm_id"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    """Drop the table and the columns where they exist."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if not inspector.has_table("delivery_notes"):
        return
    present = _columns(inspector, "delivery_notes")
    for name in ("challan_reason_note", "challan_reason"):
        if name in present:
            op.drop_column("delivery_notes", name)
