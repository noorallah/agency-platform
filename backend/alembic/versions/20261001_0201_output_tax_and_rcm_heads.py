"""An output-tax account per GST head, and reverse-charge payable (63.3, 68.8).

Every sales document credited one `OUTPUT_TAX` account, while purchases
already split input tax by head (D-CMP-20), so the ledger could not say how
much CGST the firm owed. Three purposes join `OUTPUT_TAX`: `OUTPUT_TAX_IGST`
(2210), `OUTPUT_TAX_CGST` (2220) and `OUTPUT_TAX_SGST` (2230); 2200 stays for
cess and keeps every balance posted before the split -- history is left as
posted, never moved.

Reverse charge on inward supplies is owed through accounts of its own --
`RCM_PAYABLE` (2250, cess and the rest), `RCM_PAYABLE_IGST` (2260),
`RCM_PAYABLE_CGST` (2270), `RCM_PAYABLE_SGST` (2280) -- because it is paid in
cash only and credit may never be set against it.

Seeded for every firm that has a chart, idempotent, the way the input heads
were in `20260924_0156`: an existing mapping is never overwritten, an existing
account with the code is reused. Firm-owned, so run it through
``scripts/migrate_all_stores.py``.

Revision ID: 20261001_0201
Revises: 20261001_0200
Create Date: 2026-10-01

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0201"
down_revision: str | Sequence[str] | None = "20261001_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCOUNTS = (
    ("OUTPUT_TAX_IGST", "2210", "Output IGST", "LIABILITY", "CL"),
    ("OUTPUT_TAX_CGST", "2220", "Output CGST", "LIABILITY", "CL"),
    ("OUTPUT_TAX_SGST", "2230", "Output SGST", "LIABILITY", "CL"),
    ("RCM_PAYABLE", "2250", "Reverse Charge Payable", "LIABILITY", "CL"),
    ("RCM_PAYABLE_IGST", "2260", "Reverse Charge IGST Payable", "LIABILITY", "CL"),
    ("RCM_PAYABLE_CGST", "2270", "Reverse Charge CGST Payable", "LIABILITY", "CL"),
    ("RCM_PAYABLE_SGST", "2280", "Reverse Charge SGST Payable", "LIABILITY", "CL"),
)


def _seed_control_accounts(inspector: sa.Inspector) -> None:
    """Give every firm the output heads and the reverse-charge accounts.

    The same shape as `20260924_0156`: a purpose with no mapping is an error
    naming the purpose, never a fallback, so an unmapped firm could not
    approve an invoice once the split posting shipped.
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
    """Map the seven purposes for every firm that lacks them."""
    _seed_control_accounts(sa.inspect(op.get_bind()))


def downgrade() -> None:
    """Drop the seven mappings; the accounts stay, since journals may name them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("firm_control_accounts"):
        return
    op.get_bind().execute(
        sa.text(
            "DELETE FROM firm_control_accounts WHERE purpose IN "
            "('OUTPUT_TAX_IGST', 'OUTPUT_TAX_CGST', 'OUTPUT_TAX_SGST', "
            "'RCM_PAYABLE', 'RCM_PAYABLE_IGST', 'RCM_PAYABLE_CGST', "
            "'RCM_PAYABLE_SGST')"
        )
    )
