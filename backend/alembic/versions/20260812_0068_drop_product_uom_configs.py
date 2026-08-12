"""Retire product_uom_configs, the second home for a product's units.

``product_uom_configs`` duplicated **fourteen** columns of ``products`` -- all
seven unit slots, ``allow_fraction`` / ``allow_decimal``, and weight, volume,
length, width and height -- and declared nothing of its own. The live copy is
the one on ``products``: every transactional module reads
``product.purchase_uom_id`` and ``product.inventory_uom_id`` when it builds a
line, and the desktop product form writes those columns.

Nothing ever wrote the table. It held zero rows in all four stores, no client
called ``GET``/``PUT /uom-framework/products/{id}/config``, and no service
outside ``app/uom`` referenced the model.

That it is empty is not why it goes. It goes because a second home for the
same seven answers is a trap that had already sprung once:
``_assert_uom_unused`` checked *this* table before soft-deleting a unit, so the
guard passed however many products used it, and deleting STRIP left every
medicine pointing at a unit the catalogue no longer offered. The guard now
reads ``products``. Leaving the table would also have let someone set a
product's units through the endpoint and watch every document ignore them.

Dropping is safe to replay: the table is created only by this project's own
metadata, so a store rebuilt by ``Base.metadata.create_all`` before this
revision may still have it, and one built after will not.

Firm-owned: run ``scripts/migrate_all_stores.py``, not a bare
``alembic upgrade head``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0068"
down_revision: str | Sequence[str] | None = "20260812_0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "product_uom_configs"


def upgrade() -> None:
    """Drop the duplicate, once it is confirmed empty."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    rows = bind.execute(
        sa.text(f"SELECT count(*) FROM {_TABLE}")
    ).scalar()  # noqa: S608
    if rows:
        # Never discard rows silently. Nothing writes this table, so a row here
        # means an assumption in this migration is wrong and someone should
        # look before it is dropped.
        raise RuntimeError(
            f"{_TABLE} holds {rows} row(s); nothing should ever have written "
            "it. Inspect them before rerunning this migration."
        )
    op.drop_table(_TABLE)


def downgrade() -> None:
    """Recreate the table, empty, as it always was."""
    bind = op.get_bind()
    if sa.inspect(bind).has_table(_TABLE):
        return
    from app.core.database.types import UUIDType

    op.create_table(
        _TABLE,
        sa.Column("id", UUIDType(), primary_key=True),
        sa.Column("firm_id", UUIDType(), nullable=False, index=True),
        sa.Column("product_id", UUIDType(), nullable=False, index=True),
        sa.Column("base_uom_id", UUIDType()),
        sa.Column("inventory_uom_id", UUIDType()),
        sa.Column("purchase_uom_id", UUIDType()),
        sa.Column("sales_uom_id", UUIDType()),
        sa.Column("minimum_sales_uom_id", UUIDType()),
        sa.Column("default_receiving_uom_id", UUIDType()),
        sa.Column("default_dispatch_uom_id", UUIDType()),
        sa.Column("allow_fraction", sa.Boolean(), nullable=False, default=False),
        sa.Column("allow_decimal", sa.Boolean(), nullable=False, default=True),
        sa.Column("weight", sa.Numeric(18, 6)),
        sa.Column("volume", sa.Numeric(18, 6)),
        sa.Column("length", sa.Numeric(18, 6)),
        sa.Column("width", sa.Numeric(18, 6)),
        sa.Column("height", sa.Numeric(18, 6)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUIDType()),
        sa.Column("updated_by", UUIDType()),
        sa.Column("deleted_by", UUIDType()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
        sa.Column("version", sa.Integer(), nullable=False, default=1),
        sa.UniqueConstraint(
            "firm_id", "product_id", name="UQ_product_uom_configs_firm_product"
        ),
    )
