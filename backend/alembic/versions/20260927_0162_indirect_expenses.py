"""Give every firm with open books an Indirect Expenses group and its accounts.

The books opened with Direct Expenses only, so rent and salaries had nowhere of
their own: they sat beside Purchases and Cost of Goods Sold, or were not
recorded at all. New firms now open with an *Indirect Expenses* group holding
the usual running costs (``INDIRECT_EXPENSE_ACCOUNTS`` in
``app/finance/services/opening_setup.py``); this gives an existing firm the
same, which is what the Expenses screen records against (owner, 2026-09-27).

Only where missing, never overwriting: a firm that already has an account
under one of these codes keeps it as it is, and a firm whose books were never
opened is left alone -- opening them seeds the lot.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260927_0162
Revises: 20260924_0161
Create Date: 2026-09-27

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0162"
down_revision: str | Sequence[str] | None = "20260924_0161"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GROUP = ("IEXP", "Indirect Expenses")

#: Kept in step with ``INDIRECT_EXPENSE_ACCOUNTS``, written out so this
#: migration means the same thing whatever the seed says later.
_ACCOUNTS = (
    ("6000", "Rent"),
    ("6100", "Salaries and Wages"),
    ("6200", "Electricity"),
    ("6300", "Telephone and Internet"),
    ("6400", "Travel and Conveyance"),
    ("6500", "Office and General Expenses"),
    ("6600", "Repairs and Maintenance"),
    ("6700", "Bank Charges"),
)


def upgrade() -> None:
    """Add the group and the accounts to every firm whose books are open."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("account_groups") or not inspector.has_table(
        "ledger_accounts"
    ):
        return
    # A firm's books are open once its Direct Expenses group exists: that is
    # what opening them creates first.
    firms = (
        bind.execute(
            sa.text(
                "SELECT DISTINCT firm_id FROM account_groups "
                "WHERE code = 'EXP' AND is_deleted = false"
            )
        )
        .scalars()
        .all()
    )
    for firm_id in firms:
        group_id = bind.execute(
            sa.text(
                "SELECT id FROM account_groups WHERE firm_id = :firm "
                "AND code = :code AND is_deleted = false"
            ),
            {"firm": firm_id, "code": _GROUP[0]},
        ).scalar()
        if group_id is None:
            group_id = uuid4()
            bind.execute(
                sa.text(
                    "INSERT INTO account_groups (id, firm_id, code, name, "
                    "account_type, is_active, is_deleted, version, "
                    "created_at, updated_at) VALUES (:id, :firm, :code, :name, "
                    "'EXPENSE', true, false, 1, now(), now())"
                ),
                {
                    "id": group_id,
                    "firm": firm_id,
                    "code": _GROUP[0],
                    "name": _GROUP[1],
                },
            )
        for code, name in _ACCOUNTS:
            taken = bind.execute(
                sa.text(
                    "SELECT id FROM ledger_accounts WHERE firm_id = :firm "
                    "AND code = :code AND is_deleted = false"
                ),
                {"firm": firm_id, "code": code},
            ).scalar()
            if taken is not None:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO ledger_accounts (id, firm_id, "
                    "account_group_id, code, name, account_type, "
                    "is_balance_sheet, is_profit_loss, "
                    "requires_cost_center, requires_profit_center, "
                    "is_active, is_deleted, version, created_at, "
                    "updated_at) VALUES (:id, :firm, :group, :code, :name, "
                    "'EXPENSE', false, true, false, false, "
                    "true, false, 1, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "firm": firm_id,
                    "group": group_id,
                    "code": code,
                    "name": name,
                },
            )


def downgrade() -> None:
    """Leave the accounts in place.

    They may already carry postings, and a downgrade that deleted accounts
    with journal lines against them would be refused by the database or,
    worse, orphan the lines.
    """
