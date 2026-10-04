"""Serial numbers captured on a goods receipt line (PG-10, backlog 86 #11).

A serial-tracked product's trail starts where it arrives. The storekeeper
types, scans or range-fills the serials on the receipt line while it is a
draft -- held in ``goods_receipt_line_serials``, and allowed to be incomplete
-- and completing the receipt refuses until there is one per unit received,
then creates each unit AVAILABLE in the receipt's warehouse, its first pick
the receipt line. Cancelling the receipt removes them, unless one has moved
since.

The units themselves, their status and their picks belong to
``app/batch_serial`` (:class:`SerialTrailService`); this module only keeps
what a receipt line typed and asks that service to act on it. It flushes and
never commits: the receipt's own transaction does that once.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.batch_serial.services.serial_trail_service import (
    GOODS_RECEIPT,
    LineRef,
    SerialTrailService,
    clean_serials,
    serial_key,
)
from app.core.exceptions import ValidationError
from app.goods_receipt.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    GoodsReceiptLineSerial,
)
from app.inventory.models import InventoryTransaction
from app.products.models import Product

#: The most units one range fill may produce, and the most serials one
#: receipt line may carry -- a container of phones, not a warehouse.
MAX_SERIALS_PER_LINE = 10000

_CHUNK = 5000


def expand_range(*, prefix: str, start: int, count: int, width: int) -> list[str]:
    """Return ``count`` serials from ``start``, zero-padded to ``width`` digits.

    ``prefix="IMEI", start=98, count=3, width=4`` gives IMEI0098, IMEI0099 and
    IMEI0100. A number wider than ``width`` is written in full rather than cut.
    """
    if count < 1 or count > MAX_SERIALS_PER_LINE:
        raise ValidationError(
            f"A range fills between 1 and {MAX_SERIALS_PER_LINE} serial numbers."
        )
    return [
        f"{prefix.strip()}{number:0{width}d}" for number in range(start, start + count)
    ]


def _line_ref(receipt: GoodsReceipt, line: GoodsReceiptLine) -> LineRef:
    """Describe a receipt line to the serial trail."""
    return LineRef(
        firm_id=receipt.firm_id,
        document_type=GOODS_RECEIPT,
        document_id=receipt.id,
        line_id=line.id,
        line_number=line.line_number,
        product_id=line.product_id,
    )


def received_units(line: GoodsReceiptLine) -> Decimal:
    """Return how many stock units the line puts on the shelf.

    The accepted quantity and the free goods that came with it, in the unit
    stock is counted in -- free units are units, and each carries its own
    number exactly as a paid one does.
    """
    return (
        Decimal(str(line.accepted_quantity)) + Decimal(str(line.free_quantity))
    ) * Decimal(str(line.conversion_factor or 1))


class ReceiptSerials:
    """Keep what a receipt line typed, and turn it into units on completion."""

    def __init__(self, session: Session) -> None:
        """Bind to the receipt's unit of work."""
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
                    GoodsReceiptLineSerial.goods_receipt_line_id,
                    GoodsReceiptLineSerial.serial_number,
                )
                .where(
                    GoodsReceiptLineSerial.goods_receipt_line_id.in_(
                        ids[start : start + _CHUNK]
                    ),
                    GoodsReceiptLineSerial.is_deleted.is_(False),
                )
                .order_by(
                    GoodsReceiptLineSerial.goods_receipt_line_id,
                    GoodsReceiptLineSerial.position,
                )
            ).all():
                found[line_id].append(serial)
        return found

    def tracked(self, product_ids: Iterable[UUID]) -> set[UUID]:
        """Return which of these products carry a serial per unit."""
        ids = set(product_ids)
        if not ids:
            return set()
        return set(
            self._session.scalars(
                select(Product.id).where(
                    Product.id.in_(ids), Product.track_serial.is_(True)
                )
            ).all()
        )

    # ---- writing a draft ----------------------------------------------

    def replace(
        self,
        receipt: GoodsReceipt,
        line: GoodsReceiptLine,
        serials: Sequence[str],
        *,
        actor_id: UUID,
    ) -> None:
        """Make ``serials`` what this line has typed.

        Blanks are dropped and each number trimmed. Refused: a number typed
        twice, one the firm already gave to a live unit, and any number at all
        on a product nobody tracks by serial -- naming one there is a mistake,
        not a preference. The count is not checked: a draft may be part-typed.
        """
        ref = _line_ref(receipt, line)
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
        self._trail.refuse_taken(receipt.firm_id, cleaned, label=label)
        self.clear_lines([line.id])
        for position, serial in enumerate(cleaned, start=1):
            self._session.add(
                GoodsReceiptLineSerial(
                    firm_id=receipt.firm_id,
                    goods_receipt_id=receipt.id,
                    goods_receipt_line_id=line.id,
                    position=position,
                    serial_number=serial,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def clear_lines(self, line_ids: Iterable[UUID]) -> None:
        """Forget what these lines typed."""
        ids = set(line_ids)
        if ids:
            self._session.execute(
                delete(GoodsReceiptLineSerial).where(
                    GoodsReceiptLineSerial.goods_receipt_line_id.in_(ids)
                )
            )

    def refuse_repeats(
        self, receipt: GoodsReceipt, lines: Sequence[GoodsReceiptLine]
    ) -> None:
        """Refuse one number typed on two lines of the same receipt."""
        numbers = {line.id: line.line_number for line in lines}
        seen: dict[str, int] = {}
        for line_id, serials in self.typed(numbers).items():
            for serial in serials:
                key = serial_key(serial)
                first = seen.setdefault(key, numbers[line_id])
                if first != numbers[line_id]:
                    raise ValidationError(
                        f"Serial {serial} is entered on line {first} and on "
                        f"line {numbers[line_id]} of {receipt.grn_number}."
                    )

    # ---- completing and cancelling ------------------------------------

    def check_counts(
        self, receipt: GoodsReceipt, lines: Sequence[GoodsReceiptLine]
    ) -> None:
        """Refuse completion unless every serial-tracked line has one per unit."""
        tracked = self.tracked(line.product_id for line in lines)
        typed = self.typed(line.id for line in lines)
        self.refuse_repeats(receipt, lines)
        for line in lines:
            if line.product_id not in tracked:
                continue
            ref = _line_ref(receipt, line)
            entered = typed.get(line.id, [])
            self._trail.assert_count(
                ref,
                len(entered),
                received_units(line),
                verb="receives",
                where="goods receipt",
                entered="entered",
                add="enter",
            )
            self._trail.refuse_taken(
                receipt.firm_id,
                entered,
                label=ref.label(self._trail.product(line.product_id)),
            )

    def receive(
        self,
        receipt: GoodsReceipt,
        line: GoodsReceiptLine,
        movement: InventoryTransaction,
        *,
        actor_id: UUID,
    ) -> None:
        """Create the units a serial-tracked line brought in, on completion."""
        if not self._trail.is_serialised(line.product_id):
            return
        serials = self.typed([line.id]).get(line.id, [])
        if not serials:
            return
        self._trail.receive(
            _line_ref(receipt, line),
            serials,
            movement=movement,
            batch_id=line.batch_id,
            reference=receipt.grn_number,
            actor_id=actor_id,
        )

    def refuse_cancel(self, receipt: GoodsReceipt) -> None:
        """Refuse to cancel a receipt one of whose units has moved since."""
        self._trail.refuse_unreceive(
            self._trail.received_picks(self._line_ids(receipt)),
            reference=receipt.grn_number,
        )

    def withdraw(self, receipt: GoodsReceipt, *, actor_id: UUID) -> None:
        """Remove the units a cancelled receipt brought in."""
        self._trail.unreceive_units(
            self._trail.received_picks(self._line_ids(receipt)),
            reference=receipt.grn_number,
            actor_id=actor_id,
        )

    def _line_ids(self, receipt: GoodsReceipt) -> list[UUID]:
        """Return the receipt's live line ids."""
        return list(
            self._session.scalars(
                select(GoodsReceiptLine.id).where(
                    GoodsReceiptLine.goods_receipt_id == receipt.id,
                    GoodsReceiptLine.is_deleted.is_(False),
                )
            ).all()
        )
