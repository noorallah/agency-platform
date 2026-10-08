"""Where one serialised unit has been: its trail, read from its picks (PG-10).

Every document that moved a unit left a moved pick in
``document_line_serials``: the receipt it arrived on, the delivery notes it
left on, the sales returns it came back on, the purchase return that sent it
to the supplier, the transfers that took it to another warehouse, and the
opening stock it was counted in on day one. Read in order -- the receipt or
the opening stock first, since that is where the trail starts, then by when
each moved -- with each document's number, date and counterparty, one read
per document type.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import DocumentLineSerial
from app.batch_serial.schemas.batch_serial import (
    SerialResponse,
    SerialTrail,
    SerialTrailEvent,
)
from app.batch_serial.services.batch_serial_service import BatchSerialService
from app.batch_serial.services.serial_trail_service import (
    ARRIVALS,
    DELIVERY_NOTE,
    GOODS_RECEIPT,
    OPENING_STOCK,
    PURCHASE_RETURN,
    SALES_RETURN,
    STOCK_MOVE,
    STOCK_TRANSFER,
)
from app.common.report_names import customer_names, vendor_names
from app.core.utils.dates import as_utc, utc_now

#: (number, date, party id, whether the party is a supplier) per document.
_Header = tuple[str, date | None, UUID | None, bool]


def _headers(session: Session, wanted: dict[str, set[UUID]]) -> dict[UUID, _Header]:
    """Read each document's number, date and party, one read per type."""
    from app.delivery_note.models import DeliveryNote
    from app.goods_receipt.models import GoodsReceipt
    from app.inventory.models import InventoryTransaction, OpeningStockBatch
    from app.inventory.models.stock_transfer import StockTransfer
    from app.purchase_return.models import PurchaseReturn
    from app.sales_return.models import SalesReturn

    found: dict[UUID, _Header] = {}
    if wanted.get(GOODS_RECEIPT):
        for row_id, number, on, party in session.execute(
            select(
                GoodsReceipt.id,
                GoodsReceipt.grn_number,
                GoodsReceipt.receipt_date,
                GoodsReceipt.vendor_id,
            ).where(GoodsReceipt.id.in_(wanted[GOODS_RECEIPT]))
        ).all():
            found[row_id] = (number, on, party, True)
    if wanted.get(PURCHASE_RETURN):
        for row_id, number, on, party in session.execute(
            select(
                PurchaseReturn.id,
                PurchaseReturn.return_number,
                PurchaseReturn.return_date,
                PurchaseReturn.vendor_id,
            ).where(PurchaseReturn.id.in_(wanted[PURCHASE_RETURN]))
        ).all():
            found[row_id] = (number, on, party, True)
    if wanted.get(DELIVERY_NOTE):
        for row_id, number, on, party in session.execute(
            select(
                DeliveryNote.id,
                DeliveryNote.delivery_note_number,
                DeliveryNote.delivery_date,
                DeliveryNote.customer_id,
            ).where(DeliveryNote.id.in_(wanted[DELIVERY_NOTE]))
        ).all():
            found[row_id] = (number, on, party, False)
    if wanted.get(SALES_RETURN):
        for row_id, number, on, party in session.execute(
            select(
                SalesReturn.id,
                SalesReturn.return_number,
                SalesReturn.return_date,
                SalesReturn.customer_id,
            ).where(SalesReturn.id.in_(wanted[SALES_RETURN]))
        ).all():
            found[row_id] = (number, on, party, False)
    # The three below have no counterparty: the goods never left the firm.
    if wanted.get(STOCK_TRANSFER):
        for row_id, number, on in session.execute(
            select(
                StockTransfer.id,
                StockTransfer.transfer_number,
                StockTransfer.transfer_date,
            ).where(StockTransfer.id.in_(wanted[STOCK_TRANSFER]))
        ).all():
            found[row_id] = (number, on, None, False)
    if wanted.get(STOCK_MOVE):
        for row_id, number, on in session.execute(
            select(
                InventoryTransaction.id,
                InventoryTransaction.reference_number,
                InventoryTransaction.transaction_date,
            ).where(InventoryTransaction.id.in_(wanted[STOCK_MOVE]))
        ).all():
            found[row_id] = (number or "", on, None, False)
    if wanted.get(OPENING_STOCK):
        for row_id, number, on in session.execute(
            select(
                OpeningStockBatch.id,
                OpeningStockBatch.reference_number,
                OpeningStockBatch.posting_date,
            ).where(OpeningStockBatch.id.in_(wanted[OPENING_STOCK]))
        ).all():
            found[row_id] = (number, on, None, False)
    return found


def serial_trail(session: Session, *, firm_id: UUID, serial_id: UUID) -> SerialTrail:
    """Return one unit and the documents it moved on, the receipt first."""
    serial = BatchSerialService(session).get_serial(
        firm_scope=firm_id, serial_id=serial_id
    )
    picks = list(
        session.scalars(
            select(DocumentLineSerial).where(
                DocumentLineSerial.firm_id == firm_id,
                DocumentLineSerial.serial_id == serial.id,
                DocumentLineSerial.moved_at.is_not(None),
                DocumentLineSerial.is_deleted.is_(False),
            )
        ).all()
    )
    wanted: dict[str, set[UUID]] = defaultdict(set)
    for pick in picks:
        wanted[pick.document_type].add(pick.document_id)
    headers = _headers(session, wanted)
    suppliers = vendor_names(session, (h[2] for h in headers.values() if h[3]))
    customers = customer_names(session, (h[2] for h in headers.values() if not h[3]))

    def order(pick: DocumentLineSerial) -> tuple[int, datetime]:
        """Put where the unit arrived first, then the rest as it moved."""
        # Read through `as_utc`: SQLite hands back naive what PostgreSQL
        # hands back aware.
        moved = as_utc(pick.moved_at) if pick.moved_at is not None else utc_now()
        return (0 if pick.document_type in ARRIVALS else 1, moved)

    events: list[SerialTrailEvent] = []
    for pick in sorted(picks, key=order):
        number, on, party, supplier = headers.get(
            pick.document_id, ("", None, None, False)
        )
        names = suppliers if supplier else customers
        events.append(
            SerialTrailEvent(
                document_type=pick.document_type,
                document_id=pick.document_id,
                document_number=number,
                document_date=on,
                party_name=names.get(party, "") if party is not None else "",
                line_number=pick.line_number,
                moved_at=pick.moved_at,
            )
        )
    return SerialTrail(serial=SerialResponse.model_validate(serial), events=events)
