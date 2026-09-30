"""Record a TAN, and give every firm somewhere to book TDS (backlog 53.1).

Some firms already hold a Tax Deduction Account Number and deduct TDS -- on
purchases from a principal (194Q), rent, professional fees, transporters --
and had nowhere to write the TAN and no account for the tax. This adds:

* ``firms.tan_number`` (platform) and ``customers.tan_number`` (firm stores):
  a customer's TAN is what appears on the TDS certificate it issues the firm.
* *TDS Payable* (``2700``, current liabilities) and *TDS Receivable*
  (``1400``, current assets), mapped to the ``TDS_PAYABLE`` and
  ``TDS_RECEIVABLE`` control purposes, for every firm whose books are open --
  new firms get them from ``opening_setup``. Only where missing, never
  overwriting: a firm already mapping a purpose keeps its account, and an
  account already holding one of these codes is the one mapped.

Idempotent throughout: firm stores are partly built by ``create_all``.
Firm-owned parts run per store: ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260930_0166"
down_revision: str | Sequence[str] | None = "20260930_0165"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (purpose, code, name, account type, group code)
_ACCOUNTS = (
    ("TDS_PAYABLE", "2700", "TDS Payable", "LIABILITY", "CL"),
    ("TDS_RECEIVABLE", "1400", "TDS Receivable", "ASSET", "CA"),
)


def _add_tan(inspector: sa.Inspector, table: str) -> None:
    """Add ``tan_number`` to one table where it exists and lacks it."""
    if not inspector.has_table(table):
        return
    columns = {column["name"] for column in inspector.get_columns(table)}
    if "tan_number" not in columns:
        op.add_column(table, sa.Column("tan_number", sa.String(10), nullable=True))


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
    group_id = bind.execute(
        sa.text(
            "SELECT id FROM account_groups WHERE firm_id = :firm "
            "AND account_type = :kind AND is_deleted = false "
            "ORDER BY code LIMIT 1"
        ),
        {"firm": firm_id, "kind": kind},
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
    """Give every firm with open books the two TDS accounts and mappings."""
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
        for purpose, code, name, kind, group_code in _ACCOUNTS:
            mapped = bind.execute(
                sa.text(
                    "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                    "AND purpose = :purpose AND is_deleted = false"
                ),
                {"firm": firm_id, "purpose": purpose},
            ).scalar()
            if mapped is not None:
                continue
            account_id = bind.execute(
                sa.text(
                    "SELECT id FROM ledger_accounts WHERE firm_id = :firm "
                    "AND code = :code AND is_deleted = false"
                ),
                {"firm": firm_id, "code": code},
            ).scalar()
            if account_id is None:
                group_id = _group_for(
                    bind,
                    firm_id,
                    code=group_code,
                    kind=kind,
                    name=(
                        "Current Liabilities"
                        if kind == "LIABILITY"
                        else "Current Assets"
                    ),
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
    """Add the TAN columns and the TDS accounts where each belongs."""
    inspector = sa.inspect(op.get_bind())
    _add_tan(inspector, "firms")
    _add_tan(inspector, "customers")
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the TAN columns and the two mappings; leave the accounts.

    The accounts may carry postings by then, and deleting accounts with
    journal lines against them would be refused or would orphan the lines.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose IN ('TDS_PAYABLE', 'TDS_RECEIVABLE')"
            )
        )
    for table in ("firms", "customers"):
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "tan_number" in columns:
            op.drop_column(table, "tan_number")
