"""A self-invoice is numbered ``RSI`` and a rate contract ``RTC`` (D-BUY-58, 57).

Two pairs of documents shared a default prefix, as the requisition and the
purchase return did (``20261005_0327``):

* the **reverse-charge self-invoice** and the **sales invoice**, both ``SI``;
* the supplier **rate contract** and the customer **receipt**, both ``RC``.

A number is issued by stepping over numbers of the same document type and
over journal references. A self-invoice and a rate contract post no journal
under their number, so the next sales invoice or receipt took the same one:
``SI-26-27-000002`` twice, two GST documents under one serial number.

The services now create the rules with ``RSI`` and ``RTC``. A rule is created
on a firm's first such document, so a store that has raised one already holds
the old prefix; this moves those. **Only a rule still at the default**: its
own code, and exactly the old prefix. A firm that chose another keeps it. The
sales invoice and the receipt keep theirs. Numbers already issued stay as
issued, and the sequence carries on under the new prefix.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a second run
finds no rule at the old prefix.

Revision ID: 20261005_0328
Revises: 20261005_0327
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0328"
down_revision: str | Sequence[str] | None = "20261005_0327"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_numbering_rules"
#: (the rule's code, the prefix it shared, the prefix of its own).
_MOVES = (
    ("RCM_SELF_INVOICE_DEFAULT", "SI", "RSI"),
    ("RATE_CONTRACT_DEFAULT", "RC", "RTC"),
)


def _move(*, back: bool) -> None:
    """Move each rule's prefix where the store keeps such rules."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    for rule, shared, own in _MOVES:
        old, new = (own, shared) if back else (shared, own)
        bind.execute(
            sa.text(
                f"UPDATE {_TABLE} SET prefix = :new "  # noqa: S608
                "WHERE code = :rule AND prefix = :old"
            ),
            {"new": new, "old": old, "rule": rule},
        )


def upgrade() -> None:
    """Give the self-invoice and the rate contract prefixes of their own."""
    _move(back=False)


def downgrade() -> None:
    """Put the shared prefix back on a rule still at the new default."""
    _move(back=True)
