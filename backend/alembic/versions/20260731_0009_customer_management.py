"""Create the firm-scoped customer management schema.

Revision ID: 20260731_0009
Revises: 20260730_0008
Create Date: 2026-07-31
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0009"
down_revision: str | None = "20260730_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column[object]]:
    """Return columns shared by all persisted entities."""
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    """Create customer masters and synchronize the expanded system permissions."""
    op.create_table(
        "customers",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("customer_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("gst_number", sa.String(length=32), nullable=True),
        sa.Column("pan_number", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("alternate_phone", sa.String(length=20), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column(
            "credit_limit",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "opening_balance",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "payment_terms_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.UniqueConstraint("firm_id", "code", name="UQ_customers_firm_code"),
        sa.UniqueConstraint(
            "firm_id", "gst_number", name="UQ_customers_firm_gst_number"
        ),
        sa.UniqueConstraint(
            "firm_id", "pan_number", name="UQ_customers_firm_pan_number"
        ),
    )
    op.create_index("IX_customers_firm_id", "customers", ["firm_id"])
    op.create_index("IX_customers_firm_name", "customers", ["firm_id", "name"])
    op.create_index("IX_customers_firm_status", "customers", ["firm_id", "status"])

    op.create_table(
        "customer_addresses",
        *_base_columns(),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("address_type", sa.String(length=20), nullable=False),
        sa.Column("address_line1", sa.String(length=250), nullable=False),
        sa.Column("address_line2", sa.String(length=250), nullable=True),
        sa.Column("area", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("district", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=24), nullable=False),
        sa.Column(
            "is_default_billing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_default_shipping",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "IX_customer_addresses_customer_id",
        "customer_addresses",
        ["customer_id"],
    )
    op.create_index(
        "IX_customer_addresses_customer_city",
        "customer_addresses",
        ["customer_id", "city"],
    )

    op.create_table(
        "customer_contacts",
        *_base_columns(),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("designation", sa.String(length=100), nullable=True),
        sa.Column("mobile", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "IX_customer_contacts_customer_id",
        "customer_contacts",
        ["customer_id"],
    )

    connection = op.get_bind()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'CUSTOMER_RESTORE'")
    ).scalar()
    if permission_id is None:
        permission_id = uuid4()
        connection.execute(
            sa.text(
                "INSERT INTO permissions "
                "(id, code, name, description, is_active, is_system) "
                "VALUES (:id, 'CUSTOMER_RESTORE', 'Customer Restore', "
                "'System-defined permission.', true, true)"
            ),
            {"id": permission_id},
        )
    role_ids = connection.execute(
        sa.text(
            "SELECT id FROM roles WHERE code IN "
            "('PLATFORM_ADMIN', 'SUPPORT_ADMIN', 'FIRM_ADMIN', 'SALES_MANAGER')"
        )
    ).scalars()
    for role_id in role_ids:
        exists = connection.execute(
            sa.text(
                "SELECT id FROM role_permissions "
                "WHERE role_id = :role_id AND permission_id = :permission_id"
            ),
            {"role_id": role_id, "permission_id": permission_id},
        ).scalar()
        if exists is None:
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, role_id, permission_id) "
                    "VALUES (:id, :role_id, :permission_id)"
                ),
                {
                    "id": uuid4(),
                    "role_id": role_id,
                    "permission_id": permission_id,
                },
            )


def downgrade() -> None:
    """Remove customer tables and the permission introduced by this revision."""
    connection = op.get_bind()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'CUSTOMER_RESTORE'")
    ).scalar()
    if permission_id is not None:
        connection.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE permission_id = :permission_id"
            ),
            {"permission_id": permission_id},
        )
        connection.execute(
            sa.text("DELETE FROM permissions WHERE id = :permission_id"),
            {"permission_id": permission_id},
        )
    op.drop_index("IX_customer_contacts_customer_id", table_name="customer_contacts")
    op.drop_table("customer_contacts")
    op.drop_index(
        "IX_customer_addresses_customer_city",
        table_name="customer_addresses",
    )
    op.drop_index(
        "IX_customer_addresses_customer_id",
        table_name="customer_addresses",
    )
    op.drop_table("customer_addresses")
    op.drop_index("IX_customers_firm_status", table_name="customers")
    op.drop_index("IX_customers_firm_name", table_name="customers")
    op.drop_index("IX_customers_firm_id", table_name="customers")
    op.drop_table("customers")
