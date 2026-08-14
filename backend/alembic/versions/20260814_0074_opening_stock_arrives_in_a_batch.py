"""Let day-one stock arrive in a batch, like every other delivery.

Opening stock was the last way stock could enter with no batch behind it. A
pharmacy's opening shelf was one untraceable heap while every later delivery
was traced, and a product that requires a batch on issue could never ship what
it started with -- there was no batch for the allocator to draw from.

``opening_stock_lines`` gains what the other document lines already carry:

* ``batch_number`` -- what was written on the day-one paperwork.
* ``batch_id`` -- what it resolved to. Opening stock is stock arriving, so an
  unknown number registers the batch the way a goods receipt does rather than
  being refused.
* ``expiry_date`` -- the manufacturer's fact, recorded when the paperwork has
  it and gated by EXPIRY_TRACKING like everywhere else.

``UQ_opening_stock_lines_batch_product_location`` gains ``batch_number`` too.
Day-one stock of one product in one bay is routinely two deliveries expiring
months apart, and keying without the batch made that impossible to record on
one document -- it would have forced a second opening stock document for what
is one count of one shelf.

``opening_stock_lines`` is firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260814_0074"
down_revision: str | Sequence[str] | None = "20260813_0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "opening_stock_lines"
_UNIQUE = "UQ_opening_stock_lines_batch_product_location"


def upgrade() -> None:
    """Point the opening-stock line at the batch register."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return  # platform schema: firm-owned tables are not there.
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "batch_number" not in columns:
        op.add_column(_TABLE, sa.Column("batch_number", sa.String(120), nullable=True))
    if "expiry_date" not in columns:
        op.add_column(_TABLE, sa.Column("expiry_date", sa.Date(), nullable=True))
    # `IX_opening_stock_lines_batch_id` already exists and indexes
    # `opening_stock_batch_id` -- named for the table it refers to rather than
    # the column it is on, which is the collision this repository documents for
    # foreign keys and which bites the same way here. It is renamed to match
    # its column so the conventional name is free for the column that deserves
    # it. Dropped and recreated rather than renamed, because ALTER INDEX RENAME
    # is not portable and these tables are small.
    indexes = {
        index["name"]: list(index["column_names"])
        for index in inspector.get_indexes(_TABLE)
    }
    if indexes.get(f"IX_{_TABLE}_batch_id") == ["opening_stock_batch_id"]:
        op.drop_index(f"IX_{_TABLE}_batch_id", table_name=_TABLE)
        op.create_index(
            f"IX_{_TABLE}_opening_stock_batch_id", _TABLE, ["opening_stock_batch_id"]
        )
    if "batch_id" not in columns:
        op.add_column(_TABLE, sa.Column("batch_id", UUIDType(), nullable=True))
        op.create_foreign_key(
            f"FK_{_TABLE}_batch_id",
            _TABLE,
            "batches",
            ["batch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"IX_{_TABLE}_batch_id", _TABLE, ["batch_id"])
    existing = {
        constraint["name"] for constraint in inspector.get_unique_constraints(_TABLE)
    }
    if _UNIQUE in existing:
        op.drop_constraint(_UNIQUE, _TABLE, type_="unique")
    op.create_unique_constraint(
        _UNIQUE,
        _TABLE,
        ["opening_stock_batch_id", "product_id", "storage_locator", "batch_number"],
    )


def downgrade() -> None:
    """Return the line to carrying no batch, and the key to three columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing = {
        constraint["name"] for constraint in inspector.get_unique_constraints(_TABLE)
    }
    if _UNIQUE in existing:
        op.drop_constraint(_UNIQUE, _TABLE, type_="unique")
    op.create_unique_constraint(
        _UNIQUE,
        _TABLE,
        ["opening_stock_batch_id", "product_id", "storage_locator"],
    )
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if "batch_id" in columns:
        if f"IX_{_TABLE}_batch_id" in indexes:
            op.drop_index(f"IX_{_TABLE}_batch_id", table_name=_TABLE)
        op.drop_constraint(f"FK_{_TABLE}_batch_id", _TABLE, type_="foreignkey")
        op.drop_column(_TABLE, "batch_id")
    for column in ("expiry_date", "batch_number"):
        if column in columns:
            op.drop_column(_TABLE, column)
    # Give the old index its ambiguous name back, so the schema matches what
    # `20260801_0019` built.
    if f"IX_{_TABLE}_opening_stock_batch_id" in indexes:
        op.drop_index(f"IX_{_TABLE}_opening_stock_batch_id", table_name=_TABLE)
        op.create_index(f"IX_{_TABLE}_batch_id", _TABLE, ["opening_stock_batch_id"])
