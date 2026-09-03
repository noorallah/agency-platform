"""Earn, spend, expire and correct a customer's credit.

One rule underlies the rest: **the balance is the sum of the ledger**, never a
column. An invoice's outstanding is derived from its allocations for the same
reason -- a stored total is a second copy, and the copy is wrong the first time
anything writes one without going through here.
"""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger, quantize_money
from app.customers.models import Customer
from app.customers.schemas import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services import CustomerService
from app.finance.services.document_posting import DocumentPostingService
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind, LoyaltySettings
from app.loyalty.schemas import (
    LoyaltyBalance,
    LoyaltyEntryResponse,
    LoyaltySettingsResponse,
    LoyaltySettingsWrite,
)
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import Settlement, SettlementAllocation, SettlementStatus

HUNDRED = Decimal("100")

#: How far ahead "expiring soon" looks. Ninety days is long enough for a
#: customer to do something about it and short enough that the warning still
#: means something.
EXPIRING_SOON_DAYS = 90

#: Invoices that earn. A draft is not a sale and a cancelled one has been
#: undone, so neither credits anybody.
_LIVE_INVOICE_STATUSES = ("APPROVED", "CLOSED")


class LoyaltyService:
    """Maintain a firm's scheme and every customer's credit under it."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._posting = DocumentPostingService(session)
        self._customers = CustomerService(session)

    # ---- settings ------------------------------------------------------

    def settings_for(self, firm_id: UUID) -> LoyaltySettings | None:
        """Return a firm's scheme, or None where it has never set one."""
        return self._session.scalar(
            select(LoyaltySettings).where(
                LoyaltySettings.firm_id == firm_id,
                LoyaltySettings.is_deleted.is_(False),
            )
        )

    def read_settings(self, firm_id: UUID) -> LoyaltySettingsResponse:
        """Return a firm's scheme, or the shape one would take.

        A firm with no row runs no scheme, which is what the defaults say.
        Answering with them rather than with nulls means the screen shows what
        a scheme would look like if switched on, which is the question
        somebody opening this page has.

        Args:
            firm_id: The firm to read.

        Returns:
            The scheme as it stands.

        """
        row = self.settings_for(firm_id)
        if row is None:
            return LoyaltySettingsResponse(
                is_enabled=False,
                points_per_amount=Decimal("1"),
                amount_per_point=Decimal("1"),
                minimum_redemption_points=0,
                expiry_months=None,
            )
        return LoyaltySettingsResponse.model_validate(row)

    def write_settings(
        self, firm_id: UUID, payload: LoyaltySettingsWrite, *, actor_id: UUID
    ) -> LoyaltySettingsResponse:
        """Create or amend a firm's scheme.

        Dumped with ``exclude_unset``, so an omitted field is left alone. Here
        that matters more than usual: a full dump would reset a conversion rate
        a firm had agreed with its customers.

        Args:
            firm_id: The firm to configure.
            payload: The fields to change.
            actor_id: The user making the change.

        Returns:
            The scheme as it now stands.

        """
        row = self.settings_for(firm_id)
        before = None if row is None else self._settings_snapshot(row)
        if row is None:
            row = LoyaltySettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="loyalty.settings_changed",
            entity_type="loyalty_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._settings_snapshot(row),
        )
        self._session.commit()
        return LoyaltySettingsResponse.model_validate(row)

    # ---- reading -------------------------------------------------------

    def balance(self, customer_id: UUID, *, firm_scope: UUID) -> LoyaltyBalance:
        """Return what a customer holds, and whether they can spend it.

        Summed from the ledger. `redeemable` is answered here rather than left
        to the screen, so a client cannot offer a redemption the service would
        refuse.

        Args:
            customer_id: The customer to read.
            firm_scope: The owning firm.

        Returns:
            The balance, its worth at today's rate, and what lapses soon.

        Raises:
            ResourceNotFoundError: If the customer is not this firm's.

        """
        customer = self._customer(customer_id, firm_scope=firm_scope)
        settings = self.settings_for(firm_scope)
        points = self._points_of(customer_id, firm_scope=firm_scope)
        rate = Decimal("1") if settings is None else settings.amount_per_point
        floor = 0 if settings is None else settings.minimum_redemption_points
        horizon = date.fromordinal(utc_now().date().toordinal() + EXPIRING_SOON_DAYS)
        expiring = self._session.scalar(
            select(func.coalesce(func.sum(LoyaltyEntry.points), 0)).where(
                LoyaltyEntry.firm_id == firm_scope,
                LoyaltyEntry.customer_id == customer_id,
                LoyaltyEntry.is_deleted.is_(False),
                LoyaltyEntry.points > ZERO,
                LoyaltyEntry.expires_on.is_not(None),
                LoyaltyEntry.expires_on <= horizon,
            )
        )
        return LoyaltyBalance(
            customer_id=customer.id,
            customer_name=customer.name,
            points=points,
            amount=quantize_ledger(points * rate),
            redeemable=(
                settings is not None
                and settings.is_enabled
                and points >= Decimal(floor)
                and points > ZERO
            ),
            expiring_soon=quantize_money(Decimal(str(expiring or 0))),
        )

    def entries(
        self,
        *,
        firm_scope: UUID,
        customer_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LoyaltyEntry], int]:
        """Return the ledger, newest first.

        Args:
            firm_scope: The owning firm.
            customer_id: Narrow to one customer.
            offset: Rows to skip.
            limit: Rows to return.

        Returns:
            The page, and how many rows match in all.

        """
        query = select(LoyaltyEntry).where(
            LoyaltyEntry.firm_id == firm_scope,
            LoyaltyEntry.is_deleted.is_(False),
        )
        if customer_id is not None:
            query = query.where(LoyaltyEntry.customer_id == customer_id)
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = list(
            self._session.scalars(
                query.order_by(LoyaltyEntry.earned_on.desc(), LoyaltyEntry.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
        )
        return rows, int(total or 0)

    def describe(self, rows: list[LoyaltyEntry]) -> list[LoyaltyEntryResponse]:
        """Name the customer and the bill behind each entry."""
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
        invoice_ids = {row.sales_invoice_id for row in rows if row.sales_invoice_id}
        numbers: dict[UUID, str] = {}
        if invoice_ids:
            numbers = {
                row_id: number
                for row_id, number in self._session.execute(
                    select(SalesInvoice.id, SalesInvoice.invoice_number).where(
                        SalesInvoice.id.in_(invoice_ids)
                    )
                ).all()
            }
        described: list[LoyaltyEntryResponse] = []
        for row in rows:
            answer = LoyaltyEntryResponse.model_validate(row)
            answer.customer_name = names.get(row.customer_id)
            answer.sales_invoice_number = (
                None
                if row.sales_invoice_id is None
                else numbers.get(row.sales_invoice_id)
            )
            described.append(answer)
        return described

    # ---- earning -------------------------------------------------------

    def stage_earning(
        self, invoice: SalesInvoice, *, firm_id: UUID, actor_id: UUID
    ) -> LoyaltyEntry | None:
        """Credit the customer for a bill, without committing.

        Flushed rather than committed, so the caller that owns the invoice owns
        the transaction: an approved bill and a credit that did not happen
        would leave the customer short with nothing on the record to say why.

        Earning **posts**: a scheme costs the firm money the moment it promises
        the credit, and booking it only on redemption would leave the liability
        off the books for as long as customers held their points.

        Args:
            invoice: The bill just approved.
            firm_id: The owning firm.
            actor_id: The user approving it.

        Returns:
            The entry written, or None where the scheme credits nothing.

        """
        settings = self.settings_for(firm_id)
        if settings is None or not settings.is_enabled:
            return None
        if settings.points_per_amount <= ZERO:
            return None
        if self._earned_for(invoice.id, firm_id=firm_id) is not None:
            # One credit per bill. A second would pay twice for one sale and
            # nothing would say which was the real one.
            return None
        points = quantize_money(
            Decimal(str(invoice.grand_total)) * settings.points_per_amount / HUNDRED
        )
        if points <= ZERO:
            return None
        amount = quantize_ledger(points * settings.amount_per_point)
        entry = LoyaltyEntry(
            firm_id=firm_id,
            customer_id=invoice.customer_id,
            kind=LoyaltyEntryKind.EARNED.value,
            points=points,
            amount=amount,
            sales_invoice_id=invoice.id,
            earned_on=invoice.invoice_date,
            expires_on=self._expiry(invoice.invoice_date, settings),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(entry)
        self._session.flush()
        posted = self._posting.post_loyalty(
            firm_id=firm_id,
            entry_id=entry.id,
            reference=f"LOY-{invoice.invoice_number}",
            on=invoice.invoice_date,
            amount=amount,
            earning=True,
            actor_id=actor_id,
        )
        entry.journal_entry_id = None if posted is None else posted.id
        self._session.flush()
        record_audit(
            self._session,
            action="loyalty.earned",
            entity_type="loyalty_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._entry_snapshot(entry),
        )
        return entry

    # ---- spending ------------------------------------------------------

    def redeem(
        self,
        *,
        firm_scope: UUID,
        invoice_id: UUID,
        points: Decimal,
        actor_id: UUID,
    ) -> LoyaltyEntry:
        """Spend credit against a bill.

        **Refused rather than trimmed** when the balance or the bill cannot
        take it: a customer told their points cleared a bill and finding
        otherwise is worse than being told no.

        The redemption settles the invoice through the same allocation
        machinery a receipt uses, so what the bill still owes stays derived
        from one place.

        Args:
            firm_scope: The owning firm.
            invoice_id: The bill to spend against.
            points: How many points to spend.
            actor_id: The user redeeming them.

        Returns:
            The entry written.

        Raises:
            ValidationError: If the scheme is off, the balance too small, or
                the bill owes less than the points are worth.
            ResourceNotFoundError: If the invoice is not this firm's.

        """
        settings = self.settings_for(firm_scope)
        if settings is None or not settings.is_enabled:
            raise ValidationError("This firm does not run a loyalty scheme.")
        invoice = self._invoice(invoice_id, firm_scope=firm_scope)
        asked = quantize_money(points)
        if asked <= ZERO:
            raise ValidationError("A redemption must be for more than nothing.")
        held = self._points_of(invoice.customer_id, firm_scope=firm_scope)
        if asked > held:
            raise ValidationError(f"That customer holds {held} points, not {asked}.")
        if held < Decimal(settings.minimum_redemption_points):
            raise ValidationError(
                f"At least {settings.minimum_redemption_points} points are "
                "needed before any can be spent."
            )
        amount = quantize_ledger(asked * settings.amount_per_point)
        owed = self._outstanding_of(invoice, firm_scope=firm_scope)
        if amount > owed:
            raise ValidationError(
                f"{invoice.invoice_number} owes only {owed}, and those points "
                f"are worth {amount}."
            )

        entry = LoyaltyEntry(
            firm_id=firm_scope,
            customer_id=invoice.customer_id,
            kind=LoyaltyEntryKind.REDEEMED.value,
            # Negative, so the balance stays one sum.
            points=-asked,
            amount=amount,
            sales_invoice_id=invoice.id,
            earned_on=utc_now().date(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(entry)
        self._session.flush()
        posted = self._posting.post_loyalty(
            firm_id=firm_scope,
            entry_id=entry.id,
            reference=f"LOY-RED-{invoice.invoice_number}",
            on=entry.earned_on,
            amount=amount,
            earning=False,
            actor_id=actor_id,
        )
        entry.journal_entry_id = None if posted is None else posted.id
        # And the customer's own balance, or the journal above would reduce
        # the receivable control account while the subsidiary ledger stayed
        # where it was -- the two books drifting apart by every redemption.
        self._customers.post_receivable_transaction(
            invoice.customer_id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.LOYALTY,
                amount=amount,
                transaction_date=entry.earned_on,
                reference_number=invoice.invoice_number,
                remarks=f"{asked} points spent on {invoice.invoice_number}.",
            ),
            firm_scope=firm_scope,
            actor_id=actor_id,
            commit=False,
        )
        self._session.flush()
        record_audit(
            self._session,
            action="loyalty.redeemed",
            entity_type="loyalty_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=self._entry_snapshot(entry),
        )
        self._session.commit()
        return entry

    def adjust(
        self,
        *,
        firm_scope: UUID,
        customer_id: UUID,
        points: Decimal,
        reason: str,
        actor_id: UUID,
    ) -> LoyaltyEntry:
        """Correct a balance by hand, saying why.

        Posts nothing. An adjustment is a correction to a count, not a
        transaction: the money side was either already booked when the points
        were earned, or was never right to book at all. Booking it again would
        double what the scheme appears to have cost.

        Args:
            firm_scope: The owning firm.
            customer_id: Whose balance.
            points: Signed -- positive gives, negative takes back.
            reason: Why, kept on the record.
            actor_id: The user adjusting it.

        Returns:
            The entry written.

        Raises:
            ValidationError: If it is for nothing, or would take the balance
                below zero.

        """
        customer = self._customer(customer_id, firm_scope=firm_scope)
        change = quantize_money(points)
        if change == ZERO:
            raise ValidationError("An adjustment of nothing changes nothing.")
        held = self._points_of(customer_id, firm_scope=firm_scope)
        if held + change < ZERO:
            raise ValidationError(
                f"That customer holds {held} points, so {change} would take "
                "the balance below zero."
            )
        entry = LoyaltyEntry(
            firm_id=firm_scope,
            customer_id=customer.id,
            kind=LoyaltyEntryKind.ADJUSTED.value,
            points=change,
            amount=ZERO,
            earned_on=utc_now().date(),
            remarks=reason,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(entry)
        self._session.flush()
        record_audit(
            self._session,
            action="loyalty.adjusted",
            entity_type="loyalty_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=self._entry_snapshot(entry),
        )
        self._session.commit()
        return entry

    def expire(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        as_of: date | None = None,
    ) -> int:
        """Write off points that have run out of time, and release their cost.

        A sweep rather than a rule applied at read time, so the balance is
        answerable without knowing today's date and a customer can be shown
        what lapsed and when. Each expiry names the entry it takes, so running
        the sweep twice cannot take the same points twice.

        **Only the part of a batch nobody spent.** It used to write back the
        whole earned entry, so a batch the customer had already spent lapsed a
        second time and left them holding *negative* points -- the balance is
        a sum over the ledger with no floor, and redeeming is refused above
        it, so this sweep was the only way to go below zero. Spending is
        allocated oldest batch first, which is both the ordinary treatment and
        the reason the fix cannot simply cap at the balance: a customer with
        one lapsing batch and one fresh one, who spent the older one's worth,
        should keep the fresh one in full.

        **And the liability comes back.** Earning posts
        `Dr Loyalty Expense / Cr Loyalty Payable`; nothing released that when
        the credit ran out of time, so `Loyalty Payable` kept a debt no
        customer could ever claim. A lapse posts the accrual in reverse, for
        the share of the batch that lapsed.

        `as_of` defaults to today **in UTC**, because everything stored here is
        UTC and the server's local date is already tomorrow, or still
        yesterday, for part of every day.

        Args:
            firm_scope: The owning firm.
            actor_id: Whoever ran the sweep. Required rather than synthetic:
                the release posts a journal, and a journal with no author is
                one nobody can ask about.
            as_of: The day to expire against.

        Returns:
            How many batches lapsed.

        """
        today = as_of or utc_now().date()
        lapsed = 0
        for customer_id in self._customers_with_lapsing_points(
            firm_scope=firm_scope, today=today
        ):
            lapsed += self._expire_for(
                customer_id, firm_scope=firm_scope, today=today, actor_id=actor_id
            )
        if lapsed:
            self._session.commit()
        return lapsed

    def _customers_with_lapsing_points(
        self, *, firm_scope: UUID, today: date
    ) -> list[UUID]:
        """Whose batches are past their date. One pass, not one per customer."""
        return list(
            self._session.scalars(
                select(LoyaltyEntry.customer_id)
                .where(
                    LoyaltyEntry.firm_id == firm_scope,
                    LoyaltyEntry.is_deleted.is_(False),
                    LoyaltyEntry.kind == LoyaltyEntryKind.EARNED.value,
                    LoyaltyEntry.expires_on.is_not(None),
                    LoyaltyEntry.expires_on < today,
                )
                .group_by(LoyaltyEntry.customer_id)
            ).all()
        )

    def _expire_for(
        self, customer_id: UUID, *, firm_scope: UUID, today: date, actor_id: UUID
    ) -> int:
        """Lapse one customer's unspent, out-of-date batches."""
        entries = list(
            self._session.scalars(
                select(LoyaltyEntry)
                .where(
                    LoyaltyEntry.firm_id == firm_scope,
                    LoyaltyEntry.customer_id == customer_id,
                    LoyaltyEntry.is_deleted.is_(False),
                )
                .order_by(LoyaltyEntry.earned_on.asc(), LoyaltyEntry.id.asc())
            ).all()
        )
        batches = [row for row in entries if row.kind == LoyaltyEntryKind.EARNED.value]
        # What each batch has already had taken off it by a previous sweep.
        # Those name their batch, so they are attributed rather than pooled.
        taken: dict[UUID, Decimal] = {}
        for row in entries:
            if row.kind == LoyaltyEntryKind.EXPIRED.value and row.reverses_id:
                taken[row.reverses_id] = taken.get(row.reverses_id, ZERO) + abs(
                    Decimal(str(row.points))
                )
        # Everything else that took points off: redemptions, and adjustments
        # that reduced the balance. Allocated oldest batch first.
        pool = sum(
            (
                abs(Decimal(str(row.points)))
                for row in entries
                if row.kind != LoyaltyEntryKind.EXPIRED.value
                and Decimal(str(row.points)) < ZERO
            ),
            ZERO,
        )
        lapsed = 0
        for batch in batches:
            held = Decimal(str(batch.points)) - taken.get(batch.id, ZERO)
            spent_here = min(pool, max(held, ZERO))
            pool -= spent_here
            remaining = held - spent_here
            if remaining <= ZERO:
                continue
            if batch.expires_on is None or batch.expires_on >= today:
                continue
            self._lapse(
                batch,
                remaining,
                firm_scope=firm_scope,
                today=today,
                actor_id=actor_id,
            )
            lapsed += 1
        return lapsed

    def _lapse(
        self,
        batch: LoyaltyEntry,
        points: Decimal,
        *,
        firm_scope: UUID,
        today: date,
        actor_id: UUID,
    ) -> None:
        """Write one lapse, and hand back the cost it raised."""
        points = quantize_money(points)
        earned = Decimal(str(batch.points))
        # Pro-rata, because only part of the batch may be lapsing.
        worth = quantize_ledger(
            Decimal(str(batch.amount)) * points / earned if earned else ZERO
        )
        entry = LoyaltyEntry(
            firm_id=firm_scope,
            customer_id=batch.customer_id,
            kind=LoyaltyEntryKind.EXPIRED.value,
            points=-points,
            amount=worth,
            earned_on=today,
            reverses_id=batch.id,
            remarks=f"Earned {batch.earned_on}, lapsed {batch.expires_on}.",
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(entry)
        self._session.flush()
        posted = self._posting.post_loyalty(
            firm_id=firm_scope,
            entry_id=entry.id,
            reference=f"LOY-EXP-{entry.id}",
            on=today,
            amount=worth,
            earning=False,
            expiring=True,
            actor_id=actor_id,
        )
        entry.journal_entry_id = None if posted is None else posted.id
        record_audit(
            self._session,
            action="loyalty.expired",
            entity_type="loyalty_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=self._entry_snapshot(entry),
        )
        self._session.flush()

    # ---- internals -----------------------------------------------------

    def _points_of(self, customer_id: UUID, *, firm_scope: UUID) -> Decimal:
        """Return a customer's balance, summed from the ledger."""
        total = self._session.scalar(
            select(func.coalesce(func.sum(LoyaltyEntry.points), 0)).where(
                LoyaltyEntry.firm_id == firm_scope,
                LoyaltyEntry.customer_id == customer_id,
                LoyaltyEntry.is_deleted.is_(False),
            )
        )
        return quantize_money(Decimal(str(total or 0)))

    def _earned_for(self, invoice_id: UUID, *, firm_id: UUID) -> LoyaltyEntry | None:
        """Return the credit already given for a bill, if any."""
        return self._session.scalar(
            select(LoyaltyEntry).where(
                LoyaltyEntry.firm_id == firm_id,
                LoyaltyEntry.sales_invoice_id == invoice_id,
                LoyaltyEntry.kind == LoyaltyEntryKind.EARNED.value,
                LoyaltyEntry.is_deleted.is_(False),
            )
        )

    @staticmethod
    def _expiry(earned_on: date, settings: LoyaltySettings) -> date | None:
        """Return when points earned today lapse, or None if they never do."""
        months = settings.expiry_months
        if months is None:
            return None
        year = earned_on.year + (earned_on.month - 1 + months) // 12
        month = (earned_on.month - 1 + months) % 12 + 1
        # Clamped to the month's length: three months after 30 November is
        # 28 February, not a date that does not exist.
        day = min(earned_on.day, _days_in(year, month))
        return date(year, month, day)

    def _outstanding_of(self, invoice: SalesInvoice, *, firm_scope: UUID) -> Decimal:
        """Return what a bill still owes, off its allocations.

        The same derivation `outstanding_invoices` uses, because a second way
        of working out what a bill owes is a second answer.
        """
        paid = self._session.scalar(
            select(func.coalesce(func.sum(SettlementAllocation.amount), 0))
            .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
            .where(
                SettlementAllocation.sales_invoice_id == invoice.id,
                SettlementAllocation.is_deleted.is_(False),
                Settlement.status != SettlementStatus.REVERSED.value,
                Settlement.is_deleted.is_(False),
            )
        )
        spent = self._session.scalar(
            select(func.coalesce(func.sum(LoyaltyEntry.amount), 0)).where(
                LoyaltyEntry.firm_id == firm_scope,
                LoyaltyEntry.sales_invoice_id == invoice.id,
                LoyaltyEntry.kind == LoyaltyEntryKind.REDEEMED.value,
                LoyaltyEntry.is_deleted.is_(False),
            )
        )
        owed = (
            quantize_ledger(invoice.grand_total)
            - quantize_ledger(Decimal(str(paid or 0)))
            - quantize_ledger(Decimal(str(spent or 0)))
        )
        return owed if owed > ZERO else ZERO

    def _customer(self, customer_id: UUID, *, firm_scope: UUID) -> Customer:
        """Return one of this firm's customers."""
        row = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_scope,
                Customer.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Customer not found.")
        return row

    def _invoice(self, invoice_id: UUID, *, firm_scope: UUID) -> SalesInvoice:
        """Return one of this firm's live invoices."""
        row = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        if row.status not in _LIVE_INVOICE_STATUSES:
            raise ValidationError(
                "Only an approved invoice can be settled with points."
            )
        return row

    @staticmethod
    def _settings_snapshot(row: LoyaltySettings) -> dict[str, object]:
        """Describe a scheme for the audit trail."""
        return {
            "is_enabled": row.is_enabled,
            "points_per_amount": str(row.points_per_amount),
            "amount_per_point": str(row.amount_per_point),
            "minimum_redemption_points": row.minimum_redemption_points,
            "expiry_months": row.expiry_months,
        }

    @staticmethod
    def _entry_snapshot(row: LoyaltyEntry) -> dict[str, object]:
        """Describe a ledger entry for the audit trail."""
        return {
            "customer_id": str(row.customer_id),
            "kind": row.kind,
            "points": str(row.points),
            "amount": str(row.amount),
            "sales_invoice_id": (
                None if row.sales_invoice_id is None else str(row.sales_invoice_id)
            ),
            "expires_on": (
                None if row.expires_on is None else row.expires_on.isoformat()
            ),
            "remarks": row.remarks,
        }


def _days_in(year: int, month: int) -> int:
    """Return how many days a month has."""
    return monthrange(year, month)[1]
