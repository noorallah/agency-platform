"""An opening balance typed on the customer is given a bill (D-MST-13).

``customer_opening_bills.covers_master_balance`` -- true for the one row that
stands for ``customers.opening_balance``. The single figure posted its journal
and raised what the customer owes, and was then on no receipt list, collection
sheet or ageing report, because each of those is a list of bills. From this
revision the figure is given one bill a receipt can be allocated to; the bill
posts nothing and moves no balance of its own.

The backfill gives that bill to every live customer who already carries a
positive opening balance with its journal posted and has no standing opening
bill. It is dated the day the balance was entered and falls due on the
customer's terms. It writes no journal and no receivable row -- both exist --
so no balance moves. A receipt taken on account against such a customer
before this revision stays on account: the bill reads its full amount and the
receipt reads as unapplied, which is how the ageing already shows it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a second run
finds every such customer already has its bill.

Revision ID: 20261005_0333
Revises: 20261005_0329
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0333"
down_revision: str | Sequence[str] | None = "20261005_0329"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "customer_opening_bills"
_COLUMN = "covers_master_balance"
_NARRATION = "Opening balance entered on the customer."


def upgrade() -> None:
    """Add the column, then give each standing opening balance its bill."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not inspector.has_table("customers") or not inspector.has_table(
        "customer_receivable_transactions"
    ):
        return
    owed = bind.execute(
        sa.text(
            "SELECT c.id, c.firm_id, c.opening_balance, c.payment_terms_days, "
            "t.transaction_date, t.journal_entry_id "
            "FROM customers c "
            "JOIN customer_receivable_transactions t ON t.customer_id = c.id "
            "WHERE c.is_deleted = false AND c.opening_balance > 0 "
            "AND t.transaction_type = 'OPENING_BALANCE' "
            "AND t.is_deleted = false AND t.journal_entry_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM customer_opening_bills b "
            "WHERE b.customer_id = c.id AND b.status = 'POSTED' "
            "AND b.is_deleted = false) "
            "ORDER BY c.firm_id, c.code"
        )
    ).all()
    if not owed:
        return
    issued = {
        firm_id: int(count)
        for firm_id, count in bind.execute(
            sa.text(
                f"SELECT firm_id, COUNT(*) FROM {_TABLE} GROUP BY firm_id"
            )  # noqa: S608
        ).all()
    }
    bills = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    now = datetime.now(UTC)
    seen: set[object] = set()
    for customer_id, firm_id, balance, terms, entered, journal_id in owed:
        if customer_id in seen:
            continue
        seen.add(customer_id)
        issued[firm_id] = issued.get(firm_id, 0) + 1
        bind.execute(
            bills.insert().values(
                id=uuid4(),
                firm_id=firm_id,
                customer_id=customer_id,
                bill_number=f"OBC-{issued[firm_id]:05d}",
                bill_date=entered,
                due_date=entered + timedelta(days=int(terms or 0)),
                posting_date=entered,
                amount=balance,
                narration=_NARRATION,
                status="POSTED",
                journal_entry_id=journal_id,
                covers_master_balance=True,
                version=1,
                is_deleted=False,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    """Remove the bills this revision made, then the column."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        return
    # Only those nothing has been received against: a receipt allocated to
    # one holds it by foreign key, and that bill stays as an ordinary one.
    bind.execute(
        sa.text(
            f"DELETE FROM {_TABLE} WHERE {_COLUMN} = true "  # noqa: S608
            "AND NOT EXISTS (SELECT 1 FROM settlement_allocations a "
            f"WHERE a.customer_opening_bill_id = {_TABLE}.id)"
        )
    )
    op.drop_column(_TABLE, _COLUMN)
