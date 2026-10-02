"""Stock issued for internal use, to staff, or for display (STK-3, A61).

Three control purposes for every firm whose books are open -- new firms get
them from ``opening_setup``: ``INTERNAL_USE`` on *Stock Used in Business*
(6900), ``STAFF_WELFARE`` on *Staff Welfare* (6910) and ``SAMPLES_AND_DISPLAY``
on *Samples and Display* (6920), all indirect expenses. A write-off for one of
the three new reasons posts there instead of to the inventory adjustment
account. Only where missing, never overwriting: a purpose already mapped keeps
its account, and an account already holding the code is the one mapped --
unless it is of another type, when the purpose is left for the firm to map
and the readiness check says so. The shape of ``20261001_0191``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0243
Revises: 20261003_0242
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0243"
down_revision: str | Sequence[str] | None = "20261003_0242"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    (
        "INTERNAL_USE",
        "6900",
        "Stock Used in Business",
        "EXPENSE",
        "IEXP",
        "Indirect Expenses",
    ),
    ("STAFF_WELFARE", "6910", "Staff Welfare", "EXPENSE", "IEXP", "Indirect Expenses"),
    (
        "SAMPLES_AND_DISPLAY",
        "6920",
        "Samples and Display",
        "EXPENSE",
        "IEXP",
        "Indirect Expenses",
    ),
)


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
    """Map the three issue purposes for every firm whose books are open."""
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
                # post an issue to whatever that is. Left for the firm.
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
    """Map the three purposes where the books are open."""
    _seed_accounts(sa.inspect(op.get_bind()))


def downgrade() -> None:
    """Drop the three mappings; keep the accounts, which may carry postings."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose IN "
                "('INTERNAL_USE', 'STAFF_WELFARE', 'SAMPLES_AND_DISPLAY')"
            )
        )
