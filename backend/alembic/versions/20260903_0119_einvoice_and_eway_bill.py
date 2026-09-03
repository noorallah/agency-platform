"""What the tax authority knows about an invoice, and about its movement.

`einvoice_registrations` and `eway_bills` hold the references the government
portal returns. Both carry `mode`, NOT NULL and with **no server default**: a
default that could resolve to LIVE is a default that files a return by
accident, and a row that could not say whether it was a rehearsal is a
document somebody eventually presents at a check post.

One registration per invoice and one bill per invoice, by unique key. Two
references for one supply would leave nothing to say which the customer holds.

`EINVOICE_VIEW` and `EINVOICE_MANAGE` go in here as well. A code a router
enforces and the catalogue does not define has no permission row, so the
endpoint quietly becomes platform-admin-only. `EINVOICE_MANAGE` is not granted
to `SALES_MANAGER`: reading what was registered is part of running a sales
desk, filing with the authority is not.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0119
Revises: 20260903_0118
Create Date: 2026-09-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20260903_0119"
down_revision: str | Sequence[str] | None = "20260903_0118"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REGISTRATIONS = "einvoice_registrations"
_BILLS = "eway_bills"
_NEW_CODES = ("EINVOICE_VIEW", "EINVOICE_MANAGE")

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
_roles = sa.table("roles", sa.column("id", UUIDType()), sa.column("code", sa.String()))
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


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP`: a hand-written
    `create_table` that omits it builds a NOT NULL column with no default and
    the first insert fails, which `20260903_0114` had to repair everywhere.
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
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def _invoice_fk(inspector: sa.Inspector, name: str) -> list[sa.ForeignKeyConstraint]:
    """Return an invoice foreign key only where the table is present."""
    if not inspector.has_table("sales_invoices"):
        return []
    return [
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"],
            ["sales_invoices.id"],
            name=name,
            ondelete="RESTRICT",
        )
    ]


def _create_tables(inspector: sa.Inspector) -> None:
    """Create both tables where a firm store lacks them."""
    if not inspector.has_table("sales_invoices"):
        return
    if not inspector.has_table(_REGISTRATIONS):
        op.create_table(
            _REGISTRATIONS,
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("sales_invoice_id", UUIDType(), nullable=False),
            # No server default. SANDBOX is chosen by the service; a column
            # default is one migration away from silently being LIVE.
            sa.Column("mode", sa.String(length=20), nullable=False),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column("irn", sa.String(length=80), nullable=True),
            sa.Column("acknowledgement_number", sa.String(length=40), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("signed_qr_code", sa.Text(), nullable=True),
            sa.Column("signed_invoice", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(length=40), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancellation_reason", sa.String(length=200), nullable=True),
            sa.Column("request_payload", sa.JSON(), nullable=True),
            sa.UniqueConstraint(
                "firm_id",
                "sales_invoice_id",
                name="UQ_einvoice_registrations_invoice",
            ),
            *_invoice_fk(inspector, "FK_einvoice_registrations_sales_invoice_id"),
        )
        op.create_index(
            "IX_einvoice_registrations_firm_id", _REGISTRATIONS, ["firm_id"]
        )
        op.create_index(
            "IX_einvoice_registrations_firm_status",
            _REGISTRATIONS,
            ["firm_id", "status"],
        )

    if inspector.has_table(_BILLS):
        return
    op.create_table(
        _BILLS,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="PENDING"
        ),
        sa.Column("eway_bill_number", sa.String(length=40), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("distance_km", sa.Numeric(9, 2), nullable=False, server_default="0"),
        sa.Column(
            "transport_mode",
            sa.String(length=20),
            nullable=False,
            server_default="ROAD",
        ),
        sa.Column("transporter_id", sa.String(length=40), nullable=True),
        sa.Column("transporter_name", sa.String(length=200), nullable=True),
        sa.Column("vehicle_number", sa.String(length=20), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=200), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "firm_id", "sales_invoice_id", name="UQ_eway_bills_invoice"
        ),
        *_invoice_fk(inspector, "FK_eway_bills_sales_invoice_id"),
    )
    op.create_index("IX_eway_bills_firm_id", _BILLS, ["firm_id"])
    op.create_index("IX_eway_bills_firm_status", _BILLS, ["firm_id", "status"])


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Define the two codes and grant them where the seed says."""
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code).where(
                _permissions.c.code.in_(_NEW_CODES)
            )
        ).all()
    }
    for code in _NEW_CODES:
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
        for code in _NEW_CODES:
            if code not in permission_codes:
                continue
            permission_id = existing[code]
            if (role_id, permission_id) in granted:
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
    """Create both tables and seed their permission codes."""
    inspector = sa.inspect(op.get_bind())
    _create_tables(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop both tables and leave the permission codes in place."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_BILLS):
        op.drop_table(_BILLS)
    if inspector.has_table(_REGISTRATIONS):
        op.drop_table(_REGISTRATIONS)
