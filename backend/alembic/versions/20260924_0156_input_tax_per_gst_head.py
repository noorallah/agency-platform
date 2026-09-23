"""An input-tax account per GST head (D-CMP-20).

Purchase input tax posted to the ledger as one total, so GSTR-3B's input
credit -- claimed per head, IGST against IGST and CGST and SGST each against
their own -- could not be derived from the books. Three control-account
purposes join `INPUT_TAX`: `INPUT_TAX_IGST` (1310), `INPUT_TAX_CGST` (1320)
and `INPUT_TAX_SGST` (1330); 1300 stays for cess and any other tax system.

Seeded for every firm that has a chart, idempotent, the way TCS and loyalty
were. Firm-owned, so run it through ``scripts/migrate_all_stores.py``.

Revision ID: 20260924_0156
Revises: 20260924_0155
Create Date: 2026-09-24

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0156"
down_revision: str | Sequence[str] | None = "20260924_0155"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCOUNTS = (
    ("INPUT_TAX_IGST", "1310", "Input IGST", "ASSET", "CA"),
    ("INPUT_TAX_CGST", "1320", "Input CGST", "ASSET", "CA"),
    ("INPUT_TAX_SGST", "1330", "Input SGST", "ASSET", "CA"),
)


def _seed_control_accounts(inspector: sa.Inspector) -> None:
    """Give every firm an account per GST head.

    The same shape as `20260903_0120` and `20260903_0126`: a purpose with no
    mapping is an error naming the purpose, never a fallback, so an unmapped
    firm could not approve a bill once the split posting shipped.
    """
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
        for purpose, code, name, account_type, group_code in _ACCOUNTS:
            mapped = bind.execute(
                sa.text(
                    "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                    "AND purpose = :purpose AND is_deleted = false"
                ),
                {"firm": firm_id, "purpose": purpose},
            ).scalar()
            if mapped is not None:
                continue
            group_id = bind.execute(
                sa.text(
                    "SELECT id FROM account_groups WHERE firm_id = :firm "
                    "AND account_type = :kind AND is_deleted = false "
                    "ORDER BY code LIMIT 1"
                ),
                {"firm": firm_id, "kind": account_type},
            ).scalar()
            if group_id is None:
                group_id = uuid4()
                bind.execute(
                    sa.text(
                        "INSERT INTO account_groups (id, firm_id, code, name, "
                        "account_type, is_active, is_deleted, version, "
                        "created_at, updated_at) VALUES (:id, :firm, :code, "
                        ":name, :kind, true, false, 1, now(), now())"
                    ),
                    {
                        "id": group_id,
                        "firm": firm_id,
                        "code": group_code,
                        "name": name,
                        "kind": account_type,
                    },
                )
            account_id = bind.execute(
                sa.text(
                    "SELECT id FROM ledger_accounts WHERE firm_id = :firm "
                    "AND code = :code AND is_deleted = false"
                ),
                {"firm": firm_id, "code": code},
            ).scalar()
            if account_id is None:
                account_id = uuid4()
                bind.execute(
                    sa.text(
                        "INSERT INTO ledger_accounts (id, firm_id, "
                        "account_group_id, code, name, account_type, "
                        "is_balance_sheet, is_profit_loss, "
                        "requires_cost_center, requires_profit_center, "
                        "is_active, is_deleted, version, created_at, "
                        "updated_at) VALUES (:id, :firm, :group, :code, :name, "
                        ":kind, true, false, false, false, "
                        "true, false, 1, now(), now())"
                    ),
                    {
                        "id": account_id,
                        "firm": firm_id,
                        "group": group_id,
                        "code": code,
                        "name": name,
                        "kind": account_type,
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
    """Map the three heads for every firm that lacks them."""
    _seed_control_accounts(sa.inspect(op.get_bind()))


def downgrade() -> None:
    """Drop the three mappings; the accounts stay, since journals may name them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("firm_control_accounts"):
        return
    op.get_bind().execute(
        sa.text(
            "DELETE FROM firm_control_accounts WHERE purpose IN "
            "('INPUT_TAX_IGST', 'INPUT_TAX_CGST', 'INPUT_TAX_SGST')"
        )
    )
