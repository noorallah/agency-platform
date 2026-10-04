"""TDS on contracts (194C) and professional or technical fees (194J) (PG-5).

Worked out the way 194Q is (ACC-8): two sums read from the documents and never
kept in a counter -- **what the supplier is owed for** in the Income-tax year
and **what was already deducted** from it under the section -- and the next
document proposes the difference between the tax due on the first and the
second. Where 194Q only suggests a figure for the payment screen, these two
sections are deducted at the **earlier of credit and payment**, as the Act
says, so the bill proposes it when it is approved and the payment proposes it
when money goes ahead of any bill.

**What the tax is due on.** The supplier's approved bills in the year, valued
before GST (CBDT circular 23 of 2017: GST shown separately is left out), plus
money paid on account that no open bill yet covers. An advance waiting for its
bill is netted against what the supplier's open bills owe, so a bill that
arrives after the advance is not taxed twice: the advance deducted, the bill
finds the deduction already made and proposes nothing more.

**When it applies.** 194C: one bill past the single limit (30,000), or the
year's total past the annual one (1,00,000). 194J: the year's total past
30,000. Once the year's total is past its limit the tax is due on **all** of
it, not on the excess as under 194Q -- the Act's words for these sections --
so the bill that crosses the limit carries the tax on the earlier bills too.
Because each proposal is the year's due less the year's deductions, the
catch-up happens once, on the crossing document, and never again.

**The rate.** 20% where the supplier gave no PAN (section 206AA). Otherwise
194C takes 1% from an individual or HUF and 2% from anybody else, and 194J
10% on professional fees and 2% on technical services. The supplier master
says which; for 194C a blank reads the PAN's fourth letter (P or H).

The year is the Income-tax year, April to March, as 194Q's is: the section
counts on the government's calendar, whatever the firm's own books run on.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.models.tds_sections import TdsSectionSettings
from app.finance.services.tds_194q import income_tax_year
from app.purchase_invoice.models import PurchaseInvoice
from app.settlements.models import Settlement, SettlementDirection, SettlementStatus
from app.vendors.models import Vendor

HUNDRED = Decimal("100")
#: The sections worked out here.
SECTIONS = ("194C", "194J")
#: Bills that stand: a draft has not been credited and a cancelled one never was.
_COUNTED = ("APPROVED", "CLOSED")
#: The highest rate a setting may hold.
_MAX_RATE = Decimal("30")


@dataclass(frozen=True)
class SectionSettings:
    """A firm's switch, thresholds and rates for one section."""

    section: str
    is_enabled: bool
    single_threshold_amount: Decimal | None
    annual_threshold_amount: Decimal
    rate_percent: Decimal
    lower_rate_percent: Decimal
    rate_without_pan_percent: Decimal


#: What a firm that never saved its settings works to (Finance Act 2024).
DEFAULTS: dict[str, SectionSettings] = {
    "194C": SectionSettings(
        section="194C",
        is_enabled=True,
        single_threshold_amount=Decimal("30000"),
        annual_threshold_amount=Decimal("100000"),
        rate_percent=Decimal("2"),
        lower_rate_percent=Decimal("1"),
        rate_without_pan_percent=Decimal("20"),
    ),
    "194J": SectionSettings(
        section="194J",
        is_enabled=True,
        single_threshold_amount=None,
        annual_threshold_amount=Decimal("30000"),
        rate_percent=Decimal("10"),
        lower_rate_percent=Decimal("2"),
        rate_without_pan_percent=Decimal("20"),
    ),
}

_FIELDS = (
    "is_enabled",
    "single_threshold_amount",
    "annual_threshold_amount",
    "rate_percent",
    "lower_rate_percent",
    "rate_without_pan_percent",
)


@dataclass(frozen=True)
class TdsProposal:
    """What the next document for one supplier should deduct, and why."""

    vendor_id: UUID
    #: ``194C`` or ``194J``; None where the supplier is under neither.
    section: str | None
    pan: str | None
    rate_percent: Decimal
    #: Why that rate: ``NO_PAN``, ``INDIVIDUAL_HUF``, ``OTHER``,
    #: ``PROFESSIONAL`` or ``TECHNICAL``; blank under no section.
    rate_basis: str
    year_from: date
    year_to: date
    #: The year's other approved bills, before GST.
    billed: Decimal
    #: The document being proposed for: a bill before GST, or the part of a
    #: payment no bill takes.
    this_document: Decimal
    #: Money paid on account that the supplier's open bills do not cover.
    advances: Decimal
    #: ``billed + advances`` plus the bill, if it is one: what the year owes on.
    base_total: Decimal
    #: ``SINGLE`` (one bill past the single limit), ``ANNUAL`` (the year past
    #: its limit) or blank where neither is.
    threshold_crossed: str
    due: Decimal
    #: Already deducted under the section this year, bills and payments.
    deducted: Decimal
    proposed: Decimal
    applies: bool


class TdsSectionService:
    """Read and set 194C and 194J, and propose each document's deduction."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store."""
        self._session = session

    # ---- settings ---------------------------------------------------------

    def settings(self, firm_id: UUID, section: str) -> SectionSettings:
        """Return the firm's settings for a section, the defaults where unsaved."""
        default = _default(section)
        row = self._row(firm_id, section)
        if row is None:
            return default
        return SectionSettings(
            section=section,
            is_enabled=row.is_enabled,
            single_threshold_amount=row.single_threshold_amount,
            annual_threshold_amount=row.annual_threshold_amount,
            rate_percent=row.rate_percent,
            lower_rate_percent=row.lower_rate_percent,
            rate_without_pan_percent=row.rate_without_pan_percent,
        )

    def all_settings(self, firm_id: UUID) -> list[SectionSettings]:
        """Return both sections' settings, 194C first."""
        return [self.settings(firm_id, section) for section in SECTIONS]

    def save_settings(
        self,
        firm_id: UUID,
        section: str,
        changes: dict[str, object],
        *,
        actor_id: UUID,
    ) -> SectionSettings:
        """Apply the fields sent to the section's settings and audit the change.

        ``changes`` holds only what the caller sent: a field left out keeps
        what is saved, or the default where nothing is.

        Raises:
            ValidationError: If a threshold is negative or a rate is not more
                than 0 and at most 30 percent.

        """
        current = self.settings(firm_id, section)
        unknown = set(changes) - set(_FIELDS)
        if unknown:
            raise ValidationError(f"Unknown setting(s): {', '.join(sorted(unknown))}.")
        merged = replace(current, **changes)  # type: ignore[arg-type]
        if section == "194J" and merged.single_threshold_amount is not None:
            raise ValidationError(
                "194J has no single-bill limit: it applies on the year's total."
            )
        if merged.annual_threshold_amount < ZERO or (
            merged.single_threshold_amount is not None
            and merged.single_threshold_amount < ZERO
        ):
            raise ValidationError("A threshold cannot be negative.")
        for rate in (
            merged.rate_percent,
            merged.lower_rate_percent,
            merged.rate_without_pan_percent,
        ):
            if not ZERO < rate <= _MAX_RATE:
                raise ValidationError("A rate is more than 0 and at most 30 percent.")
        row = self._row(firm_id, section)
        before = None if row is None else self._snapshot(row)
        if row is None:
            row = TdsSectionSettings(
                firm_id=firm_id, section=section, created_by=actor_id
            )
            self._session.add(row)
        row.is_enabled = merged.is_enabled
        row.single_threshold_amount = merged.single_threshold_amount
        row.annual_threshold_amount = merged.annual_threshold_amount
        row.rate_percent = merged.rate_percent
        row.lower_rate_percent = merged.lower_rate_percent
        row.rate_without_pan_percent = merged.rate_without_pan_percent
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="tds_section.settings_saved",
            entity_type="tds_section_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return self.settings(firm_id, section)

    # ---- proposals --------------------------------------------------------

    def supplier(
        self,
        vendor_id: UUID,
        *,
        firm_id: UUID,
        on: date,
        bill_amount: Decimal = ZERO,
        bill_total: Decimal = ZERO,
        advance_amount: Decimal = ZERO,
        allocating: Decimal = ZERO,
        exclude_invoice_id: UUID | None = None,
    ) -> TdsProposal:
        """Return what a document for this supplier dated ``on`` should deduct.

        Raises:
            ResourceNotFoundError: If the firm has no such supplier.

        """
        vendor = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if vendor is None:
            raise ResourceNotFoundError("Supplier not found.")
        return self.propose(
            vendor,
            firm_id=firm_id,
            on=on,
            bill_amount=bill_amount,
            bill_total=bill_total,
            advance_amount=advance_amount,
            allocating=allocating,
            exclude_invoice_id=exclude_invoice_id,
        )

    def propose(
        self,
        vendor: Vendor,
        *,
        firm_id: UUID,
        on: date,
        bill_amount: Decimal = ZERO,
        bill_total: Decimal = ZERO,
        advance_amount: Decimal = ZERO,
        allocating: Decimal = ZERO,
        exclude_invoice_id: UUID | None = None,
    ) -> TdsProposal:
        """Work out the deduction for one bill or one payment.

        Args:
            vendor: The supplier.
            firm_id: The owning firm.
            on: The document's date; it picks the Income-tax year.
            bill_amount: For a bill, its value before GST; zero for a payment.
            bill_total: For a bill, its grand total: what it adds to the open
                bills an advance is netted against.
            advance_amount: For a payment, the part no bill takes.
            allocating: For a payment, what it is about to clear off open
                bills, which those bills will no longer owe.
            exclude_invoice_id: The bill being proposed for, left out of the
                year's other bills.

        """
        start, end = income_tax_year(on)
        section = (
            vendor.default_tds_section
            if vendor.default_tds_section in SECTIONS
            else None
        )
        pan = (vendor.pan or "").strip().upper() or None
        bill_amount = quantize_ledger(max(bill_amount, ZERO))
        advance_amount = quantize_ledger(max(advance_amount, ZERO))
        if section is None:
            return TdsProposal(
                vendor_id=vendor.id,
                section=None,
                pan=pan,
                rate_percent=ZERO,
                rate_basis="",
                year_from=start,
                year_to=end,
                billed=ZERO,
                this_document=bill_amount or advance_amount,
                advances=ZERO,
                base_total=ZERO,
                threshold_crossed="",
                due=ZERO,
                deducted=ZERO,
                proposed=ZERO,
                applies=False,
            )
        settings = self.settings(firm_id, section)
        rate, basis = _rate(vendor, pan, settings)
        bills = self._bills(firm_id, vendor.id, start, end, exclude_invoice_id)
        bases = [base for base, _, _ in bills]
        deducted = sum(
            (tds for _, tds, code in bills if code == section), ZERO
        ) + self._paid_deductions(firm_id, vendor.id, section, start, end)
        advances = self._uncovered_advances(
            firm_id,
            vendor.id,
            start,
            end,
            extra_advance=advance_amount,
            extra_open=quantize_ledger(max(bill_total, ZERO))
            - quantize_ledger(max(allocating, ZERO)),
        )
        items = [*bases, *([bill_amount] if bill_amount > ZERO else [])]
        if advances > ZERO:
            items.append(advances)
        total = quantize_ledger(sum(items, ZERO))
        single = settings.single_threshold_amount
        crossed = ""
        taxed = ZERO
        if total > settings.annual_threshold_amount:
            crossed, taxed = "ANNUAL", total
        elif single is not None and any(item > single for item in items):
            crossed = "SINGLE"
            taxed = sum((item for item in items if item > single), ZERO)
        due = quantize_ledger(taxed * rate / HUNDRED) if settings.is_enabled else ZERO
        deducted = quantize_ledger(deducted)
        proposed = max(due - deducted, ZERO)
        return TdsProposal(
            vendor_id=vendor.id,
            section=section,
            pan=pan,
            rate_percent=rate,
            rate_basis=basis,
            year_from=start,
            year_to=end,
            billed=quantize_ledger(sum(bases, ZERO)),
            this_document=bill_amount or advance_amount,
            advances=advances,
            base_total=total,
            threshold_crossed=crossed,
            due=due,
            deducted=deducted,
            proposed=proposed,
            applies=settings.is_enabled and due > ZERO,
        )

    # ---- reads ------------------------------------------------------------

    def _bills(
        self,
        firm_id: UUID,
        vendor_id: UUID,
        start: date,
        end: date,
        exclude_invoice_id: UUID | None,
    ) -> list[tuple[Decimal, Decimal, str | None]]:
        """Return each approved bill in the year: its base, TDS and section."""
        statement = select(
            PurchaseInvoice.subtotal + PurchaseInvoice.additional_charges,
            PurchaseInvoice.tds_amount,
            PurchaseInvoice.tds_section,
        ).where(
            PurchaseInvoice.firm_id == firm_id,
            PurchaseInvoice.vendor_id == vendor_id,
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status.in_(_COUNTED),
            PurchaseInvoice.invoice_date >= start,
            PurchaseInvoice.invoice_date <= end,
        )
        if exclude_invoice_id is not None:
            statement = statement.where(PurchaseInvoice.id != exclude_invoice_id)
        return [
            (
                quantize_ledger(Decimal(str(base or 0))),
                quantize_ledger(Decimal(str(tds or 0))),
                section,
            )
            for base, tds, section in self._session.execute(statement).all()
        ]

    def _paid_deductions(
        self, firm_id: UUID, vendor_id: UUID, section: str, start: date, end: date
    ) -> Decimal:
        """Sum what posted payments in the year deducted under the section."""
        total = self._session.scalar(
            select(func.coalesce(func.sum(Settlement.tds_amount), 0)).where(
                Settlement.firm_id == firm_id,
                Settlement.vendor_id == vendor_id,
                Settlement.direction == SettlementDirection.PAYMENT.value,
                Settlement.status == SettlementStatus.POSTED.value,
                Settlement.is_deleted.is_(False),
                Settlement.tds_section == section,
                Settlement.settlement_date >= start,
                Settlement.settlement_date <= end,
            )
        )
        return Decimal(str(total or 0))

    def _uncovered_advances(
        self,
        firm_id: UUID,
        vendor_id: UUID,
        start: date,
        end: date,
        *,
        extra_advance: Decimal,
        extra_open: Decimal,
    ) -> Decimal:
        """Money on account in the year that the supplier's open bills do not take.

        An advance is money ahead of its bill. While the supplier has bills
        open, the advance is waiting to be set against them and was taxed --
        or will be -- as those bills; only what is left over is a payment
        ahead of any credit.
        """
        held = self._session.scalar(
            select(func.coalesce(func.sum(Settlement.unallocated_amount), 0)).where(
                Settlement.firm_id == firm_id,
                Settlement.vendor_id == vendor_id,
                Settlement.direction == SettlementDirection.PAYMENT.value,
                Settlement.status == SettlementStatus.POSTED.value,
                Settlement.is_deleted.is_(False),
                Settlement.settlement_date >= start,
                Settlement.settlement_date <= end,
            )
        )
        advances = quantize_ledger(Decimal(str(held or 0))) + extra_advance
        if advances <= ZERO:
            return ZERO
        # Imported here: the settlements service imports this module.
        from app.settlements.services import PaymentService

        owing = sum(
            (
                record.outstanding_amount
                for record in PaymentService(self._session).outstanding_invoices(
                    firm_id=firm_id, party_id=vendor_id
                )
            ),
            ZERO,
        )
        return max(advances - max(owing + extra_open, ZERO), ZERO)

    # ---- helpers ----------------------------------------------------------

    def _row(self, firm_id: UUID, section: str) -> TdsSectionSettings | None:
        """Return the firm's saved row for a section, if any."""
        return self._session.scalar(
            select(TdsSectionSettings).where(
                TdsSectionSettings.firm_id == firm_id,
                TdsSectionSettings.section == section,
                TdsSectionSettings.is_deleted.is_(False),
            )
        )

    @staticmethod
    def _snapshot(row: TdsSectionSettings) -> dict[str, object]:
        """Return the settings as the audit trail records them."""
        return {
            "section": row.section,
            "is_enabled": row.is_enabled,
            "single_threshold_amount": (
                None
                if row.single_threshold_amount is None
                else str(row.single_threshold_amount)
            ),
            "annual_threshold_amount": str(row.annual_threshold_amount),
            "rate_percent": str(row.rate_percent),
            "lower_rate_percent": str(row.lower_rate_percent),
            "rate_without_pan_percent": str(row.rate_without_pan_percent),
        }


def _default(section: str) -> SectionSettings:
    """Return a section's defaults, refusing one not worked out here."""
    found = DEFAULTS.get(section)
    if found is None:
        raise ValidationError(
            f"{section} is not worked out here; use one of " + ", ".join(SECTIONS)
        )
    return found


def is_individual_or_huf(vendor: Vendor, pan: str | None) -> bool:
    """Say whether a 194C supplier is an individual or HUF.

    The master's own answer when it gives one; else the PAN's fourth letter,
    which the Income-tax department sets to P for a person and H for an HUF.
    """
    if vendor.tds_individual_huf is not None:
        return vendor.tds_individual_huf
    return pan is not None and pan[3:4] in ("P", "H")


def _rate(
    vendor: Vendor, pan: str | None, settings: SectionSettings
) -> tuple[Decimal, str]:
    """Return the rate a supplier is deducted at under the section, and why."""
    if pan is None:
        return settings.rate_without_pan_percent, "NO_PAN"
    if settings.section == "194C":
        if is_individual_or_huf(vendor, pan):
            return settings.lower_rate_percent, "INDIVIDUAL_HUF"
        return settings.rate_percent, "OTHER"
    if vendor.tds_technical_services:
        return settings.lower_rate_percent, "TECHNICAL"
    return settings.rate_percent, "PROFESSIONAL"
