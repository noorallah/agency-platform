"""Margin by lot: what each lot sold for and what it cost (L2 step 10).

`docs/design/LOT_COST_DESIGN.md`, section 5, "Margin reports, sales
analysis". One row per product and lot over a period: the quantity billed
from it, the taxable value that quantity was sold for, what its units cost
when they left, and the margin between.

**Where the figures come from.** A bill line ships a delivery note line, and
each lot that line took is a ``delivery_note_line_batches`` row carrying the
cost its units left with (L2 step 5). A bill may take only part of what its
note line delivered, so the lot's quantity and cost are scaled by the share
billed -- the same share the bill line's own ``cost_amount`` is pro-rated by.
The line's taxable value (net of its own discount, its share of the bill
discount and of freight, since all three sit inside ``net_amount``) is split
across its lots by each lot's share of the quantity.

Returns completed in the period take quantity, value and cost back from the
lots they refilled (``sales_return_line_batches``, L2 step 6) -- the billed
part only, as the sales analysis takes it: goods that came back before they
were billed were never in billed sales.

**A cost is reported only where every row behind it carried one.** A lot row
written before the lots kept their cost has none, and None is not zero: the
lot then shows its quantity and value with cost and margin blank.

**A firm on Average.** Its batch-tracked items record lots on dispatch too,
so it sees one row per batch, each at the average cost its units left with;
items not tracked by batch take no lot and are not listed.

Grouped in SQL; nothing is loaded row by row to be summed.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.delivery_note.models import DeliveryNoteLineBatch
from app.inventory.services.lots import costs_by_lot
from app.products.models import Product
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_return.billing import billed_part
from app.sales_return.models import (
    SalesReturn,
    SalesReturnLine,
    SalesReturnLineBatch,
)

ZERO = Decimal("0")
_PAISE = Decimal("0.01")
_UNITS = Decimal("0.0001")
#: Bills that count as sales, and returns that count as having come back --
#: the sales analysis's own states.
BILLED = ("APPROVED", "CLOSED")
RETURNED = ("COMPLETED", "CLOSED")

BY_LOT_NOTE = "Each lot at the cost its units left with."
AVERAGE_NOTE = (
    "This firm costs its stock at average: each row is a batch its "
    "batch-tracked items left from, at the average cost its units left with. "
    "Items not tracked by batch are not listed."
)


class LotMarginRecord(BaseModel):
    """One product's lot over the period: sold, returned, worth and cost."""

    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    product_code: str
    product_name: str
    batch_id: UUID
    #: Our own running reference for the lot.
    lot_reference: str
    #: The batch printed on the goods; None where they carry none.
    batch_number: str | None
    received_on: date | None
    #: Stock units billed from the lot, less those returned into it.
    quantity: Decimal
    #: Taxable value, net of every discount, apportioned to the lot.
    sales_value: Decimal
    #: What the lot's units cost when they left. Omitted (None) for a caller
    #: who may not see cost, and where any row behind it recorded none.
    cost: Decimal | None = None
    margin: Decimal | None = None
    #: Margin as a percentage of the sales value.
    margin_percent: Decimal | None = None


@dataclass
class _Lot:
    """The running figures for one (product, lot)."""

    quantity: Decimal = ZERO
    value: Decimal = ZERO
    cost: Decimal = ZERO
    uncosted: int = 0
    labels: tuple[Any, ...] = field(default_factory=tuple)


def _dec(value: object) -> Decimal:
    """Read a summed figure, which SQLite may hand back as a float."""
    return ZERO if value is None else Decimal(str(value))


class LotMarginService:
    """Report what each lot was sold for against what it cost."""

    def __init__(self, session: Session) -> None:
        """Hold the session the report reads on."""
        self._session = session

    def note(self, firm_id: UUID) -> str:
        """Say how the firm's rows are costed, by lot or at average."""
        return BY_LOT_NOTE if costs_by_lot(self._session, firm_id) else AVERAGE_NOTE

    def report(
        self,
        firm_id: UUID,
        *,
        from_date: date,
        to_date: date,
        show_cost: bool,
    ) -> list[LotMarginRecord]:
        """Return one row per product and lot sold or returned in the period.

        ``show_cost`` false omits cost, margin and margin percent rather than
        zeroing them (``PRODUCT_VIEW_COST_PRICE``).
        """
        lots: dict[tuple[UUID, UUID], _Lot] = {}
        for sign, rows in (
            (1, self._sold(firm_id, from_date, to_date)),
            (-1, self._returned(firm_id, from_date, to_date)),
        ):
            for row in rows:
                (
                    product_id,
                    code,
                    name,
                    batch_id,
                    reference,
                    number,
                    printed,
                    received_on,
                    quantity,
                    value,
                    cost,
                    uncosted,
                ) = row
                lot = lots.setdefault((product_id, batch_id), _Lot())
                lot.labels = (
                    code,
                    name,
                    reference,
                    number if printed else None,
                    received_on,
                )
                lot.quantity += sign * _dec(quantity)
                lot.value += sign * _dec(value)
                lot.cost += sign * _dec(cost)
                lot.uncosted += int(uncosted or 0)
        records = [
            self._record(product_id, batch_id, lot, show_cost=show_cost)
            for (product_id, batch_id), lot in lots.items()
        ]
        return sorted(
            records,
            key=lambda item: (
                item.product_code,
                item.received_on is None,
                item.received_on or date.min,
                item.lot_reference,
            ),
        )

    @staticmethod
    def _record(
        product_id: UUID, batch_id: UUID, lot: _Lot, *, show_cost: bool
    ) -> LotMarginRecord:
        """Shape one lot's figures, with cost only where it may be shown."""
        code, name, reference, number, received_on = lot.labels
        value = lot.value.quantize(_PAISE)
        cost = margin = percent = None
        if show_cost and not lot.uncosted:
            cost = lot.cost.quantize(_PAISE)
            margin = value - cost
            percent = (margin * 100 / value).quantize(_PAISE) if value else None
        return LotMarginRecord(
            product_id=product_id,
            product_code=code,
            product_name=name,
            batch_id=batch_id,
            lot_reference=reference,
            batch_number=number,
            received_on=received_on,
            quantity=lot.quantity.quantize(_UNITS),
            sales_value=value,
            cost=cost,
            margin=margin,
            margin_percent=percent,
        )

    @staticmethod
    def _labels() -> list[Any]:
        """Return the columns that name a row, grouped on as well as shown."""
        return [
            Product.id,
            Product.code,
            Product.name,
            BatchRecord.id,
            BatchRecord.lot_reference,
            BatchRecord.batch_number,
            BatchRecord.has_printed_batch,
            BatchRecord.received_on,
        ]

    def _sold(self, firm_id: UUID, from_date: date, to_date: date) -> Sequence[Any]:
        """Return each lot's billed quantity, value and cost over the period."""
        lot = DeliveryNoteLineBatch
        line = SalesInvoiceLine
        totals = (
            select(
                lot.delivery_note_line_id.label("note_line_id"),
                func.sum(lot.quantity).label("quantity"),
            )
            .where(lot.firm_id == firm_id, lot.is_deleted.is_(False))
            .group_by(lot.delivery_note_line_id)
            .subquery()
        )
        # The share of the note line this bill line takes.
        share = case(
            (
                line.delivered_quantity > 0,
                line.current_invoice_quantity / line.delivered_quantity,
            ),
            else_=0,
        )
        portion = case(
            (totals.c.quantity > 0, lot.quantity / totals.c.quantity), else_=0
        )
        labels = self._labels()
        statement = (
            select(
                *labels,
                func.sum(lot.quantity * share),
                func.sum((line.net_amount - line.tax_amount) * portion),
                func.sum(lot.cost_amount * share),
                func.sum(case((lot.cost_amount.is_(None), 1), else_=0)),
            )
            .select_from(line)
            .join(SalesInvoice, SalesInvoice.id == line.sales_invoice_id)
            .join(lot, lot.delivery_note_line_id == line.source_document_line_id)
            .join(totals, totals.c.note_line_id == lot.delivery_note_line_id)
            .join(BatchRecord, BatchRecord.id == lot.batch_id)
            .join(Product, Product.id == line.product_id)
            .where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status.in_(BILLED),
                SalesInvoice.invoice_date >= from_date,
                SalesInvoice.invoice_date <= to_date,
                line.is_deleted.is_(False),
                line.source_document_type == "DELIVERY_NOTE",
                lot.is_deleted.is_(False),
            )
            .group_by(*labels)
        )
        return self._session.execute(statement).all()

    def _returned(self, firm_id: UUID, from_date: date, to_date: date) -> Sequence[Any]:
        """Return each lot's billed share of returns completed in the period."""
        lot = SalesReturnLineBatch
        line = SalesReturnLine
        totals = (
            select(
                lot.sales_return_line_id.label("return_line_id"),
                func.sum(lot.quantity).label("quantity"),
            )
            .where(lot.firm_id == firm_id, lot.is_deleted.is_(False))
            .group_by(lot.sales_return_line_id)
            .subquery()
        )
        portion = case(
            (totals.c.quantity > 0, lot.quantity / totals.c.quantity), else_=0
        )
        labels = self._labels()
        statement = (
            select(
                *labels,
                func.sum(billed_part(lot.quantity)),
                func.sum(billed_part(line.net_amount - line.tax_amount) * portion),
                func.sum(billed_part(lot.cost_amount)),
                func.sum(case((lot.cost_amount.is_(None), 1), else_=0)),
            )
            .select_from(line)
            .join(SalesReturn, SalesReturn.id == line.sales_return_id)
            .join(lot, lot.sales_return_line_id == line.id)
            .join(totals, totals.c.return_line_id == line.id)
            .join(BatchRecord, BatchRecord.id == lot.batch_id)
            .join(Product, Product.id == line.product_id)
            .where(
                SalesReturn.firm_id == firm_id,
                SalesReturn.is_deleted.is_(False),
                SalesReturn.status.in_(RETURNED),
                SalesReturn.return_date >= from_date,
                SalesReturn.return_date <= to_date,
                line.is_deleted.is_(False),
                lot.is_deleted.is_(False),
            )
            .group_by(*labels)
        )
        return self._session.execute(statement).all()
