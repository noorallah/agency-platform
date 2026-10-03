"""Principal and brand masters (MST-1, decision A118).

* ``principals`` (code, name, the vendor) and ``brands`` (name, principal).
* ``products.brand_id``, with every distinct free-text ``brand`` a firm's
  products carry made a brand row and linked -- only where not yet linked.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0281
Revises: 20261003_0280
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0281"
down_revision: str | Sequence[str] | None = "20261003_0280"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the masters, link products and backfill brands."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("products"):
        return
    if not inspector.has_table("principals"):
        op.create_table(
            "principals",
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
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("vendor_id", UUIDType(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_principals"),
            sa.ForeignKeyConstraint(
                ["vendor_id"],
                ["vendors.id"],
                name="FK_principals_vendor_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index("IX_principals_firm_id", "principals", ["firm_id"])
        op.create_index(
            "UQ_principals_code_active",
            "principals",
            ["firm_id", "code"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if not inspector.has_table("brands"):
        op.create_table(
            "brands",
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
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("principal_id", UUIDType(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_brands"),
            sa.ForeignKeyConstraint(
                ["principal_id"],
                ["principals.id"],
                name="FK_brands_principal_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index("IX_brands_firm_id", "brands", ["firm_id"])
        op.create_index(
            "UQ_brands_name_active",
            "brands",
            ["firm_id", "name"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if "brand_id" not in {c["name"] for c in inspector.get_columns("products")}:
        op.add_column("products", sa.Column("brand_id", UUIDType()))
        op.create_foreign_key(
            "FK_products_brand_id",
            "products",
            "brands",
            ["brand_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    _backfill_brands()


def _backfill_brands() -> None:
    """Make a brand row for each firm's distinct text brand, and link it."""
    bind = op.get_bind()
    pairs = bind.execute(
        sa.text(
            "SELECT DISTINCT firm_id, TRIM(brand) FROM products "
            "WHERE brand IS NOT NULL AND TRIM(brand) <> '' "
            "AND brand_id IS NULL AND is_deleted = false"
        )
    ).all()
    for firm_id, name in pairs:
        brand_id = bind.execute(
            sa.text(
                "SELECT id FROM brands WHERE firm_id = :firm AND name = :name "
                "AND is_deleted = false"
            ),
            {"firm": firm_id, "name": name},
        ).scalar()
        if brand_id is None:
            brand_id = uuid4()
            bind.execute(
                sa.text(
                    "INSERT INTO brands (id, firm_id, name, is_active, is_deleted, "
                    "version, created_at, updated_at) VALUES (:id, :firm, :name, "
                    "true, false, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": brand_id, "firm": firm_id, "name": name},
            )
        bind.execute(
            sa.text(
                "UPDATE products SET brand_id = :brand WHERE firm_id = :firm "
                "AND TRIM(brand) = :name AND brand_id IS NULL"
            ),
            {"brand": brand_id, "firm": firm_id, "name": name},
        )


def downgrade() -> None:
    """Unlink products and drop the masters; the text brands stay."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("products") and "brand_id" in {
        c["name"] for c in inspector.get_columns("products")
    }:
        op.drop_constraint("FK_products_brand_id", "products", type_="foreignkey")
        op.drop_column("products", "brand_id")
    for table in ("brands", "principals"):
        if inspector.has_table(table):
            op.drop_table(table)
