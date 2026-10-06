"""Claims to the principal (SEL-11, decision A128).

A distributor passes the principal's schemes on to its customers, writes off
the principal's goods that expire on its shelf, and takes back the ones that
arrive broken -- and the principal owes it for all three. A claim gathers
them for one principal and one period:

* **Scheme** -- each redemption of a promotion the principal funds, at the
  principal's share of the benefit the customer was given; and the free
  goods such a promotion put on a dispatched line, at the same share of what
  they cost. A redemption's benefit is money only, so the goods are a line
  of their own.
* **Free goods** -- free quantity somebody *typed* on a line of the
  principal's products (the "10 + 1" a salesman gives), at what the dispatch
  that shipped it cost. Its own kind, so the principal sees what the firm
  gave of its own accord apart from what its schemes gave.
* **Expiry** -- each stock write-off for expiry of the principal's products,
  at the value the books took off.
* **Breakage** -- each damaged or scrapped line of a completed sales return of
  the principal's products, at the taxable rate the customer was credited.

A fifth kind is not a period's at all. A **rate difference** claim is for one
price cut: the principal lowers its rate from a day, and owes the difference
on the stock the firm held when the day before closed.

* The **rate** is the purchase rate per stock unit before tax -- what the
  principal bills the firm, which is what the cut lowered. Not a batch's
  ``pts``/``ptr``: those are what the *firm* sells a batch at, and a batch
  keeps one figure with no history. The rates default from the product's
  price revision dated that day (new) and the rate in force the day before
  (old), and a typed rate replaces either: the circular is the authority.
* The **stock** is never typed. It is the sum of the movements dated on or
  before the day before the cut -- the figure *Stock valuation* shows as on
  that day, every warehouse summed -- per batch where the product is kept by
  batch.
* The **source** is the principal, the product, the batch and the day
  (``rate_difference_source``), so the same stock is claimed once for one
  cut; a line that is typed and can claim nothing is refused by name, and a
  proposed one is left out.
* The journal credits **purchase price variance**. The stock is not revalued:
  it keeps its moving average, leaves at the dearer cost, and this credit
  offsets that cost of sales. The claim carries no tax; where the principal
  settles it by a GST credit note, the tax follows that note, booked as a
  supplier credit note.

Free goods are valued from the stock ledger's dispatch, never from a price:
a line whose dispatch has no cost contributes nothing rather than zero, and
goods on a note not yet shipped are not claimed. Free goods a completed
sales return has brought back (D-PRC-8) are not claimed: they were not given
after all. A return of the charged units alone reduces nothing, and a claim
already raised is not rewritten by a return that comes after it.

A source is claimed once. Raising posts Dr claims receivable, Cr the
expense the cost sat in -- promotional expense for a scheme's discount, cost
of goods sold for goods given free, inventory adjustment for stock -- so the
firm's costs fall by what it expects back.
The principal settles by credit note (a party adjustment of kind
``PRINCIPAL_CLAIM`` set against its bills) or by paying; how far a claim is
settled is derived from both, never stored. A claim with nothing settled
can be cancelled, which reverses its journal and frees its sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Row, and_, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import ScalarSelect

from app.batch_serial.models import BatchRecord
from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.inventory.models import (
    InventoryRecord,
    InventoryTransaction,
    StockLedgerEntry,
)
from app.principal_claims.models import (
    PrincipalClaim,
    PrincipalClaimLine,
    PrincipalClaimReceipt,
)
from app.products.models import Product
from app.products.models.brand import Brand, Principal
from app.products.models.price_revision import ProductPriceRevision
from app.promotions.models import Promotion, PromotionRedemption
from app.sales_order.models import SalesOrderLine
from app.sales_return.free_goods import free_goods_returned
from app.sales_return.models import SalesReturn, SalesReturnLine

if TYPE_CHECKING:
    from app.document_framework.services.letter_pdf import LetterTable

#: What a period's claim gathers: things that happened between two dates.
PERIOD_KINDS = ("SCHEME", "FREE_GOODS", "EXPIRY", "BREAKAGE")
#: A price cut is one day, not a period, so its claim stands on its own.
RATE_DIFFERENCE = "RATE_DIFFERENCE"
KINDS = (*PERIOD_KINDS, RATE_DIFFERENCE)
_DONE_RETURNS = ("COMPLETED", "CLOSED")
#: A note whose goods have left. A draft or approved note has shipped
#: nothing, and a cancelled one gave its goods back.
_SHIPPED_NOTES = ("DISPATCHED", "COMPLETED", "CLOSED")
#: Where a claimed amount's cost sat, and so which account gets it back.
_PROMOTION, _STOCK, _SOLD, _PRICE = "PROMOTION", "STOCK", "SOLD", "PRICE"
CENT = Decimal("0.01")
#: Fixed, so the same principal, product, batch and day always make the same
#: source id -- which is what lets the lines' unique index refuse a second
#: claim for one price cut.
_RATE_SOURCES = UUID("6f0f5c1e-6a0b-4d53-9a3f-2f1c8f4a7d10")


def rate_difference_source(
    principal_id: UUID, product_id: UUID, batch_id: UUID | None, effective_date: date
) -> UUID:
    """Return the source a price cut's stock is claimed under, once."""
    return uuid5(
        _RATE_SOURCES,
        f"{principal_id}:{product_id}:{batch_id or '-'}:{effective_date.isoformat()}",
    )


class RateDifferenceLineWrite(BaseModel):
    """One product on a price cut: its rates, never its stock.

    The quantity is the server's, read from the stock ledger. A rate left out
    is taken from the price revision recorded for that day; a rate typed
    replaces it, because the principal's circular is the authority.
    """

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    #: One batch of a product kept by batch. Left out, the line covers every
    #: batch with stock that no other line names.
    batch_id: UUID | None = None
    #: Purchase rate per stock unit before tax, before and after the cut.
    old_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    new_rate: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )


class PrincipalClaimWrite(BaseModel):
    """Raise a claim on one principal: for one period, or for one price cut.

    A rate difference claim names ``kinds=["RATE_DIFFERENCE"]`` and the
    ``effective_date`` of the cut; its period is that one day, so
    ``period_from`` and ``period_to`` may be left out.
    """

    model_config = ConfigDict(extra="forbid")

    principal_id: UUID
    period_from: date
    period_to: date
    claim_date: date
    #: Which of the period's four to claim; all four when omitted. A rate
    #: difference is asked for by name and alone.
    kinds: list[str] = Field(default_factory=lambda: list(PERIOD_KINDS), min_length=1)
    #: Rate difference only: the day the principal's new rates took effect.
    #: The stock claimed on is what stood at the close of the day before.
    effective_date: date | None = None
    #: Rate difference only. Left out, the claim is every product of the
    #: principal with stock and a recorded cut that day. Given, it is exactly
    #: these lines -- the proposed ones as corrected, less any taken off, plus
    #: any added by product.
    rate_lines: list[RateDifferenceLineWrite] | None = Field(
        default=None, min_length=1, max_length=2000
    )
    remarks: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def _one_day(cls, data: object) -> object:
        """Give a rate difference claim its one-day period where none is sent."""
        if (
            isinstance(data, dict)
            and data.get("kinds") == [RATE_DIFFERENCE]
            and data.get("effective_date") is not None
        ):
            data = dict(data)
            for end in ("period_from", "period_to"):
                if data.get(end) is None:
                    data[end] = data["effective_date"]
        return data

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
        if RATE_DIFFERENCE not in self.kinds:
            if self.effective_date is not None or self.rate_lines is not None:
                raise ValueError(
                    "An effective date and rates belong to a price cut: only a "
                    "rate difference claim takes them."
                )
            return self
        if self.kinds != [RATE_DIFFERENCE]:
            raise ValueError(
                "A rate difference claim stands on its own: it is for one price "
                "cut, not a period. Raise the period's claim separately."
            )
        if self.effective_date is None:
            raise ValueError("Give the date the new rates took effect.")
        if (self.period_from, self.period_to) != (
            self.effective_date,
            self.effective_date,
        ):
            raise ValueError(
                "A rate difference claim's period is the day of the cut: leave "
                "the period out."
            )
        named = [(line.product_id, line.batch_id) for line in self.rate_lines or []]
        if len(named) != len(set(named)):
            raise ValueError("A product (or a batch of it) is listed more than once.")
        return self

    @property
    def is_rate_difference(self) -> bool:
        """Say whether this is a claim for a price cut rather than a period."""
        return self.kinds == [RATE_DIFFERENCE]


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
    #: For a rate difference: the stock on hand at the close of the day
    #: before the cut, summed over the firm's warehouses.
    quantity: Decimal | None
    #: Rate difference only: the batch, and the purchase rate per stock unit
    #: before tax before and after the cut.
    batch_id: UUID | None = None
    batch_number: str | None = None
    old_rate: Decimal | None = None
    new_rate: Decimal | None = None
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
    #: Free goods typed on bill lines of the principal's products, at cost.
    free_goods_amount: Decimal
    expiry_amount: Decimal
    breakage_amount: Decimal
    #: A price cut on the stock in hand: (old rate - new rate) x quantity.
    rate_difference_amount: Decimal
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
    free_goods_amount: Decimal
    expiry_amount: Decimal
    breakage_amount: Decimal
    rate_difference_amount: Decimal
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
    #: Which expense the cost sat in: the journal credits it back there.
    credit: str = _PROMOTION
    #: Rate difference only.
    batch_id: UUID | None = None
    batch_number: str | None = None
    old_rate: Decimal | None = None
    new_rate: Decimal | None = None


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
        """Return every unclaimed source of the period, schemes first.

        The period's four kinds only: a price cut is gathered for a day, by
        ``_rate_differences``.
        """
        self._principal(principal_id, firm_id=firm_id)
        wanted = set(kinds or PERIOD_KINDS)
        found: list[_Candidate] = []
        goods = (
            self._free_goods(firm_id, principal_id, period_from, period_to)
            if wanted & {"SCHEME", "FREE_GOODS"}
            else []
        )
        if "SCHEME" in wanted:
            found += self._schemes(firm_id, principal_id, period_from, period_to)
            found += [c for c in goods if c.kind == "SCHEME"]
        if "FREE_GOODS" in wanted:
            found += [c for c in goods if c.kind == "FREE_GOODS"]
        if "EXPIRY" in wanted:
            found += self._expiries(firm_id, principal_id, period_from, period_to)
        if "BREAKAGE" in wanted:
            found += self._breakages(firm_id, principal_id, period_from, period_to)
        claimed = self._claimed({c.source_id for c in found})
        return [
            c for c in found if (c.kind, c.source_id) not in claimed and c.amount > 0
        ]

    def _gather(self, data: PrincipalClaimWrite, *, firm_id: UUID) -> list[_Candidate]:
        """Return what the claim described would hold: a cut's, or a period's."""
        if data.is_rate_difference and data.effective_date is not None:
            return self._rate_differences(
                firm_id, data.principal_id, data.effective_date, data.rate_lines
            )
        return self.candidates(
            firm_id=firm_id,
            principal_id=data.principal_id,
            period_from=data.period_from,
            period_to=data.period_to,
            kinds=data.kinds,
        )

    def preview(
        self, data: PrincipalClaimWrite, *, firm_id: UUID
    ) -> PrincipalClaimPreview:
        """Return what raising the claim would hold, writing nothing."""
        found = self._gather(data, firm_id=firm_id)
        totals = self._totals(found)
        names = self._product_names({c.product_id for c in found if c.product_id})
        return PrincipalClaimPreview(
            principal_id=data.principal_id,
            period_from=data.period_from,
            period_to=data.period_to,
            scheme_amount=totals["SCHEME"],
            free_goods_amount=totals["FREE_GOODS"],
            expiry_amount=totals["EXPIRY"],
            breakage_amount=totals["BREAKAGE"],
            rate_difference_amount=totals[RATE_DIFFERENCE],
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
        found = self._gather(data, firm_id=firm_id)
        if not found:
            what = (
                f"the price cut of {data.period_from:%d-%m-%Y}"
                if data.is_rate_difference
                else "that period"
            )
            raise ValidationError(
                f"Nothing is left to claim from {principal.name} for {what}."
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
            free_goods_amount=totals["FREE_GOODS"],
            expiry_amount=totals["EXPIRY"],
            breakage_amount=totals["BREAKAGE"],
            rate_difference_amount=totals[RATE_DIFFERENCE],
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
                    batch_id=candidate.batch_id,
                    old_rate=candidate.old_rate,
                    new_rate=candidate.new_rate,
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
        # By where the cost sat, not by kind: a scheme's discount went to
        # promotional expense and its free goods to cost of goods sold.
        back = dict.fromkeys((_PROMOTION, _STOCK, _SOLD, _PRICE), ZERO)
        for candidate in found:
            back[candidate.credit] += candidate.amount
        entry = DocumentPostingService(self._session).post_principal_claim(
            firm_id=firm_id,
            claim_id=row.id,
            claim_number=number,
            claim_date=data.claim_date,
            scheme_amount=back[_PROMOTION],
            stock_amount=back[_STOCK],
            free_goods_amount=back[_SOLD],
            rate_difference_amount=back[_PRICE],
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
        batch_ids = {line.batch_id for line in lines if line.batch_id}
        batches: dict[UUID, str] = (
            {
                batch_id: number
                for batch_id, number in self._session.execute(
                    select(BatchRecord.id, BatchRecord.batch_number).where(
                        BatchRecord.id.in_(batch_ids)
                    )
                ).all()
            }
            if batch_ids
            else {}
        )
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
                    free_goods_amount=row.free_goods_amount,
                    expiry_amount=row.expiry_amount,
                    breakage_amount=row.breakage_amount,
                    rate_difference_amount=row.rate_difference_amount,
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
                            batch_id=line.batch_id,
                            batch_number=(
                                batches.get(line.batch_id) if line.batch_id else None
                            ),
                            old_rate=line.old_rate,
                            new_rate=line.new_rate,
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
        )
        from app.document_framework.services.print_support import (
            firm_party,
            load_template,
        )
        from app.sales_invoice.services.invoice_pdf import PartyBlock

        row = self.get(claim_id, firm_id=firm_id)
        view = self.responses([row])[0]
        tables = self.statement_tables(view)
        cut = any(line.kind == RATE_DIFFERENCE for line in view.lines)
        facts = [
            ("Claim number", row.claim_number),
            ("Date", row.claim_date.strftime("%d-%m-%Y")),
            (
                # A price cut is a day, and the stock is the day before's.
                ("New rates effective", f"{row.period_from:%d-%m-%Y}")
                if cut
                else (
                    "Period",
                    f"{row.period_from:%d-%m-%Y} to {row.period_to:%d-%m-%Y}",
                )
            ),
            ("Schemes", f"{Decimal(str(row.scheme_amount)):,.2f}"),
            ("Free goods", f"{Decimal(str(row.free_goods_amount)):,.2f}"),
            ("Expiry", f"{Decimal(str(row.expiry_amount)):,.2f}"),
            ("Breakage", f"{Decimal(str(row.breakage_amount)):,.2f}"),
            (
                "Rate difference",
                f"{Decimal(str(row.rate_difference_amount)):,.2f}",
            ),
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
                        (
                            (
                                "We claim the difference between the old and the "
                                "new rate on the stock we held at the close of "
                                f"{row.period_from - timedelta(days=1):%d-%m-%Y}, "
                                "and request your credit note or payment."
                            )
                            if cut
                            else (
                                "We claim the amounts below for the period, and "
                                "request your credit note or payment."
                            )
                        )
                    ],
                    tables=tables,
                )
            ]
        )
        return pdf, f"{row.claim_number}.pdf".replace("/", "-")

    @staticmethod
    def statement_tables(view: PrincipalClaimResponse) -> list[LetterTable]:
        """Lay a claim's lines out as the statement's tables, one per kind.

        A rate difference has columns of its own -- the batch and both rates
        -- so the principal can check each line against its circular and the
        stock statement.
        """
        from app.document_framework.services.letter_pdf import LetterTable

        def units(value: Decimal | None) -> str:
            """Print a quantity without trailing zeros."""
            return "" if value is None else f"{Decimal(str(value)).normalize():f}"

        def money(value: Decimal | None) -> str:
            """Print an amount or a rate to the paisa."""
            return "" if value is None else f"{Decimal(str(value)):,.2f}"

        headings = {
            "SCHEME": "Schemes passed on",
            "FREE_GOODS": "Free goods given on bills",
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
                        units(line.quantity),
                        money(line.amount),
                    )
                    for line in view.lines
                    if line.kind == kind
                ],
                numeric=frozenset({"Quantity", "Amount"}),
            )
            for kind in PERIOD_KINDS
            if any(line.kind == kind for line in view.lines)
        ]
        cut = [line for line in view.lines if line.kind == RATE_DIFFERENCE]
        if cut:
            tables.append(
                LetterTable(
                    heading="Rate difference on stock in hand",
                    columns=(
                        "Item",
                        "Batch",
                        "Quantity",
                        "Old rate",
                        "New rate",
                        "Amount",
                    ),
                    rows=[
                        (
                            line.product_name or line.description,
                            line.batch_number or "",
                            units(line.quantity),
                            money(line.old_rate),
                            money(line.new_rate),
                            money(line.amount),
                        )
                        for line in cut
                    ],
                    numeric=frozenset({"Quantity", "Old rate", "New rate", "Amount"}),
                )
            )
        return tables

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

    def _free_goods(
        self, firm_id: UUID, principal_id: UUID, start: date, end: date
    ) -> list[_Candidate]:
        """Free goods shipped in the period, at what their dispatch cost.

        Two kinds from one read of the period's shipped note lines. Free
        quantity an offer gave (the order line names the offer) is the
        scheme's, claimed where the principal funds that offer and at its
        share. Free quantity a person typed is claimed in full where the
        product is the principal's. An offer the firm funds itself is claimed
        from nobody.

        The cost is the stock ledger's for the note and product, split over
        the note's lines by what each shipped and then by the free part of
        the line. No cost on the ledger is no claim: NULL is not zero.
        """
        shipped = (
            DeliveryNote.firm_id == firm_id,
            DeliveryNote.is_deleted.is_(False),
            DeliveryNote.status.in_(_SHIPPED_NOTES),
            DeliveryNote.delivery_date >= start,
            DeliveryNote.delivery_date <= end,
        )
        funded = {
            promotion_id: (name, Decimal(str(share)))
            for promotion_id, name, share in self._session.execute(
                select(
                    Promotion.id, Promotion.name, Promotion.principal_share_percent
                ).where(
                    Promotion.firm_id == firm_id,
                    Promotion.principal_id == principal_id,
                )
            ).all()
        }
        rows = self._session.execute(
            select(DeliveryNoteLine, DeliveryNote, SalesOrderLine.free_promotion_id)
            .join(DeliveryNote, DeliveryNote.id == DeliveryNoteLine.delivery_note_id)
            .outerjoin(
                SalesOrderLine,
                SalesOrderLine.id == DeliveryNoteLine.sales_order_line_id,
            )
            .where(
                *shipped,
                DeliveryNoteLine.is_deleted.is_(False),
                DeliveryNoteLine.free_quantity > 0,
                or_(
                    and_(
                        SalesOrderLine.free_promotion_id.is_(None),
                        DeliveryNoteLine.product_id.in_(
                            self._principal_products(firm_id, principal_id)
                        ),
                    ),
                    SalesOrderLine.free_promotion_id.in_(
                        select(Promotion.id).where(
                            Promotion.firm_id == firm_id,
                            Promotion.principal_id == principal_id,
                        )
                    ),
                ),
            )
            .order_by(DeliveryNote.delivery_date, DeliveryNoteLine.id)
        ).all()
        if not rows:
            return []
        # Grouped in SQL over the period's notes, never by a list of ids.
        costs = {
            (note_id, product_id): Decimal(str(total))
            for note_id, product_id, total in self._session.execute(
                select(
                    DeliveryNote.id,
                    StockLedgerEntry.product_id,
                    func.sum(StockLedgerEntry.total_cost),
                )
                .join(
                    DeliveryNote,
                    and_(
                        DeliveryNote.delivery_note_number
                        == StockLedgerEntry.reference_number,
                        DeliveryNote.firm_id == StockLedgerEntry.firm_id,
                    ),
                )
                .where(
                    *shipped,
                    StockLedgerEntry.reference_type == "DELIVERY_NOTE",
                    StockLedgerEntry.transaction_type == "DISPATCH",
                    StockLedgerEntry.total_cost.is_not(None),
                    StockLedgerEntry.is_deleted.is_(False),
                )
                .group_by(DeliveryNote.id, StockLedgerEntry.product_id)
            ).all()
            if total is not None
        }
        moved = {
            (note_id, product_id): Decimal(str(total or 0))
            for note_id, product_id, total in self._session.execute(
                select(
                    DeliveryNoteLine.delivery_note_id,
                    DeliveryNoteLine.product_id,
                    func.sum(DeliveryNoteLine.delivered_quantity),
                )
                .join(
                    DeliveryNote, DeliveryNote.id == DeliveryNoteLine.delivery_note_id
                )
                .where(*shipped, DeliveryNoteLine.is_deleted.is_(False))
                .group_by(
                    DeliveryNoteLine.delivery_note_id, DeliveryNoteLine.product_id
                )
            ).all()
        }
        # Free goods that have since come back were not given after all
        # (D-PRC-8): a completed return, off the note line or off the bill
        # that billed it, takes its free units out of what is claimed. Read
        # over the period's notes, never by a list of ids.
        came_back = {
            note_line_id: Decimal(str(units or 0))
            for note_line_id, units in self._session.execute(
                free_goods_returned(
                    DeliveryNoteLine.id,
                    func.sum(SalesReturnLine.free_quantity),
                )
                .join(
                    DeliveryNote, DeliveryNote.id == DeliveryNoteLine.delivery_note_id
                )
                .where(*shipped, SalesReturn.firm_id == firm_id)
                .group_by(DeliveryNoteLine.id)
            ).all()
        }
        found: list[_Candidate] = []
        for line, note, promotion_id in rows:
            key = (note.id, line.product_id)
            cost = costs.get(key)
            whole = moved.get(key, ZERO)
            shipped_free = Decimal(str(line.free_quantity or 0))
            sent = Decimal(str(line.current_delivery_quantity or 0)) + shipped_free
            free = shipped_free - came_back.get(line.id, ZERO)
            if cost is None or whole <= 0 or sent <= 0 or free <= 0:
                continue
            # The line's part of the movement, then the free part of the line.
            given = (
                abs(cost)
                * Decimal(str(line.delivered_quantity or 0))
                / whole
                * free
                / sent
            )
            if promotion_id is None:
                kind, description, share = (
                    "FREE_GOODS",
                    "Free goods given on the bill",
                    Decimal("100"),
                )
            else:
                name, share = funded[promotion_id]
                kind, description = "SCHEME", f"Free goods under {name}"
            found.append(
                _Candidate(
                    kind=kind,
                    source_id=line.id,
                    source_number=note.delivery_note_number,
                    source_date=note.delivery_date,
                    product_id=line.product_id,
                    quantity=free,
                    description=description,
                    amount=(given * share / Decimal("100")).quantize(CENT),
                    credit=_SOLD,
                )
            )
        return found

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
                credit=_STOCK,
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
                    credit=_STOCK,
                )
            )
        return found

    def _rate_differences(
        self,
        firm_id: UUID,
        principal_id: UUID,
        on: date,
        typed: list[RateDifferenceLineWrite] | None,
    ) -> list[_Candidate]:
        """Return what a price cut taking effect on ``on`` lets the firm claim.

        One line per product, or per batch of a product kept by batch: the
        stock at the close of the day before, times the old rate less the
        new. With no lines typed it is every product of the principal with
        stock and a recorded cut that day, less what a live claim already
        holds; a rise, an unchanged rate and an empty shelf are left out.
        With lines typed it is exactly those, and one that can claim nothing
        -- not the principal's, no drop, no stock, claimed already -- is
        refused by name rather than dropped, since somebody asked for it.

        Raises:
            ValidationError: If the cut has not taken effect, or a typed line
                can claim nothing.

        """
        principal = self._principal(principal_id, firm_id=firm_id)
        if on > firm_today(self._session, firm_id):
            raise ValidationError(
                f"A price cut from {on:%d-%m-%Y} has not taken effect: the stock "
                "it is claimed on is what closes the day before."
            )
        close = on - timedelta(days=1)
        catalogue = {
            row.id: row
            for row in self._session.execute(
                select(
                    Product.id,
                    Product.code,
                    Product.name,
                    Product.track_batch,
                    Product.purchase_price,
                )
                .join(Brand, Brand.id == Product.brand_id)
                .where(Product.firm_id == firm_id, Brand.principal_id == principal_id)
            ).all()
        }
        recorded = self._recorded_rates(firm_id, principal_id, on, catalogue)
        held = self._stock_at_close(firm_id, principal_id, close)
        explicit = typed is not None
        asked: list[tuple[UUID, UUID | None, Decimal | None, Decimal | None]]
        if typed is None:
            asked = [
                (product_id, None, old, new)
                for product_id, (old, new) in recorded.items()
                if new < old
            ]
        else:
            asked = [
                (line.product_id, line.batch_id, line.old_rate, line.new_rate)
                for line in typed
            ]
        strangers = [
            product_id for product_id, *_ in asked if product_id not in catalogue
        ]
        if strangers:
            codes = self._session.scalars(
                select(Product.code).where(
                    Product.firm_id == firm_id, Product.id.in_(strangers)
                )
            ).all()
            raise ValidationError(
                f"{', '.join(sorted(codes)) or 'A product listed'} is not one of "
                f"{principal.name}'s products, so it is no part of this claim."
            )
        # A line naming a batch speaks for that batch; one naming none covers
        # whatever of the product is left.
        named = {
            (product_id, batch_id)
            for product_id, batch_id, *_ in asked
            if batch_id is not None
        }
        found: list[_Candidate] = []
        for product_id, batch_id, typed_old, typed_new in asked:
            product = catalogue[product_id]
            if batch_id is not None and not product.track_batch:
                raise ValidationError(
                    f"{product.code} is not kept by batch; leave the batch out."
                )
            default = recorded.get(product_id)
            old = typed_old if typed_old is not None else (default or (None,))[0]
            new = typed_new if typed_new is not None else (default or (None, None))[1]
            if old is None or new is None:
                raise ValidationError(
                    f"No change of purchase price is recorded for {product.code} "
                    f"from {on:%d-%m-%Y}; type the old and the new rate."
                )
            if new >= old:
                raise ValidationError(
                    f"{product.code}: the new rate {new:f} is not lower than the "
                    f"old rate {old:f}, so there is nothing to claim."
                )
            stock = held.get(product_id, {})
            if product.track_batch:
                shelves = [
                    (held_batch, number, quantity)
                    for held_batch, (number, quantity) in stock.items()
                    if (
                        held_batch == batch_id
                        if batch_id is not None
                        else (product_id, held_batch) not in named
                    )
                ]
            else:
                shelves = [(None, None, sum((q for _, q in stock.values()), ZERO))]
            shelves = [shelf for shelf in shelves if shelf[2] > 0]
            if not shelves and explicit:
                raise ValidationError(
                    f"{product.code} had no stock on hand at the close of "
                    f"{close:%d-%m-%Y}, so there is nothing to claim on it."
                )
            how = (
                "rates from the price revision"
                if default == (old, new)
                else "rates as typed"
            )
            for held_batch, number, quantity in shelves:
                amount = ((old - new) * quantity).quantize(CENT)
                if amount <= 0:
                    continue
                found.append(
                    _Candidate(
                        kind=RATE_DIFFERENCE,
                        source_id=rate_difference_source(
                            principal_id, product_id, held_batch, on
                        ),
                        source_number=product.code,
                        source_date=on,
                        product_id=product_id,
                        quantity=quantity,
                        description=(
                            f"Price cut from {on:%d-%m-%Y} on stock at the close "
                            f"of {close:%d-%m-%Y}: {how}"
                        ),
                        amount=amount,
                        credit=_PRICE,
                        batch_id=held_batch,
                        batch_number=number,
                        old_rate=old,
                        new_rate=new,
                    )
                )
        found.sort(key=lambda c: (c.source_number, c.batch_number or ""))
        holders = self._claimed_on({c.source_id for c in found})
        if explicit:
            for candidate in found:
                if candidate.source_id in holders:
                    batch = (
                        f" batch {candidate.batch_number}"
                        if candidate.batch_number
                        else ""
                    )
                    raise ValidationError(
                        f"{candidate.source_number}{batch} is already claimed for "
                        f"the price cut of {on:%d-%m-%Y}, on claim "
                        f"{holders[candidate.source_id]}; cancel that claim to "
                        "claim it again."
                    )
        return [c for c in found if c.source_id not in holders]

    def _recorded_rates(
        self,
        firm_id: UUID,
        principal_id: UUID,
        on: date,
        catalogue: dict[UUID, Row[tuple[UUID, str, str, bool, Decimal | None]]],
    ) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return the purchase rate before and from ``on``, where one was revised.

        The new rate is the price revision dated that day; the old one is the
        rate in force the day before -- the latest earlier revision naming a
        purchase price, else the product's own. A product with no revision
        that day, or no earlier rate to compare with, is absent.
        """
        revised = (
            ProductPriceRevision.firm_id == firm_id,
            ProductPriceRevision.is_deleted.is_(False),
            ProductPriceRevision.purchase_price.is_not(None),
            ProductPriceRevision.product_id.in_(
                self._principal_products(firm_id, principal_id)
            ),
        )
        new = {
            product_id: Decimal(str(price))
            for product_id, price in self._session.execute(
                select(
                    ProductPriceRevision.product_id,
                    ProductPriceRevision.purchase_price,
                ).where(*revised, ProductPriceRevision.effective_from == on)
            ).all()
        }
        if not new:
            return {}
        old: dict[UUID, Decimal] = {}
        # Oldest first, so the latest earlier revision is what is left. Read
        # for the principal's products, never by a list of ids.
        for product_id, price in self._session.execute(
            select(ProductPriceRevision.product_id, ProductPriceRevision.purchase_price)
            .where(*revised, ProductPriceRevision.effective_from < on)
            .order_by(ProductPriceRevision.effective_from.asc())
        ).all():
            old[product_id] = Decimal(str(price))
        rates: dict[UUID, tuple[Decimal, Decimal]] = {}
        for product_id, price in new.items():
            product = catalogue.get(product_id)
            before = old.get(product_id)
            if before is None and product is not None:
                card = product.purchase_price
                before = None if card is None else Decimal(str(card))
            if before is not None and before > 0:
                rates[product_id] = (before, price)
        return rates

    def _stock_at_close(
        self, firm_id: UUID, principal_id: UUID, close: date
    ) -> dict[UUID, dict[UUID | None, tuple[str | None, Decimal]]]:
        """Return the principal's stock at the close of a day, by product and batch.

        Read from the movements dated on or before the day, as the stock
        valuation reads it, so the figure is the one *Stock valuation* shows
        as on that day: what the firm owns, every warehouse summed,
        quarantined goods included. Grouped in SQL by the batch of the stock
        row each movement moved.
        """
        owned = func.coalesce(
            InventoryTransaction.owned_quantity_delta,
            InventoryTransaction.current_quantity_delta
            + InventoryTransaction.quarantine_quantity_delta,
        )
        stock: dict[UUID, dict[UUID | None, tuple[str | None, Decimal]]] = {}
        for product_id, batch_id, number, quantity in self._session.execute(
            select(
                InventoryTransaction.product_id,
                InventoryRecord.batch_id,
                BatchRecord.batch_number,
                func.sum(owned),
            )
            .join(
                InventoryRecord, InventoryRecord.id == InventoryTransaction.inventory_id
            )
            .outerjoin(BatchRecord, BatchRecord.id == InventoryRecord.batch_id)
            .where(
                InventoryTransaction.firm_id == firm_id,
                InventoryTransaction.is_deleted.is_(False),
                InventoryTransaction.transaction_date <= close,
                InventoryTransaction.product_id.in_(
                    self._principal_products(firm_id, principal_id)
                ),
            )
            .group_by(
                InventoryTransaction.product_id,
                InventoryRecord.batch_id,
                BatchRecord.batch_number,
            )
        ).all():
            stock.setdefault(product_id, {})[batch_id] = (
                number,
                Decimal(str(quantity or 0)),
            )
        return stock

    def _claimed_on(self, source_ids: set[UUID]) -> dict[UUID, str]:
        """Return the claim number holding each rate difference source."""
        if not source_ids:
            return {}
        return {
            source_id: number
            for source_id, number in self._session.execute(
                select(PrincipalClaimLine.source_id, PrincipalClaim.claim_number)
                .join(PrincipalClaim, PrincipalClaim.id == PrincipalClaimLine.claim_id)
                .where(
                    PrincipalClaimLine.kind == RATE_DIFFERENCE,
                    PrincipalClaimLine.source_id.in_(list(source_ids)),
                    PrincipalClaimLine.is_deleted.is_(False),
                )
            ).all()
        }

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
            batch_id=candidate.batch_id,
            batch_number=candidate.batch_number,
            old_rate=candidate.old_rate,
            new_rate=candidate.new_rate,
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
