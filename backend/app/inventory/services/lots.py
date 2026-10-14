"""The lot: which firms cost by it, and the reference each one is given.

`docs/design/LOT_COST_DESIGN.md`. A lot is a ``batches`` row. Every batch
carries our own running reference, whatever the firm's costing method, and a
firm that costs by lot makes one such row for every purchase line.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.inventory.models import StockLotSettings

#: What ``stock_lot_settings.costing_method`` reads for a firm costing by lot.
FIRM_BY_LOT = "BY_LOT"

#: The lot's own series. Batches that existed before it were numbered
#: ``B000001`` onwards by migration; the prefix keeps the two apart.
LOT_SERIES = DocumentTypeSpec(
    code="STOCK_LOT",
    name="Stock Lot",
    description="The reference every lot of stock is given",
    category="INVENTORY",
    module="inventory",
    prefix="LOT",
    states=(DocumentStateSpec("OPEN", "Open", 1, is_terminal=True),),
)


@dataclass(frozen=True, slots=True)
class LotSource:
    """What made a lot, kept on it so the lot traces back to its paper."""

    document_type: str
    document_id: UUID
    line_id: UUID
    document_number: str
    received_on: date


def costs_by_lot(session: Session, firm_id: UUID) -> bool:
    """Say whether the firm costs its stock by lot; no row means Average."""
    method = session.scalar(
        select(StockLotSettings.costing_method).where(
            StockLotSettings.firm_id == firm_id,
            StockLotSettings.is_deleted.is_(False),
        )
    )
    return method == FIRM_BY_LOT


class LotNumbering(TransactionalDocumentService):
    """Issue the next lot reference, inside the caller's work.

    Reserves under the series row's lock and flushes; it never commits, so a
    receipt that is refused afterwards takes its references back with it.
    """

    DOCUMENT = LOT_SERIES

    def next_reference(self, *, firm_id: UUID, on: date, actor_id: UUID) -> str:
        """Return the reference the firm's next lot is recorded under.

        Args:
            firm_id: The owning firm.
            on: The day the lot arrived, which picks the financial year.
            actor_id: The user whose work makes the lot.

        """
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        return self._issue_number(
            rule,
            typed=None,
            number_column=BatchRecord.lot_reference,
            firm_id=firm_id,
            document_date=on,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
