"""Which serialised units a document line moves, and what moving them does.

A serial number's status was never moved by anything: a delivery note shipped
two mixer grinders and all five serials on the shelf stayed ``AVAILABLE``
(D-STK-4). The owner's decision (2026-09-18) is that the storekeeper picks the
units. A delivery note line for a serial-tracked product names which serials
are going; dispatch refuses until the count matches what leaves, and marks
each one ``SOLD``. A sales return names which of the units sold on its source
line are coming back, and completing it makes them ``AVAILABLE`` again.

This service owns the picks (``document_line_serials``) and the status moves.
The two documents call it inside their own transactions and never commit
through it: it flushes, and the caller commits once.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import DocumentLineSerial, SerialNumber
from app.batch_serial.schemas.batch_serial import PickedSerial, SerialStatus
from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.dates import as_utc, utc_now
from app.inventory.models import InventoryTransaction
from app.products.models import Product

DELIVERY_NOTE = "DELIVERY_NOTE"
SALES_RETURN = "SALES_RETURN"


@dataclass(frozen=True)
class LineRef:
    """The document line a pick belongs to, and what it is shipping."""

    firm_id: UUID
    document_type: str
    document_id: UUID
    line_id: UUID
    line_number: int
    product_id: UUID

    def label(self, product: Product | None) -> str:
        """Name the line the way a refusal has to: number and product code."""
        code = getattr(product, "code", None) or str(self.product_id)
        return f"Line {self.line_number} ({code})"


#: A rule of the calling document about one unit, returning why it may not be
#: named on the line, or None when it may.
SerialCheck = Callable[[SerialNumber], str | None]

#: One unit a line names: the pick row and the serial it names.
Pick = tuple[DocumentLineSerial, SerialNumber]


def _count(quantity: Decimal) -> int | None:
    """Return a quantity as a whole number of units, or None if it is not one."""
    value = Decimal(str(quantity))
    if value != value.to_integral_value():
        return None
    return int(value)


def _units(count: int) -> str:
    """Say "1 serial number" or "2 serial numbers"."""
    return f"{count} serial number" + ("" if count == 1 else "s")


class SerialTrailService:
    """Record which units a line names and move their status with the stock."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the caller's unit of work."""
        self._session = session

    # ---- reads ---------------------------------------------------------

    def product(self, product_id: UUID) -> Product | None:
        """Return the product a line ships, deleted or not."""
        return self._session.get(Product, product_id)

    def is_serialised(self, product_id: UUID) -> bool:
        """Say whether every unit of this product carries its own serial."""
        product = self.product(product_id)
        return bool(product is not None and product.track_serial)

    def picks(self, line_ids: Iterable[UUID]) -> dict[UUID, list[Pick]]:
        """Return each line's picks with their serials, in serial order."""
        ids = set(line_ids)
        found: dict[UUID, list[Pick]] = defaultdict(list)
        if not ids:
            return found
        rows = self._session.execute(
            select(DocumentLineSerial, SerialNumber)
            .join(SerialNumber, SerialNumber.id == DocumentLineSerial.serial_id)
            .where(
                DocumentLineSerial.document_line_id.in_(ids),
                DocumentLineSerial.is_deleted.is_(False),
            )
            .order_by(SerialNumber.serial_number.asc())
        ).all()
        for pick, serial in rows:
            found[pick.document_line_id].append((pick, serial))
        return found

    def line_picks(self, line_id: UUID) -> list[Pick]:
        """Return one line's picks with their serials, in serial order."""
        return self.picks([line_id]).get(line_id, [])

    def picked_serials(
        self, line_ids: Iterable[UUID]
    ) -> dict[UUID, list[PickedSerial]]:
        """Return what each line names, shaped for a line's response."""
        return {
            line_id: [
                PickedSerial(
                    serial_id=serial.id,
                    serial_number=serial.serial_number,
                    status=serial.status,
                )
                for _pick, serial in rows
            ]
            for line_id, rows in self.picks(line_ids).items()
        }

    def picks_by_line_number(self, document_id: UUID) -> dict[int, list[UUID]]:
        """Return a document's picks keyed by line number.

        A document whose lines are deleted and re-inserted on every save --
        the sales return -- carries its picks across by number, because the
        line ids it had a moment ago are gone.
        """
        found: dict[int, list[UUID]] = defaultdict(list)
        for pick in self._session.scalars(
            select(DocumentLineSerial).where(
                DocumentLineSerial.document_id == document_id,
                DocumentLineSerial.is_deleted.is_(False),
            )
        ).all():
            found[pick.line_number].append(pick.serial_id)
        return found

    def last_dispatch(
        self, serial_ids: Iterable[UUID]
    ) -> dict[UUID, DocumentLineSerial]:
        """Return the delivery-note line each unit most recently left on.

        A unit can be sold, returned and sold again, so "was it dispatched on
        this note" is not enough to take it back against that note: only the
        latest dispatch says who has it now.
        """
        ids = set(serial_ids)
        latest: dict[UUID, DocumentLineSerial] = {}
        if not ids:
            return latest
        for pick in self._session.scalars(
            select(DocumentLineSerial).where(
                DocumentLineSerial.serial_id.in_(ids),
                DocumentLineSerial.document_type == DELIVERY_NOTE,
                DocumentLineSerial.moved_at.is_not(None),
                DocumentLineSerial.is_deleted.is_(False),
            )
        ).all():
            held = latest.get(pick.serial_id)
            # Read through `as_utc`: one side may have been set in this
            # session (aware) and the other read back from SQLite (naive).
            if held is None or (
                pick.moved_at is not None
                and held.moved_at is not None
                and as_utc(pick.moved_at) > as_utc(held.moved_at)
            ):
                latest[pick.serial_id] = pick
        return latest

    def sold_serials(self, *, firm_id: UUID, product_id: UUID) -> list[SerialNumber]:
        """Return every unit of a product that is out with a customer."""
        return list(
            self._session.scalars(
                select(SerialNumber)
                .where(
                    SerialNumber.firm_id == firm_id,
                    SerialNumber.product_id == product_id,
                    SerialNumber.status == SerialStatus.SOLD.value,
                    SerialNumber.is_deleted.is_(False),
                )
                .order_by(SerialNumber.serial_number.asc())
            ).all()
        )

    # ---- picking -------------------------------------------------------

    def replace_picks(
        self,
        line: LineRef,
        serial_ids: Sequence[UUID],
        *,
        check: SerialCheck,
        actor_id: UUID,
    ) -> None:
        """Make ``serial_ids`` the units this line names.

        Refuses a unit named twice, a unit of another product or firm, and a
        unit the calling document's own rule turns away -- ``check`` says
        why, in words that name the unit. A product nobody tracks by serial
        takes none: naming one there is a mistake, not a preference.
        """
        product = self.product(line.product_id)
        label = line.label(product)
        seen: set[UUID] = set()
        for serial_id in serial_ids:
            if serial_id in seen:
                raise ValidationError(
                    f"{label}: a serial number is picked twice on this line."
                )
            seen.add(serial_id)
        if serial_ids and not (product is not None and product.track_serial):
            raise ValidationError(
                f"{label}: this product is not serial-tracked, so its lines "
                "take no serial numbers."
            )
        serials = (
            {
                row.id: row
                for row in self._session.scalars(
                    select(SerialNumber).where(
                        SerialNumber.id.in_(seen),
                        SerialNumber.firm_id == line.firm_id,
                        SerialNumber.is_deleted.is_(False),
                    )
                ).all()
            }
            if seen
            else {}
        )
        for serial_id in serial_ids:
            serial = serials.get(serial_id)
            if serial is None:
                raise ValidationError(
                    f"{label}: serial number {serial_id} was not found in this firm."
                )
            if serial.product_id != line.product_id:
                raise ValidationError(
                    f"{label}: serial {serial.serial_number} belongs to another "
                    "product."
                )
            problem = check(serial)
            if problem is not None:
                raise ValidationError(
                    f"{label}: serial {serial.serial_number} {problem}"
                )
        self.clear_lines([line.line_id])
        for serial_id in serial_ids:
            self._session.add(
                DocumentLineSerial(
                    firm_id=line.firm_id,
                    serial_id=serial_id,
                    document_type=line.document_type,
                    document_id=line.document_id,
                    document_line_id=line.line_id,
                    line_number=line.line_number,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def clear_lines(self, line_ids: Iterable[UUID]) -> None:
        """Forget what these lines picked. Only ever before anything moved."""
        ids = set(line_ids)
        if not ids:
            return
        self._session.execute(
            delete(DocumentLineSerial).where(
                DocumentLineSerial.document_line_id.in_(ids),
                DocumentLineSerial.moved_at.is_(None),
            )
        )

    def clear_document(self, document_id: UUID) -> None:
        """Forget every pick of a document whose lines are being rewritten."""
        self._session.execute(
            delete(DocumentLineSerial).where(
                DocumentLineSerial.document_id == document_id,
                DocumentLineSerial.moved_at.is_(None),
            )
        )

    # ---- moving --------------------------------------------------------

    def assert_count(
        self,
        line: LineRef,
        picked: int,
        quantity: Decimal,
        *,
        verb: str,
        where: str,
    ) -> None:
        """Refuse unless one serial is named per unit moving.

        ``verb`` is what the line does with the units ("ships", "brings back")
        and ``where`` is the document the storekeeper picks them on.
        """
        label = line.label(self.product(line.product_id))
        units = _count(quantity)
        if units is None:
            raise ValidationError(
                f"{label} {verb} {quantity} of a serial-tracked product; each "
                "unit carries its own serial number, so the quantity has to be "
                "a whole number."
            )
        if picked == units:
            return
        if picked < units:
            raise ValidationError(
                f"{label} {verb} {units} serial-tracked units but "
                f"{_units(picked)} {'is' if picked == 1 else 'are'} picked: "
                f"pick {units - picked} more on the {where}."
            )
        raise ValidationError(
            f"{label} {verb} {units} serial-tracked units but {_units(picked)} "
            f"are picked: remove {picked - units} on the {where}."
        )

    def check_issuable(
        self, line: LineRef, picks: Sequence[Pick], *, warehouse_id: UUID
    ) -> None:
        """Refuse a unit that cannot leave on this line any more.

        Checked again at dispatch rather than trusted from the save: a unit
        picked on two draft notes is available to both until the first one
        ships, and the second must then be refused by name.
        """
        label = line.label(self.product(line.product_id))
        for _pick, serial in picks:
            if serial.status != SerialStatus.AVAILABLE.value:
                raise ValidationError(
                    f"{label}: serial {serial.serial_number} is {serial.status}, "
                    "not AVAILABLE, so it cannot be dispatched."
                )
            if serial.warehouse_id != warehouse_id:
                raise ValidationError(
                    f"{label}: serial {serial.serial_number} is not in the "
                    "warehouse this line ships from."
                )

    @staticmethod
    def deal(picks: Sequence[Pick], quantities: Sequence[Decimal]) -> list[list[Pick]]:
        """Deal a line's units out across the movements that carry them.

        A line that spans batches posts one movement per batch, so each
        movement takes as many units as it moves, in order, and the last one
        takes whatever is left.
        """
        queue = list(picks)
        shares: list[list[Pick]] = []
        for index, quantity in enumerate(quantities):
            last = index == len(quantities) - 1
            share: list[Pick] = []
            while queue and (last or Decimal(len(share)) < abs(quantity)):
                share.append(queue.pop(0))
            shares.append(share)
        return shares

    @staticmethod
    def single_serial(share: Sequence[Pick], quantity: Decimal) -> UUID | None:
        """Name the unit a movement carried, when it carried exactly one.

        ``inventory_transactions.serial_id`` holds one serial, so a movement
        of several units cannot name them there; the picks list them instead.
        """
        if len(share) == 1 and abs(Decimal(str(quantity))) == 1:
            return share[0][1].id
        return None

    def mark_sold(
        self,
        line: LineRef,
        share: Sequence[Pick],
        *,
        movement_id: UUID,
        owner: str,
        reference: str,
        actor_id: UUID,
    ) -> None:
        """Mark the units one dispatch movement carried SOLD."""
        moved_at = utc_now()
        for pick, serial in share:
            before: dict[str, object] = {
                "status": serial.status,
                "current_owner": serial.current_owner,
            }
            serial.status = SerialStatus.SOLD.value
            serial.current_owner = owner or serial.current_owner
            serial.updated_by = actor_id
            pick.inventory_transaction_id = movement_id
            pick.moved_at = moved_at
            pick.updated_by = actor_id
            record_audit(
                self._session,
                action="serial_number.sold",
                entity_type="serial_number",
                entity_id=serial.id,
                actor_id=actor_id,
                firm_id=line.firm_id,
                before_data=before,
                after_data={
                    "status": serial.status,
                    "current_owner": serial.current_owner,
                    "document": reference,
                    "serial_number": serial.serial_number,
                },
            )
        self._session.flush()

    def check_receivable(
        self, line: LineRef, picks: Sequence[Pick], *, eligible: SerialCheck
    ) -> None:
        """Refuse a unit that cannot come back on this return line any more.

        Checked again at completion: two draft returns can name the same
        unit, and only the first to complete may take it.
        """
        label = line.label(self.product(line.product_id))
        for _pick, serial in picks:
            problem = eligible(serial)
            if problem is not None:
                raise ValidationError(
                    f"{label}: serial {serial.serial_number} {problem}"
                )

    def mark_returned(
        self,
        line: LineRef,
        picks: Sequence[Pick],
        *,
        movement: InventoryTransaction,
        reference: str,
        actor_id: UUID,
    ) -> None:
        """Put a returned line's units back on the shelf as AVAILABLE.

        They land where the return's movement put the goods -- its warehouse,
        branch and stock row -- which need not be where they left from.
        """
        moved_at = utc_now()
        for pick, serial in picks:
            before: dict[str, object] = {
                "status": serial.status,
                "current_owner": serial.current_owner,
                "warehouse_id": str(serial.warehouse_id or ""),
            }
            serial.status = SerialStatus.AVAILABLE.value
            serial.current_owner = None
            serial.warehouse_id = movement.warehouse_id
            serial.branch_id = movement.branch_id
            serial.inventory_id = movement.inventory_id
            serial.updated_by = actor_id
            pick.inventory_transaction_id = movement.id
            pick.moved_at = moved_at
            pick.updated_by = actor_id
            record_audit(
                self._session,
                action="serial_number.returned",
                entity_type="serial_number",
                entity_id=serial.id,
                actor_id=actor_id,
                firm_id=line.firm_id,
                before_data=before,
                after_data={
                    "status": serial.status,
                    "warehouse_id": str(serial.warehouse_id),
                    "document": reference,
                    "serial_number": serial.serial_number,
                },
            )
        self._session.flush()

    def unreceive(
        self, line: LineRef, *, owner: str, reference: str, actor_id: UUID
    ) -> None:
        """Undo :meth:`mark_returned` when a completed return is cancelled.

        The units go back out with the stock the cancellation takes off the
        shelf, so each has to still be on it. One sold again since is refused
        by name: the stock could leave, but the unit it names is already
        somebody else's.
        """
        picks = [
            (pick, serial)
            for pick, serial in self.picks([line.line_id]).get(line.line_id, [])
            if pick.moved_at is not None
        ]
        label = line.label(self.product(line.product_id))
        for _pick, serial in picks:
            if serial.status != SerialStatus.AVAILABLE.value:
                raise ValidationError(
                    f"{label}: serial {serial.serial_number} is {serial.status} "
                    "since it came back, so the return can no longer be "
                    "cancelled."
                )
        for pick, serial in picks:
            serial.status = SerialStatus.SOLD.value
            serial.current_owner = owner or None
            serial.updated_by = actor_id
            pick.moved_at = None
            pick.inventory_transaction_id = None
            pick.updated_by = actor_id
            record_audit(
                self._session,
                action="serial_number.return_cancelled",
                entity_type="serial_number",
                entity_id=serial.id,
                actor_id=actor_id,
                firm_id=line.firm_id,
                before_data={"status": SerialStatus.AVAILABLE.value},
                after_data={
                    "status": serial.status,
                    "current_owner": serial.current_owner,
                    "document": reference,
                    "serial_number": serial.serial_number,
                },
            )
        self._session.flush()
