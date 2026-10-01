"""Input credit eligibility on products and bill lines; its account (78 row 1).

* ``products.itc_eligibility`` and ``purchase_invoice_lines.itc_eligibility``:
  ``ELIGIBLE`` (every row already written, which is how each was posted),
  ``BLOCKED`` (s.17(5)) or ``INELIGIBLE``.
* ``INELIGIBLE_INPUT_TAX`` mapped to *Input Tax Not Claimable* (5450, direct
  expenses) for every firm whose books are open, creating the account where
  the firm has none and leaving the code alone where the firm used it for
  something that is not an expense.

No permission codes: a product's eligibility is written on
``PRODUCT_TAX_MANAGE``, like its tax group.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261002_0211
Revises: 20261002_0210
Create Date: 2026-10-02

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0211"
down_revision: str | Sequence[str] | None = "20261002_0210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSE = "INELIGIBLE_INPUT_TAX"
_CODE = "5450"
_NAME = "Input Tax Not Claimable"
_GROUP_CODE = "EXP"
_GROUP_NAME = "Direct Expenses"


def _add_column(inspector: sa.Inspector, table: str) -> None:
    """Add ``itc_eligibility`` to a table that holds none."""
    if not inspector.has_table(table):
        return
    if any(c["name"] == "itc_eligibility" for c in inspector.get_columns(table)):
        return
    op.add_column(
        table,
        sa.Column(
            "itc_eligibility",
            sa.String(length=20),
            nullable=False,
            server_default="ELIGIBLE",
        ),
    )


def _group_for(bind: sa.Connection, firm_id: object) -> object:
    """Return the firm's direct-expense group, creating it only if it has none."""
    group_id = bind.execute(
        sa.text(
            "SELECT id FROM account_groups WHERE firm_id = :firm "
            "AND code = :code AND is_deleted = false"
        ),
        {"firm": firm_id, "code": _GROUP_CODE},
    ).scalar()
    if group_id is not None:
        return group_id
    group_id = uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO account_groups (id, firm_id, code, name, "
            "account_type, is_active, is_deleted, version, "
            "created_at, updated_at) VALUES (:id, :firm, :code, "
            ":name, 'EXPENSE', true, false, 1, now(), now())"
        ),
        {"id": group_id, "firm": firm_id, "code": _GROUP_CODE, "name": _GROUP_NAME},
    )
    return group_id


def _seed_account(inspector: sa.Inspector) -> None:
    """Map the purpose for every firm whose books are open."""
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
        mapped = bind.execute(
            sa.text(
                "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                "AND purpose = :purpose AND is_deleted = false"
            ),
            {"firm": firm_id, "purpose": _PURPOSE},
        ).scalar()
        if mapped is not None:
            continue
        found = bind.execute(
            sa.text(
                "SELECT id, account_type FROM ledger_accounts "
                "WHERE firm_id = :firm AND code = :code AND is_deleted = false"
            ),
            {"firm": firm_id, "code": _CODE},
        ).first()
        if found is not None and found[1] != "EXPENSE":
            # The firm used the code for something else; mapping it would post
            # blocked tax to whatever that is. Left for the firm to map.
            continue
        account_id = None if found is None else found[0]
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
                    "'EXPENSE', false, true, false, false, "
                    "true, false, 1, now(), now())"
                ),
                {
                    "id": account_id,
                    "firm": firm_id,
                    "group": _group_for(bind, firm_id),
                    "code": _CODE,
                    "name": _NAME,
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
                "purpose": _PURPOSE,
                "account": account_id,
            },
        )


def upgrade() -> None:
    """Add the columns and map the account where this store holds them."""
    inspector = sa.inspect(op.get_bind())
    _add_column(inspector, "products")
    _add_column(inspector, "purchase_invoice_lines")
    _seed_account(inspector)


def downgrade() -> None:
    """Drop the columns and the mapping; the account stays with its history."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose = :purpose"
            ).bindparams(purpose=_PURPOSE)
        )
    for table in ("purchase_invoice_lines", "products"):
        if inspector.has_table(table) and any(
            c["name"] == "itc_eligibility" for c in inspector.get_columns(table)
        ):
            op.drop_column(table, "itc_eligibility")
