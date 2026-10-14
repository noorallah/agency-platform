"""The firm's own list of salesmen (P2, salesman list design, build step 1).

* ``salesmen`` created in every firm store, with its three partial unique
  keys: the name (case-insensitive), the code and the user, each among the
  firm's live entries.
* Every id the salesman columns already hold is given an entry **of the same
  id**, tied to that user, so the move of those columns onto this table
  (step 2) rewrites no document row. The columns read are ``salesman_id`` on
  the twelve tables that carry one, and ``territory_salesman_assignments.user_id``,
  whose firm is its territory's. Rows soft-deleted or not, since a key
  declared later holds against both.
* The entry's name is the user's ``full_name`` where ``platform.users`` can
  be reached from this connection; in a dedicated database it cannot, so the
  entry is named ``Salesman`` and the first eight characters of its id, and
  ``upgrade_every_store`` renames it from the platform store once every store
  is at head. Two users of one name in one firm: the second is named with the
  first eight characters of its id after it, so the name key holds.
* ``SALESMAN_MANAGE`` seeded and granted to every role holding
  ``TERRITORY_ASSIGN_SALESMEN``, and to the system roles that hold it in
  code (``SALES_MANAGER``).

**One id, two firms, one store.** In the shared store a user may be the
salesman of two firms, and an id can be the primary key of one entry only.
The firm that names him most keeps the entry of his id; each other firm gets
an entry of a new id tied to the same user, and its documents still hold the
user's id. Step 2, which declares the keys, must point those firms' documents
at their own entry first.

Firm-owned and platform data: run ``scripts/migrate_all_stores.py``.
Idempotent: the table is created only where missing, an id already holding
an entry is skipped, and a grant is inserted only where missing.

Revision ID: 20261014_0380
Revises: 20261014_0379
Create Date: 2026-10-14

"""

from collections import Counter, defaultdict
from collections.abc import Sequence
from uuid import UUID, uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.salesmen.naming import free_name, placeholder_name

revision: str = "20261014_0380"
down_revision: str | Sequence[str] | None = "20261014_0379"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "salesmen"
_CODE = "SALESMAN_MANAGE"
_SIBLING = "TERRITORY_ASSIGN_SALESMEN"

#: The tables whose ``salesman_id`` names a salesman, each with a ``firm_id``.
_SALESMAN_COLUMNS = (
    "sales_invoices",
    "sales_orders",
    "delivery_notes",
    "sales_quotations",
    "enquiries",
    "credit_notes",
    "customer_debit_notes",
    "sales_returns",
    "customers",
    "commission_rules",
    "commission_payouts",
    "sales_targets",
)

_salesmen = sa.table(
    _TABLE,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("name", sa.String()),
    sa.column("user_id", UUIDType()),
    sa.column("earns_commission", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("version", sa.Integer()),
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
_roles = sa.table(
    "roles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("firm_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP`: a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails (`20260903_0114`).
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


def _create_table(inspector: sa.Inspector) -> None:
    """Create ``salesmen`` and its keys where the store lacks it."""
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("user_id", UUIDType(), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column(
            "earns_commission",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("IX_salesmen_firm_id", _TABLE, ["firm_id"])
    live = sa.text("NOT is_deleted")
    op.create_index(
        "UQ_salesmen_firm_code_active",
        _TABLE,
        ["firm_id", "code"],
        unique=True,
        postgresql_where=live,
        sqlite_where=live,
    )
    op.create_index(
        "UQ_salesmen_firm_user_active",
        _TABLE,
        ["firm_id", "user_id"],
        unique=True,
        postgresql_where=live,
        sqlite_where=live,
    )
    op.create_index(
        "UQ_salesmen_firm_name_active",
        _TABLE,
        ["firm_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=live,
        sqlite_where=live,
    )


def _named_ids(
    bind: sa.Connection, inspector: sa.Inspector
) -> dict[UUID, Counter[UUID]]:
    """Return every id the salesman columns hold, with how often each firm does."""
    found: dict[UUID, Counter[UUID]] = defaultdict(Counter)
    for table in _SALESMAN_COLUMNS:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if not {"salesman_id", "firm_id"} <= columns:
            continue
        rows = bind.execute(
            sa.text(
                f'SELECT salesman_id, firm_id, COUNT(*) FROM "{table}" '  # noqa: S608
                "WHERE salesman_id IS NOT NULL GROUP BY salesman_id, firm_id"
            )
        ).all()
        for salesman_id, firm_id, count in rows:
            found[UUID(str(salesman_id))][UUID(str(firm_id))] += int(count)
    if inspector.has_table("territory_salesman_assignments") and inspector.has_table(
        "sales_territories"
    ):
        rows = bind.execute(
            sa.text(
                "SELECT a.user_id, t.firm_id, COUNT(*) "
                "FROM territory_salesman_assignments a "
                "JOIN sales_territories t ON t.id = a.territory_id "
                "WHERE a.user_id IS NOT NULL GROUP BY a.user_id, t.firm_id"
            )
        ).all()
        for user_id, firm_id, count in rows:
            found[UUID(str(user_id))][UUID(str(firm_id))] += int(count)
    return found


def _user_names(bind: sa.Connection, inspector: sa.Inspector) -> dict[UUID, str]:
    """Read the users' names, where ``platform.users`` is reachable from here."""
    if bind.dialect.name != "postgresql":
        return {}
    if bind.scalar(sa.text("SELECT current_schema()")) == "platform":
        return {}
    if not inspector.has_table("users", schema="platform"):
        return {}
    return {
        UUID(str(user_id)): (full_name or "").strip()
        for user_id, full_name in bind.execute(
            sa.text("SELECT id, full_name FROM platform.users")
        ).all()
        if (full_name or "").strip()
    }


def _backfill(bind: sa.Connection, inspector: sa.Inspector) -> None:
    """Give every id the salesman columns hold an entry of its own."""
    named = _named_ids(bind, inspector)
    if not named:
        return
    held = {UUID(str(row_id)) for (row_id,) in bind.execute(sa.select(_salesmen.c.id))}
    tied = {
        (UUID(str(firm_id)), UUID(str(user_id)))
        for firm_id, user_id in bind.execute(
            sa.select(_salesmen.c.firm_id, _salesmen.c.user_id).where(
                _salesmen.c.user_id.is_not(None),
                _salesmen.c.is_deleted.is_(False),
            )
        )
    }
    taken: dict[UUID, set[str]] = defaultdict(set)
    for firm_id, name in bind.execute(
        sa.select(_salesmen.c.firm_id, _salesmen.c.name).where(
            _salesmen.c.is_deleted.is_(False)
        )
    ):
        taken[UUID(str(firm_id))].add(str(name).lower())
    names = _user_names(bind, inspector)

    for user_id in sorted(named, key=str):
        firms = named[user_id]
        # The firm that names him most keeps the entry of his id; a tie goes
        # to the lower firm id, so a replay chooses the same firm.
        ordered = sorted(firms, key=lambda firm: (-firms[firm], str(firm)))
        for position, firm_id in enumerate(ordered):
            if (firm_id, user_id) in tied:
                continue
            entry_id = user_id if position == 0 else uuid4()
            if entry_id in held:
                continue
            name = free_name(
                names.get(user_id, placeholder_name(user_id)),
                user_id,
                taken[firm_id],
            )
            if name is None:
                continue
            bind.execute(
                _salesmen.insert().values(
                    id=entry_id,
                    firm_id=firm_id,
                    name=name,
                    user_id=user_id,
                    earns_commission=True,
                    is_active=True,
                    is_deleted=False,
                    version=1,
                )
            )
            held.add(entry_id)
            tied.add((firm_id, user_id))
            taken[firm_id].add(name.lower())


def _display_name(code: str) -> str:
    """Render a permission code as a readable name."""
    return code.replace("_", " ").title()


def _grant(bind: sa.Connection) -> None:
    """Seed ``SALESMAN_MANAGE`` and grant it where it belongs."""
    permission_id = bind.scalar(
        sa.select(_permissions.c.id).where(_permissions.c.code == _CODE)
    )
    if permission_id is None:
        permission_id = uuid4()
        bind.execute(
            _permissions.insert().values(
                id=permission_id,
                code=_CODE,
                name=_display_name(_CODE),
                description="System-defined permission.",
                is_system=True,
                is_active=True,
                is_deleted=False,
            )
        )
    sibling_id = bind.scalar(
        sa.select(_permissions.c.id).where(_permissions.c.code == _SIBLING)
    )
    role_ids: set[object] = set()
    if sibling_id is not None:
        role_ids |= {
            role_id
            for (role_id,) in bind.execute(
                sa.select(_role_permissions.c.role_id).where(
                    _role_permissions.c.permission_id == sibling_id,
                    _role_permissions.c.is_deleted.is_(False),
                )
            )
        }
    # The platform's own roles that hold the code in code: a firm may have
    # named a role of its own with a system role's code.
    holders = [code for code, codes in ROLE_PERMISSION_CODES.items() if _CODE in codes]
    role_ids |= {
        role_id
        for (role_id,) in bind.execute(
            sa.select(_roles.c.id).where(
                _roles.c.code.in_(holders),
                _roles.c.firm_id.is_(None),
                _roles.c.is_deleted.is_(False),
            )
        )
    }
    granted = {
        role_id
        for (role_id,) in bind.execute(
            sa.select(_role_permissions.c.role_id).where(
                _role_permissions.c.permission_id == permission_id,
                _role_permissions.c.is_deleted.is_(False),
            )
        )
    }
    for role_id in role_ids - granted:
        bind.execute(
            _role_permissions.insert().values(
                id=uuid4(),
                role_id=role_id,
                permission_id=permission_id,
                is_deleted=False,
            )
        )


def upgrade() -> None:
    """Create the list, give each named id its entry, and seed the code."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # A store without sales documents is not a firm store.
    if inspector.has_table("sales_invoices"):
        _create_table(inspector)
        _backfill(bind, sa.inspect(bind))
    # Identity tables live only in the platform schema.
    if inspector.has_table("permissions") and inspector.has_table("roles"):
        _grant(bind)


def downgrade() -> None:
    """Drop the list. The permission stays: a grant may already rest on it."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
