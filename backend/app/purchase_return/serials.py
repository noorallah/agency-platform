"""Which serialised units a purchase return sends back (PG-10).

A purchase return of a serial-tracked product names the units going back,
by number: one per unit returned, each AVAILABLE and received from this
supplier. They are picked while the return is a draft
(``document_line_serials``, document type ``PURCHASE_RETURN``), checked again
at completion -- two drafts may name the same unit -- and marked RETURNED when
the stock leaves. Cancelling a completed return puts them back on the shelf.

The return's lines are deleted and re-inserted on every save, so a line that
says nothing about its serials keeps them by line number, the way the sales
return carries its picks. Flushes, never commits.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import SerialNumber
from app.batch_serial.schemas.batch_serial import SerialStatus
from app.batch_serial.services.serial_trail_service import (
    PURCHASE_RETURN,
    LineRef,
    Pick,
    SerialCheck,
    SerialTrailService,
    clean_serials,
    serial_key,
)
from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceipt
from app.products.models import Product
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine


def _line_ref(row: PurchaseReturn, line: PurchaseReturnLine) -> LineRef:
    """Describe a return line to the serial trail."""
    return LineRef(
        firm_id=row.firm_id,
        document_type=PURCHASE_RETURN,
        document_id=row.id,
        line_id=line.id,
        line_number=line.line_number,
        product_id=line.product_id,
    )


class ReturnSerials:
    """Pick, check and move the units a purchase return sends back."""

    def __init__(self, session: Session) -> None:
        """Bind to the return's unit of work."""
        self._session = session
        self._trail = SerialTrailService(session)

    # ---- reads ---------------------------------------------------------

    def named(self, line_ids: Iterable[UUID]) -> dict[UUID, list[str]]:
        """Return the serial numbers each line names, for its response."""
        return {
            line_id: [serial.serial_number for serial in picked]
            for line_id, picked in self._trail.picked_serials(line_ids).items()
        }

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

    def kept(self, row: PurchaseReturn) -> dict[int, list[UUID]]:
        """Return the draft's picks by line number, before its lines go."""
        return self._trail.picks_by_line_number(row.id)

    def clear(self, row: PurchaseReturn) -> None:
        """Forget every pick of the return that has not moved."""
        self._trail.clear_document(row.id)

    # ---- picking on a draft -------------------------------------------

    def eligibility(
        self, row: PurchaseReturn, serials: Sequence[SerialNumber]
    ) -> SerialCheck:
        """Return the rule a unit must pass to go back on this return.

        It has to be on the shelf, and to have arrived on a receipt from this
        return's supplier: a unit nobody received from them is not theirs to
        take back.
        """
        receipts = self._trail.receivers(serial.id for serial in serials)
        suppliers: dict[UUID, UUID] = (
            {
                receipt_id: vendor_id
                for receipt_id, vendor_id in self._session.execute(
                    select(GoodsReceipt.id, GoodsReceipt.vendor_id).where(
                        GoodsReceipt.id.in_(set(receipts.values()))
                    )
                ).all()
            }
            if receipts
            else {}
        )

        def check(serial: SerialNumber) -> str | None:
            """Say why one unit may not go back, or None when it may."""
            if serial.status != SerialStatus.AVAILABLE.value:
                return f"is {serial.status}, not in stock, so it cannot be sent back."
            receipt_id = receipts.get(serial.id)
            if receipt_id is None or suppliers.get(receipt_id) != row.vendor_id:
                return "was not received from this supplier."
            return None

        return check

    def pick(
        self,
        row: PurchaseReturn,
        specs: Sequence[dict[str, object]],
        kept: dict[int, list[UUID]],
        *,
        actor_id: UUID,
    ) -> None:
        """Name each line's units: what it sent, or what it named before.

        ``specs`` are the request's lines in order; the return numbers its
        lines by position, so ``specs[n - 1]`` is line ``n``.
        """
        self._session.flush()
        lines = list(
            self._session.scalars(
                select(PurchaseReturnLine)
                .where(
                    PurchaseReturnLine.purchase_return_id == row.id,
                    PurchaseReturnLine.is_deleted.is_(False),
                )
                .order_by(PurchaseReturnLine.line_number)
            ).all()
        )
        for line in lines:
            spec = specs[line.line_number - 1] if line.line_number <= len(specs) else {}
            typed = spec.get("serial_numbers")
            ref = _line_ref(row, line)
            if isinstance(typed, list):
                ids = self._resolve(ref, [str(value) for value in typed])
            else:
                ids = kept.get(line.line_number, [])
                if not ids or not self._trail.is_serialised(line.product_id):
                    continue
            units = list(
                self._session.scalars(
                    select(SerialNumber).where(SerialNumber.id.in_(ids))
                ).all()
            )
            self._trail.replace_picks(
                ref,
                ids,
                check=self.eligibility(row, units),
                actor_id=actor_id,
            )

    def _resolve(self, ref: LineRef, typed: Sequence[str]) -> list[UUID]:
        """Turn the numbers a line names into this product's units."""
        product = self._trail.product(ref.product_id)
        label = ref.label(product)
        cleaned = clean_serials(typed, label=label)
        if cleaned and not (product is not None and product.track_serial):
            raise ValidationError(
                f"{label}: this product is not serial-tracked, so its lines "
                "take no serial numbers."
            )
        units = self._trail.product_serials(ref.firm_id, ref.product_id, cleaned)
        ids: list[UUID] = []
        for serial in cleaned:
            unit = units.get(serial_key(serial))
            if unit is None:
                raise ValidationError(
                    f"{label}: serial {serial} is not a unit of this product "
                    "in this firm."
                )
            ids.append(unit.id)
        return ids

    # ---- completing and cancelling ------------------------------------

    def send_back(
        self,
        row: PurchaseReturn,
        line: PurchaseReturnLine,
        *,
        base_quantity: Decimal,
        warehouse_id: UUID,
        movement_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Check a completing line's units and mark them RETURNED.

        One per stock unit leaving, each still on the shelf of the warehouse
        the line sends back from and received from this supplier.
        """
        if not self._trail.is_serialised(line.product_id):
            return
        ref = _line_ref(row, line)
        picks: list[Pick] = self._trail.line_picks(line.id)
        self._trail.assert_count(
            ref,
            len(picks),
            base_quantity,
            verb="sends back",
            where="purchase return",
        )
        self._trail.check_receivable(
            ref, picks, eligible=self.eligibility(row, [s for _p, s in picks])
        )
        label = ref.label(self._trail.product(line.product_id))
        for _pick, serial in picks:
            if serial.warehouse_id != warehouse_id:
                raise ValidationError(
                    f"{label}: serial {serial.serial_number} is not in the "
                    "warehouse this line sends back from."
                )
        self._trail.mark_sent_back(
            ref,
            picks,
            movement_id=movement_id,
            reference=row.return_number,
            actor_id=actor_id,
        )

    def take_back(self, row: PurchaseReturn, *, actor_id: UUID) -> None:
        """Undo a return's picks as it is cancelled.

        A completed return's units come back onto the shelf; a draft's or an
        approved one's picks are simply forgotten.
        """
        for line in self._session.scalars(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id == row.id,
                PurchaseReturnLine.is_deleted.is_(False),
            )
        ).all():
            self._trail.unsend(
                _line_ref(row, line), reference=row.return_number, actor_id=actor_id
            )
        self.clear(row)
