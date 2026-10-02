"""E-invoice registrations for a sales return's credit note (D-TAX-2).

A completed sales return against an invoice is a credit note under CGST s.34
and reaches GSTR-1 as one, so a firm that e-invoices must register it with the
IRP as a CRN. ``einvoice_registrations`` gains ``sales_return_id`` with its own
one-registration key, and the one-document check counts it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0234
Revises: 20261002_0233
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0234"
down_revision: str | Sequence[str] | None = "20261002_0233"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "einvoice_registrations"
_COLUMN = "sales_return_id"
_KEY = "UQ_einvoice_registrations_sales_return"
_CHECK = "CK_einvoice_registrations_one_document"
_THREE = (
    "(CASE WHEN sales_invoice_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN credit_note_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN customer_debit_note_id IS NULL THEN 0 ELSE 1 END) = 1"
)
_FOUR = (
    "(CASE WHEN sales_invoice_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN credit_note_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN customer_debit_note_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN sales_return_id IS NULL THEN 0 ELSE 1 END) = 1"
)


def _replace_check(inspector: sa.Inspector, sql: str) -> None:
    """Drop the one-document check, under whatever name it has, and recreate it.

    The metadata's naming convention rewrites ``CK_einvoice_registrations_
    one_document`` into a longer, truncated name when it is created -- by 0229
    and by ``create_all`` alike -- so the check is found by what its name
    contains and dropped by its real name (``op.f`` stops the convention
    renaming it a second time). Created by the plain name, so it gets the
    same name the ORM gives it.
    """
    for item in inspector.get_check_constraints(_TABLE):
        name = item.get("name") or ""
        if "one_d" in name:
            op.drop_constraint(op.f(name), _TABLE, type_="check")
    op.create_check_constraint(_CHECK, _TABLE, sql)


def upgrade() -> None:
    """Let a registration name a sales return."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))
    if inspector.has_table("sales_returns"):
        op.create_foreign_key(
            f"FK_{_TABLE}_{_COLUMN}",
            _TABLE,
            "sales_returns",
            [_COLUMN],
            ["id"],
            ondelete="RESTRICT",
        )
    uniques = {item["name"] for item in inspector.get_unique_constraints(_TABLE)}
    if _KEY not in uniques:
        op.create_unique_constraint(_KEY, _TABLE, ["firm_id", _COLUMN])
    _replace_check(inspector, _FOUR)


def downgrade() -> None:
    """Drop the column; refused while a sales return is registered."""
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
        raise RuntimeError(f"{held} sales-return registration(s) would be lost.")
    _replace_check(inspector, _THREE)
    op.drop_constraint(_KEY, _TABLE, type_="unique")
    op.drop_column(_TABLE, _COLUMN)
