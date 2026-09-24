"""Collect tax at source on what a buyer actually pays.

The one thing to understand before changing anything here: **206C(1H) is
charged on consideration received, not on what was invoiced.** Every other tax
in this system is computed while a document is priced; this one is computed
when money arrives, and everything below follows from that.

The second: **the Finance Act 2025 omitted section 206C(1H) with effect from
1 April 2025.** A receipt dated on or after that day attracts no tax under it,
whatever the firm's settings say; a receipt dated before it is charged exactly
as it always was, and a collection already made is never rewritten (D-CMP-12).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.money import ZERO, quantize_ledger
from app.customers.models import Customer
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services import CustomerService
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.settlements.models import Settlement, SettlementDirection, SettlementStatus
from app.tcs.models import TcsCollection, TcsCollectionStatus, TcsSettings
from app.tcs.schemas import (
    TcsBuyerPosition,
    TcsCollectionResponse,
    TcsPreview,
    TcsSettingsResponse,
    TcsSettingsWrite,
)

HUNDRED = Decimal("100")

#: The day section 206C(1H) stopped applying: omitted by the Finance Act 2025
#: with effect from 1 April 2025. Judged on the receipt's own date, so a
#: receipt from before it -- recorded late, or reversed -- is treated as the
#: law then stood.
SECTION_206C_1H_OMITTED_FROM = date(2025, 4, 1)

#: What the section says, for a firm that has never opened the settings. These
#: are the defaults on the row as well; named here so the service can answer
#: about a firm with no row at all without writing one to do it.
DEFAULT_THRESHOLD = Decimal("5000000")
DEFAULT_RATE = Decimal("0.1")
DEFAULT_RATE_WITHOUT_PAN = Decimal("1")
DEFAULT_SELLER_TURNOVER = Decimal("100000000")


class TcsService:
    """Decide, record and reverse tax collected at source."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._firms = FirmMetadataReader(session)
        self._customers = CustomerService(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)

    # ---- settings ------------------------------------------------------

    def settings_for(self, firm_id: UUID) -> TcsSettings | None:
        """Return a firm's TCS row, or None where it has never set one."""
        return self._session.scalar(
            select(TcsSettings).where(
                TcsSettings.firm_id == firm_id,
                TcsSettings.is_deleted.is_(False),
            )
        )

    def read_settings(self, firm_id: UUID) -> TcsSettingsResponse:
        """Return a firm's policy, or the section's own defaults.

        A firm with no row is not in scope and collects nothing, which is what
        the defaults say. Answering with them rather than with nulls means the
        screen shows the rule the firm would be under if it switched the
        section on, which is the question somebody opening this page has.

        Args:
            firm_id: The firm to read.

        Returns:
            The policy as it stands.

        """
        row = self.settings_for(firm_id)
        if row is None:
            return TcsSettingsResponse(
                section_code="206C_1H",
                is_enabled=False,
                threshold_amount=DEFAULT_THRESHOLD,
                rate_percent=DEFAULT_RATE,
                rate_without_pan_percent=DEFAULT_RATE_WITHOUT_PAN,
                preceding_year_turnover=ZERO,
                seller_turnover_threshold=DEFAULT_SELLER_TURNOVER,
                seller_in_scope=False,
            )
        return self._settings_response(row)

    def write_settings(
        self, firm_id: UUID, payload: TcsSettingsWrite, *, actor_id: UUID
    ) -> TcsSettingsResponse:
        """Create or amend a firm's policy.

        Dumped with ``exclude_unset``, so an omitted field is left alone and an
        explicit value is written. Switching the section on is deliberately
        allowed even below the turnover threshold -- the firm may know
        something about its own preceding year that the number here does not
        yet reflect -- but nothing is collected until both are true, and the
        response says which.

        Args:
            firm_id: The firm to configure.
            payload: The fields to change.
            actor_id: The user making the change.

        Returns:
            The policy as it now stands.

        """
        row = self.settings_for(firm_id)
        before = None if row is None else self._snapshot(row)
        if row is None:
            row = TcsSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="tcs.settings_changed",
            entity_type="tcs_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return self._settings_response(row)

    # ---- deciding ------------------------------------------------------

    def preview(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        amount: Decimal,
        on: date,
        excluding_settlement_id: UUID | None = None,
    ) -> TcsPreview:
        """Say what a receipt of this size would attract, before it is taken.

        The question "how much do I ask this buyer for" has to be answerable
        before the receipt exists, or the figure is only ever discovered after
        the money has been taken and the buyer has to be asked for more.

        Args:
            firm_id: The collecting firm.
            customer_id: The buyer.
            amount: The consideration about to be received.
            on: The date it would be received.
            excluding_settlement_id: A receipt to leave out of the running
                total. Set when charging a receipt that has already been
                written, so it is not counted as money the buyer had already
                paid before it -- which would charge the first receipt over
                the threshold on itself.

        Returns:
            The whole calculation, including why nothing is due where nothing
            is.

        Raises:
            ValidationError: If the amount is negative.
            ResourceNotFoundError: If the customer is not this firm's.

        """
        if amount < ZERO:
            raise ValidationError("A receipt cannot be for a negative amount.")
        customer = self._customer(firm_id=firm_id, customer_id=customer_id)
        year_start = self._financial_year_start(firm_id, on)
        settings = self.settings_for(firm_id)
        threshold = DEFAULT_THRESHOLD if settings is None else settings.threshold_amount
        cumulative, tax_owed = self._consideration_so_far(
            firm_id=firm_id,
            customer_id=customer_id,
            year_start=year_start,
            up_to=on,
            excluding_settlement_id=excluding_settlement_id,
        )
        # Money the buyer sends first settles the tax already collected from
        # them, and that part is not consideration for the goods -- so it is
        # not charged again (D-CMP-13). What is left of the receipt is.
        pays_tax = min(amount, tax_owed)
        consideration = amount - pays_tax
        without_pan = not (customer.pan_number or "").strip()
        rate = self._rate(settings, without_pan=without_pan)

        blank = {
            "financial_year_start": year_start,
            "cumulative_before": cumulative,
            "threshold_amount": threshold,
            "taxable_amount": ZERO,
            "rate_percent": rate,
            "without_pan": without_pan,
            "tcs_amount": ZERO,
        }
        if on >= SECTION_206C_1H_OMITTED_FROM:
            return TcsPreview(
                applicable=False,
                reason=(
                    "Section 206C(1H) was omitted by the Finance Act 2025 from "
                    "1 April 2025, so nothing is collected under it on a "
                    "receipt from that date."
                ),
                **blank,
            )
        if settings is None or not settings.is_enabled:
            return TcsPreview(
                applicable=False,
                reason="This firm does not collect tax at source.",
                **blank,
            )
        if not self._seller_in_scope(settings):
            return TcsPreview(
                applicable=False,
                reason=(
                    "The firm's preceding-year turnover is below the threshold "
                    "the section applies from."
                ),
                **blank,
            )
        if consideration <= ZERO:
            return TcsPreview(
                applicable=False,
                reason=(
                    "This receipt only settles tax already collected from the "
                    "buyer, which is not consideration for the goods."
                ),
                **blank,
            )
        taxable = self._taxable_part(
            amount=consideration,
            cumulative=cumulative,
            threshold=threshold,
            already_taxed=self._already_taxed(
                firm_id=firm_id,
                customer_id=customer_id,
                year_start=year_start,
                up_to=on,
                excluding_settlement_id=excluding_settlement_id,
            ),
        )
        if taxable <= ZERO:
            return TcsPreview(
                applicable=False,
                reason=(
                    "This buyer has not yet paid more than the threshold this "
                    "financial year, above what standing collections have "
                    "already charged them on."
                ),
                **blank,
            )
        tcs = quantize_ledger(taxable * rate / HUNDRED)
        return TcsPreview(
            applicable=tcs > ZERO,
            reason=(
                ""
                if tcs > ZERO
                # A rate of zero is a firm's own choice and a real answer, so
                # it is not reported as an oversight.
                else "The rate in force is zero, so nothing is collected."
            ),
            financial_year_start=year_start,
            cumulative_before=cumulative,
            threshold_amount=threshold,
            taxable_amount=taxable,
            rate_percent=rate,
            without_pan=without_pan,
            tcs_amount=tcs,
        )

    # ---- collecting ----------------------------------------------------

    def stage_collection(
        self, settlement: Settlement, *, firm_id: UUID, actor_id: UUID
    ) -> TcsCollection | None:
        """Charge a receipt, without committing.

        Flushes rather than commits, so the caller that owns the receipt owns
        the transaction: a receipt that posted and a collection that did not
        would leave the buyer under-charged with nothing to say why. That is
        the `stage_*` split `SalesChainService` uses, and for the same reason.

        A payment to a vendor is not a receipt and is left alone; so is a
        receipt for nothing.

        Args:
            settlement: The receipt just recorded.
            firm_id: The collecting firm.
            actor_id: The user recording it.

        Returns:
            The collection written, or None where nothing was due.

        """
        if (
            settlement.direction != SettlementDirection.RECEIPT.value
            or settlement.customer_id is None
        ):
            return None
        preview = self.preview(
            firm_id=firm_id,
            customer_id=settlement.customer_id,
            amount=Decimal(str(settlement.amount)),
            on=settlement.settlement_date,
            # This receipt is already written by the time it is charged, and
            # counting it as money the buyer had *already* paid would charge
            # the first receipt over the threshold on itself.
            excluding_settlement_id=settlement.id,
        )
        if not preview.applicable or preview.tcs_amount <= ZERO:
            return None

        row = TcsCollection(
            firm_id=firm_id,
            customer_id=settlement.customer_id,
            settlement_id=settlement.id,
            financial_year_start=preview.financial_year_start,
            collected_on=settlement.settlement_date,
            consideration_amount=quantize_ledger(settlement.amount),
            cumulative_before=preview.cumulative_before,
            taxable_amount=preview.taxable_amount,
            rate_percent=preview.rate_percent,
            without_pan=preview.without_pan,
            tcs_amount=preview.tcs_amount,
            status=TcsCollectionStatus.COLLECTED.value,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()

        entry = self._posting.post_tcs_collection(
            firm_id=firm_id,
            collection_id=row.id,
            reference=self.reference_for(settlement),
            collected_on=settlement.settlement_date,
            amount=row.tcs_amount,
            actor_id=actor_id,
        )
        row.journal_entry_id = None if entry is None else entry.id
        transaction = self._customers.post_receivable_transaction(
            settlement.customer_id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.TCS,
                transaction_date=settlement.settlement_date,
                amount=row.tcs_amount,
                reference_number=self.reference_for(settlement),
                remarks="Tax collected at source under 206C(1H).",
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
            commit=False,
        )
        row.receivable_transaction_id = transaction.id
        self._session.flush()
        record_audit(
            self._session,
            action="tcs.collected",
            entity_type="tcs_collection",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._collection_snapshot(row),
        )
        return row

    def stage_reversal(
        self, settlement: Settlement, *, firm_id: UUID, actor_id: UUID
    ) -> TcsCollection | None:
        """Take back the collection a reversed receipt carried.

        Mirrored rather than deleted: the quarterly return may already have
        reported it, and a row that vanished would leave that filing with
        nothing behind it. The customer's balance is put back by the deltas
        stored on the original receivable row, never recomputed -- the rule
        `reverse_receivable_transaction` exists to hold.

        Args:
            settlement: The receipt being reversed.
            firm_id: The collecting firm.
            actor_id: The user reversing it.

        Returns:
            The collection reversed, or None where there was none.

        """
        row = self._session.scalar(
            select(TcsCollection).where(
                TcsCollection.settlement_id == settlement.id,
                TcsCollection.firm_id == firm_id,
                TcsCollection.is_deleted.is_(False),
                TcsCollection.status == TcsCollectionStatus.COLLECTED.value,
            )
        )
        if row is None:
            return None
        before = self._collection_snapshot(row)
        if row.journal_entry_id is not None:
            mirror = self._journals.reverse_entry(
                row.journal_entry_id,
                firm_id=firm_id,
                actor_id=actor_id,
                # A journal reference is unique, so the reversal cannot reuse
                # the collection's -- the same trap that stopped an approved
                # commission payout ever being paid.
                reference_number=f"{self.reference_for(settlement)}-REV",
            )
            row.reversal_journal_entry_id = mirror.id
        if row.receivable_transaction_id is not None:
            self._customers.reverse_receivable_transaction(
                row.receivable_transaction_id,
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
        row.status = TcsCollectionStatus.REVERSED.value
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="tcs.reversed",
            entity_type="tcs_collection",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._collection_snapshot(row),
        )
        return row

    # ---- reading -------------------------------------------------------

    def list_collections(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TcsCollection], int]:
        """Return collections for a firm, newest first.

        Args:
            firm_id: The collecting firm.
            customer_id: Narrow to one buyer.
            from_date: First day to include.
            to_date: Last day to include.
            offset: Rows to skip.
            limit: Rows to return.

        Returns:
            The page, and how many rows match in all.

        Raises:
            ValidationError: If the period runs backwards.

        """
        if from_date and to_date and to_date < from_date:
            raise ValidationError("to_date cannot be before from_date.")
        query = select(TcsCollection).where(
            TcsCollection.firm_id == firm_id,
            TcsCollection.is_deleted.is_(False),
        )
        if customer_id is not None:
            query = query.where(TcsCollection.customer_id == customer_id)
        if from_date is not None:
            query = query.where(TcsCollection.collected_on >= from_date)
        if to_date is not None:
            query = query.where(TcsCollection.collected_on <= to_date)
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = list(
            self._session.scalars(
                query.order_by(
                    TcsCollection.collected_on.desc(), TcsCollection.id.desc()
                )
                .offset(offset)
                .limit(limit)
            ).all()
        )
        return rows, int(total or 0)

    def describe(self, rows: list[TcsCollection]) -> list[TcsCollectionResponse]:
        """Name the buyer and the receipt behind each collection.

        Resolved for the page rather than per row, and here rather than in the
        router, because a grid of ids is a grid nobody can read -- the question
        somebody brings to this list is "who, and against which receipt".

        Args:
            rows: The page to describe.

        Returns:
            The same rows, with the two names filled in.

        """
        if not rows:
            return []
        names: dict[UUID, str] = {
            row_id: name
            for row_id, name in self._session.execute(
                select(Customer.id, Customer.name).where(
                    Customer.id.in_({row.customer_id for row in rows})
                )
            ).all()
        }
        numbers: dict[UUID, str] = {
            row_id: number
            for row_id, number in self._session.execute(
                select(Settlement.id, Settlement.settlement_number).where(
                    Settlement.id.in_({row.settlement_id for row in rows})
                )
            ).all()
        }
        described: list[TcsCollectionResponse] = []
        for row in rows:
            answer = TcsCollectionResponse.model_validate(row)
            answer.customer_name = names.get(row.customer_id)
            answer.settlement_number = numbers.get(row.settlement_id)
            described.append(answer)
        return described

    def charged_versus_due(self, *, firm_id: UUID, on: date) -> list[TcsBuyerPosition]:
        """Return each buyer's year: what was due against what was charged.

        One row per buyer who paid anything, or was charged anything, in the
        financial year ``on`` falls in. What is due is worked out afresh from
        the receipts, the way the next receipt would square it; what was
        charged is summed from the standing collections. The two differ only
        where the history moved under collections already made -- a receipt
        reversed, or one back-dated in front of them (D-CMP-16) -- and that is
        what this exists to show (D-CMP-21).

        Args:
            firm_id: The collecting firm.
            on: Any day in the year to report.

        Returns:
            The buyers, largest difference first.

        """
        year_start = self._financial_year_start(firm_id, on)
        year_end = date(year_start.year + 1, year_start.month, year_start.day)
        last_day = date.fromordinal(year_end.toordinal() - 1)
        # Only what was received while the section stood could be due under it.
        cut_off = min(
            last_day, date.fromordinal(SECTION_206C_1H_OMITTED_FROM.toordinal() - 1)
        )
        settings = self.settings_for(firm_id)
        applies = (
            settings is not None
            and settings.is_enabled
            and self._seller_in_scope(settings)
            and cut_off >= year_start
        )
        threshold = DEFAULT_THRESHOLD if settings is None else settings.threshold_amount

        paid = set(
            self._session.scalars(
                select(Settlement.customer_id).where(
                    Settlement.firm_id == firm_id,
                    Settlement.customer_id.is_not(None),
                    Settlement.direction.in_(
                        (
                            SettlementDirection.RECEIPT.value,
                            SettlementDirection.REFUND.value,
                        )
                    ),
                    Settlement.is_deleted.is_(False),
                    Settlement.status != SettlementStatus.REVERSED.value,
                    Settlement.settlement_date >= year_start,
                    Settlement.settlement_date < year_end,
                )
            ).all()
        )
        charged: dict[UUID, tuple[Decimal, Decimal]] = {}
        for customer_id, taxable, tcs in self._session.execute(
            select(
                TcsCollection.customer_id,
                func.coalesce(func.sum(TcsCollection.taxable_amount), 0),
                func.coalesce(func.sum(TcsCollection.tcs_amount), 0),
            )
            .where(
                TcsCollection.firm_id == firm_id,
                TcsCollection.is_deleted.is_(False),
                TcsCollection.status == TcsCollectionStatus.COLLECTED.value,
                TcsCollection.financial_year_start == year_start,
            )
            .group_by(TcsCollection.customer_id)
        ).all():
            charged[customer_id] = (Decimal(str(taxable)), Decimal(str(tcs)))
        buyers = {row for row in paid if row is not None} | set(charged)
        if not buyers:
            return []
        customers = {
            row.id: row
            for row in self._session.scalars(
                select(Customer).where(Customer.id.in_(buyers))
            ).all()
        }

        answer: list[TcsBuyerPosition] = []
        for customer_id in buyers:
            customer = customers.get(customer_id)
            if customer is None:
                continue
            received, _ = self._consideration_so_far(
                firm_id=firm_id,
                customer_id=customer_id,
                year_start=year_start,
                up_to=last_day,
            )
            chargeable = ZERO
            if applies:
                within, _ = self._consideration_so_far(
                    firm_id=firm_id,
                    customer_id=customer_id,
                    year_start=year_start,
                    up_to=cut_off,
                )
                chargeable = max(within - threshold, ZERO)
            rate = self._rate(
                settings, without_pan=not (customer.pan_number or "").strip()
            )
            due = quantize_ledger(chargeable * rate / HUNDRED)
            taxable_charged, tcs_charged = charged.get(customer_id, (ZERO, ZERO))
            difference = quantize_ledger(tcs_charged - due)
            answer.append(
                TcsBuyerPosition(
                    customer_id=customer_id,
                    customer_code=customer.code,
                    customer_name=customer.name,
                    financial_year_start=year_start,
                    consideration_received=received,
                    threshold_amount=threshold,
                    taxable_due=quantize_ledger(chargeable),
                    rate_percent=rate,
                    tcs_due=due,
                    taxable_charged=quantize_ledger(taxable_charged),
                    tcs_charged=quantize_ledger(tcs_charged),
                    difference=difference,
                    position=(
                        "OVER"
                        if difference > ZERO
                        else "SHORT" if difference < ZERO else "SQUARE"
                    ),
                )
            )
        answer.sort(key=lambda row: (-abs(row.difference), row.customer_name))
        return answer

    @staticmethod
    def reference_for(settlement: Settlement) -> str:
        """Return the journal reference a receipt's collection posts under."""
        return f"TCS-{settlement.settlement_number}"

    # ---- the arithmetic ------------------------------------------------

    @staticmethod
    def _taxable_part(
        *,
        amount: Decimal,
        cumulative: Decimal,
        threshold: Decimal,
        already_taxed: Decimal = ZERO,
    ) -> Decimal:
        """Return what this receipt is charged on, once the year is squared up.

        The first fifty lakh a buyer pays in the year attracts nothing, so a
        receipt straddling that line is charged on the part above it and no
        more. Charging the whole receipt is the obvious mistake and it
        over-collects by the entire remaining headroom.

        The charge is therefore a **running total**, not a per-receipt sum: by
        this receipt's date the buyer owes tax on everything they have paid in
        the year above the threshold, less what standing collections have
        already charged them on. In the ordinary sequence that is exactly this
        receipt's own excess. It differs only where the history behind it
        moved -- a receipt reversed, or one back-dated in front of collections
        already made -- and then this receipt settles the difference, because
        a collection already made is never rewritten (D-CMP-16). An
        over-collection likewise stands: it simply means nothing more is
        charged until the buyer's excess catches up with it.

        Args:
            amount: What is being received now.
            cumulative: What the buyer has already paid this year, by this
                receipt's own date.
            threshold: Where charging starts.
            already_taxed: What standing collections dated on or before this
                receipt have already charged this buyer on, this year.

        Returns:
            The chargeable part, never negative.

        """
        due = cumulative + amount - threshold - already_taxed
        return quantize_ledger(due) if due > ZERO else ZERO

    def _already_taxed(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        year_start: date,
        up_to: date,
        excluding_settlement_id: UUID | None = None,
    ) -> Decimal:
        """Return what standing collections have charged this buyer this year.

        Summed from the collections themselves, like every other running total
        here, and only the ones that still stand: a reversed collection has
        been handed back, so the money it charged on is chargeable again. Only
        collections dated on or before this receipt count, for the same reason
        the consideration is counted that way (D-CMP-7) -- the question is what
        had been charged by then.

        Args:
            firm_id: The collecting firm.
            customer_id: The buyer.
            year_start: First day of the financial year.
            up_to: The receipt's own date; later collections are not counted.
            excluding_settlement_id: A receipt whose own collection to leave
                out, so re-charging a receipt does not count itself.

        Returns:
            The taxable amount already charged, never below zero.

        """
        query = select(func.coalesce(func.sum(TcsCollection.taxable_amount), 0)).where(
            TcsCollection.firm_id == firm_id,
            TcsCollection.customer_id == customer_id,
            TcsCollection.is_deleted.is_(False),
            TcsCollection.status == TcsCollectionStatus.COLLECTED.value,
            TcsCollection.financial_year_start == year_start,
            TcsCollection.collected_on <= up_to,
        )
        if excluding_settlement_id is not None:
            query = query.where(TcsCollection.settlement_id != excluding_settlement_id)
        taxed = Decimal(str(self._session.scalar(query) or 0))
        return quantize_ledger(taxed if taxed > ZERO else ZERO)

    def _consideration_so_far(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        year_start: date,
        up_to: date,
        excluding_settlement_id: UUID | None = None,
    ) -> tuple[Decimal, Decimal]:
        """Return what this buyer had already paid this year, by a given day.

        **Summed from the receipts, never held as a counter.** A counter and a
        reversal are two chances to disagree, and here disagreeing means
        charging a buyer on money they got back. Reversed receipts are
        excluded, because a reversed receipt is money the firm does not have.

        **Only receipts dated on or before the day in question.** The section
        charges the consideration received *in excess of* the threshold, so
        what counts is what had been received by then -- not what happened to
        be recorded first. Summing the whole year charged a back-dated receipt
        on money the buyer paid after it (D-CMP-7).

        **Not the part of a receipt that paid the tax itself.** A collection
        is debited to the buyer, and the money they send to settle it is the
        tax coming in, not consideration for goods -- charging it again is tax
        on tax (D-CMP-13). The receipts are replayed in the order they were
        received: each one settles the tax still owed first, and whatever is
        left of it is consideration; its own collection is then owed by the
        receipts after it.

        Args:
            firm_id: The collecting firm.
            customer_id: The buyer.
            year_start: First day of the financial year.
            up_to: The receipt's own date; later receipts are not counted.
            excluding_settlement_id: A receipt to leave out.

        Returns:
            The consideration received in the year so far, net of refunds and
            of tax paid, never below zero; and the tax collected from the buyer
            that those receipts have not yet paid.

        """
        year_end = date(year_start.year + 1, year_start.month, year_start.day)
        query = (
            select(Settlement.id, Settlement.direction, Settlement.amount)
            .where(
                Settlement.firm_id == firm_id,
                Settlement.customer_id == customer_id,
                Settlement.direction.in_(
                    (
                        SettlementDirection.RECEIPT.value,
                        SettlementDirection.REFUND.value,
                    )
                ),
                Settlement.is_deleted.is_(False),
                Settlement.status != SettlementStatus.REVERSED.value,
                Settlement.settlement_date >= year_start,
                Settlement.settlement_date < year_end,
                Settlement.settlement_date <= up_to,
            )
            .order_by(
                Settlement.settlement_date.asc(),
                Settlement.created_at.asc(),
                Settlement.id.asc(),
            )
        )
        if excluding_settlement_id is not None:
            query = query.where(Settlement.id != excluding_settlement_id)
        rows = self._session.execute(query).all()
        collected = {
            settlement_id: Decimal(str(amount))
            for settlement_id, amount in self._session.execute(
                select(TcsCollection.settlement_id, TcsCollection.tcs_amount).where(
                    TcsCollection.firm_id == firm_id,
                    TcsCollection.customer_id == customer_id,
                    TcsCollection.is_deleted.is_(False),
                    TcsCollection.status == TcsCollectionStatus.COLLECTED.value,
                    TcsCollection.settlement_id.in_([row[0] for row in rows] or [None]),
                )
            ).all()
        }
        received = owed = ZERO
        for settlement_id, direction, raw in rows:
            amount = Decimal(str(raw))
            if direction == SettlementDirection.REFUND.value:
                # Net of refunds. A refund hands back money the buyer had
                # paid in, so it is consideration *un*-received: leaving it in
                # would keep a buyer over the threshold on money they no
                # longer have with the firm.
                received -= amount
                continue
            paid_tax = min(amount, owed)
            owed -= paid_tax
            received += amount - paid_tax
            owed += collected.get(settlement_id, ZERO)
        return (
            quantize_ledger(received if received > ZERO else ZERO),
            quantize_ledger(owed),
        )

    def _financial_year_start(self, firm_id: UUID, on: date) -> date:
        """Return the first day of the financial year a date falls in.

        Read off the firm's own `financial_year_start`, because a firm's year
        is a firm's decision and the threshold resets with it. Assuming April
        would be right for most Indian firms and silently wrong for the rest.

        Args:
            firm_id: The firm whose calendar decides it.
            on: The date in question.

        Returns:
            The first day of that year.

        """
        anchor = self._firms.get(firm_id).financial_year_start
        if anchor is None:
            # A firm whose year nobody recorded is treated as running the
            # calendar year. Refusing outright would stop it taking money;
            # assuming April would be right for most Indian firms and quietly
            # wrong for the rest, and this at least resets on a date somebody
            # can recognise.
            anchor = date(on.year, 1, 1)
        started = date(on.year, anchor.month, anchor.day)
        return started if on >= started else date(on.year - 1, anchor.month, anchor.day)

    @staticmethod
    def _rate(settings: TcsSettings | None, *, without_pan: bool) -> Decimal:
        """Return the rate in force for this buyer."""
        if settings is None:
            return DEFAULT_RATE_WITHOUT_PAN if without_pan else DEFAULT_RATE
        return (
            settings.rate_without_pan_percent if without_pan else settings.rate_percent
        )

    @staticmethod
    def _seller_in_scope(settings: TcsSettings) -> bool:
        """Return whether the firm's own turnover puts it in scope."""
        return settings.preceding_year_turnover > settings.seller_turnover_threshold

    # ---- plumbing ------------------------------------------------------

    def _customer(self, *, firm_id: UUID, customer_id: UUID) -> Customer:
        """Return one of this firm's customers."""
        row = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Customer not found.")
        return row

    def _settings_response(self, row: TcsSettings) -> TcsSettingsResponse:
        """Describe a settings row, saying whether the firm is in scope."""
        return TcsSettingsResponse(
            section_code=row.section_code,
            is_enabled=row.is_enabled,
            threshold_amount=row.threshold_amount,
            rate_percent=row.rate_percent,
            rate_without_pan_percent=row.rate_without_pan_percent,
            preceding_year_turnover=row.preceding_year_turnover,
            seller_turnover_threshold=row.seller_turnover_threshold,
            seller_in_scope=self._seller_in_scope(row),
        )

    @staticmethod
    def _snapshot(row: TcsSettings) -> dict[str, object]:
        """Describe a settings row for the audit trail."""
        return {
            "is_enabled": row.is_enabled,
            "threshold_amount": str(row.threshold_amount),
            "rate_percent": str(row.rate_percent),
            "rate_without_pan_percent": str(row.rate_without_pan_percent),
            "preceding_year_turnover": str(row.preceding_year_turnover),
            "seller_turnover_threshold": str(row.seller_turnover_threshold),
        }

    @staticmethod
    def _collection_snapshot(row: TcsCollection) -> dict[str, object]:
        """Describe a collection for the audit trail."""
        return {
            "customer_id": str(row.customer_id),
            "settlement_id": str(row.settlement_id),
            "consideration_amount": str(row.consideration_amount),
            "cumulative_before": str(row.cumulative_before),
            "taxable_amount": str(row.taxable_amount),
            "rate_percent": str(row.rate_percent),
            "tcs_amount": str(row.tcs_amount),
            "status": row.status,
        }
