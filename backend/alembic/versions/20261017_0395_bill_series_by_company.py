"""A bill series per company (backlog 157, PRT-7).

``docs/design/BILL_SERIES_BY_COMPANY_DESIGN.md`` sections 3-5, 10 and 11:

* ``bill_series_settings`` -- one row per firm, ``series_driver``
  (``ONE_SERIES`` or ``BY_COMPANY``). No row reads as ``ONE_SERIES``, so every
  firm numbers exactly as before until it switches.
* ``bill_series_counters`` -- the next number per firm, prefix and financial
  year, unique on the three and **not** partial, so a retired row is revived
  rather than duplicated (D-CFG-7).
* ``principals.bill_series_prefix`` -- null for every company; nobody has a
  series of their own until the firm gives one.
* ``sales_invoices.series_prefix`` -- the series a bill was issued from.

The backfill gives every firm a GENERAL counter for each financial year it
has billed in or counted under, at the **higher** of the sales-bill rule's
counter and one past the highest number found on its bills with that prefix
and year -- starting GENERAL at 1 would issue a number already printed. Only
a counter not there yet is written, so a replay overwrites nothing.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent throughout: each
table and column is created only where missing, and no foreign key to
``firms`` is declared, since that table lives only in ``platform``.

Revision ID: 20261017_0395
Revises: 20261017_0394
Create Date: 2026-10-17

"""

import re
import uuid
from collections.abc import Sequence
from datetime import date, datetime

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.core.utils.dates import financial_year_label

revision: str = "20261017_0395"
down_revision: str | Sequence[str] | None = "20261017_0394"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTINGS = "bill_series_settings"
_COUNTERS = "bill_series_counters"
_GENERAL = "GENERAL"
_YEAR = re.compile(r"^\d{4}-\d{4}$")


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the ``BaseEntity`` columns, timestamps defaulted explicitly."""
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
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
    ]


def _has_column(table: str, column: str) -> bool:
    """Say whether ``table`` exists and already holds ``column``."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return any(row["name"] == column for row in inspector.get_columns(table))


def _create_tables() -> None:
    """Create the two tables where missing."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_SETTINGS):
        op.create_table(
            _SETTINGS,
            *_base_columns(),
            sa.Column(
                "series_driver",
                sa.String(length=30),
                server_default="ONE_SERIES",
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_bill_series_settings"),
            sa.UniqueConstraint("firm_id", name="UQ_bill_series_settings_firm"),
        )
        op.create_index("IX_bill_series_settings_firm_id", _SETTINGS, ["firm_id"])
    if not inspector.has_table(_COUNTERS):
        op.create_table(
            _COUNTERS,
            *_base_columns(),
            sa.Column("prefix", sa.String(length=10), nullable=False),
            sa.Column("financial_year", sa.String(length=20), nullable=False),
            sa.Column(
                "next_sequence",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_bill_series_counters"),
            sa.UniqueConstraint(
                "firm_id",
                "prefix",
                "financial_year",
                name="UQ_bill_series_counters_firm_prefix_year",
            ),
        )
        op.create_index("IX_bill_series_counters_firm_id", _COUNTERS, ["firm_id"])


def _as_date(value: object) -> date | None:
    """Read a date column as SQLite (text) or PostgreSQL (date) returns it."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def _sequence_of(number: str, prefix: str | None, separator: str) -> int | None:
    """Return the running number printed in ``number``, if it is the rule's.

    A number not starting with the rule's prefix is another series's (or a
    typed one) and says nothing about GENERAL. The running number is the last
    all-digit part, which is where every layout without a numeric suffix
    prints it.
    """
    if prefix and not number.upper().startswith(prefix.upper()):
        return None
    parts = number.split(separator) if separator else [number]
    digits = [part for part in parts if part.isdigit()]
    return int(digits[-1]) if digits else None


def _start_months(bind: sa.engine.Connection) -> dict[str, int]:
    """Return each firm's financial-year start month, where ``firms`` is visible."""
    if not sa.inspect(bind).has_table("firms"):
        return {}
    months: dict[str, int] = {}
    for firm_id, starts in bind.execute(
        sa.text("SELECT id, financial_year_start FROM firms")
    ):
        start = _as_date(starts)
        if start is not None:
            months[str(firm_id)] = start.month
    return months


def _backfill_general() -> None:
    """Give each firm's GENERAL series a counter per year, past what it issued."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    needed = (
        "document_numbering_rules",
        "document_type_definitions",
        "document_number_sequences",
        "sales_invoices",
        _COUNTERS,
    )
    if not all(inspector.has_table(name) for name in needed):
        return
    # The series a firm's sales bills are numbered from: active, then the
    # default, then the oldest -- the order `_ensure_document_setup` reads.
    rules: dict[str, tuple[str, str | None, str, bool]] = {}
    for rule_id, firm_id, prefix, separator, auto_reset in bind.execute(
        sa.text(
            "SELECT r.id, r.firm_id, r.prefix, r.separator, r.auto_reset "
            "FROM document_numbering_rules r "
            "JOIN document_type_definitions t ON t.id = r.document_type_id "
            "WHERE t.code = 'SALES_INVOICE' AND r.is_deleted = false "
            "AND t.is_deleted = false "
            "ORDER BY r.is_active DESC, r.is_default DESC, r.created_at ASC, "
            "r.id ASC"
        )
    ):
        rules.setdefault(
            str(firm_id), (str(rule_id), prefix, separator or "", bool(auto_reset))
        )
    if not rules:
        return
    rule_ids = {rule[0] for rule in rules.values()}
    counted: dict[str, dict[str, int]] = {}
    for rule_id, signature, next_sequence in bind.execute(
        sa.text(
            "SELECT numbering_rule_id, scope_signature, next_sequence "
            "FROM document_number_sequences WHERE is_deleted = false"
        )
    ):
        if str(rule_id) not in rule_ids:
            continue
        year = (signature or "").split("|")[0]
        per_rule = counted.setdefault(str(rule_id), {})
        per_rule[year] = max(per_rule.get(year, 1), int(next_sequence or 1))
    months = _start_months(bind)
    issued: dict[tuple[str, str], int] = {}
    for firm_id, number, invoice_date in bind.execute(
        sa.text("SELECT firm_id, invoice_number, invoice_date FROM sales_invoices")
    ):
        firm = str(firm_id)
        rule = rules.get(firm)
        on = _as_date(invoice_date)
        if rule is None or on is None or not number:
            continue
        year = financial_year_label(on, start_month=months.get(firm, 4))
        sequence = _sequence_of(str(number), rule[1], rule[2])
        if sequence is not None:
            issued[(firm, year)] = max(issued.get((firm, year), 0), sequence)
    existing = {
        (str(firm_id), prefix, year)
        for firm_id, prefix, year in bind.execute(
            sa.text(f"SELECT firm_id, prefix, financial_year FROM {_COUNTERS}")
        )
    }
    table = sa.table(
        _COUNTERS,
        sa.column("id", UUIDType()),
        sa.column("firm_id", UUIDType()),
        sa.column("prefix", sa.String()),
        sa.column("financial_year", sa.String()),
        sa.column("next_sequence", sa.Integer()),
    )
    rows: list[dict[str, object]] = []
    for firm, (rule_id, _prefix, _separator, auto_reset) in rules.items():
        per_rule = counted.get(rule_id, {})
        years = {year for year in per_rule if _YEAR.match(year)}
        years |= {year for (owner, year) in issued if owner == firm}
        for year in sorted(years):
            if (firm, _GENERAL, year) in existing:
                continue
            # A rule that restarts each year counts under the year; one that
            # does not keeps one counter, which every year carries on from.
            rule_next = per_rule.get(year if auto_reset else "", 1)
            if not auto_reset:
                rule_next = max([rule_next, *per_rule.values()])
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "firm_id": uuid.UUID(firm),
                    "prefix": _GENERAL,
                    "financial_year": year,
                    "next_sequence": max(rule_next, issued.get((firm, year), 0) + 1, 1),
                }
            )
    if rows:
        bind.execute(table.insert(), rows)


def upgrade() -> None:
    """Create the tables, add the two columns, backfill GENERAL."""
    inspector = sa.inspect(op.get_bind())
    # Firm-owned: a store with no customers holds no firm's bills.
    if not inspector.has_table("customers"):
        return
    _create_tables()
    if inspector.has_table("principals") and not _has_column(
        "principals", "bill_series_prefix"
    ):
        op.add_column(
            "principals",
            sa.Column("bill_series_prefix", sa.String(length=10), nullable=True),
        )
    if inspector.has_table("sales_invoices") and not _has_column(
        "sales_invoices", "series_prefix"
    ):
        op.add_column(
            "sales_invoices",
            sa.Column("series_prefix", sa.String(length=10), nullable=True),
        )
    _backfill_general()


def downgrade() -> None:
    """Drop the columns and the tables; every bill numbers from its rule again."""
    if _has_column("sales_invoices", "series_prefix"):
        op.drop_column("sales_invoices", "series_prefix")
    if _has_column("principals", "bill_series_prefix"):
        op.drop_column("principals", "bill_series_prefix")
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_COUNTERS):
        op.drop_index("IX_bill_series_counters_firm_id", table_name=_COUNTERS)
        op.drop_table(_COUNTERS)
    if inspector.has_table(_SETTINGS):
        op.drop_index("IX_bill_series_settings_firm_id", table_name=_SETTINGS)
        op.drop_table(_SETTINGS)
