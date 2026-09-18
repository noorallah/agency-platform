"""Which serialised units a document line moves (D-STK-4).

A serial number's status never moved: nothing outside ``app/batch_serial``
read or wrote ``serial_numbers``, and no movement set
``inventory_transactions.serial_id``, so a mixer grinder that left on a
delivery note kept its serial ``AVAILABLE``. The owner decided on 2026-09-18
that the storekeeper picks the units: a delivery note line for a serial-tracked
product names them, dispatch refuses until there is one per unit leaving and
marks each ``SOLD``, and a sales return names the units coming back and makes
them ``AVAILABLE`` again.

``document_line_serials`` is where a line names its units. A dispatch posts one
movement per batch drawn from, not one per unit, so each row also records the
movement that carried its unit; ``inventory_transactions.serial_id`` is set
only where a movement carried exactly one.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260919_0138
Revises: 20260917_0137
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260919_0138"
down_revision: str | Sequence[str] | None = "20260917_0137"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_line_serials"


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP` because a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails -- `20260903_0114` had to repair every store for
    exactly that.
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
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def upgrade() -> None:
    """Create the table where a firm store lacks it.

    Only where ``serial_numbers`` exists: the platform schema holds no firm
    data, and a store built by ``create_all`` may already have the table.
    """
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("serial_numbers") or inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("serial_id", UUIDType(), nullable=False),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("document_id", UUIDType(), nullable=False),
        sa.Column("document_line_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("inventory_transaction_id", UUIDType(), nullable=True),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["serial_id"],
            ["serial_numbers.id"],
            name="FK_document_line_serials_serial_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "document_line_id",
            "serial_id",
            name="UQ_document_line_serials_line_serial",
        ),
    )
    op.create_index("IX_document_line_serials_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_document_line_serials_firm_serial", _TABLE, ["firm_id", "serial_id"]
    )
    op.create_index(
        "IX_document_line_serials_firm_document", _TABLE, ["firm_id", "document_id"]
    )
    op.create_index(
        "IX_document_line_serials_firm_line", _TABLE, ["firm_id", "document_line_id"]
    )


def downgrade() -> None:
    """Drop the table, forgetting which units each line named."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
