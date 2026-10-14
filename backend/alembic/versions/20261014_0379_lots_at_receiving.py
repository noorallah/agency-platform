"""Every batch carries a lot reference; opening stock lines as lots (L2 step 3).

`docs/design/LOT_COST_DESIGN.md`, sections 3.2 and 3.3.

* ``batches.lot_reference`` becomes NOT NULL. Every creator of a batch now
  issues one from the firm's lot series; a batch made between step 1 and this
  step has none, so those are first given the firm's next ``B`` number, as
  step 1 numbered the batches it found.
* ``opening_stock_lines`` gains what a lot carries besides its cost: ``mrp``,
  ``selling_price``, ``ptr``, ``pts``, ``purchase_date`` and
  ``supplier_bill_reference``.
* ``UQ_opening_stock_lines_batch_product_location`` is dropped. A firm costing
  by lot enters two old lots of one batch at two costs on one document; a
  firm on Average is still refused the same item twice, by the service.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a firm store
is partly built by ``Base.metadata.create_all``, so each column is added only
where it is missing, the key dropped only where it is there, and a reference
written only on rows that have none.

Revision ID: 20261014_0379
Revises: 20261014_0378
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261014_0379"
down_revision: str | Sequence[str] | None = "20261014_0378"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCHES = "batches"
_LINES = "opening_stock_lines"
_LINE_KEY = "UQ_opening_stock_lines_batch_product_location"

_batches = sa.table(
    _BATCHES,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("lot_reference", sa.String()),
)


def _line_columns() -> list[sa.Column[object]]:
    """Return the columns an opening stock line gains to be a lot."""
    return [
        sa.Column("mrp", sa.Numeric(18, 2), nullable=True),
        sa.Column("selling_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("ptr", sa.Numeric(18, 2), nullable=True),
        sa.Column("pts", sa.Numeric(18, 2), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("supplier_bill_reference", sa.String(80), nullable=True),
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


def _reference_is_nullable() -> bool:
    """Say whether ``batches.lot_reference`` still accepts no value."""
    for column in sa.inspect(op.get_bind()).get_columns(_BATCHES):
        if column["name"] == "lot_reference":
            return bool(column["nullable"])
    return False


def upgrade() -> None:
    """Hold every batch to a reference; give opening stock lines the lot's columns."""
    inspector = sa.inspect(op.get_bind())
    # A firm store holds batches; the platform store has nothing to cost.
    if inspector.has_table(_BATCHES):
        columns = {column["name"] for column in inspector.get_columns(_BATCHES)}
        if "lot_reference" in columns:
            _number_the_batches()
            if _reference_is_nullable():
                op.alter_column(
                    _BATCHES,
                    "lot_reference",
                    existing_type=sa.String(40),
                    nullable=False,
                )
    if not inspector.has_table(_LINES):
        return
    present = {column["name"] for column in inspector.get_columns(_LINES)}
    for column in _line_columns():
        if column.name not in present:
            op.add_column(_LINES, column)
    uniques = {key["name"] for key in inspector.get_unique_constraints(_LINES)}
    if _LINE_KEY in uniques:
        op.drop_constraint(_LINE_KEY, _LINES, type_="unique")


def downgrade() -> None:
    """Let a batch go without a reference again; drop the lines' new columns.

    The key on product, place and batch is not put back: lines entered since
    may repeat it, and the service still refuses that for a firm on Average.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_BATCHES) and not _reference_is_nullable():
        columns = {column["name"] for column in inspector.get_columns(_BATCHES)}
        if "lot_reference" in columns:
            op.alter_column(
                _BATCHES,
                "lot_reference",
                existing_type=sa.String(40),
                nullable=True,
            )
    if not inspector.has_table(_LINES):
        return
    present = {column["name"] for column in inspector.get_columns(_LINES)}
    for column in _line_columns():
        if column.name in present:
            op.drop_column(_LINES, column.name)
