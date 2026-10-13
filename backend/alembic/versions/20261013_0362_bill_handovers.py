"""Bills handed to a collector (backlog 122, first customer row M4).

* ``bill_handovers``: which unpaid bill is out with which collector, since
  which day, and when it came back. A note beside the bill: nothing that
  states money reads it.
* ``COLLECTION_ASSIGN`` seeded and the system roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table is
created only where the store holds ``sales_invoices`` and lacks it, because a
firm store is partly built by ``Base.metadata.create_all`` and can already
have it; the permission is inserted only where the store holds the identity
tables and lacks the code.

Revision ID: 20261013_0362
Revises: 20261013_0361
Create Date: 2026-10-13

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261013_0362"
down_revision: str | Sequence[str] | None = "20261013_0361"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: A bill still out: the rows the two unique indexes hold to one per bill.
_OUT = "NOT is_deleted AND returned_at IS NULL"

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


def upgrade() -> None:
    """Create the table where a firm store lacks it; seed the permission."""
    inspector = sa.inspect(op.get_bind())
    if (
        not inspector.has_table("bill_handovers")
        and inspector.has_table("sales_invoices")
        and inspector.has_table("customer_opening_bills")
    ):
        op.create_table(
            "bill_handovers",
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
            sa.Column("customer_id", UUIDType(), nullable=False),
            sa.Column("sales_invoice_id", UUIDType(), nullable=True),
            sa.Column("customer_opening_bill_id", UUIDType(), nullable=True),
            sa.Column("collector_id", UUIDType(), nullable=False),
            sa.Column("handed_on", sa.Date(), nullable=False),
            sa.Column("handed_by", UUIDType(), nullable=False),
            sa.Column("outstanding_at_handover", sa.Numeric(18, 2), nullable=False),
            sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("returned_by", UUIDType(), nullable=True),
            sa.Column("return_note", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_bill_handovers"),
            sa.CheckConstraint(
                "(sales_invoice_id IS NULL) <> (customer_opening_bill_id IS NULL)",
                name="CK_bill_handovers_one_bill",
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="FK_bill_handovers_customer_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["sales_invoice_id"],
                ["sales_invoices.id"],
                name="FK_bill_handovers_sales_invoice_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["customer_opening_bill_id"],
                ["customer_opening_bills.id"],
                name="FK_bill_handovers_customer_opening_bill_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "UQ_bill_handovers_invoice_out",
            "bill_handovers",
            ["sales_invoice_id"],
            unique=True,
            postgresql_where=sa.text(_OUT),
            sqlite_where=sa.text(_OUT),
        )
        op.create_index(
            "UQ_bill_handovers_opening_bill_out",
            "bill_handovers",
            ["customer_opening_bill_id"],
            unique=True,
            postgresql_where=sa.text(_OUT),
            sqlite_where=sa.text(_OUT),
        )
        op.create_index(
            "IX_bill_handovers_firm_collector",
            "bill_handovers",
            ["firm_id", "collector_id"],
        )
        op.create_index(
            "IX_bill_handovers_firm_handed_on",
            "bill_handovers",
            ["firm_id", "handed_on"],
        )
        op.create_index(
            "IX_bill_handovers_firm_customer",
            "bill_handovers",
            ["firm_id", "customer_id"],
        )
    _seed_permissions()


def downgrade() -> None:
    """Drop the table; the permission stays."""
    if sa.inspect(op.get_bind()).has_table("bill_handovers"):
        op.drop_table("bill_handovers")
