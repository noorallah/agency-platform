"""Mark the support account, and what it did (backlog 29s, part c).

* ``users.is_support_account`` -- the real marker for the one account
  ``create-support-admin`` makes. Until now it was recognised by
  ``department = 'Support'`` beside an ``ALL_FIRMS`` designation, a stand-in a
  customer's own Support department could resemble. ``users`` is a platform
  table, so this half runs only in a store that has it.
* ``audit_logs.by_support`` -- set on every row written while the support
  account was signed in, so the customer can list what the vendor did.
  ``audit_logs`` lives in **every** store, so this half runs wherever the
  table is: run ``scripts/migrate_all_stores.py``.

Both columns are NOT NULL with a ``false`` server default, so every existing
row reads as not-support. Adding a column is DDL, not an ``UPDATE``, so the
append-only trigger on ``audit_logs`` (and the function it calls) is neither
fired nor touched; nothing here back-fills old audit rows, which stay
exactly as they were written.

The backfill marks only accounts still unmarked whose department reads
``Support`` and which hold a live ``ALL_FIRMS`` designation -- what the
command created before the column existed -- so a replay changes nothing.

Revision ID: 20261017_0396
Revises: 20261017_0395
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261017_0396"
down_revision: str | Sequence[str] | None = "20261017_0395"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table: str) -> bool:
    """Say whether ``table`` exists in this store."""
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    """Say whether ``table`` exists and already holds ``column``."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return any(row["name"] == column for row in inspector.get_columns(table))


def _add_flag(table: str, column: str) -> None:
    """Add a NOT NULL boolean defaulting to false, where the table lacks it."""
    if _has_table(table) and not _has_column(table, column):
        op.add_column(
            table,
            sa.Column(
                column,
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )


def _backfill_support_account() -> None:
    """Mark the account the command made before the column existed."""
    if not _has_table("platform_admins"):
        return
    op.get_bind().execute(
        sa.text(
            "UPDATE users SET is_support_account = true "
            "WHERE is_support_account = false "
            "AND is_deleted = false "
            "AND department = 'Support' "
            "AND id IN (SELECT user_id FROM platform_admins "
            "WHERE scope = 'ALL_FIRMS' AND is_deleted = false)"
        )
    )


def upgrade() -> None:
    """Add both columns where their tables are, and mark the support account."""
    if _has_table("users"):
        _add_flag("users", "is_support_account")
        _backfill_support_account()
    _add_flag("audit_logs", "by_support")


def downgrade() -> None:
    """Drop both columns; the account is recognised by nothing again."""
    if _has_column("audit_logs", "by_support"):
        op.drop_column("audit_logs", "by_support")
    if _has_column("users", "is_support_account"):
        op.drop_column("users", "is_support_account")
