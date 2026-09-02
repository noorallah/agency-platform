"""Let a price list improve its rate as the quantity rises.

A list held one rate per product, so "five percent, or eight over fifty" could
not be expressed at all -- and slab pricing is how a distributor actually
sells. `min_quantity` is the quantity a rate starts at, and the highest break
at or below the line's quantity wins.

Zero is the ordinary rate, which is what every existing row becomes, so no
list changes what it promises and no document changes price.

The unique key gains the quantity. Without it a list could hold only one row
per product, which is precisely the limitation being removed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0110"
down_revision: str | Sequence[str] | None = "20260903_0109"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "price_list_items"
_OLD = "UQ_price_list_items_list_product"
_NEW = "UQ_price_list_items_list_product_quantity"


def upgrade() -> None:
    """Add the break column and widen the key that holds it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: price lists live in firm stores.
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "min_quantity" not in columns:
        # Existing rows become the rate that starts at nothing, which is what
        # they already were.
        op.add_column(
            _TABLE,
            sa.Column(
                "min_quantity",
                sa.Numeric(18, 4),
                server_default="0",
                nullable=False,
            ),
        )
    existing = {
        constraint["name"] for constraint in inspector.get_unique_constraints(_TABLE)
    }
    if _OLD in existing:
        op.drop_constraint(_OLD, _TABLE, type_="unique")
    if _NEW not in existing:
        op.create_unique_constraint(
            _NEW, _TABLE, ["price_list_id", "product_id", "min_quantity"]
        )


def downgrade() -> None:
    """Narrow the key again, and drop the break column.

    A list holding more than one break per product cannot fit the old key, so
    the extra rows are removed first -- keeping the rate that starts at nothing,
    which is the one the old shape could express.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing = {
        constraint["name"] for constraint in inspector.get_unique_constraints(_TABLE)
    }
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "min_quantity" in columns:
        bind.execute(
            sa.text(f"DELETE FROM {_TABLE} WHERE min_quantity > 0")
        )  # noqa: S608
    if _NEW in existing:
        op.drop_constraint(_NEW, _TABLE, type_="unique")
    if _OLD not in existing:
        op.create_unique_constraint(_OLD, _TABLE, ["price_list_id", "product_id"])
    if "min_quantity" in columns:
        op.drop_column(_TABLE, "min_quantity")
