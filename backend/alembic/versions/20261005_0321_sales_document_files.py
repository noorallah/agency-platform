"""Uploaded files on the five sales documents (SG-6, backlog 87 #6).

``document_files`` (PG-4, ``20261005_0306``) named its document by one of two
nullable keys -- the purchase bill or the goods receipt -- and a check that
exactly one is set. Sales joins the same table rather than a second one: a
nullable key each for the quotation, the order, the delivery note, the invoice
and the return, an index on each, and the check widened to "exactly one of the
seven".

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a store with no
``document_files`` (a pruned platform) is skipped, each column, key and index is
made only where it is missing, and the check is replaced only while it still
reads as the two-parent one.

Revision ID: 20261005_0321
Revises: 20261005_0320
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0321"
down_revision: str | Sequence[str] | None = "20261005_0320"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_files"
_CHECK = "CK_document_files_one_parent"
#: The new key, the table it points at, and the index over it.
_SALES_PARENTS: tuple[tuple[str, str, str], ...] = (
    ("sales_quotation_id", "sales_quotations", "IX_document_files_sales_quotation"),
    ("sales_order_id", "sales_orders", "IX_document_files_sales_order"),
    ("delivery_note_id", "delivery_notes", "IX_document_files_delivery_note"),
    ("sales_invoice_id", "sales_invoices", "IX_document_files_sales_invoice"),
    ("sales_return_id", "sales_returns", "IX_document_files_sales_return"),
)
_TWO_PARENTS = "(purchase_invoice_id IS NULL) <> (goods_receipt_id IS NULL)"
_SEVEN_PARENTS = (
    "("
    + " + ".join(
        f"CASE WHEN {column} IS NULL THEN 0 ELSE 1 END"
        for column in (
            "purchase_invoice_id",
            "goods_receipt_id",
            *(column for column, _, _ in _SALES_PARENTS),
        )
    )
    + ") = 1"
)


def _replace_check(inspector: sa.Inspector, *, wanted: str, widened: bool) -> None:
    """Hold the table to ``wanted``, whatever its parent check is called today.

    The check is found by what it says, not by its name. A store built by
    ``20261005_0306`` carries it as
    ``CK_document_files_CK_document_files_one_parent`` -- the metadata's
    naming convention was applied on top of a name that already had the
    prefix -- while a store built by ``Base.metadata.create_all`` carries
    ``CK_document_files_one_parent``.
    ``op.f`` passes each name through as it is, and the replacement takes the
    name the model declares.

    Args:
        inspector: The store being migrated.
        wanted: The check the table should end up with.
        widened: Whether ``wanted`` is the seven-parent check (it names
            ``sales_invoice_id``) or the two-parent one (it does not).

    """
    done = False
    for check in inspector.get_check_constraints(_TABLE):
        name = check.get("name")
        told = str(check.get("sqltext") or "")
        if name is None or "goods_receipt_id" not in told:
            continue
        if ("sales_invoice_id" in told) == widened:
            done = True
            continue
        op.drop_constraint(op.f(name), _TABLE, type_="check")
    if not done:
        op.create_check_constraint(op.f(_CHECK), _TABLE, wanted)


def upgrade() -> None:
    """Let a file name one of the five sales documents as its parent."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    keys = {key["name"] for key in inspector.get_foreign_keys(_TABLE)}
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    for column, target, index in _SALES_PARENTS:
        if column not in columns:
            op.add_column(_TABLE, sa.Column(column, UUIDType(), nullable=True))
        key = f"FK_{_TABLE}_{column}"
        if key not in keys and inspector.has_table(target):
            op.create_foreign_key(
                key, _TABLE, target, [column], ["id"], ondelete="CASCADE"
            )
        if index not in indexes:
            op.create_index(index, _TABLE, [column])
    _replace_check(inspector, wanted=_SEVEN_PARENTS, widened=True)


def downgrade() -> None:
    """Take the sales keys off again, and the files that hang on them.

    A file kept with a sales document cannot satisfy the two-parent check, so
    those rows go first; their bytes follow by the content table's cascade.
    """
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    present = [column for column, _, _ in _SALES_PARENTS if column in columns]
    if not present:
        return
    op.execute(
        sa.text(
            f"DELETE FROM {_TABLE} WHERE "
            + " OR ".join(f"{column} IS NOT NULL" for column in present)
        )
    )
    _replace_check(inspector, wanted=_TWO_PARENTS, widened=False)
    keys = {key["name"] for key in inspector.get_foreign_keys(_TABLE)}
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    for column, _, index in _SALES_PARENTS:
        if column not in columns:
            continue
        if index in indexes:
            op.drop_index(index, table_name=_TABLE)
        key = f"FK_{_TABLE}_{column}"
        if key in keys:
            op.drop_constraint(key, _TABLE, type_="foreignkey")
        op.drop_column(_TABLE, column)
