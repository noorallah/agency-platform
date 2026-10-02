"""Rule 37 reversals and reclaims, and the firm's choice (backlog 78 row 4).

``itc_reversals``: one row per reversal or reclaim of a bill's credit under
CGST rule 37, with the journal that moved it. ``gst_compliance_settings``
gains ``rule37_mode`` (OFF, REPORT -- the default -- or POST).

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent; the foreign
keys are declared only where their targets exist in this store.

Revision ID: 20261002_0230
Revises: 20261002_0229
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0230"
down_revision: str | Sequence[str] | None = "20261002_0229"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity carries, timestamps defaulted."""
    return [
        sa.Column("id", UUIDType(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def upgrade() -> None:
    """Add the setting, and the table where this store holds purchase bills."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("gst_compliance_settings"):
        present = {
            column["name"]
            for column in inspector.get_columns("gst_compliance_settings")
        }
        if "rule37_mode" not in present:
            op.add_column(
                "gst_compliance_settings",
                sa.Column(
                    "rule37_mode",
                    sa.String(length=10),
                    nullable=False,
                    server_default="REPORT",
                ),
            )
    if not inspector.has_table("purchase_invoices"):
        return
    if not inspector.has_table("itc_reversals"):
        journal = (
            [
                sa.ForeignKeyConstraint(
                    ["journal_entry_id"],
                    ["journal_entries.id"],
                    name="FK_itc_reversals_journal_entry_id",
                    ondelete="RESTRICT",
                )
            ]
            if inspector.has_table("journal_entries")
            else []
        )
        op.create_table(
            "itc_reversals",
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("purchase_invoice_id", UUIDType(), nullable=False),
            sa.Column("movement", sa.String(length=10), nullable=False),
            sa.Column("movement_date", sa.Date(), nullable=False),
            sa.Column("outstanding_amount", sa.Numeric(18, 4), nullable=False),
            sa.Column("bill_total", sa.Numeric(18, 4), nullable=False),
            sa.Column("igst", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("cgst", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("sgst", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("cess", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("journal_entry_id", UUIDType(), nullable=True),
            sa.ForeignKeyConstraint(
                ["purchase_invoice_id"],
                ["purchase_invoices.id"],
                name="FK_itc_reversals_purchase_invoice_id",
                ondelete="RESTRICT",
            ),
            *journal,
            sa.CheckConstraint(
                "movement IN ('REVERSAL', 'RECLAIM')",
                name="CK_itc_reversals_movement",
            ),
        )
        op.create_index("IX_itc_reversals_firm_id", "itc_reversals", ["firm_id"])
        op.create_index(
            "IX_itc_reversals_firm_date", "itc_reversals", ["firm_id", "movement_date"]
        )
        op.create_index(
            "IX_itc_reversals_bill", "itc_reversals", ["purchase_invoice_id"]
        )


def downgrade() -> None:
    """Drop the table and the setting; refused while a movement is recorded."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("itc_reversals"):
        held = (
            op.get_bind()
            .execute(sa.text("SELECT count(*) FROM itc_reversals"))
            .scalar()
        )
        if held:
            raise RuntimeError(f"{held} rule 37 movement(s) would be lost.")
        op.drop_table("itc_reversals")
    if inspector.has_table("gst_compliance_settings"):
        present = {
            column["name"]
            for column in inspector.get_columns("gst_compliance_settings")
        }
        if "rule37_mode" in present:
            op.drop_column("gst_compliance_settings", "rule37_mode")
