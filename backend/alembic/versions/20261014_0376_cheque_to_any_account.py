"""The firm's own cheque may pay any account (backlog 150, row F13, COL-11).

``post_dated_cheques`` held the firm's cheque to a supplier and nothing else.
It now also holds one to a customer (a refund), to an expense account, and to
any other ledger account, and says which bank account it is drawn on and the
name written on it:

* ``paid_to_kind`` -- SUPPLIER, CUSTOMER, EXPENSE or ACCOUNT; NULL on a
  customer's cheque. Every cheque the firm has already issued is to a
  supplier, and is marked so here, only where the column is still empty.
* ``paid_account_id`` -- the expense or other ledger account paid.
* ``bank_account_id`` -- the bank account drawn on; NULL reads as the firm's
  Bank account, which is what every earlier cheque was presented through.
* ``payee_name`` -- the name on the cheque.
* ``expense_id``, ``journal_entry_id``, ``reversal_journal_entry_id`` -- what
  the cheque became when presented, where that is not a settlement.

The party check is replaced: the firm's cheque names exactly one of a
supplier, a customer or a ledger account.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column
and key is added only where missing, and the check is swapped only where it
does not already speak of ``paid_account_id``. The check is found by what it
says, not by its name: a firm store built by ``Base.metadata.create_all``
carries it under the naming convention's prefixed and shortened name
(``CK_post_dated_cheques_CK_post_dated_cheques_party_match_0f1f``), and a
swap that looked for the migration's name left that one in place and then
collided with it.

Revision ID: 20261014_0376
Revises: 20261013_0375
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261014_0376"
down_revision: str | Sequence[str] | None = "20261013_0375"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "post_dated_cheques"
_CONSTRAINT = "CK_post_dated_cheques_party_matches_direction"

_OLD = (
    "(direction = 'RECEIPT' AND customer_id IS NOT NULL AND vendor_id IS "
    "NULL) OR (direction = 'PAYMENT' AND vendor_id IS NOT NULL AND "
    "customer_id IS NULL)"
)
_NEW = (
    "(direction = 'RECEIPT' AND customer_id IS NOT NULL AND vendor_id IS NULL "
    "AND paid_account_id IS NULL) OR (direction = 'PAYMENT' AND ("
    "(vendor_id IS NOT NULL AND customer_id IS NULL AND paid_account_id IS NULL) "
    "OR (customer_id IS NOT NULL AND vendor_id IS NULL AND paid_account_id IS "
    "NULL) OR (paid_account_id IS NOT NULL AND vendor_id IS NULL AND "
    "customer_id IS NULL)))"
)

#: column -> (type, the table its key points at, or None for no key).
_COLUMNS: dict[str, tuple[sa.types.TypeEngine[object], str | None]] = {
    "paid_to_kind": (sa.String(length=20), None),
    "paid_account_id": (UUIDType(), "ledger_accounts"),
    "bank_account_id": (UUIDType(), "ledger_accounts"),
    "payee_name": (sa.String(length=200), None),
    "expense_id": (UUIDType(), "expenses"),
    "journal_entry_id": (UUIDType(), "journal_entries"),
    "reversal_journal_entry_id": (UUIDType(), "journal_entries"),
}


def _swap_check(condition: str, *, wanted: bool) -> None:
    """Replace the party check, unless it already reads the wanted way.

    ``wanted`` says whether the check to end with speaks of the paid account.
    """
    inspector = sa.inspect(op.get_bind())
    for check in inspector.get_check_constraints(_TABLE):
        text = check.get("sqltext") or ""
        if "direction" not in text or "vendor_id" not in text:
            continue
        if ("paid_account_id" in text) == wanted:
            return
        # `op.f`: the name is the one in the database, taken as it is.
        op.drop_constraint(op.f(check["name"]), _TABLE, type_="check")
    op.create_check_constraint(op.f(_CONSTRAINT), _TABLE, condition)


def upgrade() -> None:
    """Add what a cheque to any account needs, and widen the party check."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    keys = {key["name"] for key in inspector.get_foreign_keys(_TABLE)}
    for name, (kind, target) in _COLUMNS.items():
        if name not in columns:
            op.add_column(_TABLE, sa.Column(name, kind, nullable=True))
        key = f"FK_{_TABLE}_{name}"
        if target is not None and key not in keys and inspector.has_table(target):
            op.create_foreign_key(
                key, _TABLE, target, [name], ["id"], ondelete="RESTRICT"
            )
    # Only rows still unmarked: a replay cannot rewrite a cheque written since.
    op.execute(
        sa.text(
            "UPDATE post_dated_cheques SET paid_to_kind = 'SUPPLIER' "
            "WHERE direction = 'PAYMENT' AND paid_to_kind IS NULL "
            "AND vendor_id IS NOT NULL"
        )
    )
    _swap_check(_NEW, wanted=True)


def downgrade() -> None:
    """Narrow the check and drop the columns.

    A cheque to anything but a supplier breaks the old check and is the
    firm's record of money paid, so it is not deleted here: the downgrade
    fails on one, and somebody decides what becomes of it.
    """
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    _swap_check(_OLD, wanted=False)
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    keys = {key["name"] for key in inspector.get_foreign_keys(_TABLE)}
    for name, (_, target) in _COLUMNS.items():
        key = f"FK_{_TABLE}_{name}"
        if target is not None and key in keys:
            op.drop_constraint(key, _TABLE, type_="foreignkey")
        if name in columns:
            op.drop_column(_TABLE, name)
