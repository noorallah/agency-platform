"""Enforce per-firm active barcode uniqueness on product masters.

Revision ID: 20260807_0039
Revises: 20260807_0038
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260807_0039"
down_revision: str = "20260807_0038"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _firm_schemas(bind: sa.engine.Connection) -> list[str]:
    result = bind.execute(
        sa.text(
            "SELECT DISTINCT table_schema "
            "FROM information_schema.tables "
            "WHERE table_name = 'products' "
            "  AND table_schema NOT IN ('pg_catalog','information_schema')"
        )
    )
    return [row[0] for row in result.fetchall()]


def upgrade() -> None:
    """Apply enforce per-firm active barcode uniqueness on product masters."""
    bind = op.get_bind()
    for schema in _firm_schemas(bind):
        bind.execute(
            sa.text(
                f'CREATE UNIQUE INDEX IF NOT EXISTS "UQ_products_firm_barcode_active" '
                f'ON "{schema}".products (firm_id, barcode) '
                "WHERE barcode IS NOT NULL AND is_deleted IS FALSE"
            )
        )


def downgrade() -> None:
    """Reverse enforce per-firm active barcode uniqueness on product masters."""
    bind = op.get_bind()
    for schema in _firm_schemas(bind):
        bind.execute(
            sa.text(
                f'DROP INDEX IF EXISTS "{schema}"."UQ_products_firm_barcode_active"'
            )
        )
