"""TCS charged by a supplier, recorded on the bill (PG-6, backlog 86 #9).

* ``purchase_invoices.tcs_rate_percent`` (NULL) and ``tcs_amount`` (0): the
  TCS a supplier charged under 206C(1H), outside GST's taxable value. The
  supplier is owed ``grand_total + tcs_amount - tds_amount``.
* ``TCS_RECEIVABLE`` mapped to *TCS Receivable* (1430, current assets) for
  every firm whose books are open, the shape of ``20261003_0290``: only where
  missing, never overwriting.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where its table exists and it does not.

Revision ID: 20261005_0308
Revises: 20261005_0307
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0308"
down_revision: str | Sequence[str] | None = "20261005_0307"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BILLS = "purchase_invoices"

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    (
        "TCS_RECEIVABLE",
        "1430",
        "TCS Receivable",
        "ASSET",
        "CA",
        "Current Assets",
    ),
)


def _bill_columns(inspector: sa.Inspector) -> None:
    """Add the TCS rate and amount to the bill, where missing."""
    if not inspector.has_table(_BILLS):
        return
    present = {column["name"] for column in inspector.get_columns(_BILLS)}
    if "tcs_rate_percent" not in present:
        op.add_column(
            _BILLS, sa.Column("tcs_rate_percent", sa.Numeric(9, 4), nullable=True)
        )
    if "tcs_amount" not in present:
        op.add_column(
            _BILLS,
            sa.Column(
                "tcs_amount",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0",
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
    """Map the TCS receivable for every firm whose books are open."""
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
                # post TCS to whatever that is. Left for the firm.
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
                        ":kind, true, false, false, false, "
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
    """Add the bill's TCS and map the receivable."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no bills.
    if not inspector.has_table(_BILLS):
        return
    _bill_columns(inspector)
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the bill's TCS and the mapping; keep the account."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose = 'TCS_RECEIVABLE'"
            )
        )
    if inspector.has_table(_BILLS):
        present = {column["name"] for column in inspector.get_columns(_BILLS)}
        for name in ("tcs_amount", "tcs_rate_percent"):
            if name in present:
                op.drop_column(_BILLS, name)
