"""Free goods for customers (BUY-1, decision A111).

* ``products.free_issue_only`` -- promotional stock, never sold at a price.
* ``goods_receipt_lines.scheme_name`` -- the scheme a free line came under.
* ``inventory_transactions.customer_id`` -- who free goods or a sample went to.
* ``PROMOTIONAL_EXPENSE`` mapped on *Promotional Expenses* (6940) for every
  firm whose books are open, only where missing -- the shape of
  ``20261003_0243``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0275
Revises: 20261003_0274
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0275"
down_revision: str | Sequence[str] | None = "20261003_0274"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCOUNTS = (
    (
        "PROMOTIONAL_EXPENSE",
        "6940",
        "Promotional Expenses",
        "EXPENSE",
        "IEXP",
        "Indirect Expenses",
    ),
)

_COLUMNS = (
    ("products", "free_issue_only"),
    ("goods_receipt_lines", "scheme_name"),
    ("inventory_transactions", "customer_id"),
)


def _add_columns(inspector: sa.Inspector) -> None:
    """Add the three columns where their tables lack them."""
    from app.core.database.types import UUIDType

    kinds = {
        "free_issue_only": lambda: sa.Column(
            "free_issue_only", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        "scheme_name": lambda: sa.Column("scheme_name", sa.String(120)),
        "customer_id": lambda: sa.Column("customer_id", UUIDType()),
    }
    for table, column in _COLUMNS:
        if not inspector.has_table(table):
            continue
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, kinds[column]())


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
    """Map the promotional purpose for every firm whose books are open."""
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
    """Add the columns and map the promotional purpose."""
    inspector = sa.inspect(op.get_bind())
    _add_columns(inspector)
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the columns and the mapping; keep the account."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if inspector.has_table(table) and column in {
            c["name"] for c in inspector.get_columns(table)
        }:
            op.drop_column(table, column)
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose = 'PROMOTIONAL_EXPENSE'"
            )
        )
