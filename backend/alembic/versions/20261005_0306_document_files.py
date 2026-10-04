"""Files uploaded onto bills and goods receipts (PG-4, backlog 86 #16).

``document_files`` holds each file's name, type, size and hash;
``document_file_contents`` holds its bytes, apart so that a list never reads
them. Both live where ``purchase_invoices`` and ``goods_receipts`` do -- the
firm stores -- and are skipped where those are absent (a pruned platform).
``firm_id`` carries no foreign key: ``firms`` lives only in ``platform``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261005_0306
Revises: 20261004_0305
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0306"
down_revision: str | Sequence[str] | None = "20261004_0305"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str) -> sa.Column[object]:
    """Build a NOT NULL timestamp that fills itself on insert."""
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def upgrade() -> None:
    """Create both tables where a store keeps bills and receipts."""
    inspector = sa.inspect(op.get_bind())
    if not (
        inspector.has_table("purchase_invoices")
        and inspector.has_table("goods_receipts")
    ):
        return
    if not inspector.has_table("document_files"):
        op.create_table(
            "document_files",
            sa.Column("id", UUIDType(), nullable=False),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("purchase_invoice_id", UUIDType(), nullable=True),
            sa.Column("goods_receipt_id", UUIDType(), nullable=True),
            sa.Column("file_name", sa.String(260), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("caption", sa.String(200), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_document_files"),
            sa.ForeignKeyConstraint(
                ["purchase_invoice_id"],
                ["purchase_invoices.id"],
                name="FK_document_files_purchase_invoice_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["goods_receipt_id"],
                ["goods_receipts.id"],
                name="FK_document_files_goods_receipt_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "(purchase_invoice_id IS NULL) <> (goods_receipt_id IS NULL)",
                name="CK_document_files_one_parent",
            ),
        )
        op.create_index("IX_document_files_firm_id", "document_files", ["firm_id"])
        op.create_index(
            "IX_document_files_purchase_invoice",
            "document_files",
            ["purchase_invoice_id"],
        )
        op.create_index(
            "IX_document_files_goods_receipt", "document_files", ["goods_receipt_id"]
        )
    if not inspector.has_table("document_file_contents"):
        op.create_table(
            "document_file_contents",
            sa.Column("file_id", UUIDType(), nullable=False),
            sa.Column("content", sa.LargeBinary(), nullable=False),
            sa.PrimaryKeyConstraint("file_id", name="PK_document_file_contents"),
            sa.ForeignKeyConstraint(
                ["file_id"],
                ["document_files.id"],
                name="FK_document_file_contents_file_id",
                ondelete="CASCADE",
            ),
        )


def downgrade() -> None:
    """Drop both tables, contents first."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("document_file_contents"):
        op.drop_table("document_file_contents")
    if inspector.has_table("document_files"):
        op.drop_table("document_files")
