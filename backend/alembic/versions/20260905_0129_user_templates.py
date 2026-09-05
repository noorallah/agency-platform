"""A named bundle of roles for one job.

A firm administrator setting up a new counter clerk should not have to
reassemble a permission set from twelve roles and remember which. A template is
that decision, made once and given a name the firm already uses.

Deliberately a role bundle and not a dormant user row. Cloning a user carries
everything a user has -- an email, a password, memberships, an audit trail, a
login history -- and the clone quietly inherits whatever was edited after the
template was written. A bundle carries only what the job needs, and applying one
is a plain `set_user_roles` whose result the administrator is free to edit.

Platform-owned: `users`, `roles` and `firms` live only in the platform schema,
so a table of role ids scoped by firm id has nowhere else it could live. This
migration is a no-op wherever `roles` is absent, which is every firm store.

The eleven platform-provided templates are inserted **here**, not left to
`seed_system_rbac`. That seeder is called only by `generate_sample_data.py` and
never at startup, so a live database gets its seeded rows from migrations --
the same rule the permission codes follow in `20260809_0044`. Written the other
way first, and driving the endpoint against a real server answered zero
templates for every firm, which is exactly how a feature ships unreachable.

The catalogue is read from `SYSTEM_USER_TEMPLATES` rather than copied, so the
migration and the seeder cannot disagree about what a job needs, and the insert
skips anything already present so a replay is safe.

Revision ID: 20260905_0129
Revises: 20260905_0128
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import SYSTEM_USER_TEMPLATES

revision: str = "20260905_0129"
down_revision: str | None = "20260905_0128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TEMPLATES = "user_templates"
_TEMPLATE_ROLES = "user_template_roles"


def upgrade() -> None:
    """Create the template tables where the platform identity tables live."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("roles"):
        return
    existing = set(inspector.get_table_names())

    if _TEMPLATES not in existing:
        op.create_table(
            _TEMPLATES,
            sa.Column("id", UUIDType(), nullable=False),
            sa.Column("code", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("firm_id", UUIDType(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "is_system",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            # Spelled out, because `TimestampMixin` declares these with a
            # server default and SQLAlchemy therefore leaves them out of every
            # INSERT -- a hand-written table without the default is NOT NULL
            # with nothing to fill it, and the *first* write raises.
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
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(
                ["firm_id"],
                ["firms.id"],
                name="FK_user_templates_firm_id",
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name="PK_user_templates"),
        )
        op.create_index("IX_user_templates_firm_id", _TEMPLATES, ["firm_id"])
        # Two partial keys rather than one on (firm_id, code): PostgreSQL
        # treats NULLs as distinct, so a single key would let the platform
        # hold ten templates all called `counter-sales`.
        op.create_index(
            "UQ_user_templates_platform_code_active",
            _TEMPLATES,
            ["code"],
            unique=True,
            postgresql_where=sa.text("firm_id IS NULL AND is_deleted = false"),
            sqlite_where=sa.text("firm_id IS NULL AND is_deleted = 0"),
        )
        op.create_index(
            "UQ_user_templates_firm_code_active",
            _TEMPLATES,
            ["firm_id", "code"],
            unique=True,
            postgresql_where=sa.text("firm_id IS NOT NULL AND is_deleted = false"),
            sqlite_where=sa.text("firm_id IS NOT NULL AND is_deleted = 0"),
        )

    if _TEMPLATE_ROLES not in existing:
        op.create_table(
            _TEMPLATE_ROLES,
            sa.Column("id", UUIDType(), nullable=False),
            sa.Column("template_id", UUIDType(), nullable=False),
            sa.Column("role_id", UUIDType(), nullable=False),
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
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(
                ["template_id"],
                [f"{_TEMPLATES}.id"],
                name="FK_user_template_roles_template_id",
            ),
            sa.ForeignKeyConstraint(
                ["role_id"],
                ["roles.id"],
                name="FK_user_template_roles_role_id",
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name="PK_user_template_roles"),
            sa.UniqueConstraint(
                "template_id", "role_id", name="UQ_user_template_roles_template_role"
            ),
        )
        op.create_index(
            "IX_user_template_roles_template_id", _TEMPLATE_ROLES, ["template_id"]
        )

    _insert_platform_templates(bind)


def _insert_platform_templates(bind: sa.engine.Connection) -> None:
    """Insert the platform-provided job templates, skipping any that exist."""
    roles = dict(
        bind.execute(
            sa.text("SELECT code, id FROM roles WHERE is_deleted = false")
        ).all()
    )
    present = {
        row[0]
        for row in bind.execute(
            sa.text(f"SELECT code FROM {_TEMPLATES} WHERE firm_id IS NULL")
        ).all()
    }
    templates = sa.table(
        _TEMPLATES,
        sa.column("id", UUIDType()),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("firm_id", UUIDType()),
        sa.column("is_active", sa.Boolean),
        sa.column("is_system", sa.Boolean),
    )
    template_roles = sa.table(
        _TEMPLATE_ROLES,
        sa.column("id", UUIDType()),
        sa.column("template_id", UUIDType()),
        sa.column("role_id", UUIDType()),
    )
    for code, name, description, role_codes in SYSTEM_USER_TEMPLATES:
        if code in present:
            continue
        # A template whose roles are not all seeded would be one nobody can
        # apply, so it is skipped whole rather than inserted incomplete.
        if any(role_code not in roles for role_code in role_codes):
            continue
        template_id = uuid4()
        op.bulk_insert(
            templates,
            [
                {
                    "id": template_id,
                    "code": code,
                    "name": name,
                    "description": description,
                    "firm_id": None,
                    "is_active": True,
                    "is_system": True,
                }
            ],
        )
        op.bulk_insert(
            template_roles,
            [
                {
                    "id": uuid4(),
                    "template_id": template_id,
                    "role_id": roles[role_code],
                }
                for role_code in role_codes
            ],
        )


def downgrade() -> None:
    """Drop the template tables."""
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if _TEMPLATE_ROLES in existing:
        op.drop_table(_TEMPLATE_ROLES)
    if _TEMPLATES in existing:
        op.drop_table(_TEMPLATES)
