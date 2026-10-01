"""The largest discount a role may give on its own (backlog 64 row 3).

* ``role_discount_limits``, per firm and role code.
* ``discount_source`` on ``sales_invoice_lines``, so only a discount the bill
  itself typed is judged against the approver's limit. NULL on lines written
  before it.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0181"
down_revision: str | Sequence[str] | None = "20261001_0180"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_discount_source(inspector: sa.Inspector) -> None:
    """Record where a bill line's discount came from."""
    if not inspector.has_table("sales_invoice_lines"):
        return
    columns = {
        column["name"] for column in inspector.get_columns("sales_invoice_lines")
    }
    if "discount_source" not in columns:
        op.add_column(
            "sales_invoice_lines",
            sa.Column("discount_source", sa.String(20), nullable=True),
        )


def _create_limits(inspector: sa.Inspector) -> None:
    """Create the per-firm, per-role limit table in a firm store."""
    if not inspector.has_table("sales_orders"):
        return
    if inspector.has_table("role_discount_limits"):
        return
    op.create_table(
        "role_discount_limits",
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
        sa.Column("role_code", sa.String(100), nullable=False),
        sa.Column("max_discount_percent", sa.Numeric(5, 2), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_role_discount_limits"),
    )
    op.create_index(
        "IX_role_discount_limits_firm_id", "role_discount_limits", ["firm_id"]
    )
    op.create_index(
        "UQ_role_discount_limits_firm_role_active",
        "role_discount_limits",
        ["firm_id", "role_code"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def upgrade() -> None:
    """Add the limit table and the bill line's discount source."""
    inspector = sa.inspect(op.get_bind())
    _add_discount_source(inspector)
    _create_limits(inspector)


def downgrade() -> None:
    """Drop both."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("role_discount_limits"):
        op.drop_table("role_discount_limits")
    if inspector.has_table("sales_invoice_lines"):
        columns = {
            column["name"] for column in inspector.get_columns("sales_invoice_lines")
        }
        if "discount_source" in columns:
            op.drop_column("sales_invoice_lines", "discount_source")
