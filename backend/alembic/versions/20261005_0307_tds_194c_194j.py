"""TDS on contracts (194C) and fees (194J) worked out, as 194Q is (PG-5).

* ``tds_section_settings``: one row per firm and section. No row reads as the
  defaults in ``app.finance.services.tds_sections`` (194C 1%/2% past 30,000
  a bill or 1,00,000 a year; 194J 10%/2% past 30,000 a year; 20% without a
  PAN), so nothing is backfilled: a firm that never saved works to them.
* ``vendors.tds_individual_huf`` (NULL reads the PAN) and
  ``vendors.tds_technical_services`` (false): which 194C or 194J rate.
* ``purchase_invoices.tds_section``, ``tds_base_amount``,
  ``tds_proposed_amount`` and ``tds_amount``: the deduction a bill bore at
  approval, beside what was proposed.
* ``settlements.tds_proposed_amount``: what a payment was proposed.
* ``tds_challan_items.purchase_invoice_id``: a challan pays a bill's deduction
  too; the one-source check widens from two documents to three.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each object is
created only where its table exists and it does not. No cross-schema key:
``firm_id`` carries none, and the bill key is declared only where
``purchase_invoices`` is in the same store.

Revision ID: 20261005_0307
Revises: 20261005_0306
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0307"
down_revision: str | Sequence[str] | None = "20261005_0306"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTINGS = "tds_section_settings"
_ITEMS = "tds_challan_items"
_OLD_CHECK = "CK_tds_challan_items_one_source"
_NEW_CHECK = "CK_tds_challan_items_one_document"
_ONE_DOCUMENT = (
    "(CASE WHEN settlement_id IS NULL THEN 0 ELSE 1 END"
    " + CASE WHEN expense_id IS NULL THEN 0 ELSE 1 END"
    " + CASE WHEN purchase_invoice_id IS NULL THEN 0 ELSE 1 END) = 1"
)
_BILL_INDEX = "UQ_tds_challan_items_purchase_invoice_live"


def _timestamp(name: str) -> sa.Column[object]:
    """Build a NOT NULL timestamp that fills itself on insert."""
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def _add_columns(
    inspector: sa.Inspector, table: str, columns: list[sa.Column[object]]
) -> None:
    """Add each column the table lacks; skip a table this store does not hold."""
    if not inspector.has_table(table):
        return
    present = {column["name"] for column in inspector.get_columns(table)}
    for column in columns:
        if column.name not in present:
            op.add_column(table, column)


def _create_settings(inspector: sa.Inspector) -> None:
    """Create the settings table in a firm store that lacks it."""
    if not inspector.has_table("vendors") or inspector.has_table(_SETTINGS):
        return
    op.create_table(
        _SETTINGS,
        sa.Column("id", UUIDType(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("section", sa.String(10), nullable=False),
        sa.Column(
            "is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("single_threshold_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("annual_threshold_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("rate_percent", sa.Numeric(6, 3), nullable=False),
        sa.Column("lower_rate_percent", sa.Numeric(6, 3), nullable=False),
        sa.Column(
            "rate_without_pan_percent",
            sa.Numeric(6, 3),
            server_default=sa.text("20"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_tds_section_settings"),
        sa.UniqueConstraint("firm_id", "section", name="UQ_tds_section_settings_firm"),
    )
    op.create_index("IX_tds_section_settings_firm_id", _SETTINGS, ["firm_id"])


def _widen_challan_items(inspector: sa.Inspector) -> None:
    """Let a challan item name a bill, and hold it to exactly one document."""
    if not inspector.has_table(_ITEMS):
        return
    columns = {column["name"] for column in inspector.get_columns(_ITEMS)}
    if "purchase_invoice_id" not in columns:
        op.add_column(
            _ITEMS, sa.Column("purchase_invoice_id", UUIDType(), nullable=True)
        )
        if inspector.has_table("purchase_invoices"):
            op.create_foreign_key(
                f"FK_{_ITEMS}_purchase_invoice_id",
                _ITEMS,
                "purchase_invoices",
                ["purchase_invoice_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    checks = {check["name"] for check in inspector.get_check_constraints(_ITEMS)}
    if _OLD_CHECK in checks:
        op.drop_constraint(_OLD_CHECK, _ITEMS, type_="check")
    if _NEW_CHECK not in checks:
        op.create_check_constraint(_NEW_CHECK, _ITEMS, _ONE_DOCUMENT)
    indexes = {index["name"] for index in inspector.get_indexes(_ITEMS)}
    if _BILL_INDEX not in indexes:
        op.create_index(
            _BILL_INDEX,
            _ITEMS,
            ["purchase_invoice_id"],
            unique=True,
            postgresql_where=sa.text(
                "is_live = true AND purchase_invoice_id IS NOT NULL"
            ),
            sqlite_where=sa.text("is_live = 1 AND purchase_invoice_id IS NOT NULL"),
        )


def upgrade() -> None:
    """Add the 194C/194J settings, the supplier's rate, and the bill's TDS."""
    inspector = sa.inspect(op.get_bind())
    _create_settings(inspector)
    _add_columns(
        inspector,
        "vendors",
        [
            sa.Column("tds_individual_huf", sa.Boolean(), nullable=True),
            sa.Column(
                "tds_technical_services",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        ],
    )
    _add_columns(
        inspector,
        "purchase_invoices",
        [
            sa.Column("tds_section", sa.String(10), nullable=True),
            sa.Column(
                "tds_base_amount",
                sa.Numeric(18, 2),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column("tds_proposed_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column(
                "tds_amount",
                sa.Numeric(18, 2),
                server_default=sa.text("0"),
                nullable=False,
            ),
        ],
    )
    _add_columns(
        inspector,
        "settlements",
        [sa.Column("tds_proposed_amount", sa.Numeric(18, 2), nullable=True)],
    )
    _widen_challan_items(inspector)


def downgrade() -> None:
    """Take it all back; refused while a challan pays a bill's deduction."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_ITEMS):
        columns = {column["name"] for column in inspector.get_columns(_ITEMS)}
        if "purchase_invoice_id" in columns:
            held = (
                op.get_bind()
                .execute(
                    sa.text(
                        f"SELECT count(*) FROM {_ITEMS} "
                        "WHERE purchase_invoice_id IS NOT NULL"
                    )
                )
                .scalar()
            )
            if held:
                raise RuntimeError(
                    f"{_ITEMS} holds {held} row(s) naming a bill; they would be "
                    "lost by this downgrade."
                )
            indexes = {index["name"] for index in inspector.get_indexes(_ITEMS)}
            if _BILL_INDEX in indexes:
                op.drop_index(_BILL_INDEX, table_name=_ITEMS)
            checks = {c["name"] for c in inspector.get_check_constraints(_ITEMS)}
            if _NEW_CHECK in checks:
                op.drop_constraint(_NEW_CHECK, _ITEMS, type_="check")
            op.create_check_constraint(
                _OLD_CHECK, _ITEMS, "(settlement_id IS NULL) <> (expense_id IS NULL)"
            )
            keys = {key["name"] for key in inspector.get_foreign_keys(_ITEMS)}
            if f"FK_{_ITEMS}_purchase_invoice_id" in keys:
                op.drop_constraint(
                    f"FK_{_ITEMS}_purchase_invoice_id", _ITEMS, type_="foreignkey"
                )
            op.drop_column(_ITEMS, "purchase_invoice_id")
    for table, names in (
        ("settlements", ("tds_proposed_amount",)),
        (
            "purchase_invoices",
            ("tds_section", "tds_base_amount", "tds_proposed_amount", "tds_amount"),
        ),
        ("vendors", ("tds_individual_huf", "tds_technical_services")),
    ):
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name in names:
            if name in present:
                op.drop_column(table, name)
    if inspector.has_table(_SETTINGS):
        op.drop_table(_SETTINGS)
