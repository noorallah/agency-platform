"""Expenses: rent, fuel and salaries recorded without the journal screen.

One table, ``expenses``: what was spent, on which expense account, out of which
cash or bank account, and the journal that recorded it. Recording one writes
and posts that journal; cancelling one posts a mirror and keeps both. The
decision is the owner's, recorded in ``docs/PROFIT_AND_LOSS_GUIDE.md`` section
5 item 1: the industry's payment voucher (Tally) or *Expense* (Zoho Books).

The three permission codes go in here as well -- a code a router enforces and
the catalogue does not define has no permission row, so the endpoint quietly
becomes platform-admin-only. They are granted to the roles that hold them in
``ROLE_PERMISSION_CODES`` today, named here rather than read from the seed so
a replay next year does what this revision did (see ``20260906_0130``).

Firm-owned: run ``scripts/migrate_all_stores.py``. ``firms`` exists only in the
platform schema, so the ``firm_id`` key is declared only where it does.

Revision ID: 20260927_0163
Revises: 20260927_0162
Create Date: 2026-09-27

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260927_0163"
down_revision: str | Sequence[str] | None = "20260927_0162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "expenses"
_NEW_CODES = ("EXPENSE_VIEW", "EXPENSE_CREATE", "EXPENSE_CANCEL")

#: Who holds what, as `ROLE_PERMISSION_CODES` says on this date. The two
#: platform roles hold every code; `VIEWER` holds every `_VIEW` code.
_GRANTS: dict[str, tuple[str, ...]] = {
    "PLATFORM_ADMIN": _NEW_CODES,
    "SUPPORT_ADMIN": _NEW_CODES,
    "FIRM_ADMIN": _NEW_CODES,
    "FIRM_MANAGER": _NEW_CODES,
    "ACCOUNTANT": _NEW_CODES,
    "VIEWER": ("EXPENSE_VIEW",),
}

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


def _external_fk(
    inspector: sa.Inspector, table: str, column: str, name: str, ondelete: str | None
) -> list[sa.ForeignKeyConstraint]:
    """Declare a foreign key only where its target actually exists."""
    if not inspector.has_table(table):
        return []
    return [
        sa.ForeignKeyConstraint([column], [f"{table}.id"], name=name, ondelete=ondelete)
    ]


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
    """Create the expenses table where a firm store lacks it."""
    # A store without a ledger is not a firm store; it has nothing to post to.
    if not inspector.has_table("ledger_accounts") or not inspector.has_table(
        "journal_entries"
    ):
        return
    if inspector.has_table(_TABLE):
        return
    constraints = _external_fk(
        inspector, "firms", "firm_id", "FK_expenses_firm_id", None
    )
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("expense_number", sa.String(length=60), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("expense_account_id", UUIDType(), nullable=False),
        sa.Column("paid_from_account_id", UUIDType(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("payee", sa.String(length=200), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="POSTED"
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=False),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", UUIDType(), nullable=True),
        sa.UniqueConstraint(
            "firm_id", "expense_number", name="UQ_expenses_firm_number"
        ),
        sa.CheckConstraint("amount > 0", name="CK_expenses_amount_positive"),
        sa.ForeignKeyConstraint(
            ["expense_account_id"],
            ["ledger_accounts.id"],
            name="FK_expenses_expense_account_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paid_from_account_id"],
            ["ledger_accounts.id"],
            name="FK_expenses_paid_from_account_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name="FK_expenses_journal_entry_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_journal_entry_id"],
            ["journal_entries.id"],
            name="FK_expenses_reversal_journal_entry_id",
            ondelete="RESTRICT",
        ),
        *constraints,
    )
    op.create_index("IX_expenses_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_expenses_firm_date", _TABLE, ["firm_id", "expense_date"])
    op.create_index(
        "IX_expenses_firm_account", _TABLE, ["firm_id", "expense_account_id"]
    )


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Define the three codes and grant them to the roles that hold them."""
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
    for role_code, codes in _GRANTS.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for code in codes:
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
    """Create the expenses table and seed its permission codes."""
    inspector = sa.inspect(op.get_bind())
    _create_table(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the table and leave the permission codes in place.

    Removing the codes would strip grants an administrator may since have made
    to custom roles, which is more damaging than three extra catalogue rows.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
