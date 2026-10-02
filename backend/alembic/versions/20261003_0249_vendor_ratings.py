"""People's ratings of a supplier (BUY-15).

``vendor_ratings``: one person's scores (quality, delivery, price,
communication, paperwork, each 1 to 5) and a remark; one live row per person
per supplier, an earlier rating kept as history.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: created only in
a store that holds vendors and lacks it.

Revision ID: 20261003_0249
Revises: 20261003_0248
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0249"
down_revision: str | Sequence[str] | None = "20261003_0248"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "vendor_ratings"
_CRITERIA = ("quality", "delivery", "price", "communication", "paperwork")


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("vendors") or inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
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
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("rated_by", UUIDType(), nullable=False),
        sa.Column("rated_on", sa.Date(), nullable=False),
        *(sa.Column(name, sa.Integer(), nullable=False) for name in _CRITERIA),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_vendor_ratings"),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            name="FK_vendor_ratings_vendor_id",
            ondelete="RESTRICT",
        ),
        *(
            sa.CheckConstraint(
                f"{name} BETWEEN 1 AND 5", name=f"CK_vendor_ratings_{name}_range"
            )
            for name in _CRITERIA
        ),
    )
    op.create_index("IX_vendor_ratings_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_vendor_ratings_vendor_id", _TABLE, ["vendor_id"])
    op.create_index(
        "UQ_vendor_ratings_rater_active",
        _TABLE,
        ["firm_id", "vendor_id", "rated_by"],
        unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
