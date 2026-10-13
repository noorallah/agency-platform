"""The collector's end-of-day line on a handed-out bill (backlog 124, row M6).

* ``collection_returns``: one line per handed-out bill per day -- collected,
  part, promised, not collected -- naming the receipt that took its money
  into the books and the promise taken with it.
* ``credit_control_settings.collector_records_receipt``: the firm's switch
  for whether a collector's own line records the receipt. Off by default.
* ``COLLECTION_OWN_RECORD`` seeded and the system roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table is
created only where the store holds ``bill_handovers`` and lacks it, the
column only where its table exists without it, because a firm store is partly
built by ``Base.metadata.create_all`` and can already have both; the
permission is inserted only where the store holds the identity tables and
lacks the code.

Revision ID: 20261013_0364
Revises: 20261013_0363
Create Date: 2026-10-13

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261013_0364"
down_revision: str | Sequence[str] | None = "20261013_0363"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: A line still standing: the rows the unique index holds to one per bill
#: per day.
_LIVE = "NOT is_deleted AND cancelled_at IS NULL"
_SETTINGS = "credit_control_settings"
_SWITCH = "collector_records_receipt"

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
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("firm_id", UUIDType()),
    sa.column("is_system", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _display_name(code: str) -> str:
    """Render a system code as a readable name."""
    return code.replace("_", " ").title()


def _seed_permissions(bind: sa.engine.Connection) -> None:
    """Insert missing system permissions and reconcile system role grants."""
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

    # The platform's own roles only: a firm may have named a role of its own
    # with a system role's code.
    role_ids = {
        code: role_id
        for role_id, code in bind.execute(
            sa.select(_roles.c.id, _roles.c.code).where(
                _roles.c.firm_id.is_(None), _roles.c.is_deleted.is_(False)
            )
        ).all()
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


def _create_returns() -> None:
    """Create ``collection_returns`` with its keys and indexes."""
    op.create_table(
        "collection_returns",
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
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("handover_id", UUIDType(), nullable=False),
        sa.Column("collector_id", UUIDType(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("outstanding_before", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "amount_collected",
            sa.Numeric(18, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("payment_mode", sa.String(length=20), nullable=True),
        sa.Column("instrument_reference", sa.String(length=120), nullable=True),
        sa.Column("settlement_id", UUIDType(), nullable=True),
        sa.Column("payment_promise_id", UUIDType(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by", UUIDType(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", UUIDType(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_collection_returns"),
        sa.CheckConstraint(
            "amount_collected >= 0",
            name="CK_collection_returns_amount_not_negative",
        ),
        sa.ForeignKeyConstraint(
            ["handover_id"],
            ["bill_handovers.id"],
            name="FK_collection_returns_handover_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["settlements.id"],
            name="FK_collection_returns_settlement_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payment_promise_id"],
            ["payment_promises.id"],
            name="FK_collection_returns_payment_promise_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "UQ_collection_returns_handover_day",
        "collection_returns",
        ["handover_id", "return_date"],
        unique=True,
        postgresql_where=sa.text(_LIVE),
        sqlite_where=sa.text(_LIVE),
    )
    op.create_index(
        "IX_collection_returns_firm_day_collector",
        "collection_returns",
        ["firm_id", "return_date", "collector_id"],
    )
    op.create_index(
        "IX_collection_returns_firm_settlement",
        "collection_returns",
        ["firm_id", "settlement_id"],
    )


def upgrade() -> None:
    """Create the table and the switch where a firm store lacks them; seed."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if (
        not inspector.has_table("collection_returns")
        and inspector.has_table("bill_handovers")
        and inspector.has_table("settlements")
        and inspector.has_table("payment_promises")
    ):
        _create_returns()
    if inspector.has_table(_SETTINGS) and _SWITCH not in {
        column["name"] for column in inspector.get_columns(_SETTINGS)
    }:
        op.add_column(
            _SETTINGS,
            sa.Column(
                _SWITCH,
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    # Identity tables live only in the platform schema.
    if inspector.has_table("permissions") and inspector.has_table("roles"):
        _seed_permissions(bind)


def downgrade() -> None:
    """Drop the table and the switch; the permission stays."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("collection_returns"):
        op.drop_table("collection_returns")
    if inspector.has_table(_SETTINGS) and _SWITCH in {
        column["name"] for column in inspector.get_columns(_SETTINGS)
    }:
        op.drop_column(_SETTINGS, _SWITCH)
