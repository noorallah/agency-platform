"""Where one lot has been: its page, read from its movements (L2 step 11).

`docs/design/LOT_COST_DESIGN.md`, section 6 row 11: the lot's page with its
trace -- the receipt it came on, the supplier's bill, the sales, the returns
-- and its cost shown only to somebody allowed to see cost.

Every unit that entered or left a lot is an ``inventory_transactions`` row
carrying the lot's ``batch_id``, so the movements are the trail. A movement
names its document by type and number, not by id, so each document is found
by its number, one read per document type, then the parties by name in one
read each -- the shape of ``serial_history``. Two kinds of event move no
stock and are read beside them: the supplier's bill of the receipt line the
lot came on, and the sales bill of each delivery note line that drew from it.

**The quantity is what the valuation counts.** ``owned_quantity_delta``
where a movement records one, else ``current_quantity_delta`` -- the rule
``InventoryService`` values a movement by. A movement that changed neither
(a reservation, or its release) is not listed; a cost correction is, at
zero, because it changed what the lot is worth.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.batch_serial.models.batch_serial import BatchRecord
from app.batch_serial.schemas.batch_serial import LotTrail, LotTrailEvent
from app.batch_serial.services.batch_serial_service import BatchSerialService
from app.common.report_names import customer_names, vendor_names
from app.core.utils.dates import as_utc
from app.core.utils.money import quantize_money

ZERO = Decimal("0")

GOODS_RECEIPT = "GOODS_RECEIPT"
OPENING_STOCK = "OPENING_STOCK"
PURCHASE_INVOICE = "PURCHASE_INVOICE"
DELIVERY_NOTE = "DELIVERY_NOTE"
SALES_INVOICE = "SALES_INVOICE"
SALES_RETURN = "SALES_RETURN"
PURCHASE_RETURN = "PURCHASE_RETURN"
STOCK_TRANSFER = "STOCK_TRANSFER"
ADJUSTMENT = "ADJUSTMENT"
REPACK = "REPACK"
COST_CORRECTION = "COST_CORRECTION"
OTHER = "OTHER"

#: Bills that stand: the states the sales analysis and the lot margin count.
BILLED = ("APPROVED", "CLOSED")

#: The document a movement's ``reference_type`` names, where the firm keeps
#: one under that number.
_DOCUMENTS = {
    GOODS_RECEIPT: GOODS_RECEIPT,
    OPENING_STOCK: OPENING_STOCK,
    PURCHASE_INVOICE: PURCHASE_INVOICE,
    DELIVERY_NOTE: DELIVERY_NOTE,
    SALES_INVOICE: SALES_INVOICE,
    SALES_RETURN: SALES_RETURN,
    PURCHASE_RETURN: PURCHASE_RETURN,
    STOCK_TRANSFER: STOCK_TRANSFER,
    "TRANSFER": STOCK_TRANSFER,
    REPACK: REPACK,
}
#: What a movement is shown as where its reference names no such document.
_BY_TYPE = {
    GOODS_RECEIPT: GOODS_RECEIPT,
    OPENING_STOCK: OPENING_STOCK,
    SALES_RETURN: SALES_RETURN,
    "ADJUSTMENT": ADJUSTMENT,
    "WRITE_OFF": ADJUSTMENT,
    "TRANSFER_IN": STOCK_TRANSFER,
    "TRANSFER_OUT": STOCK_TRANSFER,
}
#: Movements that change what the lot is worth and move no units.
_VALUE_ONLY = {"COST_CORRECTION", "LANDED_COST"}
_SUPPLIER_SIDE = {GOODS_RECEIPT, PURCHASE_INVOICE, PURCHASE_RETURN}
_CUSTOMER_SIDE = {DELIVERY_NOTE, SALES_INVOICE, SALES_RETURN}
#: Within one day: the movement, then the bill, then the cost the bill moved.
_MOVEMENT, _BILL, _CORRECTION = 0, 1, 2

#: (id, date, party id) per (document type, number).
_Header = tuple[UUID, date | None, UUID | None]


@dataclass
class _Event:
    """One trail entry before its party is named, with what orders it."""

    document_type: str
    document_id: UUID | None
    document_number: str
    document_date: date | None
    party_id: UUID | None
    quantity: Decimal
    cost_amount: Decimal | None
    line_number: int | None
    rank: int
    created_at: datetime
    #: The document type a movement's number is looked up under, if any.
    lookup: str | None = None


def _dec(value: object) -> Decimal | None:
    """Read a stored or summed figure, which SQLite may hand back as a float."""
    return None if value is None else Decimal(str(value))


def _base_type(transaction_type: str) -> str:
    """Return the movement type a reversal reverses (``X_REVERSAL`` is X)."""
    while transaction_type.endswith("_REVERSAL"):
        transaction_type = transaction_type.removesuffix("_REVERSAL")
    return transaction_type


def _headers(
    session: Session, firm_id: UUID, wanted: dict[str, set[str]]
) -> dict[tuple[str, str], _Header]:
    """Find each document by its number, one read per document type."""
    from app.delivery_note.models import DeliveryNote
    from app.goods_receipt.models import GoodsReceipt
    from app.inventory.models import OpeningStockBatch
    from app.inventory.models.repack import Repack
    from app.inventory.models.stock_transfer import StockTransfer
    from app.purchase_invoice.models import PurchaseInvoice
    from app.purchase_return.models import PurchaseReturn
    from app.sales_invoice.models import SalesInvoice
    from app.sales_return.models import SalesReturn

    reads: dict[str, tuple[Any, Any, Any, Any, Any]] = {
        GOODS_RECEIPT: (
            GoodsReceipt,
            GoodsReceipt.grn_number,
            GoodsReceipt.receipt_date,
            GoodsReceipt.vendor_id,
            GoodsReceipt.firm_id,
        ),
        PURCHASE_INVOICE: (
            PurchaseInvoice,
            PurchaseInvoice.invoice_number,
            PurchaseInvoice.invoice_date,
            PurchaseInvoice.vendor_id,
            PurchaseInvoice.firm_id,
        ),
        PURCHASE_RETURN: (
            PurchaseReturn,
            PurchaseReturn.return_number,
            PurchaseReturn.return_date,
            PurchaseReturn.vendor_id,
            PurchaseReturn.firm_id,
        ),
        DELIVERY_NOTE: (
            DeliveryNote,
            DeliveryNote.delivery_note_number,
            DeliveryNote.delivery_date,
            DeliveryNote.customer_id,
            DeliveryNote.firm_id,
        ),
        SALES_INVOICE: (
            SalesInvoice,
            SalesInvoice.invoice_number,
            SalesInvoice.invoice_date,
            SalesInvoice.customer_id,
            SalesInvoice.firm_id,
        ),
        SALES_RETURN: (
            SalesReturn,
            SalesReturn.return_number,
            SalesReturn.return_date,
            SalesReturn.customer_id,
            SalesReturn.firm_id,
        ),
        # The three below have no counterparty: the goods never left the firm.
        STOCK_TRANSFER: (
            StockTransfer,
            StockTransfer.transfer_number,
            StockTransfer.transfer_date,
            None,
            StockTransfer.firm_id,
        ),
        OPENING_STOCK: (
            OpeningStockBatch,
            OpeningStockBatch.reference_number,
            OpeningStockBatch.posting_date,
            None,
            OpeningStockBatch.firm_id,
        ),
        REPACK: (
            Repack,
            Repack.repack_number,
            Repack.repack_date,
            None,
            Repack.firm_id,
        ),
    }
    found: dict[tuple[str, str], _Header] = {}
    for kind, numbers in wanted.items():
        if not numbers or kind not in reads:
            continue
        model, number, on, party, firm = reads[kind]
        columns = [model.id, number, on] + ([party] if party is not None else [])
        for row in session.execute(
            select(*columns).where(
                firm == firm_id,
                number.in_(numbers),
                model.is_deleted.is_(False),
            )
        ).all():
            found[(kind, row[1])] = (row[0], row[2], row[3] if len(row) > 3 else None)
    return found


def _movements(
    session: Session, firm_id: UUID, batch_id: UUID
) -> tuple[list[_Event], dict[str, set[str]]]:
    """Read the lot's movements, and the document numbers they name."""
    from app.inventory.models import InventoryTransaction, StockLedgerEntry

    move = InventoryTransaction
    rows = session.execute(
        select(
            move.transaction_type,
            move.reference_type,
            move.reference_number,
            move.transaction_date,
            move.current_quantity_delta,
            move.owned_quantity_delta,
            move.created_at,
            StockLedgerEntry.total_cost,
        )
        .outerjoin(StockLedgerEntry, StockLedgerEntry.transaction_id == move.id)
        .where(
            move.firm_id == firm_id,
            move.batch_id == batch_id,
            move.is_deleted.is_(False),
        )
    ).all()
    events: list[_Event] = []
    wanted: dict[str, set[str]] = defaultdict(set)
    for kind, reference, number, on, current, owned, created, cost in rows:
        base = _base_type(kind)
        quantity = _dec(owned if owned is not None else current) or ZERO
        value_only = base in _VALUE_ONLY
        if quantity == ZERO and not value_only:
            continue
        document = _DOCUMENTS.get(reference)
        if document is not None:
            wanted[document].add(number)
        shown = COST_CORRECTION if value_only else document or _BY_TYPE.get(base, OTHER)
        events.append(
            _Event(
                document_type=shown,
                # Resolved once the headers are read, through ``lookup``.
                document_id=None,
                document_number=number or "",
                document_date=on,
                party_id=None,
                quantity=ZERO if value_only else quantity,
                cost_amount=_dec(cost),
                line_number=None,
                rank=_CORRECTION if value_only else _MOVEMENT,
                created_at=as_utc(created),
                lookup=document,
            )
        )
    return events, wanted


def _supplier_bills(
    session: Session, firm_id: UUID, batch: BatchRecord
) -> list[_Event]:
    """Return the bill lines that bill a receipt line the lot came on."""
    from app.goods_receipt.models import GoodsReceiptLine
    from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine

    line = PurchaseInvoiceLine
    receipt_lines = select(GoodsReceiptLine.id).where(
        GoodsReceiptLine.firm_id == firm_id,
        GoodsReceiptLine.batch_id == batch.id,
        GoodsReceiptLine.is_deleted.is_(False),
    )
    billing: ColumnElement[bool] = line.source_document_line_id.in_(receipt_lines)
    if (
        batch.source_document_type == GOODS_RECEIPT
        and batch.source_document_line_id is not None
    ):
        billing = or_(
            billing, line.source_document_line_id == batch.source_document_line_id
        )
    rows = session.execute(
        select(
            PurchaseInvoice.id,
            PurchaseInvoice.invoice_number,
            PurchaseInvoice.invoice_date,
            PurchaseInvoice.vendor_id,
            PurchaseInvoice.created_at,
            line.line_number,
            line.net_amount - line.tax_amount,
        )
        .join(PurchaseInvoice, PurchaseInvoice.id == line.purchase_invoice_id)
        .where(
            PurchaseInvoice.firm_id == firm_id,
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status.in_(BILLED),
            line.is_deleted.is_(False),
            line.source_document_type == GOODS_RECEIPT,
            billing,
        )
    ).all()
    return [
        _Event(
            document_type=PURCHASE_INVOICE,
            document_id=bill_id,
            document_number=number,
            document_date=on,
            party_id=vendor_id,
            quantity=ZERO,
            cost_amount=_dec(amount),
            line_number=line_number,
            rank=_BILL,
            created_at=as_utc(created),
        )
        for bill_id, number, on, vendor_id, created, line_number, amount in rows
    ]


def _sales_bills(session: Session, firm_id: UUID, batch_id: UUID) -> list[_Event]:
    """Return the bill lines that bill a delivery note line drawn from the lot.

    The join ``LotMarginService`` makes: a bill line continues a note line,
    and the note line's lot rows say which lots it drew. The line's value
    before tax is split across its lots by quantity, as the margin splits it.
    """
    from app.delivery_note.models import DeliveryNoteLineBatch
    from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

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
    portion = case((totals.c.quantity > 0, lot.quantity / totals.c.quantity), else_=0)
    rows = session.execute(
        select(
            SalesInvoice.id,
            SalesInvoice.invoice_number,
            SalesInvoice.invoice_date,
            SalesInvoice.customer_id,
            SalesInvoice.created_at,
            line.line_number,
            func.sum((line.net_amount - line.tax_amount) * portion),
        )
        .select_from(line)
        .join(SalesInvoice, SalesInvoice.id == line.sales_invoice_id)
        .join(lot, lot.delivery_note_line_id == line.source_document_line_id)
        .join(totals, totals.c.note_line_id == lot.delivery_note_line_id)
        .where(
            SalesInvoice.firm_id == firm_id,
            SalesInvoice.is_deleted.is_(False),
            SalesInvoice.status.in_(BILLED),
            line.is_deleted.is_(False),
            line.source_document_type == DELIVERY_NOTE,
            lot.batch_id == batch_id,
            lot.is_deleted.is_(False),
        )
        .group_by(
            SalesInvoice.id,
            SalesInvoice.invoice_number,
            SalesInvoice.invoice_date,
            SalesInvoice.customer_id,
            SalesInvoice.created_at,
            line.id,
            line.line_number,
        )
    ).all()
    return [
        _Event(
            document_type=SALES_INVOICE,
            document_id=bill_id,
            document_number=number,
            document_date=on,
            party_id=customer_id,
            quantity=ZERO,
            # A share by quantity divides, so the sum runs to as many places
            # as the database likes; the trail shows a document's four
            # (D-STK-75).
            cost_amount=None if amount is None else quantize_money(amount),
            line_number=line_number,
            rank=_BILL,
            created_at=as_utc(created),
        )
        for bill_id, number, on, customer_id, created, line_number, amount in rows
    ]


def lot_trail(
    session: Session, *, firm_id: UUID, batch_id: UUID, show_cost: bool
) -> LotTrail:
    """Return one lot, where it came from, and every document since.

    ``show_cost`` false leaves every cost figure out (None) rather than
    zeroing it (``PRODUCT_VIEW_COST_PRICE``).
    """
    from app.inventory.models import BatchValuation

    service = BatchSerialService(session)
    batch = service.get_batch(firm_scope=firm_id, batch_id=batch_id)
    movements, wanted = _movements(session, firm_id, batch.id)
    headers = _headers(session, firm_id, wanted)
    for event in movements:
        kind = event.lookup
        header = headers.get((kind, event.document_number)) if kind else None
        if header is None:
            continue
        event.document_id, on, party = header
        event.document_date = on or event.document_date
        if event.document_type in _SUPPLIER_SIDE | _CUSTOMER_SIDE:
            event.party_id = party
    events = (
        movements
        + _supplier_bills(session, firm_id, batch)
        + _sales_bills(session, firm_id, batch.id)
    )
    suppliers = vendor_names(
        session, (e.party_id for e in events if e.document_type in _SUPPLIER_SIDE)
    )
    customers = customer_names(
        session, (e.party_id for e in events if e.document_type in _CUSTOMER_SIDE)
    )
    # The arrival is the first movement into the lot; everything else follows
    # by its date, the movement before the bill before the cost it moved.
    arrivals = [e for e in movements if e.quantity > ZERO]
    arrival = min(arrivals, key=lambda e: e.created_at) if arrivals else None

    def order(event: _Event) -> tuple[int, date, int, datetime]:
        """Put the arrival first, then the rest by day and kind."""
        return (
            0 if event is arrival else 1,
            event.document_date or date.min,
            event.rank,
            event.created_at,
        )

    unit_cost = None
    if show_cost:
        unit_cost = _dec(
            session.scalar(
                select(BatchValuation.unit_cost).where(
                    BatchValuation.batch_id == batch.id,
                    BatchValuation.is_deleted.is_(False),
                )
            )
        )
    return LotTrail(
        batch=service.batch_response(batch, firm_scope=firm_id),
        lot_reference=batch.lot_reference,
        has_printed_batch=batch.has_printed_batch,
        received_on=batch.received_on,
        source_type=batch.source_document_type,
        unit_cost=unit_cost,
        events=[
            LotTrailEvent(
                document_type=event.document_type,
                document_id=event.document_id,
                document_number=event.document_number,
                document_date=event.document_date,
                party_name=(
                    None
                    if event.party_id is None
                    else (
                        suppliers
                        if event.document_type in _SUPPLIER_SIDE
                        else customers
                    ).get(event.party_id)
                ),
                quantity=event.quantity,
                cost_amount=event.cost_amount if show_cost else None,
                line_number=event.line_number,
            )
            for event in sorted(events, key=order)
        ],
    )
