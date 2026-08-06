"""Move firm storage routing into a dedicated mapping table.

Revision ID: 20260805_0035
Revises: 20260804_0034
Create Date: 2026-08-05
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260805_0035"
down_revision: str | None = "20260804_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create firm_storage_mappings and migrate tenancy fields from firms."""
    op.create_table(
        "firm_storage_mappings",
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
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "deployment_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'SHARED'"),
        ),
        sa.Column(
            "database_type",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'postgresql'"),
        ),
        sa.Column("database_name", sa.String(length=128), nullable=True),
        sa.Column("schema_name", sa.String(length=128), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.ForeignKeyConstraint(
            ["firm_id"], ["firms.id"], name="FK_firm_storage_mappings_firms"
        ),
        sa.PrimaryKeyConstraint("id", name="PK_firm_storage_mappings"),
        sa.UniqueConstraint("firm_id", name="UQ_firm_storage_mappings_firm_id"),
    )
    op.create_index(
        "IX_firm_storage_mappings_firm_id", "firm_storage_mappings", ["firm_id"]
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("firms")}
    required = {"deployment_mode", "database_type", "database_name", "schema_name"}
    if required.issubset(columns):
        firms = sa.table(
            "firms",
            sa.column("id", UUIDType()),
            sa.column("deployment_mode", sa.String()),
            sa.column("database_type", sa.String()),
            sa.column("database_name", sa.String()),
            sa.column("schema_name", sa.String()),
            sa.column("is_deleted", sa.Boolean()),
        )
        mappings = sa.table(
            "firm_storage_mappings",
            sa.column("id", UUIDType()),
            sa.column("firm_id", UUIDType()),
            sa.column("deployment_mode", sa.String()),
            sa.column("database_type", sa.String()),
            sa.column("database_name", sa.String()),
            sa.column("schema_name", sa.String()),
            sa.column("is_active", sa.Boolean()),
        )
        rows = bind.execute(
            sa.select(
                firms.c.id,
                firms.c.deployment_mode,
                firms.c.database_type,
                firms.c.database_name,
                firms.c.schema_name,
            ).where(firms.c.is_deleted.is_(False))
        ).all()
        if rows:
            op.bulk_insert(
                mappings,
                [
                    {
                        "id": uuid4(),
                        "firm_id": row.id,
                        "deployment_mode": row.deployment_mode or "SHARED",
                        "database_type": row.database_type or "postgresql",
                        "database_name": row.database_name,
                        "schema_name": row.schema_name,
                        "is_active": True,
                    }
                    for row in rows
                ],
            )
        with op.batch_alter_table("firms") as batch_op:
            batch_op.drop_column("schema_name")
            batch_op.drop_column("database_name")
            batch_op.drop_column("database_type")
            batch_op.drop_column("deployment_mode")


def downgrade() -> None:
    """Restore tenancy fields on firms and remove storage mapping table."""
    with op.batch_alter_table("firms") as batch_op:
        batch_op.add_column(
            sa.Column(
                "deployment_mode",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'SHARED'"),
            )
        )
        batch_op.add_column(sa.Column("database_name", sa.String(length=128)))
        batch_op.add_column(sa.Column("schema_name", sa.String(length=128)))
        batch_op.add_column(
            sa.Column(
                "database_type",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'postgresql'"),
            )
        )
    op.execute(
        sa.text(
            """
            UPDATE firms f
            SET
                deployment_mode = m.deployment_mode,
                database_type = m.database_type,
                database_name = m.database_name,
                schema_name = m.schema_name
            FROM firm_storage_mappings m
            WHERE m.firm_id = f.id
              AND m.is_deleted = false
              AND m.is_active = true
            """
        )
    )
    op.drop_index(
        "IX_firm_storage_mappings_firm_id", table_name="firm_storage_mappings"
    )
    op.drop_table("firm_storage_mappings")
