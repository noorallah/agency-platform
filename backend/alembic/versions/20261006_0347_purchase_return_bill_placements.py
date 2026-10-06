"""Where a completed purchase return came off its supplier bills.

``purchase_return_bill_placements`` -- one row per return line and supplier
bill line: the billed units of the line placed on that bill line, and what
they claimed there before tax. Written when a return completes and removed
when it is cancelled (D-PRC-73).

A return raised off a goods receipt line names no bill, and the receipt line
may have been billed by several. Which bill each unit came off was worked out
again on every read, and a later return naming the first bill's own line
moved an earlier one onto the next bill after it had been valued: 2,171.20
was claimed from a supplier against bills of 1,699.20. Stored, every reader
agrees with what was posted.

**Backfill.** Every return already completed is placed here by the rule the
service now applies, in the order raised (return date, number, line): a line
off a bill on that bill line first and then the other standing bills of the
same receipt line, a line off a receipt on its bills earliest first; only
the billed part (quantity less ``unbilled_quantity``); the value shared by
units and never more to a bill line than it is still worth after approved
debit notes and the returns placed before it, what fits nowhere staying with
the last. Nothing is restated -- a return keeps the value it posted. A line
that already has rows is read from them and left alone, so a replay adds
only what is missing.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent. The reference
to ``firms`` is declared only where that table is in the same store.

Revision ID: 20261006_0347
Revises: 20261006_0346
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

revision: str = "20261006_0347"
down_revision: str | Sequence[str] | None = "20261006_0346"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "purchase_return_bill_placements"
_RETURNS = "purchase_returns"
_RETURN_LINES = "purchase_return_lines"
_BILLS = "purchase_invoices"
_BILL_LINES = "purchase_invoice_lines"
_NOTES = "debit_notes"
_NOTE_LINES = "debit_note_lines"

_ZERO = Decimal("0")
_FOUR = Decimal("0.0001")
_CHUNK = 5000


def _create(with_firms: bool) -> None:
    """Create the table, with the columns every ``BaseEntity`` table carries."""
    keys = [
        sa.ForeignKeyConstraint(
            ["purchase_return_id"],
            [f"{_RETURNS}.id"],
            name="FK_purchase_return_bill_placements_purchase_return_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_return_line_id"],
            [f"{_RETURN_LINES}.id"],
            name="FK_purchase_return_bill_placements_purchase_return_line_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_invoice_line_id"],
            [f"{_BILL_LINES}.id"],
            name="FK_purchase_return_bill_placements_purchase_invoice_line_id",
            ondelete="CASCADE",
        ),
    ]
    if with_firms:
        keys.append(
            sa.ForeignKeyConstraint(
                ["firm_id"],
                ["firms.id"],
                name="FK_purchase_return_bill_placements_firm_id",
            )
        )
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
        sa.Column("purchase_return_id", UUIDType(), nullable=False),
        sa.Column("purchase_return_line_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("purchase_invoice_line_id", UUIDType(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(18, 4), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_purchase_return_bill_placements"),
        *keys,
    )
    op.create_index(
        "IX_purchase_return_bill_placements_return", _TABLE, ["purchase_return_id"]
    )
    op.create_index(
        "IX_purchase_return_bill_placements_firm_bill_line",
        _TABLE,
        ["firm_id", "purchase_invoice_line_id"],
    )
    op.create_index(
        "ix_purchase_return_bill_placements_purchase_return_line_id",
        _TABLE,
        ["purchase_return_line_id"],
    )
    op.create_index("ix_purchase_return_bill_placements_firm_id", _TABLE, ["firm_id"])


def _chunks(ids: Sequence[Any]) -> Iterator[list[Any]]:
    """Yield the ids a few thousand at a time, under the driver's limit."""
    unique = list(dict.fromkeys(ids))
    for start in range(0, len(unique), _CHUNK):
        yield unique[start : start + _CHUNK]


def _decimal(value: object) -> Decimal:
    """Read a stored number."""
    return Decimal(str(value or 0))


def _goods_billed(line: sa.Row[Any]) -> Decimal:
    """Return what a bill line charged for its goods, before tax."""
    return (
        _decimal(line.gross_amount)
        - _decimal(line.discount_amount)
        - _decimal(line.bill_discount_amount)
        + _decimal(line.charges_amount)
    )


def _share_out(
    amount: Decimal, parts: Sequence[tuple[Decimal, Decimal]]
) -> list[Decimal]:
    """Share a value over bill lines by units, within what each is worth."""
    whole = sum((units for units, _ in parts), _ZERO)
    if not parts or whole <= _ZERO:
        return [_ZERO for _ in parts]
    shares = [min(amount * units / whole, limit) for units, limit in parts]
    left = amount - sum(shares, _ZERO)
    for index, (_, limit) in enumerate(parts):
        if left <= _ZERO:
            break
        more = min(limit - shares[index], left)
        if more > _ZERO:
            shares[index] += more
            left -= more
    if left > _ZERO:
        shares[-1] += left
    return shares


def _backfill(bind: sa.Connection) -> None:
    """Place every completed return that has no rows yet, in the order raised."""
    meta = sa.MetaData()
    returns = sa.Table(_RETURNS, meta, autoload_with=bind, resolve_fks=False)
    return_lines = sa.Table(_RETURN_LINES, meta, autoload_with=bind, resolve_fks=False)
    bills = sa.Table(_BILLS, meta, autoload_with=bind, resolve_fks=False)
    bill_lines = sa.Table(_BILL_LINES, meta, autoload_with=bind, resolve_fks=False)
    notes = sa.Table(_NOTES, meta, autoload_with=bind, resolve_fks=False)
    note_lines = sa.Table(_NOTE_LINES, meta, autoload_with=bind, resolve_fks=False)
    # Typed here, not reflected: the ids read above are written back as ids.
    placements = sa.table(
        _TABLE,
        sa.column("id", UUIDType()),
        sa.column("purchase_return_id", UUIDType()),
        sa.column("purchase_return_line_id", UUIDType()),
        sa.column("firm_id", UUIDType()),
        sa.column("purchase_invoice_line_id", UUIDType()),
        sa.column("quantity", sa.Numeric(18, 4)),
        sa.column("taxable_amount", sa.Numeric(18, 4)),
        sa.column("is_deleted", sa.Boolean()),
        sa.column("version", sa.Integer()),
    )
    # Read back as the driver gives them, like the ids of the tables above.
    placed_already = sa.table(
        _TABLE,
        sa.column("purchase_return_line_id"),
        sa.column("purchase_invoice_line_id"),
        sa.column("quantity"),
        sa.column("taxable_amount"),
        sa.column("is_deleted", sa.Boolean()),
    )

    backs = bind.execute(
        sa.select(
            return_lines.c.id,
            return_lines.c.purchase_return_id,
            return_lines.c.firm_id,
            return_lines.c.source_document_type,
            return_lines.c.source_document_line_id,
            return_lines.c.current_return_quantity,
            return_lines.c.unbilled_quantity,
            return_lines.c.net_amount,
            return_lines.c.tax_amount,
        )
        .select_from(
            return_lines.join(
                returns, returns.c.id == return_lines.c.purchase_return_id
            )
        )
        .where(
            return_lines.c.source_document_type.in_(
                ("PURCHASE_INVOICE", "GOODS_RECEIPT")
            ),
            return_lines.c.is_deleted.is_(False),
            returns.c.is_deleted.is_(False),
            returns.c.status.in_(("COMPLETED", "CLOSED")),
        )
        .order_by(
            returns.c.return_date.asc(),
            returns.c.return_number.asc(),
            return_lines.c.line_number.asc(),
        )
    ).all()
    if not backs:
        return

    # The bill lines named, then every standing bill line of the receipt
    # lines behind them and of the receipt lines returned against.
    standing = sa.and_(
        bill_lines.c.is_deleted.is_(False),
        bills.c.is_deleted.is_(False),
        bills.c.status.in_(("APPROVED", "CLOSED")),
    )
    columns = (
        bill_lines.c.id,
        bill_lines.c.source_document_type,
        bill_lines.c.source_document_line_id,
        bill_lines.c.current_invoice_quantity,
        bill_lines.c.gross_amount,
        bill_lines.c.discount_amount,
        bill_lines.c.bill_discount_amount,
        bill_lines.c.charges_amount,
    )
    joined = bill_lines.join(bills, bills.c.id == bill_lines.c.purchase_invoice_id)
    by_id: dict[Any, Any] = {}
    named_ids = [
        back.source_document_line_id
        for back in backs
        if back.source_document_type == "PURCHASE_INVOICE"
    ]
    for chunk in _chunks(named_ids):
        for line in bind.execute(
            sa.select(*columns).select_from(joined).where(bill_lines.c.id.in_(chunk))
        ).all():
            by_id[line.id] = line
    receipt_ids = [
        back.source_document_line_id
        for back in backs
        if back.source_document_type == "GOODS_RECEIPT"
    ] + [
        line.source_document_line_id
        for line in by_id.values()
        if line.source_document_type == "GOODS_RECEIPT"
        and line.source_document_line_id is not None
    ]
    families: dict[Any, list[Any]] = defaultdict(list)
    for chunk in _chunks(receipt_ids):
        for line in bind.execute(
            sa.select(*columns)
            .select_from(joined)
            .where(
                bill_lines.c.source_document_type == "GOODS_RECEIPT",
                bill_lines.c.source_document_line_id.in_(chunk),
                standing,
            )
            .order_by(
                bills.c.invoice_date.asc(),
                bills.c.invoice_number.asc(),
                bill_lines.c.line_number.asc(),
            )
        ).all():
            families[line.source_document_line_id].append(line)
            by_id.setdefault(line.id, line)

    claimed: dict[Any, Decimal] = defaultdict(lambda: _ZERO)
    quantity: dict[Any, Decimal] = defaultdict(lambda: _ZERO)
    taxable: dict[Any, Decimal] = defaultdict(lambda: _ZERO)
    stored: dict[Any, list[tuple[Any, Decimal, Decimal]]] = defaultdict(list)
    for chunk in _chunks(list(by_id)):
        for line_id, total in bind.execute(
            sa.select(
                note_lines.c.purchase_invoice_line_id,
                sa.func.coalesce(sa.func.sum(note_lines.c.taxable_amount), 0),
            )
            .select_from(
                note_lines.join(notes, notes.c.id == note_lines.c.debit_note_id)
            )
            .where(
                note_lines.c.purchase_invoice_line_id.in_(chunk),
                note_lines.c.is_deleted.is_(False),
                notes.c.is_deleted.is_(False),
                notes.c.status == "APPROVED",
            )
            .group_by(note_lines.c.purchase_invoice_line_id)
        ).all():
            claimed[line_id] = _decimal(total)
    for chunk in _chunks([back.id for back in backs]):
        for row in bind.execute(
            sa.select(
                placed_already.c.purchase_return_line_id,
                placed_already.c.purchase_invoice_line_id,
                placed_already.c.quantity,
                placed_already.c.taxable_amount,
            ).where(
                placed_already.c.purchase_return_line_id.in_(chunk),
                placed_already.c.is_deleted.is_(False),
            )
        ).all():
            stored[row.purchase_return_line_id].append(
                (
                    row.purchase_invoice_line_id,
                    _decimal(row.quantity),
                    _decimal(row.taxable_amount),
                )
            )

    rows: list[dict[str, Any]] = []
    for back in backs:
        if back.id in stored:
            for line_id, units, value in stored[back.id]:
                quantity[line_id] += units
                taxable[line_id] += value
            continue
        whole = _decimal(back.current_return_quantity)
        if whole <= _ZERO:
            continue
        units = whole - min(_decimal(back.unbilled_quantity), whole)
        if units <= _ZERO:
            continue
        worth = (_decimal(back.net_amount) - _decimal(back.tax_amount)) * units / whole
        if back.source_document_type == "PURCHASE_INVOICE":
            named = by_id.get(back.source_document_line_id)
            if named is None:
                continue
            family = (
                families.get(named.source_document_line_id, [])
                if named.source_document_type == "GOODS_RECEIPT"
                else []
            )
            order = [named, *(line for line in family if line.id != named.id)]
            last = named
        else:
            order = families.get(back.source_document_line_id, [])
            if not order:
                continue
            last = order[-1]
        placed: list[tuple[Any, Decimal]] = []
        left = units
        for line in order:
            if left <= _ZERO:
                break
            part = min(
                left, _decimal(line.current_invoice_quantity) - quantity[line.id]
            )
            if part > _ZERO:
                placed.append((line, part))
                left -= part
        if left > _ZERO:
            placed.append((last, left))
        limits = []
        for line, part in placed:
            room = _goods_billed(line) - claimed[line.id] - taxable[line.id]
            held = _decimal(line.current_invoice_quantity) - quantity[line.id]
            limits.append(
                room * min(part, held) / held
                if room > _ZERO and held > _ZERO
                else _ZERO
            )
        shares = [
            share.quantize(_FOUR)
            for share in _share_out(
                worth,
                [
                    (part, limit)
                    for (_, part), limit in zip(placed, limits, strict=True)
                ],
            )
        ]
        shares[-1] += worth.quantize(_FOUR) - sum(shares, _ZERO)
        for (line, part), value in zip(placed, shares, strict=True):
            quantity[line.id] += part
            taxable[line.id] += value
            rows.append(
                {
                    "id": uuid4(),
                    "purchase_return_id": back.purchase_return_id,
                    "purchase_return_line_id": back.id,
                    "firm_id": back.firm_id,
                    "purchase_invoice_line_id": line.id,
                    "quantity": part.quantize(_FOUR),
                    "taxable_amount": value,
                    # Stated, not left to the column default: a store built
                    # from the models spells that default as text.
                    "is_deleted": False,
                    "version": 1,
                }
            )
    for start in range(0, len(rows), 1000):
        bind.execute(sa.insert(placements), rows[start : start + 1000])


def upgrade() -> None:
    """Create the table where the store keeps purchase returns, and fill it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm stores only: the platform store holds no purchase returns.
    needed = (_RETURNS, _RETURN_LINES, _BILLS, _BILL_LINES)
    if not all(inspector.has_table(name) for name in needed):
        return
    if not inspector.has_table(_TABLE):
        _create(with_firms=inspector.has_table("firms"))
    if inspector.has_table(_NOTES) and inspector.has_table(_NOTE_LINES):
        _backfill(bind)


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
