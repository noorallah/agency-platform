"""Foreign-currency supplier bills and exchange gain or loss (PG-12 part A).

* ``vendors.currency_code`` (NULL = rupees): the currency a supplier bills in,
  which a new bill from it starts at.
* ``purchase_invoices.base_tax_total`` and ``base_grand_total`` (NULL on a
  rupee bill): the bill's tax and total in rupees at its own rate, each leg
  rounded to the ledger on its own.
* ``settlements.currency_code``, ``exchange_rate`` and ``currency_amount``
  (NULL on a rupee payment): a payment in the bill's currency at the rate of
  the day it was paid.
* ``settlement_allocations.currency_amount`` and ``base_amount`` (NULL on a
  rupee allocation): what the allocation cleared in the bill's currency and
  what that was worth at the bill's rate. ``amount`` stays the rupees paid;
  the difference is the exchange gain or loss.
* ``EXCHANGE_GAIN_LOSS`` mapped to *Exchange Gain/Loss* (4950, revenue) for
  every firm whose books are open, the shape of ``20261005_0308``: only where
  missing, never overwriting.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where its table exists and it does not.

Revision ID: 20261005_0313
Revises: 20261005_0312
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0313"
down_revision: str | Sequence[str] | None = "20261005_0312"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, column, type) -- every column nullable, so a replay or an old row
#: reads as rupees.
_COLUMNS: tuple[tuple[str, str, sa.types.TypeEngine[object]], ...] = (
    ("vendors", "currency_code", sa.String(3)),
    ("purchase_invoices", "base_tax_total", sa.Numeric(18, 2)),
    ("purchase_invoices", "base_grand_total", sa.Numeric(18, 2)),
    ("settlements", "currency_code", sa.String(3)),
    ("settlements", "exchange_rate", sa.Numeric(18, 6)),
    ("settlements", "currency_amount", sa.Numeric(18, 2)),
    ("settlement_allocations", "currency_amount", sa.Numeric(18, 2)),
    ("settlement_allocations", "base_amount", sa.Numeric(18, 2)),
)

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    (
        "EXCHANGE_GAIN_LOSS",
        "4950",
        "Exchange Gain/Loss",
        "INCOME",
        "REV",
        "Revenue",
    ),
)


def _add_columns(inspector: sa.Inspector) -> None:
    """Add each currency column where its table exists and it does not."""
    for table, name, kind in _COLUMNS:
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        if name not in present:
            op.add_column(table, sa.Column(name, kind, nullable=True))


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
    """Map the exchange gain/loss account for every firm whose books are open."""
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
            if found is not None and found[1] not in ("INCOME", "EXPENSE"):
                # The firm used the code for something else; mapping it would
                # post exchange differences to whatever that is. Left for the
                # firm.
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
    """Add the currency columns and map the exchange gain/loss account."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no bills.
    if not inspector.has_table("purchase_invoices"):
        return
    _add_columns(inspector)
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the currency columns and the mapping; keep the account."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose = 'EXCHANGE_GAIN_LOSS'"
            )
        )
    for table, name, _ in reversed(_COLUMNS):
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        if name in present:
            op.drop_column(table, name)
