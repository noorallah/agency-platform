"""Vendor ageing: what the firm owes each supplier, by how long (55 S7).

The mirror of the customer ageing (`CustomerStatementService.ageing`): one
row per supplier with anything owing, split into the same buckets of days
past due -- the firm's own bands (ACC-6), 0-29, 30-59, 60-89 and 90 and over
unless it chose others -- counted from each bill's due date, or from its date
where it has no terms. A bill not yet due sits in
the first bucket, as it does on the customer side.

**What a bill owes is derived exactly as Record Payment derives it**
(`PaymentService.outstanding_invoices`): the bill less posted payments,
completed returns off its own lines, applied supplier credit and party
adjustments, over the states that are debts -- opening bills from the
previous books included. So a supplier paid in full leaves the ageing the
moment the payment posts, and the ageing and the payment screen cannot age
one bill at two figures. It is as on today: what a bill owed on a past day
is not something the payment derivation answers.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.firm_metadata import firm_today
from app.core.utils.chunks import over_chunks
from app.vendors.models import Vendor

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class VendorAgeingBand:
    """What one supplier is owed in one band of days past due."""

    from_days: int
    #: None on the last band, which is open-ended.
    to_days: int | None
    label: str
    amount: Decimal


@dataclass(frozen=True)
class VendorAgeingRow:
    """One supplier's unpaid bills, by days past due."""

    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    as_of: date
    bills: int
    total_outstanding: Decimal
    #: One per band of the firm's ageing, in order, empty ones included.
    buckets: list[VendorAgeingBand]
    oldest_days: int


class VendorAgeingService:
    """Age what the firm owes its suppliers."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def ageing(self, firm_id: UUID) -> list[VendorAgeingRow]:
        """Return each supplier owed anything, the largest debt first."""
        # Imported here: the settlement service imports this module's models.
        from app.finance.services.ageing_settings import band_label, bucket_bounds
        from app.settlements.services.settlement_service import PaymentService

        bounds = bucket_bounds(self._session, firm_id)
        today = firm_today(self._session, firm_id)
        owing = PaymentService(self._session).outstanding_invoices(
            firm_id=firm_id, party_id=None
        )
        totals: dict[UUID, list[Decimal]] = {}
        bills: dict[UUID, int] = {}
        oldest: dict[UUID, int] = {}
        for record in owing:
            if record.party_id is None:  # pragma: no cover - always set
                continue
            due = record.due_date or record.invoice_date
            days = max((today - due).days, 0)
            bucket = sum(1 for bound in bounds[1:] if days >= bound)
            row = totals.setdefault(record.party_id, [ZERO] * len(bounds))
            row[bucket] += record.outstanding_amount
            bills[record.party_id] = bills.get(record.party_id, 0) + 1
            oldest[record.party_id] = max(oldest.get(record.party_id, 0), days)
        names = _vendors(self._session, vendor_ids=list(totals))
        rows = [
            VendorAgeingRow(
                vendor_id=vendor_id,
                vendor_code=names.get(vendor_id, ("", ""))[0],
                vendor_name=names.get(vendor_id, ("", str(vendor_id)))[1],
                as_of=today,
                bills=bills[vendor_id],
                total_outstanding=sum(buckets, ZERO),
                buckets=[
                    VendorAgeingBand(
                        from_days=lower,
                        to_days=(
                            bounds[index + 1] - 1 if index + 1 < len(bounds) else None
                        ),
                        label=band_label(bounds, index),
                        amount=buckets[index],
                    )
                    for index, lower in enumerate(bounds)
                ],
                oldest_days=oldest[vendor_id],
            )
            for vendor_id, buckets in totals.items()
        ]
        rows.sort(key=lambda row: (-row.total_outstanding, row.vendor_name))
        return rows


@over_chunks("vendor_ids")
def _vendors(
    session: Session, *, vendor_ids: list[UUID]
) -> dict[UUID, tuple[str, str]]:
    """Read each supplier's code and name."""
    if not vendor_ids:
        return {}
    return {
        vendor_id: (code, display or name)
        for vendor_id, code, display, name in session.execute(
            select(Vendor.id, Vendor.code, Vendor.display_name, Vendor.name).where(
                Vendor.id.in_(vendor_ids)
            )
        ).all()
    }
