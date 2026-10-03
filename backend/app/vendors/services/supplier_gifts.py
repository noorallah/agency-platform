"""The supplier gifts and incentives register (BUY-2, decision A112).

A gift is recorded once and posts one journal by who keeps it, always Cr
*Supplier Incentives Received*:

* kept by the business as an asset -- Dr the asset account named;
* used up by the business -- Dr the expense account named;
* taken by the owner -- Dr *Drawings*.

No GST input credit is taken. Taking an entry back reverses its journal. The
194R summary totals each supplier's benefits in the statutory year (April to
March) and flags a total past 20,000, beside what the supplier says it
deducted, to match against Form 26AS.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.common.audit.services import record_audit
from app.common.report_names import vendor_names
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.models import LedgerAccount
from app.finance.services.document_posting import DocumentPostingService
from app.vendors.models import Vendor
from app.vendors.models.supplier_gift import SupplierGift
from app.vendors.schemas.supplier_gift import (
    SupplierGift194RRecord,
    SupplierGiftResponse,
    SupplierGiftWrite,
)

ZERO = Decimal("0")
#: Benefits from one supplier in a year past this attract 194R TDS.
TDS_194R_THRESHOLD = Decimal("20000")
_ACCOUNT_TYPE = {"ASSET": "ASSET", "EXPENSE": "EXPENSE"}


def statutory_year(on: date) -> tuple[date, date]:
    """Return the April-to-March year holding ``on``."""
    start = date(on.year if on.month >= 4 else on.year - 1, 4, 1)
    return start, date(start.year + 1, 3, 31)


class SupplierGiftService(TransactionalDocumentService):
    """Record, take back and total supplier gifts."""

    DOCUMENT = DocumentTypeSpec(
        code="SUPPLIER_GIFT",
        name="Supplier Gift",
        description="A gift or incentive received from a supplier.",
        category="FINANCE",
        module="vendors",
        prefix="GIFT",
        rule_code="SUPPLIER_GIFT_DEFAULT",
        rule_name="Supplier Gift Default Numbering",
        states=(
            DocumentStateSpec("POSTED", "Posted", 10),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    def create(
        self, data: SupplierGiftWrite, *, firm_id: UUID, actor_id: UUID
    ) -> SupplierGift:
        """Record a gift and post its journal; commit.

        Raises:
            ValidationError: For a supplier or account not the firm's, or an
                account of the wrong kind.

        """
        vendor = self._session.get(Vendor, data.vendor_id)
        if vendor is None or vendor.is_deleted or vendor.firm_id != firm_id:
            raise ValidationError("That supplier is not one of this firm's.")
        if data.debit_account_id is not None:
            account = self._session.get(LedgerAccount, data.debit_account_id)
            wanted = _ACCOUNT_TYPE[data.kept_by]
            if (
                account is None
                or account.is_deleted
                or account.firm_id != firm_id
                or account.account_type != wanted
            ):
                raise ValidationError(
                    f"A gift kept as {data.kept_by.lower()} is booked to one of "
                    f"the firm's {wanted.lower()} accounts."
                )
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        number = self._issue_number(
            rule,
            typed=None,
            number_column=SupplierGift.gift_number,
            firm_id=firm_id,
            document_date=data.gift_date,
            actor_id=actor_id,
            branch_code=None,
            company_code=self._company_code(firm_id),
        )
        row = SupplierGift(
            firm_id=firm_id,
            gift_number=number,
            status="POSTED",
            created_by=actor_id,
            updated_by=actor_id,
            **data.model_dump(),
        )
        self._session.add(row)
        self._flush_or_conflict("Gift number already exists in this firm.")
        entry = DocumentPostingService(self._session).post_supplier_gift(
            firm_id=firm_id,
            gift_id=row.id,
            reference_number=number,
            gift_date=data.gift_date,
            value=data.value,
            debit_account_id=data.debit_account_id,
            actor_id=actor_id,
            narration=f"Gift from {vendor.display_name}: {data.item}",
        )
        row.journal_entry_id = entry.id
        self._audit("supplier_gift.posted", row, actor_id)
        self._session.commit()
        return row

    def cancel(
        self, gift_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> SupplierGift:
        """Take an entry back and reverse its journal; commit."""
        row = self.get(gift_id, firm_id=firm_id)
        if row.status != "POSTED":
            raise ValidationError("This gift entry was already taken back.")
        if not reason.strip():
            raise ValidationError("Say why the gift entry is taken back.")
        if row.journal_entry_id is not None:
            reversal = DocumentPostingService(self._session).reverse_supplier_gift(
                firm_id=firm_id,
                journal_entry_id=row.journal_entry_id,
                reference_number=f"{row.gift_number}-REV",
                actor_id=actor_id,
            )
            row.reversal_journal_entry_id = reversal.id
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("supplier_gift.cancelled", row, actor_id)
        self._session.commit()
        return row

    def get(self, gift_id: UUID, *, firm_id: UUID) -> SupplierGift:
        """Return one of the firm's gift entries."""
        row = self._session.get(SupplierGift, gift_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Gift entry not found.")
        return row

    def list_rows(
        self, firm_id: UUID, *, vendor_id: UUID | None = None
    ) -> list[SupplierGift]:
        """Return the firm's register, newest first."""
        query = select(SupplierGift).where(
            SupplierGift.firm_id == firm_id, SupplierGift.is_deleted.is_(False)
        )
        if vendor_id is not None:
            query = query.where(SupplierGift.vendor_id == vendor_id)
        return list(
            self._session.scalars(
                query.order_by(
                    SupplierGift.gift_date.desc(), SupplierGift.gift_number.desc()
                )
            ).all()
        )

    def summary_194r(self, firm_id: UUID, *, on: date) -> list[SupplierGift194RRecord]:
        """Total each supplier's posted gifts in the statutory year holding ``on``."""
        start, end = statutory_year(on)
        totals: dict[UUID, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO, ZERO])
        for row in self._session.scalars(
            select(SupplierGift).where(
                SupplierGift.firm_id == firm_id,
                SupplierGift.status == "POSTED",
                SupplierGift.is_deleted.is_(False),
                SupplierGift.gift_date >= start,
                SupplierGift.gift_date <= end,
            )
        ).all():
            bucket = totals[row.vendor_id]
            bucket[0] += 1
            bucket[1] += Decimal(str(row.value))
            bucket[2] += Decimal(str(row.tds_194r_amount))
        names = vendor_names(self._session, totals)
        return sorted(
            (
                SupplierGift194RRecord(
                    vendor_id=vendor_id,
                    vendor_name=names.get(vendor_id, ""),
                    gifts=int(count),
                    total_value=value,
                    tds_deducted=tds,
                    over_threshold=value > TDS_194R_THRESHOLD,
                    year_from=start,
                    year_to=end,
                )
                for vendor_id, (count, value, tds) in totals.items()
            ),
            key=lambda record: record.vendor_name.lower(),
        )

    def responses(self, rows: list[SupplierGift]) -> list[SupplierGiftResponse]:
        """Shape register rows, naming suppliers in one read."""
        names = vendor_names(self._session, (row.vendor_id for row in rows))
        return [
            SupplierGiftResponse(
                id=row.id,
                gift_number=row.gift_number,
                gift_date=row.gift_date,
                vendor_id=row.vendor_id,
                vendor_name=names.get(row.vendor_id, ""),
                item=row.item,
                value=row.value,
                kept_by=row.kept_by,
                debit_account_id=row.debit_account_id,
                goods_receipt_id=row.goods_receipt_id,
                scheme_name=row.scheme_name,
                tds_194r_amount=row.tds_194r_amount,
                status=row.status,
                journal_entry_id=row.journal_entry_id,
                remarks=row.remarks,
                cancel_reason=row.cancel_reason,
                version=row.version,
            )
            for row in rows
        ]

    def _audit(self, action: str, row: SupplierGift, actor_id: UUID) -> None:
        """Write one audit row for a gift entry."""
        record_audit(
            self._session,
            action=action,
            entity_type="supplier_gift",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "gift_number": row.gift_number,
                "value": str(row.value),
                "kept_by": row.kept_by,
                "status": row.status,
            },
        )
