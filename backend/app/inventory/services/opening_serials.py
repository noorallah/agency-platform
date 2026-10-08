"""Serial numbers typed on an opening stock line (D-STK-40).

Day-one stock of a serial-numbered product is units like any other. The
storekeeper types or scans them on the opening stock line while the document
is a draft -- held in ``opening_stock_line_serials``, and allowed to be
incomplete -- and posting creates each unit AVAILABLE in the document's
warehouse, its first pick the opening stock line, which is where its trail
starts. This is what ``app/goods_receipt/serials.py`` does for a receipt.

A line that names no serial at all still posts as a quantity: stores that
took their opening stock before this could be typed are in that state
already, and their units are entered on Serial Numbers. A line that names
some must name one per unit.

The units, their status and their picks belong to ``app/batch_serial``
(:class:`SerialTrailService`); this module keeps what a line typed and asks
that service to act on it. It flushes and never commits.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.batch_serial.services.serial_trail_service import (
    OPENING_STOCK,
    LineRef,
    SerialTrailService,
    clean_serials,
    serial_key,
)
from app.core.exceptions import ValidationError
from app.inventory.models import (
    InventoryTransaction,
    OpeningStockBatch,
    OpeningStockLine,
    OpeningStockLineSerial,
)
from app.products.models import Product

#: The most serials one opening stock line may carry.
MAX_SERIALS_PER_LINE = 10000

_CHUNK = 5000


def _line_ref(batch: OpeningStockBatch, line: OpeningStockLine) -> LineRef:
    """Describe an opening stock line to the serial trail."""
    return LineRef(
        firm_id=batch.firm_id,
        document_type=OPENING_STOCK,
        document_id=batch.id,
        line_id=line.id,
        line_number=line.line_number,
        product_id=line.product_id,
    )


class OpeningSerials:
    """Keep what an opening stock line typed, and make the units on posting."""

    def __init__(self, session: Session) -> None:
        """Bind to the document's unit of work."""
        self._session = session
        self._trail = SerialTrailService(session)

    # ---- reads ---------------------------------------------------------

    def typed(self, line_ids: Iterable[UUID]) -> dict[UUID, list[str]]:
        """Return each line's typed serials in the order they were typed."""
        ids = sorted(set(line_ids))
        found: dict[UUID, list[str]] = defaultdict(list)
        for start in range(0, len(ids), _CHUNK):
            for line_id, serial in self._session.execute(
                select(
                    OpeningStockLineSerial.opening_stock_line_id,
                    OpeningStockLineSerial.serial_number,
                )
                .where(
                    OpeningStockLineSerial.opening_stock_line_id.in_(
                        ids[start : start + _CHUNK]
                    ),
                    OpeningStockLineSerial.is_deleted.is_(False),
                )
                .order_by(
                    OpeningStockLineSerial.opening_stock_line_id,
                    OpeningStockLineSerial.position,
                )
            ).all():
                found[line_id].append(serial)
        return found

    def tracked(self, product_ids: Iterable[UUID]) -> set[UUID]:
        """Return which of these products carry a serial per unit."""
        ids = sorted(set(product_ids))
        found: set[UUID] = set()
        for start in range(0, len(ids), _CHUNK):
            found.update(
                self._session.scalars(
                    select(Product.id).where(
                        Product.id.in_(ids[start : start + _CHUNK]),
                        Product.track_serial.is_(True),
                    )
                ).all()
            )
        return found

    # ---- writing a draft ----------------------------------------------

    def replace(
        self,
        batch: OpeningStockBatch,
        line: OpeningStockLine,
        serials: Sequence[str],
        *,
        actor_id: UUID,
    ) -> None:
        """Make ``serials`` what this line has typed.

        Blanks are dropped and each number trimmed. Refused: a number typed
        twice, one the firm already gave to a live unit, and any number at all
        on a product nobody tracks by serial. The count is not checked: a
        draft may be part-typed.
        """
        ref = _line_ref(batch, line)
        label = ref.label(self._trail.product(line.product_id))
        cleaned = clean_serials(serials, label=label)
        if len(cleaned) > MAX_SERIALS_PER_LINE:
            raise ValidationError(
                f"{label}: a line carries at most {MAX_SERIALS_PER_LINE} serial "
                "numbers."
            )
        if cleaned and not self._trail.is_serialised(line.product_id):
            raise ValidationError(
                f"{label}: this product is not serial-tracked, so its lines "
                "take no serial numbers."
            )
        self._trail.refuse_taken(batch.firm_id, cleaned, label=label)
        for position, serial in enumerate(cleaned, start=1):
            self._session.add(
                OpeningStockLineSerial(
                    firm_id=batch.firm_id,
                    opening_stock_batch_id=batch.id,
                    opening_stock_line_id=line.id,
                    position=position,
                    serial_number=serial,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def clear_batch(self, batch_id: UUID) -> None:
        """Forget what a draft's lines typed, before they are rewritten."""
        self._session.execute(
            delete(OpeningStockLineSerial).where(
                OpeningStockLineSerial.opening_stock_batch_id == batch_id
            )
        )

    def refuse_repeats(
        self, batch: OpeningStockBatch, lines: Sequence[OpeningStockLine]
    ) -> None:
        """Refuse one number typed on two lines of the same document."""
        numbers = {line.id: line.line_number for line in lines}
        seen: dict[str, int] = {}
        for line_id, serials in self.typed(numbers).items():
            for serial in serials:
                key = serial_key(serial)
                first = seen.setdefault(key, numbers[line_id])
                if first != numbers[line_id]:
                    raise ValidationError(
                        f"Serial {serial} is entered on line {first} and on "
                        f"line {numbers[line_id]} of {batch.reference_number}."
                    )

    # ---- posting -------------------------------------------------------

    def receive(
        self,
        batch: OpeningStockBatch,
        line: OpeningStockLine,
        movement: InventoryTransaction,
        *,
        units: Decimal,
        batch_id: UUID | None,
        actor_id: UUID,
    ) -> None:
        """Create the units a posted line named, one per unit of its stock.

        ``units`` is the line's quantity in the unit stock is counted in: a
        line entered as two boxes of ten names twenty serials.
        """
        serials = self.typed([line.id]).get(line.id, [])
        if not serials:
            return
        ref = _line_ref(batch, line)
        self._trail.assert_count(
            ref,
            len(serials),
            units,
            verb="brings in",
            where="opening stock line",
            entered="entered",
            add="enter",
        )
        self._trail.receive(
            ref,
            serials,
            movement=movement,
            batch_id=batch_id,
            reference=batch.reference_number,
            actor_id=actor_id,
        )
