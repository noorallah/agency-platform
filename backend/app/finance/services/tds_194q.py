"""TDS on the purchase of goods, section 194Q, worked out (ACC-8, decision A78).

Past fifty lakh rupees of purchases from one supplier in a year, a buyer with
a ten-crore turnover deducts 0.1% on the excess -- 5% where the supplier gave
no PAN. Until now a firm worked that out by hand and typed it on the payment.

Two sums, both read from the documents and never kept in a counter:

* **what was bought** -- the supplier's approved bills in the Income-tax year,
  valued without GST (CBDT circular 13 of 2021: deducted on the value before
  tax where the bill shows it separately);
* **what was deducted** -- the supplier's posted payments in the year that
  carry a 194Q deduction.

What is due is the rate on the purchases past the threshold; what is still to
deduct is that less what was deducted, and the payment screen suggests it.
The year is the Income-tax year, April to March, whatever the firm's own
books run on: the section counts on the government's calendar.

Nothing here posts or stores a deduction: the payment does, as it always did,
so the 26Q return and the TDS registers stay exactly as they are.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.models.tds_194q import Tds194QSettings
from app.purchase_invoice.models import PurchaseInvoice
from app.settlements.models import Settlement, SettlementDirection, SettlementStatus
from app.vendors.models import Vendor

SECTION = "194Q"
HUNDRED = Decimal("100")
DEFAULT_THRESHOLD = Decimal("5000000")
DEFAULT_RATE = Decimal("0.1")
DEFAULT_RATE_WITHOUT_PAN = Decimal("5")
#: Bills that stand: a draft has not been credited and a cancelled one never was.
_COUNTED = ("APPROVED", "CLOSED")


def income_tax_year(on: date) -> tuple[date, date]:
    """Return the April-to-March year ``on`` falls in."""
    start = on.year if on.month >= 4 else on.year - 1
    return date(start, 4, 1), date(start + 1, 3, 31)


@dataclass(frozen=True)
class Supplier194Q:
    """One supplier's 194Q position for the year, up to a day."""

    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    pan: str | None
    year_from: date
    year_to: date
    purchases: Decimal
    threshold: Decimal
    excess: Decimal
    rate_percent: Decimal
    due: Decimal
    deducted: Decimal
    to_deduct: Decimal
    applies: bool


@dataclass(frozen=True)
class Settings194Q:
    """The firm's switch, threshold and rates, defaults where never saved."""

    is_enabled: bool
    threshold_amount: Decimal
    rate_percent: Decimal
    rate_without_pan_percent: Decimal


class Tds194QService:
    """Read and set 194Q, and work out each supplier's position."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store."""
        self._session = session

    # ---- settings ---------------------------------------------------------

    def settings(self, firm_id: UUID) -> Settings194Q:
        """Return the firm's settings, the defaults (off) where none are kept."""
        row = self._row(firm_id)
        if row is None:
            return Settings194Q(
                False, DEFAULT_THRESHOLD, DEFAULT_RATE, DEFAULT_RATE_WITHOUT_PAN
            )
        return Settings194Q(
            row.is_enabled,
            row.threshold_amount,
            row.rate_percent,
            row.rate_without_pan_percent,
        )

    def save_settings(
        self,
        firm_id: UUID,
        *,
        actor_id: UUID,
        is_enabled: bool,
        threshold_amount: Decimal,
        rate_percent: Decimal,
        rate_without_pan_percent: Decimal,
    ) -> Settings194Q:
        """Store the firm's 194Q settings and audit the change."""
        if threshold_amount < ZERO:
            raise ValidationError("The threshold cannot be negative.")
        for rate in (rate_percent, rate_without_pan_percent):
            if not ZERO < rate <= Decimal("20"):
                raise ValidationError("A rate is more than 0 and at most 20 percent.")
        row = self._row(firm_id)
        before = None if row is None else self._snapshot(row)
        if row is None:
            row = Tds194QSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        row.is_enabled = is_enabled
        row.threshold_amount = threshold_amount
        row.rate_percent = rate_percent
        row.rate_without_pan_percent = rate_without_pan_percent
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="tds_194q.settings_saved",
            entity_type="tds_194q_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return self.settings(firm_id)

    # ---- positions --------------------------------------------------------

    def supplier(self, vendor_id: UUID, *, firm_id: UUID, on: date) -> Supplier194Q:
        """Return one supplier's position for the year ``on`` falls in."""
        vendor = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if vendor is None:
            raise ResourceNotFoundError("Supplier not found.")
        positions = self._positions(firm_id, on=on, vendors=[vendor])
        return positions[0]

    def register(self, *, firm_id: UUID, on: date) -> list[Supplier194Q]:
        """Return every supplier bought from this year, largest first."""
        start, _ = income_tax_year(on)
        bought = select(PurchaseInvoice.vendor_id).where(
            PurchaseInvoice.firm_id == firm_id,
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status.in_(_COUNTED),
            PurchaseInvoice.invoice_date >= start,
            PurchaseInvoice.invoice_date <= on,
        )
        vendors = list(
            self._session.scalars(
                select(Vendor).where(Vendor.firm_id == firm_id, Vendor.id.in_(bought))
            )
        )
        rows = self._positions(firm_id, on=on, vendors=vendors)
        return sorted(rows, key=lambda row: (-row.purchases, row.vendor_code))

    def _positions(
        self, firm_id: UUID, *, on: date, vendors: list[Vendor]
    ) -> list[Supplier194Q]:
        """Work out each supplier's position from two grouped reads."""
        start, end = income_tax_year(on)
        settings = self.settings(firm_id)
        ids = [vendor.id for vendor in vendors]
        purchases: dict[UUID | None, object] = {
            key: value
            for key, value in self._session.execute(
                select(
                    PurchaseInvoice.vendor_id,
                    func.coalesce(
                        func.sum(
                            PurchaseInvoice.subtotal
                            + PurchaseInvoice.additional_charges
                        ),
                        0,
                    ),
                )
                .where(
                    PurchaseInvoice.firm_id == firm_id,
                    PurchaseInvoice.vendor_id.in_(ids),
                    PurchaseInvoice.is_deleted.is_(False),
                    PurchaseInvoice.status.in_(_COUNTED),
                    PurchaseInvoice.invoice_date >= start,
                    PurchaseInvoice.invoice_date <= on,
                )
                .group_by(PurchaseInvoice.vendor_id)
            ).all()
        }
        deducted: dict[UUID | None, object] = {
            key: value
            for key, value in self._session.execute(
                select(
                    Settlement.vendor_id,
                    func.coalesce(func.sum(Settlement.tds_amount), 0),
                )
                .where(
                    Settlement.firm_id == firm_id,
                    Settlement.vendor_id.in_(ids),
                    Settlement.direction == SettlementDirection.PAYMENT.value,
                    Settlement.status == SettlementStatus.POSTED.value,
                    Settlement.is_deleted.is_(False),
                    Settlement.tds_section == SECTION,
                    Settlement.settlement_date >= start,
                    Settlement.settlement_date <= end,
                )
                .group_by(Settlement.vendor_id)
            ).all()
        }
        rows: list[Supplier194Q] = []
        for vendor in vendors:
            bought = quantize_ledger(Decimal(str(purchases.get(vendor.id, 0))))
            taken = quantize_ledger(Decimal(str(deducted.get(vendor.id, 0))))
            pan = (vendor.pan or "").strip() or None
            rate = (
                settings.rate_percent
                if pan is not None
                else settings.rate_without_pan_percent
            )
            excess = max(bought - settings.threshold_amount, ZERO)
            due = (
                quantize_ledger(excess * rate / HUNDRED)
                if settings.is_enabled
                else ZERO
            )
            rows.append(
                Supplier194Q(
                    vendor_id=vendor.id,
                    vendor_code=vendor.code,
                    vendor_name=vendor.name,
                    pan=pan,
                    year_from=start,
                    year_to=end,
                    purchases=bought,
                    threshold=settings.threshold_amount,
                    excess=quantize_ledger(excess),
                    rate_percent=rate,
                    due=due,
                    deducted=taken,
                    to_deduct=max(due - taken, ZERO),
                    applies=settings.is_enabled and excess > ZERO,
                )
            )
        return rows

    # ---- helpers ----------------------------------------------------------

    def _row(self, firm_id: UUID) -> Tds194QSettings | None:
        """Return the firm's saved settings row, if any."""
        return self._session.scalar(
            select(Tds194QSettings).where(
                Tds194QSettings.firm_id == firm_id,
                Tds194QSettings.is_deleted.is_(False),
            )
        )

    @staticmethod
    def _snapshot(row: Tds194QSettings) -> dict[str, object]:
        """Return the settings as the audit trail records them."""
        return {
            "is_enabled": row.is_enabled,
            "threshold_amount": str(row.threshold_amount),
            "rate_percent": str(row.rate_percent),
            "rate_without_pan_percent": str(row.rate_without_pan_percent),
        }
