"""Give every firm the equity account day-one stock is credited to.

Opening stock was the last movement that changed stock value and wrote no
journal, and it was the one that *could not* post: the chart had no equity
account at all, so there was nothing to credit. Day-one stock arrived from
nowhere the ledger can see -- no supplier was invoiced and no money left -- and
what it represents is what the owners put into the business.

`3000 Opening Balance Equity` is created under an `EQ` equity group and mapped
to the new `OPENING_BALANCE_EQUITY` purpose, for every firm that already has a
chart. Without it, posting would refuse every opening stock batch, which is the
first thing a new firm does.

The same account is what a balance sheet wants for any day-one balance, so a
firm that later records opening receivables or opening cash has somewhere
consistent to put them.

Firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0080"
down_revision: str | Sequence[str] | None = "20260814_0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSE = "OPENING_BALANCE_EQUITY"
_GROUP_CODE = "EQ"
_GROUP_NAME = "Equity"
_CODE = "3000"
_NAME = "Opening Balance Equity"


def _has(table: str) -> bool:
    """Return whether a table exists in this store, asked for now."""
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    """Create the equity group, the account and the mapping, per firm."""
    if not _has("ledger_accounts") or not _has("firm_control_accounts"):
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
        mapped = bind.execute(
            sa.text(
                "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                "AND purpose = :purpose AND is_deleted = false"
            ),
            {"firm": firm_id, "purpose": _PURPOSE},
        ).scalar()
        if mapped is not None:
            continue

        group_id = bind.execute(
            sa.text(
                "SELECT id FROM account_groups WHERE firm_id = :firm "
                "AND account_type = 'EQUITY' AND is_deleted = false "
                "ORDER BY code LIMIT 1"
            ),
            {"firm": firm_id},
        ).scalar()
        if group_id is None:
            # No firm has one: the chart was built before equity existed in it.
            group_id = uuid4()
            bind.execute(
                sa.text(
                    "INSERT INTO account_groups (id, firm_id, code, name, "
                    "account_type, is_active, is_deleted, version, created_at, "
                    "updated_at) VALUES (:id, :firm, :code, :name, 'EQUITY', "
                    "true, false, 1, now(), now())"
                ),
                {
                    "id": group_id,
                    "firm": firm_id,
                    "code": _GROUP_CODE,
                    "name": _GROUP_NAME,
                },
            )

        account_id = bind.execute(
            sa.text(
                "SELECT id FROM ledger_accounts WHERE firm_id = :firm "
                "AND code = :code AND is_deleted = false"
            ),
            {"firm": firm_id, "code": _CODE},
        ).scalar()
        if account_id is None:
            account_id = uuid4()
            bind.execute(
                sa.text(
                    "INSERT INTO ledger_accounts (id, firm_id, account_group_id, "
                    "code, name, account_type, is_balance_sheet, is_profit_loss, "
                    "requires_cost_center, requires_profit_center, is_active, "
                    "is_deleted, version, created_at, updated_at) "
                    "VALUES (:id, :firm, :group, :code, :name, 'EQUITY', true, "
                    "false, false, false, true, false, 1, now(), now())"
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
    """Unmap the purpose and leave the account and group in place.

    Either may have postings against it by then, and dropping an account that
    has been posted to would take its history with it.
    """
    if not _has("firm_control_accounts"):
        return
    op.get_bind().execute(
        sa.text("DELETE FROM firm_control_accounts WHERE purpose = :purpose"),
        {"purpose": _PURPOSE},
    )
