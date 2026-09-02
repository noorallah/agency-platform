"""Let a firm run promotions, and record what each one gave away.

A promotion is a rule with typed conditions and actions, evaluated while a
sales document is priced. Unlike a tax rule it **stacks**: every matching
promotion applies, in priority order, until one that refuses further stacking
is reached.

The tables are firm-owned, so they belong in every firm store and not in
`platform`, and `firm_id` deliberately carries **no foreign key** -- `firms`
exists only in the platform schema, and `Base.metadata.create_all`, which the
seed and tenancy-reset scripts use to build a firm store, would refuse a table
referencing it. `price_lists` and `commission_rules` are the precedent.

The permission half runs only where the identity tables are, which is the
platform store, so the two halves never both apply to one database.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20260902_0106"
down_revision: str | Sequence[str] | None = "20260902_0105"
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


def _base_columns() -> list[sa.Column]:
    """Return the `BaseEntity` columns every table here carries.

    Written out in full rather than trusted to a helper somewhere else: a
    migration that quietly omits one is invisible to the SQLite suite, which
    builds its schema from the ORM metadata instead.
    """
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


def _display_name(code: str) -> str:
    """Render a permission code as a readable name."""
    return code.replace("_", " ").title()


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Insert the new codes and reconcile system role grants.

    Identity tables live only in the platform schema, so every firm store
    returns here immediately. Without this an enforced code has no permission
    row, cannot be attached to any role, and the endpoint silently becomes
    platform-admin-only.
    """
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
    """Create the promotion tables, and seed the codes that guard them."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _seed_permissions(inspector)

    # Firm-owned: sales orders live in firm stores, so the platform schema has
    # no documents to promote and gets no tables.
    if not inspector.has_table("sales_orders"):
        return

    if not inspector.has_table("promotions"):
        op.create_table(
            "promotions",
            *_base_columns(),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "priority", sa.Integer(), server_default=sa.text("100"), nullable=False
            ),
            sa.Column(
                "status", sa.String(length=20), server_default="DRAFT", nullable=False
            ),
            sa.Column(
                "allow_stacking",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column("effective_from", sa.Date(), nullable=True),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("version_group_id", UUIDType(), nullable=False),
            sa.Column(
                "version_number",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            ),
            sa.Column("supersedes_promotion_id", UUIDType(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_promotions"),
            sa.UniqueConstraint(
                "firm_id",
                "code",
                "version_number",
                name="UQ_promotions_firm_code_version",
            ),
            sa.ForeignKeyConstraint(
                ["supersedes_promotion_id"],
                ["promotions.id"],
                name="FK_promotions_supersedes_promotion_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index("IX_promotions_firm_id", "promotions", ["firm_id"])
        op.create_index(
            "IX_promotions_firm_priority", "promotions", ["firm_id", "priority"]
        )
        op.create_index(
            "IX_promotions_firm_status", "promotions", ["firm_id", "status"]
        )
        op.create_index(
            "IX_promotions_firm_version_group",
            "promotions",
            ["firm_id", "version_group_id"],
        )

    for table, extra in (
        (
            "promotion_conditions",
            [
                sa.Column("field_key", sa.String(length=80), nullable=False),
                sa.Column("operator", sa.String(length=30), nullable=False),
                sa.Column("value_text", sa.Text(), nullable=True),
                sa.Column("value_number", sa.Numeric(18, 4), nullable=True),
                sa.Column("value_date", sa.Date(), nullable=True),
                sa.Column("value_boolean", sa.Boolean(), nullable=True),
                sa.Column("value_json", sa.JSON(), nullable=True),
            ],
        ),
        (
            "promotion_actions",
            [
                sa.Column("action_type", sa.String(length=40), nullable=False),
                sa.Column("parameters", sa.JSON(), nullable=False),
            ],
        ),
    ):
        if inspector.has_table(table):
            continue
        op.create_table(
            table,
            *_base_columns(),
            sa.Column("promotion_id", UUIDType(), nullable=False),
            sa.Column(
                "sequence", sa.Integer(), server_default=sa.text("1"), nullable=False
            ),
            *extra,
            sa.PrimaryKeyConstraint("id", name=f"PK_{table}"),
            sa.ForeignKeyConstraint(
                ["promotion_id"],
                ["promotions.id"],
                name=f"FK_{table}_promotion_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
        op.create_index(f"IX_{table}_promotion_id", table, ["promotion_id"])
        op.create_index(
            f"IX_{table}_firm_promotion", table, ["firm_id", "promotion_id"]
        )

    if not inspector.has_table("promotion_execution_logs"):
        op.create_table(
            "promotion_execution_logs",
            *_base_columns(),
            sa.Column("transaction_type", sa.String(length=40), nullable=False),
            sa.Column("document_date", sa.Date(), nullable=True),
            sa.Column("customer_id", UUIDType(), nullable=True),
            sa.Column("input_payload", sa.JSON(), nullable=False),
            sa.Column("evaluation_trace", sa.JSON(), nullable=False),
            sa.Column("result_payload", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id", name="PK_promotion_execution_logs"),
        )
        op.create_index(
            "IX_promotion_execution_logs_firm_id",
            "promotion_execution_logs",
            ["firm_id"],
        )
        op.create_index(
            "IX_promotion_execution_logs_firm_created",
            "promotion_execution_logs",
            ["firm_id", "created_at"],
        )
        op.create_index(
            "IX_promotion_execution_logs_customer",
            "promotion_execution_logs",
            ["customer_id"],
        )


def downgrade() -> None:
    """Drop the promotion tables, children first.

    The seeded permissions stay: removing them would strip grants an
    administrator may since have made to a custom role, which is more damaging
    than leaving extra catalogue rows.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in (
        "promotion_execution_logs",
        "promotion_actions",
        "promotion_conditions",
        "promotions",
    ):
        if inspector.has_table(table):
            op.drop_table(table)
