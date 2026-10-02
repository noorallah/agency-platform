"""E-way bills on delivery notes, recorded by hand, and the firm's limit (77.9-10).

* ``eway_bills.sales_invoice_id`` becomes nullable and ``delivery_note_id`` is
  added -- a challan no invoice bills yet travels on its own e-way bill --
  with a check that exactly one is named and a key of one bill per note.
* ``eway_bills.entered_by_hand``: raised on the portal and recorded here (A42).
* ``gst_compliance_settings.eway_bill_limit``: above it a consignment needs an
  e-way bill (A35); ₹50,000 unless the firm sets its state's.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0228
Revises: 20261002_0227
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0228"
down_revision: str | Sequence[str] | None = "20261002_0227"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BILLS = "eway_bills"
_SETTINGS = "gst_compliance_settings"


def upgrade() -> None:
    """Widen e-way bills to delivery notes and add the firm's limit."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_BILLS):
        columns = {column["name"]: column for column in inspector.get_columns(_BILLS)}
        if not columns["sales_invoice_id"]["nullable"]:
            op.alter_column(_BILLS, "sales_invoice_id", nullable=True)
        if "delivery_note_id" not in columns:
            op.add_column(
                _BILLS, sa.Column("delivery_note_id", UUIDType(), nullable=True)
            )
            if inspector.has_table("delivery_notes"):
                op.create_foreign_key(
                    "FK_eway_bills_delivery_note_id",
                    _BILLS,
                    "delivery_notes",
                    ["delivery_note_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
        if "entered_by_hand" not in columns:
            op.add_column(
                _BILLS,
                sa.Column(
                    "entered_by_hand",
                    sa.Boolean(),
                    server_default=sa.text("false"),
                    nullable=False,
                ),
            )
        uniques = {item["name"] for item in inspector.get_unique_constraints(_BILLS)}
        if "UQ_eway_bills_delivery_note" not in uniques:
            op.create_unique_constraint(
                "UQ_eway_bills_delivery_note", _BILLS, ["firm_id", "delivery_note_id"]
            )
        checks = {item["name"] for item in inspector.get_check_constraints(_BILLS)}
        if "CK_eway_bills_one_document" not in checks:
            op.create_check_constraint(
                "CK_eway_bills_one_document",
                _BILLS,
                "(sales_invoice_id IS NULL) <> (delivery_note_id IS NULL)",
            )
    if inspector.has_table(_SETTINGS) and "eway_bill_limit" not in {
        column["name"] for column in inspector.get_columns(_SETTINGS)
    }:
        op.add_column(
            _SETTINGS,
            sa.Column(
                "eway_bill_limit",
                sa.Numeric(18, 2),
                server_default="50000",
                nullable=False,
            ),
        )


def downgrade() -> None:
    """Drop the limit and the note columns; refused while a note has a bill."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_SETTINGS) and "eway_bill_limit" in {
        column["name"] for column in inspector.get_columns(_SETTINGS)
    }:
        op.drop_column(_SETTINGS, "eway_bill_limit")
    if not inspector.has_table(_BILLS):
        return
    columns = {column["name"] for column in inspector.get_columns(_BILLS)}
    if "delivery_note_id" in columns:
        held = (
            op.get_bind()
            .execute(
                sa.text(
                    f"SELECT count(*) FROM {_BILLS} WHERE delivery_note_id IS NOT NULL"
                )
            )
            .scalar()
        )
        if held:
            raise RuntimeError(
                f"{held} e-way bill(s) belong to delivery notes and would be lost."
            )
        op.drop_constraint("CK_eway_bills_one_document", _BILLS, type_="check")
        op.drop_constraint("UQ_eway_bills_delivery_note", _BILLS, type_="unique")
        op.drop_column(_BILLS, "delivery_note_id")
        op.alter_column(_BILLS, "sales_invoice_id", nullable=False)
    if "entered_by_hand" in columns:
        op.drop_column(_BILLS, "entered_by_hand")
