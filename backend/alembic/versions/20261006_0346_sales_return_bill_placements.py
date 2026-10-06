"""A completed return off a note keeps which bill each unit came from.

``sales_return_bill_placements``: one row per bill line a completed return
line raised off a delivery note took **billed** units from, with the units
and the value each took.

A delivery note line can be billed in parts, and a return raised off the note
names no bill. Which bill its units came from was worked out afresh on every
read, so it moved whenever the bills changed: a unit named later on the first
bill's own line pushed a unit of an earlier return onto the next bill, after
that return had been valued and completed at the first bill's worth, and a
customer was credited 3,304.00 against bills of 2,832.00 (D-PRC-72). The
split is now written when the return completes and read as stored.

**Backfill.** Every completed return line off a note that credited something
and has no placement is given the one the reading in force until now gives
it, so every bill reads after this migration exactly what it read before it:
what returns name on each bill line counted first, then the returns off the
note oldest first (by when each completed), each set against the bills that
charged its note line earliest first, for the units still out, up to what
they were still worth, the last bill taking the rest. A return no bill has
room for is given none, and goes on being worked out.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table is
created only where missing and a line that has a placement is left alone. No
``firm_id`` foreign key (``firms`` lives only in the platform store) and none
to the bill, which is named by a bare id as a return line names its source.

Revision ID: 20261006_0346
Revises: 20261006_0345
Create Date: 2026-10-06

"""

from collections import defaultdict
from collections.abc import Iterator, Sequence
from decimal import Decimal
from typing import Any
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261006_0346"
down_revision: str | Sequence[str] | None = "20261006_0345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_return_bill_placements"
_ZERO = Decimal("0")
_FOUR = Decimal("0.0001")
_DUST = Decimal("0.0005")
_COMPLETED = ("COMPLETED", "CLOSED")
_CHARGED = ("APPROVED", "CLOSED")

_PLACEMENTS = sa.table(
    _TABLE,
    sa.column("id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("sales_return_id", UUIDType()),
    sa.column("sales_return_line_id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("sales_invoice_id", UUIDType()),
    sa.column("sales_invoice_line_id", UUIDType()),
    sa.column("quantity", sa.Numeric(18, 4)),
    sa.column("entered_quantity", sa.Numeric(18, 4)),
    sa.column("conversion_factor", sa.Numeric(24, 10)),
    sa.column("taxable_amount", sa.Numeric(18, 4)),
    sa.column("net_amount", sa.Numeric(18, 4)),
)
_RETURNS = sa.table(
    "sales_returns",
    sa.column("id", UUIDType()),
    sa.column("status", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("completed_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("return_number", sa.String()),
)
_RETURN_LINES = sa.table(
    "sales_return_lines",
    sa.column("id", UUIDType()),
    sa.column("sales_return_id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("line_number", sa.Integer()),
    sa.column("source_document_type", sa.String()),
    sa.column("source_document_line_id", UUIDType()),
    sa.column("current_return_quantity", sa.Numeric(18, 4)),
    sa.column("unbilled_quantity", sa.Numeric(18, 4)),
    sa.column("entered_quantity", sa.Numeric(18, 4)),
    sa.column("conversion_factor", sa.Numeric(24, 10)),
    sa.column("net_amount", sa.Numeric(18, 4)),
    sa.column("tax_amount", sa.Numeric(18, 4)),
)
_BILLS = sa.table(
    "sales_invoices",
    sa.column("id", UUIDType()),
    sa.column("status", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("invoice_date", sa.Date()),
    sa.column("invoice_number", sa.String()),
)
_BILL_LINES = sa.table(
    "sales_invoice_lines",
    sa.column("id", UUIDType()),
    sa.column("sales_invoice_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("line_number", sa.Integer()),
    sa.column("source_document_type", sa.String()),
    sa.column("source_document_line_id", UUIDType()),
    sa.column("current_invoice_quantity", sa.Numeric(18, 4)),
    sa.column("gross_amount", sa.Numeric(18, 4)),
    sa.column("discount_amount", sa.Numeric(18, 4)),
    sa.column("bill_discount_amount", sa.Numeric(18, 4)),
    sa.column("charges_amount", sa.Numeric(18, 4)),
)
_NOTES = sa.table(
    "credit_notes",
    sa.column("id", UUIDType()),
    sa.column("status", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)
_NOTE_LINES = sa.table(
    "credit_note_lines",
    sa.column("credit_note_id", UUIDType()),
    sa.column("sales_invoice_line_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("taxable_amount", sa.Numeric(18, 4)),
)


def _d(value: object) -> Decimal:
    """Read a stored number as a decimal."""
    return Decimal(str(value or 0))


def _chunks(items: Sequence[Any], size: int = 1000) -> Iterator[Sequence[Any]]:
    """Yield an id list a statement's worth at a time."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _create(inspector: sa.Inspector) -> None:
    """Create the table where the store does not hold it yet."""
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("sales_return_id", UUIDType(), nullable=False),
        sa.Column("sales_return_line_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_line_id", UUIDType(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("entered_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "conversion_factor", sa.Numeric(24, 10), server_default="1", nullable=False
        ),
        sa.Column(
            "taxable_amount", sa.Numeric(18, 4), server_default="0", nullable=False
        ),
        sa.Column("net_amount", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_sales_return_bill_placements"),
        sa.ForeignKeyConstraint(
            ["sales_return_id"],
            ["sales_returns.id"],
            name="FK_sales_return_bill_placements_sales_return_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sales_return_line_id"],
            ["sales_return_lines.id"],
            name="FK_sales_return_bill_placements_sales_return_line_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "IX_sales_return_bill_placements_line", _TABLE, ["sales_return_line_id"]
    )
    op.create_index(
        "IX_sales_return_bill_placements_return", _TABLE, ["sales_return_id"]
    )
    op.create_index(
        "IX_sales_return_bill_placements_firm_bill_line",
        _TABLE,
        ["firm_id", "sales_invoice_line_id"],
    )
    op.create_index(
        "IX_sales_return_bill_placements_firm_bill",
        _TABLE,
        ["firm_id", "sales_invoice_id"],
    )


def _unplaced(bind: sa.Connection) -> list[sa.Row[Any]]:
    """Read the completed return lines off notes that credited, unplaced."""
    placed = (
        sa.select(_PLACEMENTS.c.id)
        .where(
            _PLACEMENTS.c.sales_return_line_id == _RETURN_LINES.c.id,
            _PLACEMENTS.c.is_deleted.is_(False),
        )
        .exists()
    )
    return list(
        bind.execute(
            sa.select(
                _RETURN_LINES.c.id,
                _RETURN_LINES.c.sales_return_id,
                _RETURN_LINES.c.firm_id,
                _RETURN_LINES.c.line_number,
                _RETURN_LINES.c.source_document_line_id,
                _RETURN_LINES.c.current_return_quantity,
                _RETURN_LINES.c.unbilled_quantity,
                _RETURN_LINES.c.entered_quantity,
                _RETURN_LINES.c.conversion_factor,
                _RETURN_LINES.c.net_amount,
                _RETURN_LINES.c.tax_amount,
                _RETURNS.c.completed_at,
                _RETURNS.c.created_at,
                _RETURNS.c.return_number,
            )
            .select_from(
                _RETURN_LINES.join(
                    _RETURNS, _RETURNS.c.id == _RETURN_LINES.c.sales_return_id
                )
            )
            .where(
                _RETURN_LINES.c.source_document_type == "DELIVERY_NOTE",
                _RETURN_LINES.c.is_deleted.is_(False),
                _RETURN_LINES.c.current_return_quantity
                > _RETURN_LINES.c.unbilled_quantity,
                _RETURNS.c.is_deleted.is_(False),
                _RETURNS.c.status.in_(_COMPLETED),
                ~placed,
            )
        ).all()
    )


def _bills_of(
    bind: sa.Connection, note_line_ids: Sequence[Any]
) -> dict[Any, list[dict[str, Any]]]:
    """Read the bill lines that charged these note lines, earliest first."""
    by_note: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for part in _chunks(note_line_ids):
        for row in bind.execute(
            sa.select(
                _BILL_LINES.c.id,
                _BILL_LINES.c.sales_invoice_id,
                _BILL_LINES.c.source_document_line_id,
                _BILL_LINES.c.current_invoice_quantity,
                _BILL_LINES.c.gross_amount,
                _BILL_LINES.c.discount_amount,
                _BILL_LINES.c.bill_discount_amount,
                _BILL_LINES.c.charges_amount,
            )
            .select_from(
                _BILL_LINES.join(_BILLS, _BILLS.c.id == _BILL_LINES.c.sales_invoice_id)
            )
            .where(
                _BILL_LINES.c.source_document_type == "DELIVERY_NOTE",
                _BILL_LINES.c.source_document_line_id.in_(part),
                _BILL_LINES.c.is_deleted.is_(False),
                _BILLS.c.is_deleted.is_(False),
                _BILLS.c.status.in_(_CHARGED),
            )
            .order_by(
                _BILLS.c.invoice_date.asc(),
                _BILLS.c.invoice_number.asc(),
                _BILL_LINES.c.line_number.asc(),
            )
        ).all():
            by_note[row.source_document_line_id].append(
                {
                    "line_id": row.id,
                    "invoice_id": row.sales_invoice_id,
                    "quantity": _d(row.current_invoice_quantity),
                    # What the line is still worth, before tax.
                    "left": _d(row.gross_amount)
                    - _d(row.discount_amount)
                    - _d(row.bill_discount_amount)
                    + _d(row.charges_amount),
                    # Its units already back.
                    "gone": _ZERO,
                }
            )
    return by_note


def _take_what_is_already_off(
    bind: sa.Connection, inspector: sa.Inspector, bills: dict[Any, dict[str, Any]]
) -> None:
    """Take off each bill line what credit notes and returns already took.

    Approved credit notes, completed returns named on the bill line itself,
    and placements already written.
    """
    for part in _chunks(list(bills)):
        if inspector.has_table("credit_note_lines"):
            for line_id, taxable in bind.execute(
                sa.select(
                    _NOTE_LINES.c.sales_invoice_line_id,
                    sa.func.coalesce(sa.func.sum(_NOTE_LINES.c.taxable_amount), 0),
                )
                .select_from(
                    _NOTE_LINES.join(
                        _NOTES, _NOTES.c.id == _NOTE_LINES.c.credit_note_id
                    )
                )
                .where(
                    _NOTE_LINES.c.sales_invoice_line_id.in_(part),
                    _NOTE_LINES.c.is_deleted.is_(False),
                    _NOTES.c.is_deleted.is_(False),
                    _NOTES.c.status == "APPROVED",
                )
                .group_by(_NOTE_LINES.c.sales_invoice_line_id)
            ).all():
                bills[line_id]["left"] -= _d(taxable)
        for line_id, quantity, taxable in bind.execute(
            sa.select(
                _RETURN_LINES.c.source_document_line_id,
                sa.func.coalesce(
                    sa.func.sum(_RETURN_LINES.c.current_return_quantity), 0
                ),
                sa.func.coalesce(
                    sa.func.sum(
                        _RETURN_LINES.c.net_amount - _RETURN_LINES.c.tax_amount
                    ),
                    0,
                ),
            )
            .select_from(
                _RETURN_LINES.join(
                    _RETURNS, _RETURNS.c.id == _RETURN_LINES.c.sales_return_id
                )
            )
            .where(
                _RETURN_LINES.c.source_document_type == "SALES_INVOICE",
                _RETURN_LINES.c.source_document_line_id.in_(part),
                _RETURN_LINES.c.is_deleted.is_(False),
                _RETURNS.c.is_deleted.is_(False),
                _RETURNS.c.status.in_(_COMPLETED),
            )
            .group_by(_RETURN_LINES.c.source_document_line_id)
        ).all():
            bills[line_id]["gone"] += _d(quantity)
            bills[line_id]["left"] -= _d(taxable)
        for line_id, quantity, taxable in bind.execute(
            sa.select(
                _PLACEMENTS.c.sales_invoice_line_id,
                sa.func.coalesce(sa.func.sum(_PLACEMENTS.c.quantity), 0),
                sa.func.coalesce(sa.func.sum(_PLACEMENTS.c.taxable_amount), 0),
            )
            .select_from(
                _PLACEMENTS.join(
                    _RETURNS, _RETURNS.c.id == _PLACEMENTS.c.sales_return_id
                )
            )
            .where(
                _PLACEMENTS.c.sales_invoice_line_id.in_(part),
                _PLACEMENTS.c.is_deleted.is_(False),
                _RETURNS.c.is_deleted.is_(False),
                _RETURNS.c.status.in_(_COMPLETED),
            )
            .group_by(_PLACEMENTS.c.sales_invoice_line_id)
        ).all():
            bills[line_id]["gone"] += _d(quantity)
            bills[line_id]["left"] -= _d(taxable)


def _place(line: sa.Row[Any], bills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Set one return line's billed units against its note line's bills.

    Earliest bill first, each for the units it billed that are still out;
    the value up to what those units were still worth, the last bill taking
    the rest. The bills are updated as it goes.
    """
    quantity = _d(line.current_return_quantity)
    billed = quantity - min(_d(line.unbilled_quantity), quantity)
    if quantity <= _ZERO or billed <= _ZERO:
        return []
    share = billed / quantity
    net = _d(line.net_amount) * share
    taxable = net - _d(line.tax_amount) * share
    units = billed
    takes: list[tuple[dict[str, Any], Decimal, Decimal]] = []
    for bill in bills:
        room = max(bill["quantity"] - bill["gone"], _ZERO)
        if room <= _ZERO:
            continue
        took = min(units, room)
        takes.append((bill, took, max(bill["left"], _ZERO) * min(took / room, 1)))
        units -= took
        if units <= _ZERO:
            break
    if not takes:
        return []
    value = max(taxable, _ZERO)
    if units > _DUST:
        value = value * (billed - units) / billed
    rows: list[dict[str, Any]] = []
    rest = value
    for position, (bill, took, worth) in enumerate(takes):
        part = rest if position == len(takes) - 1 else min(rest, worth)
        rest -= part
        bill["gone"] += took
        bill["left"] -= part
        of_units = took / billed
        of_value = part / taxable if taxable > _ZERO else of_units
        entered = line.entered_quantity
        rows.append(
            {
                "id": uuid4(),
                # Stated, not left to the column's default: a store built by
                # ``create_all`` on SQLite keeps that default as text.
                "is_deleted": False,
                "sales_return_id": line.sales_return_id,
                "sales_return_line_id": line.id,
                "firm_id": line.firm_id,
                "sales_invoice_id": bill["invoice_id"],
                "sales_invoice_line_id": bill["line_id"],
                "quantity": took.quantize(_FOUR),
                "entered_quantity": (
                    None
                    if entered is None
                    else (_d(entered) * share * of_units).quantize(_FOUR)
                ),
                "conversion_factor": _d(line.conversion_factor) or Decimal("1"),
                "taxable_amount": part.quantize(_FOUR),
                "net_amount": (net * of_value).quantize(_FOUR),
            }
        )
    return rows


def _backfill(bind: sa.Connection, inspector: sa.Inspector) -> None:
    """Give every completed return off a note the placement it reads at today."""
    lines = _unplaced(bind)
    if not lines:
        return
    by_note = _bills_of(bind, list({line.source_document_line_id for line in lines}))
    bills = {bill["line_id"]: bill for found in by_note.values() for bill in found}
    if not bills:
        return
    _take_what_is_already_off(bind, inspector, bills)
    rows: list[dict[str, Any]] = []
    # Oldest first, as the reading in force until now took them.
    for line in sorted(
        lines,
        key=lambda item: (
            item.completed_at is None,
            str(item.completed_at or ""),
            str(item.created_at or ""),
            item.return_number,
            item.line_number,
        ),
    ):
        rows.extend(_place(line, by_note.get(line.source_document_line_id, [])))
    for part in _chunks(rows, 500):
        bind.execute(sa.insert(_PLACEMENTS), list(part))


def upgrade() -> None:
    """Create the table and place every completed return off a note."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # A store with no returns keeps no placements of them: the platform
    # store, once the firm-owned tables are pruned from it.
    if not inspector.has_table("sales_return_lines"):
        return
    _create(inspector)
    if inspector.has_table("sales_invoice_lines"):
        _backfill(bind, sa.inspect(bind))


def downgrade() -> None:
    """Drop the table; the split goes back to being worked out on each read."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
