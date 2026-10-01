"""Messaging: email, WhatsApp and SMS, switched on by each firm (backlog 51).

* ``messaging_settings``, ``messaging_channel_configs``,
  ``messaging_event_configs`` and ``messaging_outbox`` in every firm store.
* ``no_reminders``, ``preferred_channel``, ``whatsapp_opt_in`` and
  ``whatsapp_opt_in_at`` on ``customers``.
* ``DOCUMENT_SEND`` in the platform store, with every system role's grants
  reconciled -- the shape of ``20261001_0180``.

Idempotent throughout; firm-owned parts run per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261001_0185"
down_revision: str | Sequence[str] | None = "20261001_0190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the BaseEntity columns, with database-side timestamp defaults."""
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
    ]


def _unique_active(name: str, table: str, columns: list[str]) -> None:
    """Create a unique index over live rows only."""
    op.create_index(
        name,
        table,
        columns,
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def _create_tables(inspector: sa.Inspector) -> None:
    """Create the four messaging tables in a firm store that lacks them."""
    if not inspector.has_table("customers"):
        return
    if not inspector.has_table("messaging_settings"):
        op.create_table(
            "messaging_settings",
            *_base_columns(),
            sa.Column(
                "is_enabled",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "due_soon_days", sa.Integer(), server_default="3", nullable=False
            ),
            sa.Column(
                "overdue_every_days", sa.Integer(), server_default="7", nullable=False
            ),
            sa.Column("last_reminder_scan_on", sa.Date(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_messaging_settings"),
        )
        op.create_index(
            "IX_messaging_settings_firm_id", "messaging_settings", ["firm_id"]
        )
        _unique_active(
            "UQ_messaging_settings_firm_active", "messaging_settings", ["firm_id"]
        )
    if not inspector.has_table("messaging_channel_configs"):
        op.create_table(
            "messaging_channel_configs",
            *_base_columns(),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("provider", sa.String(30), nullable=False),
            sa.Column(
                "is_enabled",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("public_settings", sa.JSON(), nullable=True),
            sa.Column("credentials_encrypted", sa.Text(), nullable=True),
            sa.Column(
                "health",
                sa.String(20),
                server_default="NOT_CONFIGURED",
                nullable=False,
            ),
            sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_messaging_channel_configs"),
        )
        op.create_index(
            "IX_messaging_channel_configs_firm_id",
            "messaging_channel_configs",
            ["firm_id"],
        )
        _unique_active(
            "UQ_messaging_channel_configs_firm_channel_active",
            "messaging_channel_configs",
            ["firm_id", "channel"],
        )
    if not inspector.has_table("messaging_event_configs"):
        op.create_table(
            "messaging_event_configs",
            *_base_columns(),
            sa.Column("event_code", sa.String(40), nullable=False),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column(
                "is_enabled",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column("priority", sa.Integer(), server_default="1", nullable=False),
            sa.Column("template_name", sa.String(120), nullable=True),
            sa.Column("template_language", sa.String(10), nullable=True),
            sa.Column("subject", sa.String(300), nullable=True),
            sa.Column("body", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_messaging_event_configs"),
        )
        op.create_index(
            "IX_messaging_event_configs_firm_id",
            "messaging_event_configs",
            ["firm_id"],
        )
        _unique_active(
            "UQ_messaging_event_configs_firm_event_channel_active",
            "messaging_event_configs",
            ["firm_id", "event_code", "channel"],
        )
    if not inspector.has_table("messaging_outbox"):
        op.create_table(
            "messaging_outbox",
            *_base_columns(),
            sa.Column("event_code", sa.String(40), nullable=False),
            sa.Column("document_type", sa.String(40), nullable=True),
            sa.Column("document_id", UUIDType(), nullable=True),
            sa.Column("document_number", sa.String(80), nullable=True),
            sa.Column("customer_id", UUIDType(), nullable=True),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("provider", sa.String(30), nullable=True),
            sa.Column("recipient", sa.String(320), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("subject", sa.String(300), nullable=True),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("template_name", sa.String(120), nullable=True),
            sa.Column("template_language", sa.String(10), nullable=True),
            sa.Column("variables", sa.JSON(), nullable=True),
            sa.Column(
                "attach_pdf",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("fallback_channels", sa.JSON(), nullable=True),
            sa.Column("occurrence", sa.String(40), nullable=True),
            sa.Column("dedupe_key", sa.String(300), nullable=True),
            sa.Column(
                "is_resend",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("previous_message_id", UUIDType(), nullable=True),
            sa.Column("requested_by", UUIDType(), nullable=True),
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provider_message_id", sa.String(200), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_messaging_outbox"),
        )
        op.create_index("IX_messaging_outbox_firm_id", "messaging_outbox", ["firm_id"])
        op.create_index(
            "IX_messaging_outbox_firm_status_due",
            "messaging_outbox",
            ["firm_id", "status"],
        )
        op.create_index(
            "IX_messaging_outbox_document",
            "messaging_outbox",
            ["firm_id", "document_id"],
        )
        op.create_index(
            "UQ_messaging_outbox_firm_dedupe_active",
            "messaging_outbox",
            ["firm_id", "dedupe_key"],
            unique=True,
            postgresql_where=sa.text("dedupe_key IS NOT NULL AND NOT is_deleted"),
            sqlite_where=sa.text("dedupe_key IS NOT NULL AND NOT is_deleted"),
        )


def _add_customer_columns(inspector: sa.Inspector) -> None:
    """Give customers the messaging preferences, where customers live."""
    if not inspector.has_table("customers"):
        return
    columns = {column["name"] for column in inspector.get_columns("customers")}
    if "no_reminders" not in columns:
        op.add_column(
            "customers",
            sa.Column(
                "no_reminders",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    if "preferred_channel" not in columns:
        op.add_column(
            "customers", sa.Column("preferred_channel", sa.String(20), nullable=True)
        )
    if "whatsapp_opt_in" not in columns:
        op.add_column(
            "customers",
            sa.Column(
                "whatsapp_opt_in",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    if "whatsapp_opt_in_at" not in columns:
        op.add_column(
            "customers",
            sa.Column("whatsapp_opt_in_at", sa.DateTime(timezone=True), nullable=True),
        )


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


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Insert missing system permissions and reconcile system role grants."""
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in existing:
            continue
        existing[code] = uuid4()
        bind.execute(
            _permissions.insert().values(
                id=existing[code],
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
    granted = set(
        bind.execute(
            sa.select(
                _role_permissions.c.role_id, _role_permissions.c.permission_id
            ).where(_role_permissions.c.is_deleted.is_(False))
        )
        .tuples()
        .all()
    )
    for role_code, codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for code in codes:
            permission_id = existing.get(code)
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
    """Add the messaging tables, the customer preferences and DOCUMENT_SEND."""
    inspector = sa.inspect(op.get_bind())
    _create_tables(inspector)
    _add_customer_columns(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the messaging tables and the customer preferences.

    The permission stays, as every permission migration here leaves it.
    """
    inspector = sa.inspect(op.get_bind())
    for table in (
        "messaging_outbox",
        "messaging_event_configs",
        "messaging_channel_configs",
        "messaging_settings",
    ):
        if inspector.has_table(table):
            op.drop_table(table)
    if inspector.has_table("customers"):
        columns = {column["name"] for column in inspector.get_columns("customers")}
        for column in (
            "whatsapp_opt_in_at",
            "whatsapp_opt_in",
            "preferred_channel",
            "no_reminders",
        ):
            if column in columns:
                op.drop_column("customers", column)
