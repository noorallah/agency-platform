"""Supplier credit set against an opening bill (BUY-17, decision A52).

`supplier_credit_applications` names the bill a credit clears: a purchase
invoice, as before, or now a supplier's opening bill brought over from the old
software. `purchase_invoice_id` becomes nullable, `vendor_opening_bill_id` is
added, and a check holds exactly one of the two. Existing rows all name a
purchase invoice, so they satisfy it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0239
Revises: 20261003_0238
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0239"
down_revision: str | Sequence[str] | None = "20261003_0238"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "supplier_credit_applications"
_COLUMN = "vendor_opening_bill_id"
_INDEX = "IX_supplier_credit_applications_opening_bill"
_CHECK = "CK_supplier_credit_applications_one_bill"


def _drop_check(inspector: sa.Inspector) -> None:
    """Drop the one-bill check under whatever name the convention gave it.

    The metadata's naming convention rewrites the name when the check is
    created -- here and by ``create_all`` alike -- so it is found by what its
    name contains and dropped by its real name (``op.f`` stops the convention
    renaming it a second time), as `20261002_0234` does.
    """
    for item in inspector.get_check_constraints(_TABLE):
        name = item.get("name") or ""
        if "one_bill" in name:
            op.drop_constraint(op.f(name), _TABLE, type_="check")


def upgrade() -> None:
    """Let a supplier credit application name an opening bill."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"]: column for column in inspector.get_columns(_TABLE)}
    if not columns["purchase_invoice_id"]["nullable"]:
        op.alter_column(_TABLE, "purchase_invoice_id", nullable=True)
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))
        if inspector.has_table("vendor_opening_bills"):
            op.create_foreign_key(
                f"FK_{_TABLE}_{_COLUMN}",
                _TABLE,
                "vendor_opening_bills",
                [_COLUMN],
                ["id"],
                ondelete="RESTRICT",
            )
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, ["firm_id", _COLUMN])
    checks = [
        item.get("name") or "" for item in inspector.get_check_constraints(_TABLE)
    ]
    if not any("one_bill" in name for name in checks):
        op.create_check_constraint(
            _CHECK,
            _TABLE,
            "(purchase_invoice_id IS NULL) <> (vendor_opening_bill_id IS NULL)",
        )


def downgrade() -> None:
    """Drop the opening-bill target; refused while any row names one."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        return
    held = (
        op.get_bind()
        .execute(sa.text(f"SELECT count(*) FROM {_TABLE} WHERE {_COLUMN} IS NOT NULL"))
        .scalar()
    )
    if held:
        raise RuntimeError(
            f"{_TABLE} holds {held} row(s) naming an opening bill; they would be "
            "lost by this downgrade."
        )
    _drop_check(inspector)
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
    op.alter_column(_TABLE, "purchase_invoice_id", nullable=False)
