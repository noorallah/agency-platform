"""A commission rule can name the goods it is about, and pay per unit.

A rate was a statement about a whole document: 3% of everything, whoever sold
whatever. Firms do not work that way -- the cold chain pays better than dry
goods, and a distributor often pays two rupees a case rather than a percentage
of the price.

`product_id` and `product_category_id` make a rule a statement about *lines*.
Both null is a rule about the document, which is every rule written before
this, and those keep measuring exactly what they measured: the report
apportions each invoice's own total across its lines, so an unscoped rule
matches all of them and the parts sum to the whole.

`rate_type` PER_UNIT with `per_unit_amount` pays for units rather than value.
It is refused on the COLLECTED basis, because money collected has no cases in
it, and refused without a product or category, because a rate per unit across
everything a firm sells would add cases of biscuits to litres of oil.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0116
Revises: 20260903_0115
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260903_0116"
down_revision: str | Sequence[str] | None = "20260903_0115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "commission_rules"


def _columns(inspector: sa.Inspector) -> set[str]:
    """Return the column names the rule table already has."""
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the two scope keys and the per-unit rate."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # A store that does not trade has nothing to pay commission on, and the
    # platform schema holds a stray copy of `commission_rules` from before the
    # module was firm-scoped -- see `20260903_0113`.
    if not inspector.has_table("sales_invoices") or not inspector.has_table(_TABLE):
        return
    existing = _columns(inspector)
    if "product_id" not in existing:
        op.add_column(_TABLE, sa.Column("product_id", UUIDType(), nullable=True))
        # Declared only where the target is present, the `_external_fk` shape
        # from `20260809_0042`.
        if inspector.has_table("products"):
            op.create_foreign_key(
                "FK_commission_rules_product_id",
                _TABLE,
                "products",
                ["product_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    if "product_category_id" not in existing:
        op.add_column(
            _TABLE, sa.Column("product_category_id", UUIDType(), nullable=True)
        )
        if inspector.has_table("product_categories"):
            op.create_foreign_key(
                "FK_commission_rules_product_category_id",
                _TABLE,
                "product_categories",
                ["product_category_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    if "rate_type" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "rate_type",
                sa.String(length=20),
                nullable=False,
                server_default="PERCENT",
            ),
        )
    if "per_unit_amount" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "per_unit_amount",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),
        )
    if "IX_commission_rules_firm_product" not in {
        index["name"] for index in inspector.get_indexes(_TABLE)
    }:
        op.create_index(
            "IX_commission_rules_firm_product", _TABLE, ["firm_id", "product_id"]
        )


def downgrade() -> None:
    """Drop the scope keys and the per-unit rate."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    if "IX_commission_rules_firm_product" in {
        index["name"] for index in inspector.get_indexes(_TABLE)
    }:
        op.drop_index("IX_commission_rules_firm_product", table_name=_TABLE)
    existing = _columns(inspector)
    for column in (
        "per_unit_amount",
        "rate_type",
        "product_category_id",
        "product_id",
    ):
        if column in existing:
            op.drop_column(_TABLE, column)
