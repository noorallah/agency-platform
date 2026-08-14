"""Record money arriving and money going out, and put it in the ledger.

Nothing in the product could record a receipt or a payment. Two years of seeded
trading left Cash at 0.00 and Trade Receivables at 249,236.70, because invoices
were the only thing that ever reached the general ledger.

The one path that existed was worse than nothing:
``POST /customers/{id}/receivables/transactions`` accepts a RECEIPT, moves the
customer's outstanding balance and writes no journal. Every use of it put the
subsidiary ledger and the general ledger further apart, silently.

Two tables:

* ``settlements`` -- one movement of money against a customer or a vendor,
  carrying the journal it wrote. ``journal_entry_id`` is NOT NULL: a settlement
  that never reached the ledger is the defect this module exists to close.
* ``settlement_allocations`` -- how much of it cleared which invoice. What is
  left over is an advance, which is a normal thing for a customer to send.

Both are firm-owned: run ``scripts/migrate_all_stores.py``.

The permission half runs only where the identity tables live. ``RECEIPT_VIEW``
and ``PAYMENT_VIEW`` are new -- only the CREATE codes were ever seeded, so a
cashier could record money and not look at what they had recorded.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20260814_0076"
down_revision: str | Sequence[str] | None = "20260814_0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTLEMENTS = "settlements"
_ALLOCATIONS = "settlement_allocations"

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


def _entity_columns() -> list[sa.Column]:
    """Return the columns every business entity carries.

    Checked against ``BaseEntity`` rather than written from memory: this list
    first went in without ``deleted_by``, which the unit suite cannot catch
    because it builds its tables from the ORM and never runs the migration.
    Every read of the table failed with ``UndefinedColumn`` on the first real
    request.
    """
    return [
        sa.Column("id", UUIDType(), primary_key=True),
        # ``server_default`` matters: the timestamps are filled by the
        # database, not the ORM, so a table created without it takes every
        # insert as a not-null violation.
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
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
    ]


def _external_fk(table: str, column: str, target: str) -> list[sa.ForeignKeyConstraint]:
    """Declare a foreign key only when its target is in this store.

    ``firms`` lives only in the platform schema and ``customers`` only in firm
    schemas, so a firm-owned table cannot always see what it refers to.
    """
    if not _has(target.split(".")[0]):
        return []
    return [
        sa.ForeignKeyConstraint(
            [column], [target], name=f"FK_{table}_{column}", ondelete="RESTRICT"
        )
    ]


def _has(table: str) -> bool:
    """Return whether a table exists in this store, asking the database now.

    A single ``Inspector`` caches what it has seen, so one built before the
    first ``create_table`` still reports that table as missing afterwards --
    which silently skipped the allocations table, whose guard depends on
    ``settlements`` existing.
    """
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    """Create the settlement tables and seed the two view permissions."""
    bind = op.get_bind()

    if _has("ledger_accounts") and not _has(_SETTLEMENTS):
        op.create_table(
            _SETTLEMENTS,
            *_entity_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("direction", sa.String(length=20), nullable=False),
            sa.Column("customer_id", UUIDType(), nullable=True),
            sa.Column("vendor_id", UUIDType(), nullable=True),
            sa.Column("settlement_number", sa.String(length=60), nullable=False),
            sa.Column("settlement_date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column(
                "allocated_amount",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "unallocated_amount",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0",
            ),
            sa.Column("method", sa.String(length=20), nullable=False),
            sa.Column("ledger_account_id", UUIDType(), nullable=False),
            sa.Column("instrument_reference", sa.String(length=120), nullable=True),
            sa.Column("narration", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("journal_entry_id", UUIDType(), nullable=False),
            sa.UniqueConstraint(
                "firm_id", "settlement_number", name="UQ_settlements_firm_number"
            ),
            sa.CheckConstraint(
                "(direction = 'RECEIPT' AND customer_id IS NOT NULL "
                "AND vendor_id IS NULL) OR (direction = 'PAYMENT' "
                "AND vendor_id IS NOT NULL AND customer_id IS NULL)",
                name="CK_settlements_party_matches_direction",
            ),
            sa.CheckConstraint("amount > 0", name="CK_settlements_amount_positive"),
            sa.ForeignKeyConstraint(
                ["ledger_account_id"],
                ["ledger_accounts.id"],
                name="FK_settlements_ledger_account_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["journal_entry_id"],
                ["journal_entries.id"],
                name="FK_settlements_journal_entry_id",
                ondelete="RESTRICT",
            ),
            *_external_fk(_SETTLEMENTS, "customer_id", "customers.id"),
            *_external_fk(_SETTLEMENTS, "vendor_id", "vendors.id"),
        )
        op.create_index("IX_settlements_firm_id", _SETTLEMENTS, ["firm_id"])
        op.create_index(
            "IX_settlements_firm_direction", _SETTLEMENTS, ["firm_id", "direction"]
        )
        op.create_index(
            "IX_settlements_firm_date", _SETTLEMENTS, ["firm_id", "settlement_date"]
        )
        op.create_index(
            "IX_settlements_firm_customer", _SETTLEMENTS, ["firm_id", "customer_id"]
        )
        op.create_index(
            "IX_settlements_firm_vendor", _SETTLEMENTS, ["firm_id", "vendor_id"]
        )

    if _has(_SETTLEMENTS) and not _has(_ALLOCATIONS):
        op.create_table(
            _ALLOCATIONS,
            *_entity_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("settlement_id", UUIDType(), nullable=False),
            sa.Column("sales_invoice_id", UUIDType(), nullable=True),
            sa.Column("purchase_invoice_id", UUIDType(), nullable=True),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.CheckConstraint("amount > 0", name="CK_settlement_allocations_positive"),
            sa.UniqueConstraint(
                "settlement_id",
                "sales_invoice_id",
                name="UQ_settlement_allocations_sales_invoice",
            ),
            sa.UniqueConstraint(
                "settlement_id",
                "purchase_invoice_id",
                name="UQ_settlement_allocations_purchase_invoice",
            ),
            sa.ForeignKeyConstraint(
                ["settlement_id"],
                ["settlements.id"],
                name="FK_settlement_allocations_settlement_id",
                ondelete="CASCADE",
            ),
            *_external_fk(_ALLOCATIONS, "sales_invoice_id", "sales_invoices.id"),
            *_external_fk(_ALLOCATIONS, "purchase_invoice_id", "purchase_invoices.id"),
        )
        op.create_index("IX_settlement_allocations_firm_id", _ALLOCATIONS, ["firm_id"])
        op.create_index(
            "IX_settlement_allocations_settlement_id", _ALLOCATIONS, ["settlement_id"]
        )
        op.create_index(
            "IX_settlement_allocations_sales",
            _ALLOCATIONS,
            ["firm_id", "sales_invoice_id"],
        )
        op.create_index(
            "IX_settlement_allocations_purchase",
            _ALLOCATIONS,
            ["firm_id", "purchase_invoice_id"],
        )

    if not _has("permissions") or not _has("roles"):
        # Identity lives only in the platform schema.
        return
    _seed_permissions(bind)


def _seed_permissions(bind: sa.engine.Connection) -> None:
    """Insert any unseeded permission code and reconcile system role grants."""
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
                name=code.replace("_", " ").title(),
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


def downgrade() -> None:
    """Drop the settlement tables and leave the permission catalogue alone.

    Removing a seeded permission would strip grants administrators may since
    have made to custom roles, which is more damaging than an extra row.
    """
    if _has(_ALLOCATIONS):
        op.drop_table(_ALLOCATIONS)
    if _has(_SETTLEMENTS):
        op.drop_table(_SETTLEMENTS)
