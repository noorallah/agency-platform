"""Give every firm the account a stock adjustment posts to.

Adjustments changed stock value and wrote no journal, so the inventory control
account stopped agreeing with the stock it controls the first time one was
made -- and unlike a receipt or a return there is no document behind it, so
nothing on any screen would ever have hinted at the gap.

They post now, which means every firm needs an account for them. Without this
the posting would refuse every adjustment a firm makes -- a working endpoint
breaking on upgrade, discovered by whoever next tried to write off a broken
carton.

`5500 Inventory Adjustment` is created where it is missing and mapped to the
new `INVENTORY_ADJUSTMENT` purpose. Both steps are skipped when they are
already there, so re-running changes nothing, and a firm that has deliberately
mapped the purpose to its own account keeps it.

`ledger_accounts` and `firm_control_accounts` are firm-owned: run
``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0079"
down_revision: str | Sequence[str] | None = "20260814_0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSE = "INVENTORY_ADJUSTMENT"
_CODE = "5500"
_NAME = "Inventory Adjustment"


def _has(table: str) -> bool:
    """Return whether a table exists in this store, asked for now."""
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    """Create the adjustment account per firm and map the purpose to it."""
    if not _has("ledger_accounts") or not _has("firm_control_accounts"):
        return
    bind = op.get_bind()
    # One row per firm that already has a chart. A firm with no accounts at all
    # has nothing to hang this off and is left alone -- `seed_finance_setup`
    # builds the whole chart including this account when one is created.
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
        mapped = bind.execute(
            sa.text(
                "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                "AND purpose = :purpose AND is_deleted = false"
            ),
            {"firm": firm_id, "purpose": _PURPOSE},
        ).scalar()
        if mapped is not None:
            continue
        account_id = bind.execute(
            sa.text(
                "SELECT id FROM ledger_accounts WHERE firm_id = :firm "
                "AND code = :code AND is_deleted = false"
            ),
            {"firm": firm_id, "code": _CODE},
        ).scalar()
        if account_id is None:
            group_id = bind.execute(
                sa.text(
                    "SELECT id FROM account_groups WHERE firm_id = :firm "
                    "AND account_type = 'EXPENSE' AND is_deleted = false "
                    "ORDER BY code LIMIT 1"
                ),
                {"firm": firm_id},
            ).scalar()
            if group_id is None:
                # No expense group to hang it from: this firm's chart is not
                # one this migration built, and guessing a group is worse than
                # leaving the mapping to an administrator.
                continue
            account_id = uuid4()
            bind.execute(
                sa.text(
                    "INSERT INTO ledger_accounts (id, firm_id, account_group_id, "
                    "code, name, account_type, is_balance_sheet, is_profit_loss, "
                    "requires_cost_center, requires_profit_center, is_active, "
                    "is_deleted, version, created_at, updated_at) "
                    "VALUES (:id, :firm, :group, :code, :name, 'EXPENSE', false, "
                    "true, false, false, true, false, 1, now(), now())"
                ),
                {
                    "id": account_id,
                    "firm": firm_id,
                    "group": group_id,
                    "code": _CODE,
                    "name": _NAME,
                },
            )
        bind.execute(
            sa.text(
                "INSERT INTO firm_control_accounts (id, firm_id, purpose, "
                "ledger_account_id, is_deleted, version, created_at, updated_at) "
                "VALUES (:id, :firm, :purpose, :account, false, 1, now(), now())"
            ),
            {
                "id": uuid4(),
                "firm": firm_id,
                "purpose": _PURPOSE,
                "account": account_id,
            },
        )


def downgrade() -> None:
    """Unmap the purpose and leave the account in place.

    The account may have postings against it by then, and dropping an account
    that has been posted to would take its history with it.
    """
    if not _has("firm_control_accounts"):
        return
    op.get_bind().execute(
        sa.text("DELETE FROM firm_control_accounts WHERE purpose = :purpose"),
        {"purpose": _PURPOSE},
    )
