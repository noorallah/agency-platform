"""Serial numbers captured at receipt (PG-10, backlog 86 #11).

* ``goods_receipt_line_serials``: the serials typed or scanned on a receipt
  line, held while the receipt is a draft. Completing the receipt turns them
  into ``serial_numbers`` rows, linked to the line through
  ``document_line_serials``.
* ``serial_numbers``: a serial names one unit in the whole firm, whatever the
  product and however it was typed. ``UQ_serial_numbers_firm_serial_product``
  (firm, serial, product -- dead rows included, case kept) gives way to the
  partial ``UQ_serial_numbers_firm_serial_active`` on ``(firm_id,
  upper(serial_number))`` over live rows, so a receipt cancelled before its
  units moved releases its numbers.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table and
the index are created only in a firm store (one holding ``goods_receipts`` /
``serial_numbers``) that lacks them, and the old key is dropped only where it
is still there. No ``firm_id`` foreign key: ``firms`` lives only in the
platform store.

If live serials already repeat within a firm once case is ignored, the index
cannot be built and the upgrade stops naming them: two units sharing a number
is a mistake in the data that a person has to correct, not one to paper over.

Revision ID: 20261005_0311
Revises: 20261005_0310
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0311"
down_revision: str | Sequence[str] | None = "20261005_0310"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "goods_receipt_line_serials"
_OLD_KEY = "UQ_serial_numbers_firm_serial_product"
_NEW_KEY = "UQ_serial_numbers_firm_serial_active"


def _base_columns() -> list[sa.Column[object]]:
    """Return the columns every ``BaseEntity`` table carries."""
    return [
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
    ]


def _create_line_serials() -> None:
    """Create the table a receipt line keeps its typed serials in."""
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("goods_receipt_id", UUIDType(), nullable=False),
        sa.Column("goods_receipt_line_id", UUIDType(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("serial_number", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"PK_{_TABLE}"),
        sa.UniqueConstraint(
            "goods_receipt_line_id",
            "position",
            name="UQ_goods_receipt_line_serials_line_position",
        ),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id"],
            ["goods_receipts.id"],
            name=f"FK_{_TABLE}_goods_receipt_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goods_receipt_line_id"],
            ["goods_receipt_lines.id"],
            name=f"FK_{_TABLE}_goods_receipt_line_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(f"IX_{_TABLE}_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        f"IX_{_TABLE}_goods_receipt_line_id", _TABLE, ["goods_receipt_line_id"]
    )
    op.create_index(
        "IX_goods_receipt_line_serials_firm_receipt",
        _TABLE,
        ["firm_id", "goods_receipt_id"],
    )


def _refuse_repeated_serials() -> None:
    """Stop, naming them, if live serials already repeat within a firm."""
    repeated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT upper(serial_number) AS serial, count(*) AS units "
                "FROM serial_numbers WHERE NOT is_deleted "
                "GROUP BY firm_id, upper(serial_number) HAVING count(*) > 1 "
                "ORDER BY 1 LIMIT 20"
            )
        )
        .all()
    )
    if repeated:
        named = ", ".join(f"{row.serial} ({row.units})" for row in repeated)
        raise RuntimeError(
            "Serial numbers repeat within a firm, so they cannot be made unique: "
            f"{named}. Correct or delete the extra rows and run the upgrade again."
        )


def _rekey_serial_numbers(inspector: sa.Inspector) -> None:
    """Swap the per-product key for the firm-wide, case-blind live one."""
    uniques = {u["name"] for u in inspector.get_unique_constraints("serial_numbers")}
    if _OLD_KEY in uniques:
        op.drop_constraint(_OLD_KEY, "serial_numbers", type_="unique")
    indexes = {i["name"] for i in inspector.get_indexes("serial_numbers")}
    if _OLD_KEY in indexes:
        op.drop_index(_OLD_KEY, table_name="serial_numbers")
    if _NEW_KEY in indexes:
        return
    _refuse_repeated_serials()
    op.create_index(
        _NEW_KEY,
        "serial_numbers",
        ["firm_id", sa.text("upper(serial_number)")],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def upgrade() -> None:
    """Create the table and the key where a firm store lacks them."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("goods_receipt_lines") and not inspector.has_table(_TABLE):
        _create_line_serials()
    if inspector.has_table("serial_numbers"):
        _rekey_serial_numbers(inspector)


def downgrade() -> None:
    """Drop the table and put the per-product key back."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if inspector.has_table("serial_numbers"):
        indexes = {i["name"] for i in inspector.get_indexes("serial_numbers")}
        if _NEW_KEY in indexes:
            op.drop_index(_NEW_KEY, table_name="serial_numbers")
        uniques = {
            u["name"] for u in inspector.get_unique_constraints("serial_numbers")
        }
        if _OLD_KEY not in uniques:
            op.create_unique_constraint(
                _OLD_KEY, "serial_numbers", ["firm_id", "serial_number", "product_id"]
            )
