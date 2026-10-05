"""What approved party adjustments have taken off each bill.

One function, read beside the settlement allocations by every derivation of
what a bill still owes -- `settled_against` for a sales invoice,
`PaymentService.outstanding_invoices` for a purchase invoice, and the two
opening-bill readers -- so a written-off or set-off bill stops owing on Record
Receipt, Record Payment, the ageing and the outstanding and overdue reports at
once, and starts owing again when the adjustment is cancelled.

It imports nothing but this module's models, so the settlement and customer
modules can call it without an import cycle.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.common.firm_metadata import firm_day_after
from app.core.utils.chunks import whole_past_a_chunk
from app.core.utils.money import quantize_ledger
from app.party_adjustments.models import (
    PartyAdjustment,
    PartyAdjustmentAllocation,
    PartyAdjustmentStatus,
)

#: The bill columns an allocation can fill.
BILL_COLUMNS = (
    "sales_invoice_id",
    "purchase_invoice_id",
    "customer_opening_bill_id",
    "vendor_opening_bill_id",
)


@whole_past_a_chunk("bill_ids")
def adjusted_against(
    session: Session,
    *,
    firm_id: UUID,
    column: str,
    bill_ids: Sequence[UUID] | None,
    as_of: date | None = None,
) -> dict[UUID, Decimal]:
    """Sum what approved adjustments took off each bill of one kind.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        column: Which bill column to read -- one of ``BILL_COLUMNS``.
        bill_ids: The bills to ask about; None asks about every bill of the
            kind in one grouped read.
        as_of: Count only what stood at the end of this day: dated on or
            before it, and approved, or cancelled only after it. None counts
            what stands now.

    Returns:
        The adjusted amount per bill, for those with any.

    """
    if column not in BILL_COLUMNS:  # pragma: no cover - a programming error
        raise ValueError(f"{column} is not a bill column.")
    if bill_ids is not None and not bill_ids:
        return {}
    bill = getattr(PartyAdjustmentAllocation, column)
    if as_of is None:
        standing: Any = PartyAdjustment.status == PartyAdjustmentStatus.APPROVED.value
        dated: tuple[Any, ...] = ()
    else:
        day_after = firm_day_after(session, firm_id, as_of)
        standing = or_(
            PartyAdjustment.status == PartyAdjustmentStatus.APPROVED.value,
            and_(
                PartyAdjustment.status == PartyAdjustmentStatus.CANCELLED.value,
                PartyAdjustment.approved_at.is_not(None),
                PartyAdjustment.cancelled_at >= day_after,
            ),
        )
        dated = (PartyAdjustment.adjustment_date <= as_of,)
    rows = session.execute(
        select(bill, func.coalesce(func.sum(PartyAdjustmentAllocation.amount), 0))
        .join(
            PartyAdjustment,
            PartyAdjustment.id == PartyAdjustmentAllocation.party_adjustment_id,
        )
        .where(
            PartyAdjustmentAllocation.firm_id == firm_id,
            PartyAdjustmentAllocation.is_deleted.is_(False),
            bill.is_not(None) if bill_ids is None else bill.in_(list(bill_ids)),
            PartyAdjustment.is_deleted.is_(False),
            standing,
            *dated,
        )
        .group_by(bill)
    ).all()
    return {
        bill_id: quantize_ledger(Decimal(str(total)))
        for bill_id, total in rows
        if bill_id is not None
    }


def adjustment_numbers_against(
    session: Session, *, column: str, bill_id: UUID
) -> list[str]:
    """Name the live adjustments that took something off one bill.

    What a bill's cancel guard lists: a bill written off or set off cannot be
    cancelled under the adjustment, which would then clear nothing.
    """
    bill = getattr(PartyAdjustmentAllocation, column)
    return sorted(
        session.scalars(
            select(PartyAdjustment.adjustment_number)
            .join(
                PartyAdjustmentAllocation,
                PartyAdjustmentAllocation.party_adjustment_id == PartyAdjustment.id,
            )
            .where(
                bill == bill_id,
                PartyAdjustmentAllocation.is_deleted.is_(False),
                PartyAdjustment.is_deleted.is_(False),
                PartyAdjustment.status != PartyAdjustmentStatus.CANCELLED.value,
            )
            .distinct()
        ).all()
    )
