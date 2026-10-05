"""Record, list, import and cancel the bills a firm owed on its first day here.

Why these are bills rather than one balance per supplier, and why they are not
purchase invoices, is on `VendorOpeningBill`. What they owe now is derived --
the amount at cutover less the posted payments applied to them -- exactly as a
purchase bill's is, and `PaymentService.outstanding_invoices` offers them to
Record Payment beside the ordinary bills.
"""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_ledger
from app.vendors.models import Vendor, VendorOpeningBill, VendorOpeningBillStatus
from app.vendors.schemas.opening_bill import (
    VendorOpeningBillImportRow,
    VendorOpeningBillResponse,
    VendorOpeningBillWrite,
)

ZERO = Decimal("0.00")


def opening_bill_payments(
    session: Session, *, firm_id: UUID, bill_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """Sum the posted payments applied to each opening bill.

    Joined to the settlement so a reversed payment stops clearing anything --
    the same rule `outstanding_invoices` applies to a purchase bill.
    """
    # Imported here: the settlement models import the vendor models.
    from app.settlements.models import (
        Settlement,
        SettlementAllocation,
        SettlementStatus,
    )

    if not bill_ids:
        return {}
    rows = session.execute(
        select(
            SettlementAllocation.vendor_opening_bill_id,
            func.coalesce(func.sum(SettlementAllocation.amount), 0),
        )
        .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
        .where(
            SettlementAllocation.firm_id == firm_id,
            SettlementAllocation.is_deleted.is_(False),
            SettlementAllocation.vendor_opening_bill_id.in_(list(bill_ids)),
            Settlement.status == SettlementStatus.POSTED.value,
        )
        .group_by(SettlementAllocation.vendor_opening_bill_id)
    ).all()
    paid = {
        bill_id: quantize_ledger(Decimal(str(total)))
        for bill_id, total in rows
        if bill_id is not None
    }
    # And what a write-back or set-off took off the bill (backlog 74 row 2).
    from app.party_adjustments.services.allocations import adjusted_against

    for bill_id, amount in adjusted_against(
        session,
        firm_id=firm_id,
        column="vendor_opening_bill_id",
        bill_ids=list(bill_ids),
    ).items():
        paid[bill_id] = paid.get(bill_id, ZERO) + amount
    # And a return's or debit note's credit set against it (BUY-17).
    from app.settlements.services.supplier_credits import credit_applied_against

    for bill_id, amount in credit_applied_against(
        session, firm_id=firm_id, invoice_ids=list(bill_ids), opening=True
    ).items():
        paid[bill_id] = paid.get(bill_id, ZERO) + amount
    return paid


def standing_opening_bills(
    session: Session, *, firm_id: UUID, vendor_id: UUID | None
) -> list[VendorOpeningBill]:
    """Return the opening bills not cancelled, for one supplier or all."""
    return list(
        session.scalars(
            select(VendorOpeningBill)
            .where(
                VendorOpeningBill.firm_id == firm_id,
                *(
                    ()
                    if vendor_id is None
                    else (VendorOpeningBill.vendor_id == vendor_id,)
                ),
                VendorOpeningBill.is_deleted.is_(False),
                VendorOpeningBill.status == VendorOpeningBillStatus.POSTED.value,
            )
            .order_by(VendorOpeningBill.bill_date.asc(), VendorOpeningBill.bill_number)
        ).all()
    )


def opening_bill_label(row: VendorOpeningBill) -> str:
    """Name an opening bill the way the supplier would recognise it."""
    if row.reference_number:
        return f"{row.reference_number} (opening)"
    return row.bill_number


class VendorOpeningBillService:
    """Own the day-one bills a firm owed its suppliers."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a session it does not own."""
        self._session = session

    def list_for_vendor(
        self, vendor_id: UUID, *, firm_id: UUID, include_cancelled: bool = True
    ) -> list[VendorOpeningBillResponse]:
        """Return one supplier's opening bills, oldest first."""
        vendor = self._vendor(vendor_id, firm_id=firm_id)
        rows = self._session.scalars(
            select(VendorOpeningBill)
            .where(
                VendorOpeningBill.firm_id == firm_id,
                VendorOpeningBill.vendor_id == vendor.id,
                VendorOpeningBill.is_deleted.is_(False),
                *(
                    ()
                    if include_cancelled
                    else (
                        VendorOpeningBill.status
                        == VendorOpeningBillStatus.POSTED.value,
                    )
                ),
            )
            .order_by(VendorOpeningBill.bill_date.asc(), VendorOpeningBill.bill_number)
        ).all()
        paid = opening_bill_payments(
            self._session, firm_id=firm_id, bill_ids=[row.id for row in rows]
        )
        return [self.to_response(row, vendor=vendor, paid=paid) for row in rows]

    def get(self, bill_id: UUID, *, firm_id: UUID) -> VendorOpeningBill:
        """Return one opening bill the firm owns."""
        row = self._session.scalar(
            select(VendorOpeningBill).where(
                VendorOpeningBill.id == bill_id,
                VendorOpeningBill.firm_id == firm_id,
                VendorOpeningBill.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Opening bill not found.")
        return row

    def response_for(
        self, row: VendorOpeningBill, *, firm_id: UUID
    ) -> VendorOpeningBillResponse:
        """Build the response for one opening bill."""
        vendor = self._session.get(Vendor, row.vendor_id)
        if vendor is None:  # pragma: no cover - the foreign key guarantees it
            raise ResourceNotFoundError("Vendor not found.")
        paid = opening_bill_payments(self._session, firm_id=firm_id, bill_ids=[row.id])
        return self.to_response(row, vendor=vendor, paid=paid)

    def create(
        self,
        vendor_id: UUID,
        data: VendorOpeningBillWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> VendorOpeningBill:
        """Record and post one opening bill."""
        vendor = self._vendor(vendor_id, firm_id=firm_id)
        row = self._stage(vendor, data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def import_bills(
        self,
        records: list[VendorOpeningBillImportRow],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[VendorOpeningBill]:
        """Record a file of opening bills, all of them or none.

        Every supplier code is resolved before anything is written, and every
        unknown one is named with its row number in one refusal, so a file is
        corrected in one pass rather than one error at a time. Then each bill
        is staged and the batch committed once: a posting refused on row 40
        leaves nothing of rows 1 to 39 behind.
        """
        codes = {record.vendor_code.strip().upper() for record in records}
        vendors = {
            vendor.code.upper(): vendor
            for vendor in self._session.scalars(
                select(Vendor).where(
                    Vendor.firm_id == firm_id,
                    Vendor.is_deleted.is_(False),
                    func.upper(Vendor.code).in_(codes),
                )
            ).all()
        }
        unknown = [
            f"row {index}: {record.vendor_code}"
            for index, record in enumerate(records, start=1)
            if record.vendor_code.strip().upper() not in vendors
        ]
        if unknown:
            shown = "; ".join(unknown[:20])
            more = len(unknown) - 20
            raise ValidationError(
                f"No supplier has the code given on {len(unknown)} "
                f"row{'' if len(unknown) == 1 else 's'} -- {shown}"
                f"{f' and {more} more' if more > 0 else ''}. Nothing was imported."
            )
        rows: list[VendorOpeningBill] = []
        try:
            for index, record in enumerate(records, start=1):
                try:
                    rows.append(
                        self._stage(
                            vendors[record.vendor_code.strip().upper()],
                            record,
                            firm_id=firm_id,
                            actor_id=actor_id,
                        )
                    )
                except ValidationError as error:
                    raise ValidationError(
                        f"Row {index}: {error.message} Nothing was imported."
                    ) from error
        except Exception:
            self._session.rollback()
            raise
        self._session.commit()
        return rows

    def cancel(
        self, bill_id: UUID, *, reason: str, firm_id: UUID, actor_id: UUID
    ) -> VendorOpeningBill:
        """Take back an opening bill entered in error.

        Refused while any payment is applied to it: the payment would be left
        clearing a debt that no longer exists. Reverse the payment first, and
        it goes back to being money on account. Supplier credit set against it
        does not hold it up: that is withdrawn and free to set against another
        bill, as cancelling a purchase bill does (BUY-17).
        """
        # Imported here: the settlement models import the vendor models.
        from app.finance.services.journal_engine import JournalEntryEngine
        from app.settlements.services.supplier_credits import (
            credit_applied_against,
            withdraw_credit_applications,
        )

        row = self.get(bill_id, firm_id=firm_id)
        if row.status == VendorOpeningBillStatus.CANCELLED.value:
            raise ValidationError(f"{row.bill_number} is already cancelled.")
        credit = credit_applied_against(
            self._session, firm_id=firm_id, invoice_ids=[row.id], opening=True
        ).get(row.id, ZERO)
        paid = (
            opening_bill_payments(
                self._session, firm_id=firm_id, bill_ids=[row.id]
            ).get(row.id, ZERO)
            - credit
        )
        if paid > ZERO:
            raise ValidationError(
                f"{paid} has been paid against {row.bill_number}. Reverse "
                "those payments before cancelling it."
            )
        withdraw_credit_applications(
            self._session,
            firm_id=firm_id,
            actor_id=actor_id,
            vendor_opening_bill_id=row.id,
        )
        mirror = JournalEntryEngine(self._session).reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"{row.bill_number}-REV",
            actor_id=actor_id,
        )
        row.status = VendorOpeningBillStatus.CANCELLED.value
        row.reversal_journal_entry_id = mirror.id
        row.cancelled_at = utc_now()
        row.cancelled_by = actor_id
        row.cancellation_reason = reason.strip()
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="vendor_opening_bill.cancelled",
            entity_type="vendor_opening_bill",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"bill_number": row.bill_number, "reason": reason.strip()},
        )
        self._session.commit()
        return row

    def to_response(
        self,
        row: VendorOpeningBill,
        *,
        vendor: Vendor,
        paid: dict[UUID, Decimal],
    ) -> VendorOpeningBillResponse:
        """Shape one row, with what is paid and still owed on it."""
        amount = quantize_ledger(row.amount)
        paid_amount = paid.get(row.id, ZERO)
        standing = row.status == VendorOpeningBillStatus.POSTED.value
        return VendorOpeningBillResponse(
            id=row.id,
            vendor_id=row.vendor_id,
            vendor_code=vendor.code,
            vendor_name=vendor.display_name,
            bill_number=row.bill_number,
            reference_number=row.reference_number,
            bill_date=row.bill_date,
            due_date=row.due_date,
            posting_date=row.posting_date,
            amount=amount,
            paid_amount=paid_amount,
            outstanding_amount=amount - paid_amount if standing else ZERO,
            narration=row.narration,
            status=row.status,
            journal_entry_id=row.journal_entry_id,
            cancelled_at=row.cancelled_at,
            cancellation_reason=row.cancellation_reason,
            version=row.version,
            created_at=row.created_at,
        )

    def _vendor(self, vendor_id: UUID, *, firm_id: UUID) -> Vendor:
        """Return a live supplier of the firm, or refuse by name."""
        vendor = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if vendor is None:
            raise ResourceNotFoundError("Vendor not found.")
        return vendor

    def _stage(
        self,
        vendor: Vendor,
        data: VendorOpeningBillWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> VendorOpeningBill:
        """Post one opening bill and add its row, without committing."""
        # Imported here: the posting service reaches the settlement models,
        # which import the vendor models.
        from uuid import uuid4

        from app.finance.services.document_posting import DocumentPostingService

        posting_date = data.posting_date or firm_today(self._session, firm_id)
        if data.bill_date > posting_date:
            raise ValidationError(
                "An opening bill is one raised before the books here start, so "
                f"its date cannot be after {posting_date}."
            )
        reference = data.reference_number.strip() if data.reference_number else None
        if reference:
            taken = self._session.scalar(
                select(VendorOpeningBill.bill_number).where(
                    VendorOpeningBill.firm_id == firm_id,
                    VendorOpeningBill.vendor_id == vendor.id,
                    func.upper(VendorOpeningBill.reference_number) == reference.upper(),
                    VendorOpeningBill.status == VendorOpeningBillStatus.POSTED.value,
                    VendorOpeningBill.is_deleted.is_(False),
                )
            )
            if taken is not None:
                raise ValidationError(
                    f"{vendor.display_name}'s bill {reference} is already "
                    f"recorded as {taken}."
                )
        number = self._next_number(firm_id=firm_id)
        bill_id = uuid4()
        entry = DocumentPostingService(self._session).post_vendor_opening_bill(
            firm_id=firm_id,
            opening_bill_id=bill_id,
            bill_number=number,
            posting_date=posting_date,
            amount=data.amount,
            actor_id=actor_id,
        )
        row = VendorOpeningBill(
            id=bill_id,
            firm_id=firm_id,
            vendor_id=vendor.id,
            bill_number=number,
            reference_number=reference,
            bill_date=data.bill_date,
            due_date=data.due_date,
            posting_date=posting_date,
            amount=quantize_ledger(data.amount),
            narration=data.narration,
            status=VendorOpeningBillStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="vendor_opening_bill.recorded",
            entity_type="vendor_opening_bill",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "bill_number": number,
                "vendor": vendor.code,
                "reference_number": reference,
                "amount": str(row.amount),
                "posting_date": posting_date.isoformat(),
            },
        )
        return row

    def _next_number(self, *, firm_id: UUID) -> str:
        """Issue the next `OB-` number, counting cancelled bills too.

        A cancelled bill keeps its number and its journal keeps the reference,
        so counting only standing bills would hand the same number out twice.
        """
        issued = self._session.scalar(
            select(func.count(VendorOpeningBill.id)).where(
                VendorOpeningBill.firm_id == firm_id
            )
        )
        return f"OB-{int(issued or 0) + 1:05d}"
