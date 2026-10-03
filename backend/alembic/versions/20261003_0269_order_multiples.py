"""A supplier's order multiple, and what breaking it does (BUY-5, A103).

* ``supplier_products.order_multiple``.
* ``purchase_workflow_settings.order_quantity_policy`` -- ``WARN`` (default)
  or ``REFUSE``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0269
Revises: 20261003_0268
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0269"
down_revision: str | Sequence[str] | None = "20261003_0268"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    """Return a table's column names, empty where the table is missing."""
    if not inspector.has_table(table):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the multiple and the policy where missing."""
    inspector = sa.inspect(op.get_bind())
    have = _columns(inspector, "supplier_products")
    if have and "order_multiple" not in have:
        op.add_column(
            "supplier_products", sa.Column("order_multiple", sa.Numeric(18, 4))
        )
    have = _columns(inspector, "purchase_workflow_settings")
    if have and "order_quantity_policy" not in have:
        op.add_column(
            "purchase_workflow_settings",
            sa.Column(
                "order_quantity_policy",
                sa.String(10),
                nullable=False,
                server_default="WARN",
            ),
        )


def downgrade() -> None:
    """Drop both."""
    inspector = sa.inspect(op.get_bind())
    if "order_multiple" in _columns(inspector, "supplier_products"):
        op.drop_column("supplier_products", "order_multiple")
    if "order_quantity_policy" in _columns(inspector, "purchase_workflow_settings"):
        op.drop_column("purchase_workflow_settings", "order_quantity_policy")
