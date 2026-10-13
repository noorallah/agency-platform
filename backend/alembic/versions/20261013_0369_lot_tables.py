"""The tables cost per purchase lot is built on (backlog 101, 103; L2 step 1).

`docs/design/LOT_COST_DESIGN.md`, section 3.2. Nothing reads any of it yet:
every firm stays on one moving average per product.

* ``batches`` gains the lot's own columns: ``lot_reference``,
  ``per_purchase_line``, ``has_printed_batch``, ``received_on`` and the four
  ``source_document_*`` columns. Every batch that exists is given a
  reference, ``B000001`` onwards per firm in the order the batches were made.
* ``UQ_batches_firm_batch_product`` becomes a partial unique index over the
  same three columns, covering only rows that are not a lot of one purchase
  line. Every batch that exists is such a row, so the same number is still
  the same batch.
* ``batch_valuations``: what each lot is worth, one row per lot.
* ``stock_lot_settings``: one row per firm, its costing method and whether
  it may bill without stock. A firm with no row is on Average.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a firm store
is partly built by ``Base.metadata.create_all``, so each column, index and
table is added only where the store holds ``batches`` and lacks it, and the
reference is written only on rows that have none.

Revision ID: 20261013_0369
Revises: 20261013_0368
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261013_0369"
down_revision: str | Sequence[str] | None = "20261013_0368"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCHES = "batches"
_BATCH_KEY = "UQ_batches_firm_batch_product"
_LOT_KEY = "UQ_batches_firm_lot_reference_active"
_VALUATIONS = "batch_valuations"
_SETTINGS = "stock_lot_settings"

_batches = sa.table(
    _BATCHES,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("lot_reference", sa.String()),
)


def _lot_columns() -> list[sa.Column[object]]:
    """Return the columns a batch gains to be a lot."""
    return [
        sa.Column("lot_reference", sa.String(40), nullable=True),
        sa.Column(
            "per_purchase_line",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "has_printed_batch",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("received_on", sa.Date(), nullable=True),
        sa.Column("source_document_type", sa.String(30), nullable=True),
        sa.Column("source_document_id", UUIDType(), nullable=True),
        sa.Column("source_document_line_id", UUIDType(), nullable=True),
        sa.Column("source_document_number", sa.String(80), nullable=True),
    ]


def _entity_columns() -> list[sa.Column[object]]:
    """Return the columns every entity table starts with."""
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


def _number_the_batches() -> None:
    """Give every batch with no lot reference the firm's next ``B`` number.

    Counted on from the highest ``B`` number the firm already holds, so a
    second run numbers only the batches made since and repeats nothing.
    """
    bind = op.get_bind()
    taken: dict[object, int] = {}
    for firm_id, reference in bind.execute(
        sa.select(_batches.c.firm_id, _batches.c.lot_reference).where(
            _batches.c.lot_reference.is_not(None)
        )
    ).all():
        digits = reference[1:]
        if reference.startswith("B") and digits.isdigit():
            taken[firm_id] = max(taken.get(firm_id, 0), int(digits))
    rows = bind.execute(
        sa.select(_batches.c.id, _batches.c.firm_id)
        .where(_batches.c.lot_reference.is_(None))
        .order_by(_batches.c.firm_id, _batches.c.created_at, _batches.c.id)
    ).all()
    for batch_id, firm_id in rows:
        taken[firm_id] = taken.get(firm_id, 0) + 1
        bind.execute(
            _batches.update()
            .where(_batches.c.id == batch_id, _batches.c.lot_reference.is_(None))
            .values(lot_reference=f"B{taken[firm_id]:06d}")
        )


def _shape_batches() -> None:
    """Add the lot's columns, number the batches and make the key partial."""
    bind = op.get_bind()
    present = {column["name"] for column in sa.inspect(bind).get_columns(_BATCHES)}
    for column in _lot_columns():
        if column.name not in present:
            op.add_column(_BATCHES, column)
    _number_the_batches()

    uniques = {key["name"] for key in sa.inspect(bind).get_unique_constraints(_BATCHES)}
    if _BATCH_KEY in uniques:
        op.drop_constraint(_BATCH_KEY, _BATCHES, type_="unique")
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_BATCHES)}
    if _BATCH_KEY not in indexes:
        op.create_index(
            _BATCH_KEY,
            _BATCHES,
            ["firm_id", "batch_number", "product_id"],
            unique=True,
            postgresql_where=sa.text("NOT per_purchase_line"),
            sqlite_where=sa.text("NOT per_purchase_line"),
        )
    if _LOT_KEY not in indexes:
        op.create_index(
            _LOT_KEY,
            _BATCHES,
            ["firm_id", "lot_reference"],
            unique=True,
            postgresql_where=sa.text("NOT is_deleted"),
            sqlite_where=sa.text("NOT is_deleted"),
        )


def _create_valuations() -> None:
    """Create the table holding what each lot is worth."""
    op.create_table(
        _VALUATIONS,
        *_entity_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("batch_id", UUIDType(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column(
            "quantity_on_hand", sa.Numeric(18, 4), server_default="0", nullable=False
        ),
        sa.Column("unit_cost", sa.Numeric(18, 6), server_default="0", nullable=False),
        sa.Column("total_value", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_batch_valuations"),
        sa.UniqueConstraint("batch_id", name="UQ_batch_valuations_batch"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
            name="FK_batch_valuations_batch_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="FK_batch_valuations_product_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_batch_valuations_firm_id", _VALUATIONS, ["firm_id"])
    op.create_index(
        "IX_batch_valuations_firm_product", _VALUATIONS, ["firm_id", "product_id"]
    )


def _create_settings() -> None:
    """Create the per-firm costing method table."""
    op.create_table(
        _SETTINGS,
        *_entity_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "costing_method", sa.String(20), server_default="AVERAGE", nullable=False
        ),
        sa.Column("switched_on", sa.Date(), nullable=True),
        sa.Column(
            "allow_billing_without_stock",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_stock_lot_settings"),
    )
    op.create_index("IX_stock_lot_settings_firm_id", _SETTINGS, ["firm_id"])
    op.create_index(
        "UQ_stock_lot_settings_firm_active",
        _SETTINGS,
        ["firm_id"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def upgrade() -> None:
    """Shape a firm store for lots; a store with no batches is left alone."""
    inspector = sa.inspect(op.get_bind())
    # A firm store holds batches; the platform store has nothing to cost.
    if not inspector.has_table(_BATCHES):
        return
    _shape_batches()
    if not inspector.has_table(_VALUATIONS) and inspector.has_table("products"):
        _create_valuations()
    if not inspector.has_table(_SETTINGS):
        _create_settings()


def downgrade() -> None:
    """Drop the two tables and the lot's columns; the key covers every row."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in (_VALUATIONS, _SETTINGS):
        if inspector.has_table(table):
            op.drop_table(table)
    if not inspector.has_table(_BATCHES):
        return
    indexes = {index["name"] for index in inspector.get_indexes(_BATCHES)}
    uniques = {key["name"] for key in inspector.get_unique_constraints(_BATCHES)}
    if _LOT_KEY in indexes:
        op.drop_index(_LOT_KEY, table_name=_BATCHES)
    if _BATCH_KEY in indexes and _BATCH_KEY not in uniques:
        op.drop_index(_BATCH_KEY, table_name=_BATCHES)
        op.create_unique_constraint(
            _BATCH_KEY, _BATCHES, ["firm_id", "batch_number", "product_id"]
        )
    present = {column["name"] for column in inspector.get_columns(_BATCHES)}
    for column in _lot_columns():
        if column.name in present:
            op.drop_column(_BATCHES, column.name)
