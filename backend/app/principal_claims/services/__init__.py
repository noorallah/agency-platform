"""Claims to the principal (SEL-11, decision A128).

A distributor passes the principal's schemes on to its customers, writes off
the principal's goods that expire on its shelf, and takes back the ones that
arrive broken -- and the principal owes it for all three. A claim gathers
them for one principal and one period:

* **Scheme** -- each redemption of a promotion the principal funds, at the
  principal's share of the benefit the customer was given.
* **Expiry** -- each stock write-off for expiry of the principal's products,
  at the value the books took off.
* **Breakage** -- each damaged or scrapped line of a completed sales return of
  the principal's products, at the taxable rate the customer was credited.

A source is claimed once. Raising posts Dr claims receivable, Cr the
expense the cost sat in -- promotional expense for schemes, inventory
adjustment for stock -- so the firm's costs fall by what it expects back.
The principal settles by credit note (a party adjustment of kind
``PRINCIPAL_CLAIM`` set against its bills) or by paying; how far a claim is
settled is derived from both, never stored. A claim with nothing settled
can be cancelled, which reverses its journal and frees its sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import ScalarSelect

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.principal_claims.models import (
    PrincipalClaim,
    PrincipalClaimLine,
    PrincipalClaimReceipt,
)
from app.products.models import Product
from app.products.models.brand import Brand, Principal
from app.promotions.models import Promotion, PromotionRedemption
from app.sales_return.models import SalesReturn, SalesReturnLine

KINDS = ("SCHEME", "EXPIRY", "BREAKAGE")
_DONE_RETURNS = ("COMPLETED", "CLOSED")
CENT = Decimal("0.01")


class PrincipalClaimWrite(BaseModel):
    """Raise a claim on one principal for one period."""

    model_config = ConfigDict(extra="forbid")

    principal_id: UUID
    period_from: date
    period_to: date
    claim_date: date
    #: Which of the three to claim; all of them when omitted.
    kinds: list[str] = Field(default_factory=lambda: list(KINDS), min_length=1)
    remarks: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _shape(self) -> PrincipalClaimWrite:
        """Refuse a backwards period, an unknown kind, a claim dated early."""
        if self.period_to < self.period_from:
            raise ValueError("The period ends before it starts.")
        unknown = set(self.kinds) - set(KINDS)
        if unknown:
            raise ValueError(f"Unknown claim kind(s): {', '.join(sorted(unknown))}.")
        if self.claim_date < self.period_from:
            raise ValueError("A claim is raised on or after its period starts.")
        return self


class PrincipalClaimCancel(BaseModel):
    """Why a claim is withdrawn."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class PrincipalClaimReceiptWrite(BaseModel):
    """Money the principal paid against a claim."""

    model_config = ConfigDict(extra="forbid")

    received_on: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    money_account_id: UUID
    reference: str | None = Field(default=None, max_length=100)


class PrincipalClaimLineResponse(BaseModel):
    """One thing claimed."""

    model_config = ConfigDict(extra="forbid")

    line_number: int
    kind: str
    source_id: UUID
    source_number: str
    source_date: date
    product_id: UUID | None
    product_name: str | None
    quantity: Decimal | None
    description: str
    amount: Decimal


class PrincipalClaimReceiptResponse(BaseModel):
    """One payment against a claim."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    received_on: date
    amount: Decimal
    money_account_id: UUID
    reference: str | None
    status: str


class PrincipalClaimResponse(BaseModel):
    """One claim, what it holds and how far it is settled."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    claim_number: str
    claim_date: date
    principal_id: UUID
    principal_name: str
    vendor_id: UUID | None
    period_from: date
    period_to: date
    scheme_amount: Decimal
    expiry_amount: Decimal
    breakage_amount: Decimal
    total_amount: Decimal
    settled_by_credit_note: Decimal
    settled_by_payment: Decimal
    outstanding: Decimal
    #: ``RAISED``, ``PART_SETTLED``, ``SETTLED`` or ``CANCELLED``.
    status: str
    remarks: str | None
    cancel_reason: str | None
    version: int
    lines: list[PrincipalClaimLineResponse]
    receipts: list[PrincipalClaimReceiptResponse]


class PrincipalClaimPreview(BaseModel):
    """What a claim for the period would hold, before it is raised."""

    model_config = ConfigDict(extra="forbid")

    principal_id: UUID
    period_from: date
    period_to: date
    scheme_amount: Decimal
    expiry_amount: Decimal
    breakage_amount: Decimal
    total_amount: Decimal
    lines: list[PrincipalClaimLineResponse]


@dataclass(frozen=True)
class _Candidate:
    """One unclaimed source found for the period."""

    kind: str
    source_id: UUID
    source_number: str
    source_date: date
    product_id: UUID | None
    quantity: Decimal | None
    description: str
    amount: Decimal


class PrincipalClaimService(TransactionalDocumentService):
    """Raise, settle and cancel claims on principals."""

    DOCUMENT = DocumentTypeSpec(
        code="PRINCIPAL_CLAIM",
        name="Principal Claim",
        description="What a principal owes for schemes, expiry and breakage.",
        category="PURCHASE",
        module="principal_claims",
        prefix="CLM",
        rule_code="PRINCIPAL_CLAIM_DEFAULT",
        rule_name="Principal Claim Default Numbering",
        states=(
            DocumentStateSpec("RAISED", "Raised", 10),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    # ---- gathering -----------------------------------------------------

    def candidates(
        self,
        *,
        firm_id: UUID,
        principal_id: UUID,
        period_from: date,
        period_to: date,
        kinds: list[str] | None = None,
    ) -> list[_Candidate]:
        """Return every unclaimed source of the period, schemes first."""
        self._principal(principal_id, firm_id=firm_id)
        wanted = set(kinds or KINDS)
        found: list[_Candidate] = []
        if "SCHEME" in wanted:
            found += self._schemes(firm_id, principal_id, period_from, period_to)
        if "EXPIRY" in wanted:
            found += self._expiries(firm_id, principal_id, period_from, period_to)
        if "BREAKAGE" in wanted:
            found += self._breakages(firm_id, principal_id, period_from, period_to)
        claimed = self._claimed({c.source_id for c in found})
        return [
            c for c in found if (c.kind, c.source_id) not in claimed and c.amount > 0
        ]

    def preview(
        self, data: PrincipalClaimWrite, *, firm_id: UUID
    ) -> PrincipalClaimPreview:
        """Return what raising the claim would hold, writing nothing."""
        found = self.candidates(
            firm_id=firm_id,
            principal_id=data.principal_id,
            period_from=data.period_from,
            period_to=data.period_to,
            kinds=data.kinds,
        )
        totals = self._totals(found)
        names = self._product_names({c.product_id for c in found if c.product_id})
        return PrincipalClaimPreview(
            principal_id=data.principal_id,
            period_from=data.period_from,
            period_to=data.period_to,
            scheme_amount=totals["SCHEME"],
            expiry_amount=totals["EXPIRY"],
            breakage_amount=totals["BREAKAGE"],
            total_amount=sum(totals.values(), ZERO),
            lines=[
                self._line_response(number, c, names)
                for number, c in enumerate(found, start=1)
            ],
        )

    # ---- raising -------------------------------------------------------

    def raise_claim(
        self, data: PrincipalClaimWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PrincipalClaim:
        """Gather the period's sources, post the claim and commit.

        Raises:
            ValidationError: If nothing is left to claim for the period.

        """
        principal = self._principal(data.principal_id, firm_id=firm_id)
        found = self.candidates(
            firm_id=firm_id,
            principal_id=data.principal_id,
            period_from=data.period_from,
            period_to=data.period_to,
            kinds=data.kinds,
        )
        if not found:
            raise ValidationError(
                f"Nothing is left to claim from {principal.name} for that period."
            )
        totals = self._totals(found)
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        number = self._issue_number(
            rule,
            typed=None,
            number_column=PrincipalClaim.claim_number,
            firm_id=firm_id,
            document_date=data.claim_date,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
        row = PrincipalClaim(
            firm_id=firm_id,
            claim_number=number,
            claim_date=data.claim_date,
            principal_id=principal.id,
            vendor_id=principal.vendor_id,
            period_from=data.period_from,
            period_to=data.period_to,
            scheme_amount=totals["SCHEME"],
            expiry_amount=totals["EXPIRY"],
            breakage_amount=totals["BREAKAGE"],
            total_amount=sum(totals.values(), ZERO),
            status="RAISED",
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Claim number already exists in this firm.")
        for line_number, candidate in enumerate(found, start=1):
            self._session.add(
                PrincipalClaimLine(
                    claim_id=row.id,
                    firm_id=firm_id,
                    line_number=line_number,
                    kind=candidate.kind,
                    source_id=candidate.source_id,
                    source_number=candidate.source_number[:80],
                    source_date=candidate.source_date,
                    product_id=candidate.product_id,
                    quantity=candidate.quantity,
                    description=candidate.description[:300],
                    amount=candidate.amount,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        # Two claims racing for one source: the partial unique index on the
        # lines refuses the second, by name rather than by a duplicate.
        self._flush_or_conflict(
            "Part of this period was claimed a moment ago; open the claims "
            "and raise it again."
        )
        entry = DocumentPostingService(self._session).post_principal_claim(
            firm_id=firm_id,
            claim_id=row.id,
            claim_number=number,
            claim_date=data.claim_date,
            scheme_amount=totals["SCHEME"],
            stock_amount=totals["EXPIRY"] + totals["BREAKAGE"],
            actor_id=actor_id,
        )
        row.journal_entry_id = entry.id
        self._audit("principal_claim.raised", row, actor_id)
        self._session.commit()
        return row

    # ---- settling ------------------------------------------------------

    def credited(self, claim_ids: list[UUID]) -> dict[UUID, Decimal]:
        """Sum the approved credit notes (party adjustments) naming each claim."""
        # Imported here: party adjustments read this service.
        from app.party_adjustments.models import PartyAdjustment

        if not claim_ids:
            return {}
        return {
            claim_id: quantize_ledger(Decimal(str(total)))
            for claim_id, total in self._session.execute(
                select(
                    PartyAdjustment.principal_claim_id,
                    func.coalesce(func.sum(PartyAdjustment.amount), 0),
                )
                .where(
                    PartyAdjustment.principal_claim_id.in_(claim_ids),
                    PartyAdjustment.is_deleted.is_(False),
                    PartyAdjustment.status == "APPROVED",
                )
                .group_by(PartyAdjustment.principal_claim_id)
            ).all()
            if claim_id is not None
        }

    def paid(self, claim_ids: list[UUID]) -> dict[UUID, Decimal]:
        """Sum the live payments against each claim."""
        if not claim_ids:
            return {}
        return {
            claim_id: quantize_ledger(Decimal(str(total)))
            for claim_id, total in self._session.execute(
                select(
                    PrincipalClaimReceipt.claim_id,
                    func.coalesce(func.sum(PrincipalClaimReceipt.amount), 0),
                )
                .where(
                    PrincipalClaimReceipt.claim_id.in_(claim_ids),
                    PrincipalClaimReceipt.is_deleted.is_(False),
                    PrincipalClaimReceipt.status == "POSTED",
                )
                .group_by(PrincipalClaimReceipt.claim_id)
            ).all()
        }

    def outstanding(self, row: PrincipalClaim) -> Decimal:
        """Return what the principal still owes on a claim."""
        if row.status == "CANCELLED":
            return ZERO
        done = self.credited([row.id]).get(row.id, ZERO) + self.paid([row.id]).get(
            row.id, ZERO
        )
        return quantize_ledger(Decimal(str(row.total_amount)) - done)

    def to_settle(self, claim_id: UUID, *, firm_id: UUID, vendor_id: UUID) -> Decimal:
        """Return what a claim still has to settle, for a credit note.

        Raises:
            ValidationError: If the claim is cancelled or another supplier's.

        """
        row = self.get(claim_id, firm_id=firm_id)
        if row.status == "CANCELLED":
            raise ValidationError("A cancelled claim has nothing to settle.")
        if row.vendor_id != vendor_id:
            raise ValidationError(
                "That claim is not on this supplier: its principal names "
                "another supplier, or none."
            )
        return self.outstanding(row)

    def record_receipt(
        self,
        claim_id: UUID,
        data: PrincipalClaimReceiptWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PrincipalClaimReceipt:
        """Record money the principal paid, post it and commit.

        Raises:
            ValidationError: If it is more than is owed, dated before the
                claim, or the account is not one money moves through.

        """
        row = self.get(claim_id, firm_id=firm_id)
        if row.status == "CANCELLED":
            raise ValidationError("A cancelled claim takes no payment.")
        if data.received_on < row.claim_date:
            raise ValidationError("A payment cannot come before its claim.")
        owed = self.outstanding(row)
        if data.amount > owed:
            raise ValidationError(
                f"The claim has {owed} still to settle, so {data.amount} cannot "
                "be received against it."
            )
        from app.contra.services.contra_service import ContraVoucherService

        money = {
            account.id
            for account in ContraVoucherService(self._session).money_accounts(firm_id)
        }
        if data.money_account_id not in money:
            raise ValidationError("Receive the payment into a cash or bank account.")
        receipt = PrincipalClaimReceipt(
            claim_id=row.id,
            firm_id=firm_id,
            received_on=data.received_on,
            amount=data.amount,
            money_account_id=data.money_account_id,
            reference=data.reference,
            status="POSTED",
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(receipt)
        self._session.flush()
        entry = DocumentPostingService(self._session).post_principal_claim_receipt(
            firm_id=firm_id,
            settlement_id=receipt.id,
            reference_number=f"CLAIM-{row.claim_number}-PAY-{utc_now():%Y%m%d%H%M%S}",
            received_on=data.received_on,
            amount=data.amount,
            money_account_id=data.money_account_id,
            actor_id=actor_id,
        )
        receipt.journal_entry_id = entry.id
        row.updated_by = actor_id
        self._audit("principal_claim.payment_received", row, actor_id)
        self._session.commit()
        return receipt

    def reverse_receipt(
        self, claim_id: UUID, receipt_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> PrincipalClaim:
        """Take a payment back off the books (a bounced cheque); commit."""
        row = self.get(claim_id, firm_id=firm_id)
        receipt = self._session.get(PrincipalClaimReceipt, receipt_id)
        if (
            receipt is None
            or receipt.is_deleted
            or receipt.claim_id != row.id
            or receipt.status != "POSTED"
        ):
            raise ResourceNotFoundError("Payment not found on this claim.")
        if receipt.journal_entry_id is not None:
            JournalEntryEngine(self._session).reverse_entry(
                receipt.journal_entry_id,
                firm_id=firm_id,
                reference_number=(
                    f"CLAIM-{row.claim_number}-PAYREV-{utc_now():%Y%m%d%H%M%S}"
                ),
                actor_id=actor_id,
            )
        receipt.status = "REVERSED"
        receipt.updated_by = actor_id
        self._audit("principal_claim.payment_reversed", row, actor_id)
        self._session.commit()
        return row

    # ---- cancelling ----------------------------------------------------

    def cancel(
        self, claim_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> PrincipalClaim:
        """Withdraw a claim nothing has settled; reverse it; free its sources.

        Raises:
            ValidationError: If it is cancelled already or partly settled.

        """
        row = self.get(claim_id, firm_id=firm_id)
        if row.status == "CANCELLED":
            raise ValidationError("This claim was already cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the claim is cancelled.")
        if self.outstanding(row) != quantize_ledger(Decimal(str(row.total_amount))):
            raise ValidationError(
                "Part of this claim is settled; reverse its payments and cancel "
                "its credit notes first."
            )
        if row.journal_entry_id is not None:
            JournalEntryEngine(self._session).reverse_entry(
                row.journal_entry_id,
                firm_id=firm_id,
                reference_number=f"CLAIM-{row.claim_number}-REV",
                actor_id=actor_id,
            )
        now = utc_now()
        for line in self._lines([row.id]):
            line.is_deleted = True
            line.deleted_at = now
            line.deleted_by = actor_id
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("principal_claim.cancelled", row, actor_id)
        self._session.commit()
        return row

    # ---- reads ---------------------------------------------------------

    def get(self, claim_id: UUID, *, firm_id: UUID) -> PrincipalClaim:
        """Return one of the firm's claims."""
        row = self._session.get(PrincipalClaim, claim_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Claim not found.")
        return row

    def list_rows(
        self, firm_id: UUID, *, principal_id: UUID | None = None
    ) -> list[PrincipalClaim]:
        """Return the firm's claims, newest first."""
        query = select(PrincipalClaim).where(
            PrincipalClaim.firm_id == firm_id, PrincipalClaim.is_deleted.is_(False)
        )
        if principal_id is not None:
            query = query.where(PrincipalClaim.principal_id == principal_id)
        return list(
            self._session.scalars(
                query.order_by(
                    PrincipalClaim.claim_date.desc(),
                    PrincipalClaim.claim_number.desc(),
                    PrincipalClaim.id.desc(),
                )
            ).all()
        )

    def responses(self, rows: list[PrincipalClaim]) -> list[PrincipalClaimResponse]:
        """Shape claims with their lines and payments, one read per table."""
        if not rows:
            return []
        ids = [row.id for row in rows]
        credited = self.credited(ids)
        paid = self.paid(ids)
        # A cancelled claim's lines are soft-deleted; show what it held.
        lines = self._lines(ids, include_deleted=True)
        receipts = list(
            self._session.scalars(
                select(PrincipalClaimReceipt)
                .where(
                    PrincipalClaimReceipt.claim_id.in_(ids),
                    PrincipalClaimReceipt.is_deleted.is_(False),
                )
                .order_by(PrincipalClaimReceipt.received_on.asc())
            ).all()
        )
        names = self._product_names(
            {line.product_id for line in lines if line.product_id}
        )
        principals = {
            principal_id: name
            for principal_id, name in self._session.execute(
                select(Principal.id, Principal.name).where(
                    Principal.id.in_({row.principal_id for row in rows})
                )
            ).all()
        }
        answer: list[PrincipalClaimResponse] = []
        for row in rows:
            by_note = credited.get(row.id, ZERO)
            by_money = paid.get(row.id, ZERO)
            total = quantize_ledger(Decimal(str(row.total_amount)))
            owed = ZERO if row.status == "CANCELLED" else total - by_note - by_money
            if row.status == "CANCELLED":
                status = "CANCELLED"
            elif owed <= ZERO:
                status = "SETTLED"
            elif by_note + by_money > ZERO:
                status = "PART_SETTLED"
            else:
                status = "RAISED"
            answer.append(
                PrincipalClaimResponse(
                    id=row.id,
                    claim_number=row.claim_number,
                    claim_date=row.claim_date,
                    principal_id=row.principal_id,
                    principal_name=str(principals.get(row.principal_id) or ""),
                    vendor_id=row.vendor_id,
                    period_from=row.period_from,
                    period_to=row.period_to,
                    scheme_amount=row.scheme_amount,
                    expiry_amount=row.expiry_amount,
                    breakage_amount=row.breakage_amount,
                    total_amount=row.total_amount,
                    settled_by_credit_note=by_note,
                    settled_by_payment=by_money,
                    outstanding=owed,
                    status=status,
                    remarks=row.remarks,
                    cancel_reason=row.cancel_reason,
                    version=row.version,
                    lines=[
                        PrincipalClaimLineResponse(
                            line_number=line.line_number,
                            kind=line.kind,
                            source_id=line.source_id,
                            source_number=line.source_number,
                            source_date=line.source_date,
                            product_id=line.product_id,
                            product_name=(
                                names.get(line.product_id) if line.product_id else None
                            ),
                            quantity=line.quantity,
                            description=line.description,
                            amount=line.amount,
                        )
                        for line in lines
                        if line.claim_id == row.id
                    ],
                    receipts=[
                        PrincipalClaimReceiptResponse(
                            id=receipt.id,
                            received_on=receipt.received_on,
                            amount=receipt.amount,
                            money_account_id=receipt.money_account_id,
                            reference=receipt.reference,
                            status=receipt.status,
                        )
                        for receipt in receipts
                        if receipt.claim_id == row.id
                    ],
                )
            )
        return answer

    # ---- print ---------------------------------------------------------

    def render_statement(self, claim_id: UUID, *, firm_id: UUID) -> tuple[bytes, str]:
        """Draw the claim statement sent to the principal.

        Returns:
            The PDF bytes and a file name built from the claim number.

        """
        from app.document_framework.services.letter_pdf import (
            LetterPage,
            LetterPdfRenderer,
            LetterTable,
        )
        from app.document_framework.services.print_support import (
            firm_party,
            load_template,
        )
        from app.sales_invoice.services.invoice_pdf import PartyBlock

        row = self.get(claim_id, firm_id=firm_id)
        view = self.responses([row])[0]
        headings = {
            "SCHEME": "Schemes passed on",
            "EXPIRY": "Expired stock",
            "BREAKAGE": "Breakage returned by customers",
        }
        tables = [
            LetterTable(
                heading=headings[kind],
                columns=("Date", "Document", "Item", "Quantity", "Amount"),
                rows=[
                    (
                        line.source_date.strftime("%d-%m-%Y"),
                        line.source_number,
                        line.product_name or line.description,
                        (
                            f"{Decimal(str(line.quantity)).normalize():f}"
                            if line.quantity is not None
                            else ""
                        ),
                        f"{Decimal(str(line.amount)):,.2f}",
                    )
                    for line in view.lines
                    if line.kind == kind
                ],
                numeric=frozenset({"Quantity", "Amount"}),
            )
            for kind in KINDS
            if any(line.kind == kind for line in view.lines)
        ]
        facts = [
            ("Claim number", row.claim_number),
            ("Date", row.claim_date.strftime("%d-%m-%Y")),
            (
                "Period",
                f"{row.period_from:%d-%m-%Y} to {row.period_to:%d-%m-%Y}",
            ),
            ("Schemes", f"{Decimal(str(row.scheme_amount)):,.2f}"),
            ("Expiry", f"{Decimal(str(row.expiry_amount)):,.2f}"),
            ("Breakage", f"{Decimal(str(row.breakage_amount)):,.2f}"),
            ("Total claimed", f"{Decimal(str(row.total_amount)):,.2f}"),
            ("Still due", f"{view.outstanding:,.2f}"),
        ]
        if row.status == "CANCELLED":
            facts.append(("Status", f"CANCELLED -- {row.cancel_reason or ''}"))
        template = load_template(
            self._session, firm_scope=firm_id, document_type="SALES_INVOICE"
        )
        pdf = LetterPdfRenderer(template.accent_color).render(
            [
                LetterPage(
                    firm=firm_party(firm_id),
                    title="CLAIM STATEMENT",
                    facts=facts,
                    addressee=PartyBlock(name=view.principal_name, address_lines=[]),
                    paragraphs=[
                        "We claim the amounts below for the period, and request "
                        "your credit note or payment."
                    ],
                    tables=tables,
                )
            ]
        )
        return pdf, f"{row.claim_number}.pdf".replace("/", "-")

    # ---- sources -------------------------------------------------------

    def _principal_products(
        self, firm_id: UUID, principal_id: UUID
    ) -> ScalarSelect[UUID]:
        """Return a subquery of the principal's products, through their brand."""
        return (
            select(Product.id)
            .join(Brand, Brand.id == Product.brand_id)
            .where(Product.firm_id == firm_id, Brand.principal_id == principal_id)
            .scalar_subquery()
        )

    def _schemes(
        self, firm_id: UUID, principal_id: UUID, start: date, end: date
    ) -> list[_Candidate]:
        """Redemptions of the principal's schemes, at its share."""
        rows = self._session.execute(
            select(PromotionRedemption, Promotion)
            .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
            .where(
                PromotionRedemption.firm_id == firm_id,
                PromotionRedemption.is_deleted.is_(False),
                PromotionRedemption.status == "CLAIMED",
                PromotionRedemption.redeemed_on >= start,
                PromotionRedemption.redeemed_on <= end,
                Promotion.principal_id == principal_id,
            )
            .order_by(PromotionRedemption.redeemed_on, PromotionRedemption.id)
        ).all()
        return [
            _Candidate(
                kind="SCHEME",
                source_id=redemption.id,
                source_number=redemption.document_number or "",
                source_date=redemption.redeemed_on,
                product_id=None,
                quantity=None,
                description=promotion.name,
                amount=(
                    Decimal(str(redemption.benefit_amount))
                    * Decimal(str(promotion.principal_share_percent))
                    / Decimal("100")
                ).quantize(CENT),
            )
            for redemption, promotion in rows
        ]

    def _expiries(
        self, firm_id: UUID, principal_id: UUID, start: date, end: date
    ) -> list[_Candidate]:
        """Expiry write-offs of the principal's products, at book value."""
        reversal = aliased(InventoryTransaction)
        rows = self._session.execute(
            select(InventoryTransaction, StockLedgerEntry.total_cost)
            .join(
                StockLedgerEntry,
                StockLedgerEntry.transaction_id == InventoryTransaction.id,
            )
            .where(
                InventoryTransaction.firm_id == firm_id,
                InventoryTransaction.is_deleted.is_(False),
                InventoryTransaction.transaction_type == "WRITE_OFF",
                InventoryTransaction.reference_type == "EXPIRY",
                InventoryTransaction.transaction_date >= start,
                InventoryTransaction.transaction_date <= end,
                InventoryTransaction.product_id.in_(
                    self._principal_products(firm_id, principal_id)
                ),
                ~select(reversal.id)
                .where(reversal.reversal_of_transaction_id == InventoryTransaction.id)
                .exists(),
            )
            .order_by(InventoryTransaction.transaction_date, InventoryTransaction.id)
        ).all()
        return [
            _Candidate(
                kind="EXPIRY",
                source_id=movement.id,
                source_number=movement.reference_number,
                source_date=movement.transaction_date,
                product_id=movement.product_id,
                quantity=Decimal(str(movement.quantity)),
                description="Expired stock written off",
                amount=abs(Decimal(str(cost or 0))).quantize(CENT),
            )
            for movement, cost in rows
        ]

    def _breakages(
        self, firm_id: UUID, principal_id: UUID, start: date, end: date
    ) -> list[_Candidate]:
        """Damaged and scrapped return lines, at the taxable rate credited."""
        rows = self._session.execute(
            select(SalesReturnLine, SalesReturn)
            .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
            .where(
                SalesReturn.firm_id == firm_id,
                SalesReturn.is_deleted.is_(False),
                SalesReturnLine.is_deleted.is_(False),
                SalesReturn.status.in_(_DONE_RETURNS),
                SalesReturn.return_date >= start,
                SalesReturn.return_date <= end,
                SalesReturnLine.product_id.in_(
                    self._principal_products(firm_id, principal_id)
                ),
                (
                    func.coalesce(SalesReturnLine.damaged_quantity, 0)
                    + func.coalesce(SalesReturnLine.scrap_quantity, 0)
                )
                > 0,
            )
            .order_by(SalesReturn.return_date, SalesReturnLine.id)
        ).all()
        found: list[_Candidate] = []
        for line, header in rows:
            returned = Decimal(str(line.current_return_quantity or 0))
            broken = Decimal(str(line.damaged_quantity or 0)) + Decimal(
                str(line.scrap_quantity or 0)
            )
            if returned <= 0:
                continue
            taxable = Decimal(str(line.gross_amount or 0)) - Decimal(
                str(line.discount_amount or 0)
            )
            found.append(
                _Candidate(
                    kind="BREAKAGE",
                    source_id=line.id,
                    source_number=header.return_number,
                    source_date=header.return_date,
                    product_id=line.product_id,
                    quantity=broken,
                    description="Returned broken by the customer",
                    amount=(taxable * broken / returned).quantize(CENT),
                )
            )
        return found

    # ---- helpers -------------------------------------------------------

    def _principal(self, principal_id: UUID, *, firm_id: UUID) -> Principal:
        """Return one of the firm's principals."""
        row = self._session.get(Principal, principal_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ValidationError("That principal is not one of this firm's.")
        return row

    def _claimed(self, source_ids: set[UUID]) -> set[tuple[str, UUID]]:
        """Return the (kind, source) pairs a live claim already holds."""
        if not source_ids:
            return set()
        return {
            (kind, source_id)
            for kind, source_id in self._session.execute(
                select(PrincipalClaimLine.kind, PrincipalClaimLine.source_id).where(
                    PrincipalClaimLine.source_id.in_(list(source_ids)),
                    PrincipalClaimLine.is_deleted.is_(False),
                )
            ).all()
        }

    @staticmethod
    def _totals(found: list[_Candidate]) -> dict[str, Decimal]:
        """Sum the candidates by kind."""
        totals = dict.fromkeys(KINDS, ZERO)
        for candidate in found:
            totals[candidate.kind] += candidate.amount
        return totals

    def _lines(
        self, claim_ids: list[UUID], *, include_deleted: bool = False
    ) -> list[PrincipalClaimLine]:
        """Return the claims' lines in order."""
        query = select(PrincipalClaimLine).where(
            PrincipalClaimLine.claim_id.in_(claim_ids)
        )
        if not include_deleted:
            query = query.where(PrincipalClaimLine.is_deleted.is_(False))
        return list(
            self._session.scalars(
                query.order_by(
                    PrincipalClaimLine.claim_id, PrincipalClaimLine.line_number
                )
            ).all()
        )

    def _product_names(self, ids: set[UUID | None]) -> dict[UUID, str]:
        """Return product names by id."""
        wanted = [product_id for product_id in ids if product_id is not None]
        if not wanted:
            return {}
        return {
            product_id: name
            for product_id, name in self._session.execute(
                select(Product.id, Product.name).where(Product.id.in_(wanted))
            ).all()
        }

    @staticmethod
    def _line_response(
        number: int, candidate: _Candidate, names: dict[UUID, str]
    ) -> PrincipalClaimLineResponse:
        """Shape one candidate as a line."""
        return PrincipalClaimLineResponse(
            line_number=number,
            kind=candidate.kind,
            source_id=candidate.source_id,
            source_number=candidate.source_number,
            source_date=candidate.source_date,
            product_id=candidate.product_id,
            product_name=(
                names.get(candidate.product_id) if candidate.product_id else None
            ),
            quantity=candidate.quantity,
            description=candidate.description,
            amount=candidate.amount,
        )

    def _audit(self, action: str, row: PrincipalClaim, actor_id: UUID) -> None:
        """Write one audit row for a claim."""
        record_audit(
            self._session,
            action=action,
            entity_type="principal_claim",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "claim_number": row.claim_number,
                "total_amount": str(row.total_amount),
                "status": row.status,
            },
        )
