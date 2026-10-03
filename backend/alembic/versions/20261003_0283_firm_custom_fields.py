"""A firm configures its own custom fields (MST-8, decision A120).

* ``firm_id`` on ``attribute_definitions`` and ``category_attribute_rules``:
  null is the shared catalogue, a value is that firm's own.
* The table-wide unique ``code`` becomes unique per firm among live rows,
  and among the shared live rows.
* ``CUSTOM_FIELD_VIEW`` and ``CUSTOM_FIELD_MANAGE`` seeded and the system
  roles reconciled (the firm administrator holds both).

Existing rows stay shared: copying them per firm would orphan the values
records already hold against them.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0283
Revises: 20261003_0282
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261003_0283"
down_revision: str | Sequence[str] | None = "20261003_0282"
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


def upgrade() -> None:
    """Scope both tables by firm and seed the two permissions."""
    inspector = sa.inspect(op.get_bind())
    for table in ("attribute_definitions", "category_attribute_rules"):
        if not inspector.has_table(table):
            continue
        if "firm_id" not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column("firm_id", UUIDType()))
            op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
    if inspector.has_table("attribute_definitions"):
        for constraint in inspector.get_unique_constraints("attribute_definitions"):
            if constraint.get("column_names") == ["code"] and constraint.get("name"):
                op.drop_constraint(
                    constraint["name"], "attribute_definitions", type_="unique"
                )
        for index in inspector.get_indexes("attribute_definitions"):
            if (
                index.get("unique")
                and index.get("column_names") == ["code"]
                and index.get("name")
                and not str(index["name"]).startswith("UQ_attribute_definitions_")
            ):
                op.drop_index(index["name"], table_name="attribute_definitions")
        names = {
            index["name"] for index in inspector.get_indexes("attribute_definitions")
        }
        if "UQ_attribute_definitions_firm_code_active" not in names:
            op.create_index(
                "UQ_attribute_definitions_firm_code_active",
                "attribute_definitions",
                ["firm_id", "code"],
                unique=True,
                postgresql_where=sa.text("is_deleted = false AND firm_id IS NOT NULL"),
            )
        if "UQ_attribute_definitions_shared_code_active" not in names:
            op.create_index(
                "UQ_attribute_definitions_shared_code_active",
                "attribute_definitions",
                ["code"],
                unique=True,
                postgresql_where=sa.text("is_deleted = false AND firm_id IS NULL"),
            )
    _seed_permissions()


def downgrade() -> None:
    """Drop the firm scoping; the code goes back to unique across the table."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("attribute_definitions"):
        names = {
            index["name"] for index in inspector.get_indexes("attribute_definitions")
        }
        for name in (
            "UQ_attribute_definitions_firm_code_active",
            "UQ_attribute_definitions_shared_code_active",
        ):
            if name in names:
                op.drop_index(name, table_name="attribute_definitions")
    for table in ("attribute_definitions", "category_attribute_rules"):
        if inspector.has_table(table) and "firm_id" in {
            c["name"] for c in inspector.get_columns(table)
        }:
            op.drop_index(f"IX_{table}_firm_id", table_name=table)
            op.drop_column(table, "firm_id")
