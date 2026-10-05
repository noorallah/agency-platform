"""Hold a counter bill; a cashier's shift counted at close.

Backlog §87 #7 (SG-7).

* ``sales_invoices.is_held`` / ``held_at`` / ``held_note``: a draft bill
  parked while the next customer is served. A flag, never a status.
* ``counter_shifts``: a cashier's till -- opened with a float, closed on a
  count, the difference posted to *Cash short and over*. One open shift per
  cashier, held by the partial unique index.
* ``sales_invoices.counter_shift_id``: the shift a bill's counter money was
  taken in; NULL for a firm that opens none.
* ``CASH_SHORT_AND_OVER`` mapped to *Cash Short and Over* (6960, expense) for
  every firm whose books are open, the shape of ``20261005_0319``: only where
  missing, never overwriting.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: every object
is made only in a store that holds ``sales_invoices`` and lacks it. No
``firm_id`` or cashier foreign key: ``firms`` and ``users`` live only in the
platform store.

Revision ID: 20261005_0324
Revises: 20261005_0323
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0324"
down_revision: str | Sequence[str] | None = "20261005_0323"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "counter_shifts"
_BILLS = "sales_invoices"
_PURPOSE = "CASH_SHORT_AND_OVER"
_SHIFT_KEY = "FK_sales_invoices_counter_shift_id"
_SHIFT_INDEX = "IX_sales_invoices_counter_shift"
_OPEN_INDEX = "UQ_counter_shifts_open_cashier"

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    (
        _PURPOSE,
        "6960",
        "Cash Short and Over",
        "EXPENSE",
        "IEXP",
        "Indirect Expenses",
    ),
)


def _create_shifts(inspector: sa.Inspector) -> None:
    """Create the table, with the columns every ``BaseEntity`` table carries."""
    keys = [
        sa.ForeignKeyConstraint(
            [column],
            [f"{target}.id"],
            name=f"FK_{_TABLE}_{column}",
            ondelete="RESTRICT",
        )
        for column, target in (
            ("branch_id", "branches"),
            ("cash_account_id", "ledger_accounts"),
            ("difference_journal_entry_id", "journal_entries"),
        )
        if inspector.has_table(target)
    ]
    op.create_table(
        _TABLE,
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.Column("cashier_id", UUIDType(), nullable=False),
        sa.Column("cash_account_id", UUIDType(), nullable=False),
        sa.Column("shift_number", sa.String(30), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "opening_float",
            sa.Numeric(18, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(10), server_default=sa.text("'OPEN'"), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", UUIDType(), nullable=True),
        sa.Column("counted_cash", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_cash", sa.Numeric(18, 2), nullable=True),
        sa.Column("difference", sa.Numeric(18, 2), nullable=True),
        sa.Column("difference_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("closing_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=f"PK_{_TABLE}"),
        sa.UniqueConstraint("firm_id", "shift_number", name="UQ_counter_shifts_number"),
        # `op.f`: the name is final. Without it `alembic/env.py` applies the
        # naming convention again and the constraint is deployed doubled.
        sa.CheckConstraint(
            "opening_float >= 0",
            name=op.f("CK_counter_shifts_opening_float_not_negative"),
        ),
        sa.CheckConstraint(
            "counted_cash IS NULL OR counted_cash >= 0",
            name=op.f("CK_counter_shifts_counted_cash_not_negative"),
        ),
        *keys,
    )
    # One open shift per cashier: the key, not a read, is what holds it.
    op.create_index(
        _OPEN_INDEX,
        _TABLE,
        ["firm_id", "cashier_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN' AND is_deleted = false"),
        sqlite_where=sa.text("status = 'OPEN' AND is_deleted = 0"),
    )
    op.create_index("IX_counter_shifts_firm_opened", _TABLE, ["firm_id", "opened_at"])


def _add_bill_columns(inspector: sa.Inspector) -> None:
    """Add the hold flag and the shift a bill was paid in, where missing."""
    present = {column["name"] for column in inspector.get_columns(_BILLS)}
    if "is_held" not in present:
        op.add_column(
            _BILLS,
            sa.Column(
                "is_held",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    if "held_at" not in present:
        op.add_column(
            _BILLS, sa.Column("held_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "held_note" not in present:
        op.add_column(_BILLS, sa.Column("held_note", sa.String(200), nullable=True))
    if "counter_shift_id" not in present:
        op.add_column(_BILLS, sa.Column("counter_shift_id", UUIDType(), nullable=True))
    keys = {key["name"] for key in inspector.get_foreign_keys(_BILLS)}
    if _SHIFT_KEY not in keys:
        op.create_foreign_key(
            _SHIFT_KEY,
            _BILLS,
            _TABLE,
            ["counter_shift_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    indexes = {index["name"] for index in inspector.get_indexes(_BILLS)}
    if _SHIFT_INDEX not in indexes:
        op.create_index(_SHIFT_INDEX, _BILLS, ["counter_shift_id"])


def _group_for(
    bind: sa.Connection, firm_id: object, *, code: str, kind: str, name: str
) -> object:
    """Return the firm's group for an account, creating it only if it has none."""
    group_id = bind.execute(
        sa.text(
            "SELECT id FROM account_groups WHERE firm_id = :firm "
            "AND code = :code AND is_deleted = false"
        ),
        {"firm": firm_id, "code": code},
    ).scalar()
    if group_id is not None:
        return group_id
    group_id = uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO account_groups (id, firm_id, code, name, "
            "account_type, is_active, is_deleted, version, "
            "created_at, updated_at) VALUES (:id, :firm, :code, "
            ":name, :kind, true, false, 1, now(), now())"
        ),
        {"id": group_id, "firm": firm_id, "code": code, "name": name, "kind": kind},
    )
    return group_id


def _seed_accounts(inspector: sa.Inspector) -> None:
    """Map the short-and-over account for every firm whose books are open."""
    if not inspector.has_table("ledger_accounts") or not inspector.has_table(
        "firm_control_accounts"
    ):
        return
    bind = op.get_bind()
    firms = (
        bind.execute(
            sa.text(
                "SELECT DISTINCT firm_id FROM ledger_accounts WHERE is_deleted = false"
            )
        )
        .scalars()
        .all()
    )
    for firm_id in firms:
        for purpose, code, name, kind, group_code, group_name in _ACCOUNTS:
            mapped = bind.execute(
                sa.text(
                    "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                    "AND purpose = :purpose AND is_deleted = false"
                ),
                {"firm": firm_id, "purpose": purpose},
            ).scalar()
            if mapped is not None:
                continue
            found = bind.execute(
                sa.text(
                    "SELECT id, account_type FROM ledger_accounts "
                    "WHERE firm_id = :firm AND code = :code AND is_deleted = false"
                ),
                {"firm": firm_id, "code": code},
            ).first()
            if found is not None and found[1] != kind:
                # The firm used the code for something else; mapping it would
                # book a till's shortage to whatever that is. Left for the
                # firm: a close with a difference names the missing purpose.
                continue
            account_id = None if found is None else found[0]
            if account_id is None:
                group_id = _group_for(
                    bind, firm_id, code=group_code, kind=kind, name=group_name
                )
                account_id = uuid4()
                bind.execute(
                    sa.text(
                        "INSERT INTO ledger_accounts (id, firm_id, "
                        "account_group_id, code, name, account_type, "
                        "is_balance_sheet, is_profit_loss, "
                        "requires_cost_center, requires_profit_center, "
                        "is_active, is_deleted, version, created_at, "
                        "updated_at) VALUES (:id, :firm, :group, :code, :name, "
                        ":kind, false, true, false, false, "
                        "true, false, 1, now(), now())"
                    ),
                    {
                        "id": account_id,
                        "firm": firm_id,
                        "group": group_id,
                        "code": code,
                        "name": name,
                        "kind": kind,
                    },
                )
            bind.execute(
                sa.text(
                    "INSERT INTO firm_control_accounts (id, firm_id, purpose, "
                    "ledger_account_id, is_deleted, version, created_at, "
                    "updated_at) VALUES (:id, :firm, :purpose, :account, "
                    "false, 1, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "firm": firm_id,
                    "purpose": purpose,
                    "account": account_id,
                },
            )


def upgrade() -> None:
    """Create the shifts, add the bill's columns and map the account."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no bills.
    if not inspector.has_table(_BILLS):
        return
    if not inspector.has_table(_TABLE):
        _create_shifts(inspector)
    # Read again: the table the bill's key points at exists now.
    _add_bill_columns(sa.inspect(op.get_bind()))
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the bill's columns, the shifts and the mapping; keep the account."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(f"DELETE FROM firm_control_accounts WHERE purpose = '{_PURPOSE}'")
        )
    if inspector.has_table(_BILLS):
        indexes = {index["name"] for index in inspector.get_indexes(_BILLS)}
        if _SHIFT_INDEX in indexes:
            op.drop_index(_SHIFT_INDEX, table_name=_BILLS)
        keys = {key["name"] for key in inspector.get_foreign_keys(_BILLS)}
        if _SHIFT_KEY in keys:
            op.drop_constraint(_SHIFT_KEY, _BILLS, type_="foreignkey")
        present = {column["name"] for column in inspector.get_columns(_BILLS)}
        for column in ("counter_shift_id", "held_note", "held_at", "is_held"):
            if column in present:
                op.drop_column(_BILLS, column)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
