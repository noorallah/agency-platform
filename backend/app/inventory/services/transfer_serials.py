"""The serial numbers that move with a transfer (D-STK-40).

A serial records which warehouse its unit is in, and a dispatch refuses a
unit that *is not in the warehouse this line ships from*. Neither transfer
moved it, so serial-numbered goods sent to another warehouse could not be
shipped from there until each serial was edited by hand.

Both transfers now name their units, picked from the source's shelf the way a
delivery note picks them:

* the **one-step transfer** has no document, so its "line" is its outbound
  movement; the units land at the destination AVAILABLE in the same step;
* the **transfer document** picks while a draft; dispatch refuses until there
  is one per unit and puts them IN_TRANSIT; the receipt lands the good ones
  AVAILABLE and the damaged ones DAMAGED at the destination, and marks what
  never arrived LOST; cancelling a dispatched transfer puts them back.

The units, their status and their picks belong to ``app/batch_serial``
(:class:`SerialTrailService`). Nothing here commits.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.batch_serial.schemas.batch_serial import PickedSerial, SerialStatus
from app.batch_serial.services.serial_trail_service import (
    STOCK_MOVE,
    STOCK_TRANSFER,
    LineRef,
    Pick,
    SerialTrailService,
)
from app.core.exceptions import ValidationError
from app.inventory.models import InventoryTransaction
from app.inventory.models.stock_transfer import StockTransfer, StockTransferLine


def _whole(quantity: Decimal) -> int:
    """Return a quantity as a count of units."""
    return int(Decimal(str(quantity)).to_integral_value())


class TransferSerials:
    """Name the units a transfer moves, and move them with the stock."""

    def __init__(self, session: Session) -> None:
        """Bind to the transfer's unit of work."""
        self._session = session
        self._trail = SerialTrailService(session)

    # ---- the one-step transfer ----------------------------------------

    def move(
        self,
        *,
        serial_ids: Sequence[UUID],
        quantity: Decimal,
        outbound: InventoryTransaction,
        inbound: InventoryTransaction,
        actor_id: UUID,
    ) -> None:
        """Take the named units to where a one-step transfer put the goods.

        A serial-tracked product crossing to another warehouse names one unit
        per unit moved. A move between two places of one warehouse may name
        none: the units stay in the warehouse they are recorded in.
        """
        ref = LineRef(
            firm_id=outbound.firm_id,
            document_type=STOCK_MOVE,
            document_id=outbound.id,
            line_id=outbound.id,
            line_number=1,
            product_id=outbound.product_id,
        )
        if not serial_ids and (
            outbound.warehouse_id == inbound.warehouse_id
            or not self._trail.is_serialised(outbound.product_id)
        ):
            return
        self._trail.replace_picks(
            ref,
            serial_ids,
            check=SerialTrailService.on_shelf(outbound.warehouse_id),
            actor_id=actor_id,
        )
        picks = self._trail.line_picks(outbound.id)
        self._trail.assert_count(
            ref, len(picks), quantity, verb="moves", where="transfer"
        )
        self._trail.move_units(
            ref,
            picks,
            status=SerialStatus.AVAILABLE,
            action="serial_number.transferred",
            reference=outbound.reference_number,
            actor_id=actor_id,
            movement=inbound,
            place=True,
        )

    # ---- the transfer document ----------------------------------------

    @staticmethod
    def _ref(row: StockTransfer, line: StockTransferLine) -> LineRef:
        """Describe a transfer line to the serial trail."""
        return LineRef(
            firm_id=row.firm_id,
            document_type=STOCK_TRANSFER,
            document_id=row.id,
            line_id=line.id,
            line_number=line.line_number,
            product_id=line.product_id,
        )

    def picked(self, line_ids: Sequence[UUID]) -> dict[UUID, list[PickedSerial]]:
        """Return what each line names, shaped for a line's response."""
        return self._trail.picked_serials(line_ids)

    def clear(self, row: StockTransfer) -> None:
        """Forget a draft's picks before its lines are rewritten."""
        self._trail.clear_document(row.id)

    def pick(
        self,
        row: StockTransfer,
        lines: Sequence[StockTransferLine],
        stated: Sequence[Sequence[UUID]],
        *,
        actor_id: UUID,
    ) -> None:
        """Record the units each draft line names, off the source's shelf.

        A draft may name fewer than it sends; dispatch asks for the rest. One
        unit on two lines is refused here, where it can still be corrected.
        """
        seen: dict[UUID, int] = {}
        for line, serial_ids in zip(lines, stated, strict=True):
            for serial_id in serial_ids:
                first = seen.setdefault(serial_id, line.line_number)
                if first != line.line_number:
                    raise ValidationError(
                        f"A serial number is picked on line {first} and on "
                        f"line {line.line_number} of this transfer."
                    )
            if serial_ids:
                self._trail.replace_picks(
                    self._ref(row, line),
                    serial_ids,
                    check=SerialTrailService.on_shelf(row.from_warehouse_id),
                    actor_id=actor_id,
                )

    def check_dispatch(self, row: StockTransfer, line: StockTransferLine) -> list[Pick]:
        """Return the units a line dispatches, refusing unless they can go."""
        ref = self._ref(row, line)
        picks = self._trail.line_picks(line.id)
        if not self._trail.is_serialised(line.product_id):
            return picks
        self._trail.assert_count(
            ref, len(picks), line.quantity, verb="sends", where="transfer"
        )
        self._trail.check_issuable(ref, picks, warehouse_id=row.from_warehouse_id)
        return picks

    def dispatch(
        self,
        row: StockTransfer,
        line: StockTransferLine,
        picks: Sequence[Pick],
        *,
        movement: InventoryTransaction,
        actor_id: UUID,
    ) -> None:
        """Put a dispatched line's units in transit."""
        if picks:
            self._trail.move_units(
                self._ref(row, line),
                picks,
                status=SerialStatus.IN_TRANSIT,
                action="serial_number.in_transit",
                reference=row.transfer_number,
                actor_id=actor_id,
                movement=movement,
            )

    def recall(
        self, row: StockTransfer, line: StockTransferLine, *, actor_id: UUID
    ) -> None:
        """Put a cancelled transfer's units back on the source's shelf."""
        picks = self._in_transit(row, line, doing="cancelled")
        if picks:
            self._trail.move_units(
                self._ref(row, line),
                picks,
                status=SerialStatus.AVAILABLE,
                action="serial_number.transfer_cancelled",
                reference=row.transfer_number,
                actor_id=actor_id,
                moved="clear",
            )

    def receive(
        self,
        row: StockTransfer,
        line: StockTransferLine,
        *,
        movement: InventoryTransaction,
        short: Decimal,
        damaged: Decimal,
        short_ids: Sequence[UUID],
        damaged_ids: Sequence[UUID],
        actor_id: UUID,
    ) -> None:
        """Land a received line's units, each as what became of it.

        The destination says *which* units never came and which came damaged:
        a count would leave nobody able to say which serial was lost. A line
        dispatched before transfers named their units carries none, and is
        received as a quantity the way it was sent.
        """
        ref = self._ref(row, line)
        label = ref.label(self._trail.product(line.product_id))
        picks = self._in_transit(row, line, doing="received")
        if not picks:
            if short_ids or damaged_ids:
                raise ValidationError(
                    f"{label}: this line names no serial numbers, so none can "
                    "be marked short or damaged."
                )
            return
        on_line = {serial.id for _pick, serial in picks}
        for name, ids, count in (
            ("short", short_ids, short),
            ("damaged", damaged_ids, damaged),
        ):
            if len(set(ids)) != len(ids):
                raise ValidationError(
                    f"{label}: a serial number is named twice as {name}."
                )
            if set(ids) - on_line:
                raise ValidationError(
                    f"{label}: a serial number named as {name} is not one this "
                    "line sent."
                )
            if len(ids) != _whole(count):
                raise ValidationError(
                    f"{label}: {_whole(count)} unit(s) arrived {name}, so name "
                    f"{_whole(count)} of the line's serial numbers as {name} "
                    f"({len(ids)} named)."
                )
        if set(short_ids) & set(damaged_ids):
            raise ValidationError(
                f"{label}: a unit that never arrived cannot also be damaged."
            )
        lost = [p for p in picks if p[1].id in set(short_ids)]
        broken = [p for p in picks if p[1].id in set(damaged_ids)]
        apart = set(short_ids) | set(damaged_ids)
        good = [p for p in picks if p[1].id not in apart]
        if lost:
            self._trail.move_units(
                ref,
                lost,
                status=SerialStatus.LOST,
                action="serial_number.lost_in_transit",
                reference=row.transfer_number,
                actor_id=actor_id,
                moved="keep",
            )
        for share, status, action in (
            (broken, SerialStatus.DAMAGED, "serial_number.received_damaged"),
            (good, SerialStatus.AVAILABLE, "serial_number.transferred"),
        ):
            if share:
                self._trail.move_units(
                    ref,
                    share,
                    status=status,
                    action=action,
                    reference=row.transfer_number,
                    actor_id=actor_id,
                    movement=movement,
                    place=True,
                    moved="keep",
                )

    def _in_transit(
        self, row: StockTransfer, line: StockTransferLine, *, doing: str
    ) -> list[Pick]:
        """Return a dispatched line's units, each still on its way."""
        picks = [
            (pick, serial)
            for pick, serial in self._trail.line_picks(line.id)
            if pick.moved_at is not None
        ]
        ref = self._ref(row, line)
        label = ref.label(self._trail.product(line.product_id))
        for _pick, serial in picks:
            if serial.status != SerialStatus.IN_TRANSIT.value:
                raise ValidationError(
                    f"{label}: serial {serial.serial_number} is {serial.status}, "
                    f"not IN_TRANSIT, so the transfer cannot be {doing}."
                )
        return picks
