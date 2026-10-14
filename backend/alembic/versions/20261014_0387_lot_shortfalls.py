"""Units billed before any lot held them, and what cleared them (L2 step 7a).

* ``lot_shortfalls``: one row per dispatch movement a by-lot firm made for
  goods no lot held, once the bill maker confirmed it -- the item, the
  place, the delivery line, the units, the cost they left at and who
  confirmed (``docs/design/LOT_COST_DESIGN.md``, section 3.7).
* ``lot_shortfall_settlements``: what cleared part of one -- the lot a later
  receipt brought (``SETTLED``) or the customer's return (``RETURNED``).
  Keyed to ``lot_shortfalls`` (CASCADE) and ``batches`` (RESTRICT).

``stock_lot_settings.allow_billing_without_stock`` already exists
(``20261013_0369``). Both tables are firm-owned and key only to firm-owned
tables, so no key crosses a schema.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a firm store
is partly built by ``Base.metadata.create_all``, so each table is created
only where it is missing.

Revision ID: 20261014_0387
Revises: 20261014_0386
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261014_0387"
down_revision: str | Sequence[str] | None = "20261014_0386"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHORTFALLS = "lot_shortfalls"
_SETTLEMENTS = "lot_shortfall_settlements"


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP`: a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails (`20260903_0114`).
    """
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
    """Create both tables where the store holds products and batches."""
    inspector = sa.inspect(op.get_bind())
    # The platform store holds neither, and the keys below would point at
    # tables it does not have.
    if not inspector.has_table("products") or not inspector.has_table("batches"):
        return
    if not inspector.has_table(_SHORTFALLS):
        op.create_table(
            _SHORTFALLS,
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column(
                "product_id",
                UUIDType(),
                sa.ForeignKey(
                    "products.id",
                    ondelete="RESTRICT",
                    name="FK_lot_shortfalls_product_id",
                ),
                nullable=False,
            ),
            sa.Column("branch_id", UUIDType(), nullable=False),
            sa.Column("warehouse_id", UUIDType(), nullable=False),
            sa.Column("storage_node_id", UUIDType(), nullable=True),
            sa.Column("delivery_note_id", UUIDType(), nullable=False),
            sa.Column("delivery_note_line_id", UUIDType(), nullable=False),
            sa.Column("document_number", sa.String(80), nullable=False),
            sa.Column("inventory_transaction_id", UUIDType(), nullable=False),
            sa.Column("sale_date", sa.Date(), nullable=False),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
            sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False),
            sa.Column("cost_amount", sa.Numeric(18, 4), nullable=False),
            sa.Column("confirmed_by", UUIDType(), nullable=False),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("IX_lot_shortfalls_firm_id", _SHORTFALLS, ["firm_id"])
        op.create_index(
            "IX_lot_shortfalls_firm_product",
            _SHORTFALLS,
            ["firm_id", "product_id", "sale_date"],
        )
        op.create_index(
            "IX_lot_shortfalls_note_line", _SHORTFALLS, ["delivery_note_line_id"]
        )
    if not inspector.has_table(_SETTLEMENTS):
        op.create_table(
            _SETTLEMENTS,
            *_base_columns(),
            sa.Column(
                "lot_shortfall_id",
                UUIDType(),
                sa.ForeignKey(
                    "lot_shortfalls.id",
                    ondelete="CASCADE",
                    name="FK_lot_shortfall_settlements_lot_shortfall_id",
                ),
                nullable=False,
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
            sa.Column(
                "batch_id",
                UUIDType(),
                sa.ForeignKey(
                    "batches.id",
                    ondelete="RESTRICT",
                    name="FK_lot_shortfall_settlements_batch_id",
                ),
                nullable=True,
            ),
            sa.Column("cost_used_amount", sa.Numeric(18, 4), nullable=False),
            sa.Column("lot_cost_amount", sa.Numeric(18, 4), nullable=True),
            sa.Column("settled_on", sa.Date(), nullable=False),
            sa.Column("document_type", sa.String(30), nullable=False),
            sa.Column("document_id", UUIDType(), nullable=False),
            sa.Column("document_line_id", UUIDType(), nullable=False),
            sa.Column("document_number", sa.String(80), nullable=False),
            sa.Column("out_transaction_id", UUIDType(), nullable=True),
            sa.Column("in_transaction_id", UUIDType(), nullable=False),
        )
        op.create_index(
            "IX_lot_shortfall_settlements_shortfall",
            _SETTLEMENTS,
            ["lot_shortfall_id"],
        )
        op.create_index(
            "IX_lot_shortfall_settlements_line", _SETTLEMENTS, ["document_line_id"]
        )


def downgrade() -> None:
    """Drop both tables: billing without stock is refused again."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_SETTLEMENTS):
        op.drop_table(_SETTLEMENTS)
    if inspector.has_table(_SHORTFALLS):
        op.drop_table(_SHORTFALLS)
