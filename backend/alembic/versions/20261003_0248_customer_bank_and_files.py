"""A customer's bank accounts and files on record (MST-4).

``customer_bank_accounts`` and ``customer_attachments`` mirror the supplier's
twins, in every firm store that holds customers. ``CUSTOMER_MANAGE_BANK_DETAILS``
is seeded in the platform store and the system roles reconciled, the shape of
``20260928_0164``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0248
Revises: 20261003_0247
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261003_0248"
down_revision: str | Sequence[str] | None = "20261003_0247"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_permissions = sa.table(
    "permissions",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("is_system", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_roles = sa.table(
    "roles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _display_name(code: str) -> str:
    """Render a permission code as a readable name."""
    return code.replace("_", " ").title()


def _seed_permissions() -> None:
    """Insert missing system permissions and reconcile system role grants."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables live only in the platform schema.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return

    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in existing:
            continue
        permission_id = uuid4()
        existing[code] = permission_id
        bind.execute(
            _permissions.insert().values(
                id=permission_id,
                code=code,
                name=_display_name(code),
                description="System-defined permission.",
                is_system=True,
                is_active=True,
                is_deleted=False,
            )
        )

    role_ids = {
        code: role_id
        for role_id, code in bind.execute(sa.select(_roles.c.id, _roles.c.code)).all()
    }
    granted = {
        (role_id, permission_id)
        for role_id, permission_id in bind.execute(
            sa.select(
                _role_permissions.c.role_id, _role_permissions.c.permission_id
            ).where(_role_permissions.c.is_deleted.is_(False))
        ).all()
    }
    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for permission_code in permission_codes:
            permission_id = existing.get(permission_code)
            if permission_id is None or (role_id, permission_id) in granted:
                continue
            bind.execute(
                _role_permissions.insert().values(
                    id=uuid4(),
                    role_id=role_id,
                    permission_id=permission_id,
                    is_deleted=False,
                )
            )


def _audit_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity table carries."""
    return [
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
        sa.Column("customer_id", UUIDType(), nullable=False),
    ]


def _create_tables() -> None:
    """Create both tables in a firm store that holds customers."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("customers"):
        return
    if not inspector.has_table("customer_bank_accounts"):
        op.create_table(
            "customer_bank_accounts",
            *_audit_columns(),
            sa.Column("bank_name", sa.String(150), nullable=False),
            sa.Column("account_name", sa.String(150), nullable=False),
            sa.Column("account_number", sa.String(64), nullable=False),
            sa.Column("ifsc", sa.String(16), nullable=True),
            sa.Column("branch", sa.String(120), nullable=True),
            sa.Column("upi_id", sa.String(120), nullable=True),
            sa.Column(
                "is_primary",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_customer_bank_accounts"),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="FK_customer_bank_accounts_customer_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "IX_customer_bank_accounts_firm_id", "customer_bank_accounts", ["firm_id"]
        )
        op.create_index(
            "IX_customer_bank_accounts_customer_id",
            "customer_bank_accounts",
            ["customer_id"],
        )
    if not inspector.has_table("customer_attachments"):
        op.create_table(
            "customer_attachments",
            *_audit_columns(),
            sa.Column("file_name", sa.String(260), nullable=False),
            sa.Column("mime_type", sa.String(120), nullable=True),
            sa.Column("file_path", sa.String(1024), nullable=False),
            sa.Column("caption", sa.String(200), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_customer_attachments"),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="FK_customer_attachments_customer_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "IX_customer_attachments_firm_id", "customer_attachments", ["firm_id"]
        )
        op.create_index(
            "IX_customer_attachments_customer_id",
            "customer_attachments",
            ["customer_id"],
        )


def upgrade() -> None:
    """Build the firm tables and seed the permission, each where it belongs."""
    _create_tables()
    _seed_permissions()


def downgrade() -> None:
    """Drop the two tables; leave the seeded permission, as 0164 does."""
    inspector = sa.inspect(op.get_bind())
    for table in ("customer_attachments", "customer_bank_accounts"):
        if inspector.has_table(table):
            op.drop_table(table)
