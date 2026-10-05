"""Agree, follow and accrue a supplier's volume rebate (BUY-13, A124).

The volume is derived on every read -- the supplier's approved bills dated in
the period, at taxable value, less its completed purchase returns dated in
the period -- so an agreement can never disagree with the bills. The highest
slab reached sets the rate on the whole volume. Accrual snapshots the volume,
the rate and the amount with the journal that booked them, and nothing
re-reads the bills after that. What has been settled is the sum of approved
``SUPPLIER_REBATE`` party adjustments naming the agreement.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.models import JournalEntry
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
from app.supplier_rebates.models import (
    SupplierRebateAgreement,
    SupplierRebateSlab,
    SupplierRebateStatus,
)
from app.supplier_rebates.schemas import (
    RebateSlabResponse,
    RebateSlabWrite,
    SupplierRebateCreate,
    SupplierRebateResponse,
    SupplierRebateUpdate,
)
from app.vendors.models import Vendor

#: Bills that count towards the volume, and returns that come off it.
BILLED = ("APPROVED", "CLOSED")
RETURNED = ("COMPLETED", "CLOSED")


def rate_for(volume: Decimal, slabs: Sequence[SupplierRebateSlab]) -> Decimal:
    """Return the rate of the highest slab the volume reaches, or zero."""
    if volume <= ZERO:
        return ZERO
    reached = [slab for slab in slabs if volume >= slab.threshold]
    if not reached:
        return ZERO
    return max(reached, key=lambda slab: slab.threshold).rate_percent


class SupplierRebateService:
    """Keep one firm's supplier rebate agreements."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store session."""
        self._session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_agreements(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID | None = None,
        status: str | None = None,
    ) -> list[SupplierRebateAgreement]:
        """Return the firm's agreements, newest period first."""
        statement = select(SupplierRebateAgreement).where(
            SupplierRebateAgreement.firm_id == firm_id,
            SupplierRebateAgreement.is_deleted.is_(False),
        )
        if vendor_id is not None:
            statement = statement.where(SupplierRebateAgreement.vendor_id == vendor_id)
        if status is not None:
            statement = statement.where(SupplierRebateAgreement.status == status)
        return list(
            self._session.scalars(
                statement.order_by(
                    SupplierRebateAgreement.period_from.desc(),
                    SupplierRebateAgreement.code.asc(),
                )
            ).all()
        )

    def get(self, agreement_id: UUID, *, firm_id: UUID) -> SupplierRebateAgreement:
        """Return one agreement.

        Raises:
            ResourceNotFoundError: If the firm has no such agreement.

        """
        row = self._session.get(SupplierRebateAgreement, agreement_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Rebate agreement not found.")
        return row

    def responses(
        self, rows: Sequence[SupplierRebateAgreement]
    ) -> list[SupplierRebateResponse]:
        """Build the responses for a page, each table read once."""
        if not rows:
            return []
        ids = [row.id for row in rows]
        slabs = self._slabs(ids)
        volumes = self._volumes(ids)
        settled = self.settled(ids)
        names = {
            vendor_id: name
            for vendor_id, name in self._session.execute(
                select(Vendor.id, Vendor.name).where(
                    Vendor.id.in_({row.vendor_id for row in rows})
                )
            ).all()
        }
        answer: list[SupplierRebateResponse] = []
        for row in rows:
            own = slabs.get(row.id, [])
            accrued = row.status == SupplierRebateStatus.ACCRUED.value
            volume = (
                Decimal(str(row.accrued_volume))
                if accrued and row.accrued_volume is not None
                else volumes.get(row.id, ZERO)
            )
            rate = (
                Decimal(str(row.accrued_rate))
                if accrued and row.accrued_rate is not None
                else rate_for(volume, own)
            )
            earned = (
                Decimal(str(row.accrued_amount))
                if accrued and row.accrued_amount is not None
                else quantize_ledger(volume * rate / 100)
            )
            ahead = [slab for slab in own if slab.threshold > volume]
            following = min(ahead, key=lambda slab: slab.threshold) if ahead else None
            done = settled.get(row.id, ZERO)
            answer.append(
                SupplierRebateResponse(
                    id=row.id,
                    version=row.version,
                    vendor_id=row.vendor_id,
                    vendor_name=names.get(row.vendor_id),
                    code=row.code,
                    name=row.name,
                    period_from=row.period_from,
                    period_to=row.period_to,
                    status=row.status,
                    notes=row.notes,
                    slabs=[RebateSlabResponse.model_validate(slab) for slab in own],
                    volume=quantize_ledger(volume),
                    rate_percent=rate,
                    earned=earned,
                    next_threshold=None if following is None else following.threshold,
                    next_rate_percent=(
                        None if following is None else following.rate_percent
                    ),
                    to_next=(
                        None
                        if following is None
                        else quantize_ledger(following.threshold - volume)
                    ),
                    accrued_amount=row.accrued_amount,
                    accrual_journal_id=row.accrual_journal_id,
                    accrued_at=row.accrued_at,
                    settled=done,
                    to_settle=(
                        quantize_ledger(Decimal(str(row.accrued_amount)) - done)
                        if accrued and row.accrued_amount is not None
                        else ZERO
                    ),
                )
            )
        return answer

    def settled(self, agreement_ids: Sequence[UUID]) -> dict[UUID, Decimal]:
        """Sum the approved rebate settlements naming each agreement."""
        # Imported here: party adjustments read this service.
        from app.party_adjustments.models import PartyAdjustment

        if not agreement_ids:
            return {}
        return {
            agreement_id: quantize_ledger(Decimal(str(total)))
            for agreement_id, total in self._session.execute(
                select(
                    PartyAdjustment.rebate_agreement_id,
                    func.coalesce(func.sum(PartyAdjustment.amount), 0),
                )
                .where(
                    PartyAdjustment.rebate_agreement_id.in_(list(agreement_ids)),
                    PartyAdjustment.is_deleted.is_(False),
                    PartyAdjustment.status == "APPROVED",
                )
                .group_by(PartyAdjustment.rebate_agreement_id)
            ).all()
            if agreement_id is not None
        }

    def to_settle(
        self, agreement_id: UUID, *, firm_id: UUID, vendor_id: UUID
    ) -> Decimal:
        """Return what an accrued rebate still has to settle.

        Raises:
            ValidationError: If it is not accrued, or is another supplier's.

        """
        row = self.get(agreement_id, firm_id=firm_id)
        if row.vendor_id != vendor_id:
            raise ValidationError("That rebate agreement is another supplier's.")
        if (
            row.status != SupplierRebateStatus.ACCRUED.value
            or row.accrued_amount is None
        ):
            raise ValidationError(
                "Only an accrued rebate can be settled: accrue it once its "
                "period is over."
            )
        done = self.settled([row.id]).get(row.id, ZERO)
        return quantize_ledger(Decimal(str(row.accrued_amount)) - done)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(
        self, data: SupplierRebateCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SupplierRebateAgreement:
        """Agree a rebate; commit.

        Raises:
            ConflictError: If the code is taken.
            ValidationError: If the supplier is not the firm's.

        """
        self._vendor(data.vendor_id, firm_id=firm_id)
        self._assert_code_free(data.code, firm_id=firm_id)
        row = SupplierRebateAgreement(
            firm_id=firm_id,
            vendor_id=data.vendor_id,
            code=data.code,
            name=data.name.strip(),
            period_from=data.period_from,
            period_to=data.period_to,
            notes=data.notes,
            status=SupplierRebateStatus.ACTIVE.value,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._replace_slabs(row, data.slabs, actor_id=actor_id)
        self._audit("supplier_rebate.created", row, actor_id)
        self._session.commit()
        return row

    def update(
        self,
        agreement_id: UUID,
        data: SupplierRebateUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SupplierRebateAgreement:
        """Change an agreement still counting; commit.

        Raises:
            ValidationError: If it is accrued or cancelled, or the period would
                run backwards.

        """
        row = self.get(agreement_id, firm_id=firm_id)
        self._assert_counting(row, doing="changed")
        values = data.model_dump(exclude_unset=True, exclude={"slabs"})
        period_from = values.get("period_from", row.period_from)
        period_to = values.get("period_to", row.period_to)
        if period_to < period_from:
            raise ValidationError("The period must not end before it starts.")
        for field, value in values.items():
            setattr(row, field, value)
        if "slabs" in data.model_fields_set and data.slabs is not None:
            self._replace_slabs(row, data.slabs, actor_id=actor_id)
        row.updated_by = actor_id
        self._audit("supplier_rebate.updated", row, actor_id)
        self._session.commit()
        return row

    def cancel(
        self, agreement_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> SupplierRebateAgreement:
        """Withdraw an agreement nothing was accrued on; commit."""
        row = self.get(agreement_id, firm_id=firm_id)
        self._assert_counting(row, doing="cancelled")
        row.status = SupplierRebateStatus.CANCELLED.value
        row.updated_by = actor_id
        self._audit("supplier_rebate.cancelled", row, actor_id)
        self._session.commit()
        return row

    def accrue(
        self,
        agreement_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        accrual_date: date | None = None,
    ) -> SupplierRebateAgreement:
        """Book what the period earned, once, after it is over; commit.

        Dated on the period's last day unless the caller names another (that
        month may be closed). The volume, rate and amount are kept with the
        journal and never re-read.

        Raises:
            ValidationError: If the period is not over, it earned nothing, or
                it is not still counting.

        """
        row = self.get(agreement_id, firm_id=firm_id)
        self._assert_counting(row, doing="accrued")
        today = utc_now().date()
        if today <= row.period_to:
            raise ValidationError(
                f"The period runs to {row.period_to:%d %b %Y}; accrue it after "
                "that, once every bill of the period is in."
            )
        on = accrual_date or row.period_to
        if on < row.period_to:
            raise ValidationError("Accrue on or after the period's last day.")
        volume = self._volumes([row.id]).get(row.id, ZERO)
        rate = rate_for(volume, self._slabs([row.id]).get(row.id, []))
        amount = quantize_ledger(volume * rate / 100)
        if amount <= ZERO:
            raise ValidationError(
                f"Purchases of {quantize_ledger(volume)} reached no slab, so "
                "there is nothing to accrue. Cancel the agreement instead."
            )
        entry = DocumentPostingService(self._session).post_supplier_rebate_accrual(
            firm_id=firm_id,
            agreement_id=row.id,
            agreement_code=row.code,
            accrual_date=on,
            amount=amount,
            actor_id=actor_id,
            reference_number=self._accrual_reference(row),
        )
        row.accrued_volume = quantize_ledger(volume)
        row.accrued_rate = rate
        row.accrued_amount = amount
        row.accrual_journal_id = entry.id
        row.accrued_at = utc_now()
        row.accrued_by = actor_id
        row.status = SupplierRebateStatus.ACCRUED.value
        row.updated_by = actor_id
        self._audit("supplier_rebate.accrued", row, actor_id)
        self._session.commit()
        return row

    def _accrual_reference(self, row: SupplierRebateAgreement) -> str:
        """Return a journal reference no earlier accrual of this agreement took.

        A reference is unique in a firm, and an accrual that was reversed
        keeps the one it posted under, so the second accrual of an agreement
        is numbered (D-BUY-34) -- as the customer side numbers its own.
        """
        earlier = self._session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.firm_id == row.firm_id,
                JournalEntry.source_module == "supplier_rebates",
                JournalEntry.source_id == row.id,
                JournalEntry.reversal_of_id.is_(None),
            )
        )
        base = f"REBATE-{row.code}"
        return base if not earlier else f"{base}-{int(earlier) + 1}"

    def reverse_accrual(
        self, agreement_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> SupplierRebateAgreement:
        """Take an accrual back off the books while nothing is settled; commit.

        The journal is mirrored, never deleted, and the agreement counts again
        -- a bill booked late into the period can then be counted.

        Raises:
            ValidationError: If it is not accrued or part of it is settled.

        """
        row = self.get(agreement_id, firm_id=firm_id)
        if (
            row.status != SupplierRebateStatus.ACCRUED.value
            or row.accrual_journal_id is None
        ):
            raise ValidationError("Only an accrued rebate can be reversed.")
        if self.settled([row.id]).get(row.id, ZERO) > ZERO:
            raise ValidationError(
                "Part of this rebate is already set against the supplier's bills; "
                "cancel those settlements first."
            )
        JournalEntryEngine(self._session).reverse_entry(
            row.accrual_journal_id,
            firm_id=firm_id,
            reference_number=f"REBATE-{row.code}-REV-{utc_now():%Y%m%d%H%M%S}",
            actor_id=actor_id,
        )
        row.accrued_volume = None
        row.accrued_rate = None
        row.accrued_amount = None
        row.accrual_journal_id = None
        row.accrued_at = None
        row.accrued_by = None
        row.status = SupplierRebateStatus.ACTIVE.value
        row.updated_by = actor_id
        self._audit("supplier_rebate.accrual_reversed", row, actor_id)
        self._session.commit()
        return row

    # ------------------------------------------------------------------

    def _volumes(self, agreement_ids: Sequence[UUID]) -> dict[UUID, Decimal]:
        """Sum each agreement's bills less its returns, one statement each."""
        agreement = SupplierRebateAgreement
        billed = self._session.execute(
            select(
                agreement.id,
                func.coalesce(
                    func.sum(
                        PurchaseInvoiceLine.net_amount - PurchaseInvoiceLine.tax_amount
                    ),
                    0,
                ),
            )
            .select_from(agreement)
            .join(
                PurchaseInvoice,
                and_(
                    PurchaseInvoice.firm_id == agreement.firm_id,
                    PurchaseInvoice.vendor_id == agreement.vendor_id,
                    PurchaseInvoice.invoice_date >= agreement.period_from,
                    PurchaseInvoice.invoice_date <= agreement.period_to,
                    PurchaseInvoice.is_deleted.is_(False),
                    PurchaseInvoice.status.in_(BILLED),
                ),
            )
            .join(
                PurchaseInvoiceLine,
                and_(
                    PurchaseInvoiceLine.purchase_invoice_id == PurchaseInvoice.id,
                    PurchaseInvoiceLine.is_deleted.is_(False),
                ),
            )
            .where(agreement.id.in_(list(agreement_ids)))
            .group_by(agreement.id)
        ).all()
        returned = self._session.execute(
            select(
                agreement.id,
                func.coalesce(
                    func.sum(
                        PurchaseReturnLine.net_amount - PurchaseReturnLine.tax_amount
                    ),
                    0,
                ),
            )
            .select_from(agreement)
            .join(
                PurchaseReturn,
                and_(
                    PurchaseReturn.firm_id == agreement.firm_id,
                    PurchaseReturn.vendor_id == agreement.vendor_id,
                    PurchaseReturn.return_date >= agreement.period_from,
                    PurchaseReturn.return_date <= agreement.period_to,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status.in_(RETURNED),
                ),
            )
            .join(
                PurchaseReturnLine,
                and_(
                    PurchaseReturnLine.purchase_return_id == PurchaseReturn.id,
                    PurchaseReturnLine.is_deleted.is_(False),
                ),
            )
            .where(agreement.id.in_(list(agreement_ids)))
            .group_by(agreement.id)
        ).all()
        volumes: dict[UUID, Decimal] = {}
        for agreement_id, total in billed:
            volumes[agreement_id] = Decimal(str(total))
        for agreement_id, total in returned:
            volumes[agreement_id] = volumes.get(agreement_id, ZERO) - Decimal(
                str(total)
            )
        return volumes

    def _slabs(
        self, agreement_ids: Sequence[UUID]
    ) -> dict[UUID, list[SupplierRebateSlab]]:
        found: dict[UUID, list[SupplierRebateSlab]] = {}
        for slab in self._session.scalars(
            select(SupplierRebateSlab)
            .where(
                SupplierRebateSlab.agreement_id.in_(list(agreement_ids)),
                SupplierRebateSlab.is_deleted.is_(False),
            )
            .order_by(SupplierRebateSlab.threshold.asc())
        ).all():
            found.setdefault(slab.agreement_id, []).append(slab)
        return found

    def _replace_slabs(
        self,
        row: SupplierRebateAgreement,
        slabs: Sequence[RebateSlabWrite],
        *,
        actor_id: UUID,
    ) -> None:
        for old in self._slabs([row.id]).get(row.id, []):
            self._session.delete(old)
        self._session.flush()
        for number, slab in enumerate(
            sorted(slabs, key=lambda item: item.threshold), start=1
        ):
            self._session.add(
                SupplierRebateSlab(
                    agreement_id=row.id,
                    firm_id=row.firm_id,
                    line_number=number,
                    threshold=slab.threshold,
                    rate_percent=slab.rate_percent,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def _vendor(self, vendor_id: UUID, *, firm_id: UUID) -> Vendor:
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None or vendor.is_deleted or vendor.firm_id != firm_id:
            raise ValidationError("That supplier is not one of this firm's.")
        return vendor

    def _assert_code_free(self, code: str, *, firm_id: UUID) -> None:
        taken = self._session.scalar(
            select(SupplierRebateAgreement.id).where(
                SupplierRebateAgreement.firm_id == firm_id,
                SupplierRebateAgreement.code == code,
                SupplierRebateAgreement.is_deleted.is_(False),
            )
        )
        if taken is not None:
            raise ConflictError(f"A rebate agreement {code} already exists.")

    @staticmethod
    def _assert_counting(row: SupplierRebateAgreement, *, doing: str) -> None:
        if row.status != SupplierRebateStatus.ACTIVE.value:
            raise ValidationError(
                f"A rebate agreement that is {row.status.lower()} cannot be {doing}."
            )

    def _audit(self, action: str, row: SupplierRebateAgreement, actor_id: UUID) -> None:
        record_audit(
            self._session,
            action=action,
            entity_type="supplier_rebate_agreement",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "code": row.code,
                "status": row.status,
                "accrued_amount": (
                    None if row.accrued_amount is None else str(row.accrued_amount)
                ),
            },
        )


__all__ = ["SupplierRebateService", "rate_for"]
