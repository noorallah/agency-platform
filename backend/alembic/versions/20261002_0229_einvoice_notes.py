"""E-invoice registrations for credit notes and customer debit notes (77 row 4).

``einvoice_registrations`` names a sales invoice, a credit note or a debit note
to a customer -- exactly one: ``sales_invoice_id`` becomes nullable and
``credit_note_id`` and ``customer_debit_note_id`` are added, each with its own
one-registration key. Every existing row names an invoice, so the check holds.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0229
Revises: 20261002_0228
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0229"
down_revision: str | Sequence[str] | None = "20261002_0228"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "einvoice_registrations"
_ONE = (
    "(CASE WHEN sales_invoice_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN credit_note_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN customer_debit_note_id IS NULL THEN 0 ELSE 1 END) = 1"
)
_NOTES = (
    ("credit_note_id", "credit_notes", "UQ_einvoice_registrations_credit_note"),
    (
        "customer_debit_note_id",
        "customer_debit_notes",
        "UQ_einvoice_registrations_debit_note",
    ),
)


def upgrade() -> None:
    """Let a registration name a credit or a debit note."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"]: column for column in inspector.get_columns(_TABLE)}
    if not columns["sales_invoice_id"]["nullable"]:
        op.alter_column(_TABLE, "sales_invoice_id", nullable=True)
    uniques = {item["name"] for item in inspector.get_unique_constraints(_TABLE)}
    for column, target, key in _NOTES:
        if column not in columns:
            op.add_column(_TABLE, sa.Column(column, UUIDType(), nullable=True))
            if inspector.has_table(target):
                op.create_foreign_key(
                    f"FK_{_TABLE}_{column}",
                    _TABLE,
                    target,
                    [column],
                    ["id"],
                    ondelete="RESTRICT",
                )
        if key not in uniques:
            op.create_unique_constraint(key, _TABLE, ["firm_id", column])
    checks = {item["name"] for item in inspector.get_check_constraints(_TABLE)}
    if "CK_einvoice_registrations_one_document" not in checks:
        op.create_check_constraint(
            "CK_einvoice_registrations_one_document", _TABLE, _ONE
        )


def downgrade() -> None:
    """Drop the note columns; refused while a note is registered."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "credit_note_id" not in columns:
        return
    held = (
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT count(*) FROM {_TABLE} WHERE credit_note_id IS NOT NULL "
                "OR customer_debit_note_id IS NOT NULL"
            )
        )
        .scalar()
    )
    if held:
        raise RuntimeError(f"{held} note registration(s) would be lost.")
    op.drop_constraint("CK_einvoice_registrations_one_document", _TABLE, type_="check")
    for column, _target, key in _NOTES:
        op.drop_constraint(key, _TABLE, type_="unique")
        op.drop_column(_TABLE, column)
    op.alter_column(_TABLE, "sales_invoice_id", nullable=False)
