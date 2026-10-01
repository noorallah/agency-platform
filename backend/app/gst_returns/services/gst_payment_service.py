"""Settling a month's GST: set-off, cash payable, the challan posted (63).

From the month's GSTR-3B -- output tax per head (3.1(a), after credit notes)
and net input credit per head (table 4) -- plus the credit carried from the
month before, this works out what the credit pays and what is left to pay in
cash, by the order the law sets (section 49(5) and rule 88A):

1. **IGST credit first, and wholly**: against IGST, then against CGST and SGST
   in whatever split leaves the least cash to pay.
2. **CGST credit** against CGST, then IGST -- **never SGST**.
3. **SGST credit** against SGST, then IGST -- **never CGST**.
4. **Cess credit** against cess only.

Interest at 18% a year (section 50) is suggested for each day the cash is paid
after the 20th of the next month, on the cash part only; the person recording
the challan states what was actually paid. Filing on the portal is not done
here (the sandbox rule in `docs/LEDGER_POSTING_RULES.md` stands).

Reverse charge on inward supplies (3.1(d), backlog 68 row 8) is paid **in cash
only** (section 49(4)): it never enters the set-off, so no credit of any head
can pay it, and its cash is added to the challan on top of what the set-off
leaves.

Recording the challan posts **one journal**: Dr output tax for the whole
liability, head by head (below); Dr reverse-charge payable per head; Cr Input
tax, head by head, for the credit used; Cr the bank for the cash, interest and
late fee; Dr the chosen expense accounts for interest and late fee. After it
the month's output tax is cleared and the input tax holds only the credit
carried forward -- the check that the books and the return agree.

**Output tax per head, and the single account before it (backlog 63.3).**
Sales posted to one `OUTPUT_TAX` account until the split; history is left
where it was posted. So each head's account is debited by what the month's
own documents credited to it (never more than that head's liability), and
whatever is left of the liability -- a month posted before the split, cess,
a component the split does not name -- is debited to `OUTPUT_TAX`. A month
wholly before the split clears the single account exactly as it always did;
a month wholly after clears the heads; a month straddling it clears both.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_ledger
from app.finance.models import (
    AccountType,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.gst_returns.models import HEADS, GstPayment, GstPaymentStatus

ZERO = Decimal("0.00")
#: Section 50(1): 18% a year on tax paid late.
INTEREST_RATE = Decimal("0.18")
#: The input-tax account each head's credit sits in.
CREDIT_PURPOSE: dict[str, ControlAccountPurpose] = {
    "igst": ControlAccountPurpose.INPUT_TAX_IGST,
    "cgst": ControlAccountPurpose.INPUT_TAX_CGST,
    "sgst": ControlAccountPurpose.INPUT_TAX_SGST,
    "cess": ControlAccountPurpose.INPUT_TAX,
}
#: The output-tax account each head is owed through since backlog 63.3.
#: Cess has none of its own and stays on `OUTPUT_TAX`.
OUTPUT_PURPOSE: dict[str, ControlAccountPurpose] = {
    "igst": ControlAccountPurpose.OUTPUT_TAX_IGST,
    "cgst": ControlAccountPurpose.OUTPUT_TAX_CGST,
    "sgst": ControlAccountPurpose.OUTPUT_TAX_SGST,
}
#: The reverse-charge payable account each head is owed through (68 row 8).
RCM_PURPOSE: dict[str, ControlAccountPurpose] = {
    "igst": ControlAccountPurpose.RCM_PAYABLE_IGST,
    "cgst": ControlAccountPurpose.RCM_PAYABLE_CGST,
    "sgst": ControlAccountPurpose.RCM_PAYABLE_SGST,
    "cess": ControlAccountPurpose.RCM_PAYABLE,
}
SOURCE_MODULE = "gst_payment"


@dataclass
class SetOff:
    """The statutory set-off of one month, head by head."""

    liability: dict[str, Decimal]
    credit: dict[str, Decimal]
    #: (credit head, liability head) -> amount, so the utilisation can be
    #: read the way the portal's payment table shows it.
    utilised: dict[tuple[str, str], Decimal] = field(default_factory=dict)

    def used(self, head: str) -> Decimal:
        """Return the credit of ``head`` used, against whatever it paid."""
        return sum(
            (value for (source, _), value in self.utilised.items() if source == head),
            ZERO,
        )

    def paid_by_credit(self, head: str) -> Decimal:
        """Return the liability of ``head`` paid by credit of any head."""
        return sum(
            (value for (_, target), value in self.utilised.items() if target == head),
            ZERO,
        )

    def cash(self, head: str) -> Decimal:
        """Return what is left of ``head``'s liability to pay in cash."""
        return self.liability[head] - self.paid_by_credit(head)

    def carried(self, head: str) -> Decimal:
        """Return what is left of ``head``'s credit, carried forward."""
        return self.credit[head] - self.used(head)


def set_off(liability: dict[str, Decimal], credit: dict[str, Decimal]) -> SetOff:
    """Apply section 49(5) and rule 88A to one month's liability and credit."""
    result = SetOff(liability=dict(liability), credit=dict(credit))
    owed = {head: max(liability.get(head, ZERO), ZERO) for head in HEADS}
    left = {head: max(credit.get(head, ZERO), ZERO) for head in HEADS}

    def use(source: str, target: str, amount: Decimal) -> None:
        amount = min(amount, left[source], owed[target])
        if amount <= ZERO:
            return
        left[source] -= amount
        owed[target] -= amount
        key = (source, target)
        result.utilised[key] = result.utilised.get(key, ZERO) + amount

    # 1. IGST credit, first and wholly: IGST, then CGST and SGST in the split
    #    that leaves each the least its own credit cannot cover.
    use("igst", "igst", left["igst"])
    short_c = max(owed["cgst"] - left["cgst"], ZERO)
    short_s = max(owed["sgst"] - left["sgst"], ZERO)
    use("igst", "cgst", short_c)
    use("igst", "sgst", short_s)
    use("igst", "cgst", left["igst"])
    use("igst", "sgst", left["igst"])
    # 2. CGST credit: CGST, then IGST. 3. SGST credit: SGST, then IGST.
    use("cgst", "cgst", left["cgst"])
    use("sgst", "sgst", left["sgst"])
    use("cgst", "igst", left["cgst"])
    use("sgst", "igst", left["sgst"])
    # 4. Cess against cess only.
    use("cess", "cess", left["cess"])
    return result


def due_date(return_period: str) -> date:
    """Return the 20th of the month after the period: GSTR-3B's due date."""
    year, month = (int(part) for part in return_period.split("-"))
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return date(year, month, 20)


def period_bounds(return_period: str) -> tuple[date, date]:
    """Return the first and last day of a ``YYYY-MM`` return period."""
    try:
        year, month = (int(part) for part in return_period.split("-"))
        first = date(year, month, 1)
    except ValueError as error:
        raise ValidationError("A return period is a month, YYYY-MM.") from error
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, following - timedelta(days=1)


@dataclass
class GstPaymentPreview:
    """What a month owes, what its credit pays, what is left to pay."""

    return_period: str
    due_date: date
    set_off: SetOff
    brought_forward: dict[str, Decimal]
    #: Whether the brought-forward credit came from a recorded settlement of
    #: the month before. When it did not, the person states the opening
    #: credit (the portal's electronic credit ledger) or accepts none.
    previous_settled: bool
    days_late: int
    suggested_interest: Decimal
    #: Reverse charge on inward supplies per head (3.1(d)): cash only, never
    #: set off -- outside `set_off` entirely, so no credit can reach it.
    reverse_charge: dict[str, Decimal] = field(
        default_factory=lambda: {head: ZERO for head in HEADS}
    )

    def cash(self, head: str) -> Decimal:
        """Return the cash one head needs: what the set-off left, plus RCM."""
        return self.set_off.cash(head) + max(self.reverse_charge[head], ZERO)

    @property
    def cash_total(self) -> Decimal:
        """Return all cash payable for tax, before interest and late fee."""
        return sum((self.cash(head) for head in HEADS), ZERO)


class GstPaymentService:
    """Work out a month's GST settlement, record it, and take it back."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def preview(
        self,
        firm_id: UUID,
        return_period: str,
        *,
        payment_date: date | None = None,
        opening_credit: dict[str, Decimal] | None = None,
    ) -> GstPaymentPreview:
        """Return the month's set-off and cash payable; writes nothing.

        Args:
            firm_id: The firm.
            return_period: The month, ``YYYY-MM``.
            payment_date: When the cash is or was paid, for the interest
                suggestion. Today when left out.
            opening_credit: Credit brought forward per head, used only when
                no settlement of the month before is recorded -- a firm's
                first month here, from the portal's credit ledger.

        """
        from app.gst_returns.services.gstr_service import GstReturnService

        first, last = period_bounds(return_period)
        summary = GstReturnService(self._session).gstr3b(
            firm_scope=firm_id, from_date=first, to_date=last
        )
        outward = _heads(summary["outward_taxable_supplies"])
        net_itc = _heads(summary["net_itc"])
        reverse_charge = _heads(summary.get("inward_reverse_charge"))
        previous = self._previous(firm_id, return_period)
        if previous is not None:
            brought = {head: getattr(previous, f"carried_{head}") for head in HEADS}
        else:
            brought = {
                head: quantize_ledger((opening_credit or {}).get(head, ZERO))
                for head in HEADS
            }
        credit = {head: brought[head] + net_itc[head] for head in HEADS}
        result = set_off(outward, credit)
        paid_on = payment_date or utc_now().date()
        days_late = max((paid_on - due_date(return_period)).days, 0)
        cash = sum(
            (result.cash(head) + max(reverse_charge[head], ZERO) for head in HEADS),
            ZERO,
        )
        interest = (cash * INTEREST_RATE * days_late / Decimal(365)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return GstPaymentPreview(
            return_period=return_period,
            due_date=due_date(return_period),
            set_off=result,
            brought_forward=brought,
            previous_settled=previous is not None,
            days_late=days_late,
            suggested_interest=quantize_ledger(interest),
            reverse_charge=reverse_charge,
        )

    def record(
        self,
        firm_id: UUID,
        return_period: str,
        *,
        payment_date: date,
        money_account_id: UUID,
        actor_id: UUID,
        challan_cpin: str | None = None,
        challan_cin: str | None = None,
        interest_amount: Decimal = ZERO,
        interest_account_id: UUID | None = None,
        late_fee_amount: Decimal = ZERO,
        late_fee_account_id: UUID | None = None,
        opening_credit: dict[str, Decimal] | None = None,
        narration: str | None = None,
    ) -> GstPayment:
        """Record the month's settlement and post its journal; the caller commits.

        Raises:
            ValidationError: If the month is already settled, a later month
                is, an expense account is missing for a charge, or the money
                account is not one the firm pays from.

        """
        if self._standing(firm_id, return_period) is not None:
            raise ValidationError(
                f"GST for {return_period} is already recorded as paid. Reverse "
                "that settlement first to record it again."
            )
        later = self._session.scalar(
            select(GstPayment.return_period).where(
                GstPayment.firm_id == firm_id,
                GstPayment.is_deleted.is_(False),
                GstPayment.status == GstPaymentStatus.POSTED.value,
                GstPayment.return_period > return_period,
            )
        )
        if later is not None:
            raise ValidationError(
                f"{later} is already settled, and its credit was carried from "
                f"this month. Reverse {later} first."
            )
        interest = quantize_ledger(interest_amount)
        late_fee = quantize_ledger(late_fee_amount)
        if interest < ZERO or late_fee < ZERO:
            raise ValidationError("Interest and late fee cannot be negative.")
        interest_account = self._expense_account(
            firm_id, interest_account_id, interest, "interest"
        )
        late_fee_account = self._expense_account(
            firm_id, late_fee_account_id, late_fee, "late fee"
        )
        money = self._session.get(LedgerAccount, money_account_id)
        if (
            money is None
            or money.firm_id != firm_id
            or money.is_deleted
            or money.account_type != AccountType.ASSET.value
        ):
            raise ValidationError(
                "Choose the bank or cash account the challan was paid from."
            )

        preview = self.preview(
            firm_id,
            return_period,
            payment_date=payment_date,
            opening_credit=opening_credit,
        )
        result = preview.set_off
        liability_total = sum((max(result.liability[h], ZERO) for h in HEADS), ZERO)
        reverse_charge = {h: max(preview.reverse_charge[h], ZERO) for h in HEADS}
        cash_total = preview.cash_total
        if (
            liability_total == ZERO
            and sum(reverse_charge.values(), ZERO) == ZERO
            and interest == ZERO
            and late_fee == ZERO
        ):
            raise ValidationError(
                f"{return_period} owes no GST and nothing else was paid, so "
                "there is nothing to record."
            )

        control = ControlAccountService(self._session)
        lines: list[JournalLineData] = []
        first, last = period_bounds(return_period)
        for account_id, amount in self._output_debits(
            firm_id, result.liability, first=first, last=last
        ).items():
            lines.append(
                JournalLineData(
                    ledger_account_id=account_id,
                    debit_amount=amount,
                    description=f"GST {return_period} settled",
                )
            )
        for head in HEADS:
            if reverse_charge[head] > ZERO:
                lines.append(
                    JournalLineData(
                        ledger_account_id=control.resolve(firm_id, RCM_PURPOSE[head]),
                        debit_amount=reverse_charge[head],
                        description=(
                            f"{head.upper()} reverse charge paid in cash, "
                            f"{return_period}"
                        ),
                    )
                )
        for head in HEADS:
            used = result.used(head)
            if used > ZERO:
                lines.append(
                    JournalLineData(
                        ledger_account_id=control.resolve(
                            firm_id, CREDIT_PURPOSE[head]
                        ),
                        credit_amount=used,
                        description=f"{head.upper()} credit set off, {return_period}",
                    )
                )
        if interest > ZERO and interest_account is not None:
            lines.append(
                JournalLineData(
                    ledger_account_id=interest_account,
                    debit_amount=interest,
                    description=f"Interest on GST {return_period}",
                )
            )
        if late_fee > ZERO and late_fee_account is not None:
            lines.append(
                JournalLineData(
                    ledger_account_id=late_fee_account,
                    debit_amount=late_fee,
                    description=f"Late fee, GSTR-3B {return_period}",
                )
            )
        paid = cash_total + interest + late_fee
        if paid > ZERO:
            lines.append(
                JournalLineData(
                    ledger_account_id=money_account_id,
                    credit_amount=paid,
                    description=f"GST challan {challan_cpin or ''}".strip(),
                )
            )

        posting = DocumentPostingService(self._session)
        context = posting.context_for(firm_id, payment_date)
        payment_id = uuid4()
        engine = JournalEntryEngine(self._session)
        entry = engine.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=payment_date,
            reference_number=f"GST-{return_period}",
            description=f"GST for {return_period} settled",
            lines=lines,
            actor_id=actor_id,
            source_module=SOURCE_MODULE,
            source_id=payment_id,
        )
        engine.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)

        row = GstPayment(
            id=payment_id,
            firm_id=firm_id,
            return_period=return_period,
            payment_date=payment_date,
            money_account_id=money_account_id,
            challan_cpin=(challan_cpin or "").strip() or None,
            challan_cin=(challan_cin or "").strip() or None,
            interest_amount=interest,
            interest_account_id=interest_account,
            late_fee_amount=late_fee,
            late_fee_account_id=late_fee_account,
            narration=narration,
            status=GstPaymentStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        for head in HEADS:
            setattr(row, f"liability_{head}", result.liability[head])
            setattr(row, f"credit_{head}", result.credit[head])
            setattr(row, f"used_{head}", result.used(head))
            setattr(row, f"cash_{head}", result.cash(head))
            setattr(row, f"carried_{head}", result.carried(head))
            setattr(row, f"reverse_charge_{head}", reverse_charge[head])
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="gst_payment.recorded",
            entity_type="gst_payment",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "return_period": return_period,
                "cash": str(cash_total),
                "interest": str(interest),
                "late_fee": str(late_fee),
                "challan_cpin": row.challan_cpin,
            },
        )
        return row

    def reverse(
        self, payment_id: UUID, *, firm_id: UUID, actor_id: UUID, reason: str
    ) -> GstPayment:
        """Take back a recorded settlement; the latest month only.

        Raises:
            ResourceNotFoundError: If it is not the firm's.
            ValidationError: If it is already reversed, or a later month is
                settled on the credit it carried.

        """
        row = self.get(payment_id, firm_id=firm_id)
        if row.status != GstPaymentStatus.POSTED.value:
            raise ValidationError("This settlement is already reversed.")
        later = self._session.scalar(
            select(GstPayment.return_period).where(
                GstPayment.firm_id == firm_id,
                GstPayment.is_deleted.is_(False),
                GstPayment.status == GstPaymentStatus.POSTED.value,
                GstPayment.return_period > row.return_period,
            )
        )
        if later is not None:
            raise ValidationError(
                f"{later} is settled on the credit this month carried. Reverse "
                f"{later} first."
            )
        mirror = JournalEntryEngine(self._session).reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"GST-{row.return_period}-REV",
            journal_date=row.payment_date,
            actor_id=actor_id,
        )
        row.status = GstPaymentStatus.REVERSED.value
        row.reversal_journal_entry_id = mirror.id
        row.reversed_at = utc_now()
        row.reversed_by = actor_id
        row.reversal_reason = reason
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="gst_payment.reversed",
            entity_type="gst_payment",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"return_period": row.return_period, "reason": reason},
        )
        return row

    def get(self, payment_id: UUID, *, firm_id: UUID) -> GstPayment:
        """Return one of the firm's settlements."""
        row = self._session.get(GstPayment, payment_id)
        if row is None or row.firm_id != firm_id or row.is_deleted:
            raise ResourceNotFoundError("GST payment not found.")
        return row

    def list_payments(self, firm_id: UUID) -> list[GstPayment]:
        """Return every settlement of the firm, newest month first."""
        return list(
            self._session.scalars(
                select(GstPayment)
                .where(GstPayment.firm_id == firm_id, GstPayment.is_deleted.is_(False))
                .order_by(GstPayment.return_period.desc(), GstPayment.created_at.desc())
            ).all()
        )

    def _standing(self, firm_id: UUID, return_period: str) -> GstPayment | None:
        return self._session.scalar(
            select(GstPayment).where(
                GstPayment.firm_id == firm_id,
                GstPayment.is_deleted.is_(False),
                GstPayment.status == GstPaymentStatus.POSTED.value,
                GstPayment.return_period == return_period,
            )
        )

    def _previous(self, firm_id: UUID, return_period: str) -> GstPayment | None:
        first, _ = period_bounds(return_period)
        before = first - timedelta(days=1)
        return self._standing(firm_id, f"{before.year:04d}-{before.month:02d}")

    def _output_debits(
        self,
        firm_id: UUID,
        liability: dict[str, Decimal],
        *,
        first: date,
        last: date,
    ) -> dict[UUID, Decimal]:
        """Return what to debit on each output-tax account to clear the month.

        Each head's account takes what the month's documents credited to it,
        net of their reversals and never more than the head's liability; the
        rest of the liability -- posted before the split, or cess -- goes to
        `OUTPUT_TAX` (backlog 63.3). Amounts are merged by account, so a firm
        that mapped a head to the single account gets one line.
        """
        control = ControlAccountService(self._session)
        mapping = control.mapping(firm_id)
        total = sum((max(liability[head], ZERO) for head in HEADS), ZERO)
        debits: dict[UUID, Decimal] = {}
        on_heads = ZERO
        for head, purpose in OUTPUT_PURPOSE.items():
            account_id = mapping.get(purpose.value)
            owed = max(liability[head], ZERO)
            if account_id is None or owed == ZERO:
                continue
            posted = max(
                self._credited(firm_id, account_id, first=first, last=last), ZERO
            )
            amount = min(posted, owed)
            if amount > ZERO:
                debits[account_id] = debits.get(account_id, ZERO) + amount
                on_heads += amount
        rest = total - on_heads
        if rest > ZERO:
            legacy = control.resolve(firm_id, ControlAccountPurpose.OUTPUT_TAX)
            debits[legacy] = debits.get(legacy, ZERO) + rest
        return debits

    def _credited(
        self, firm_id: UUID, account_id: UUID, *, first: date, last: date
    ) -> Decimal:
        """Return the net credit the month's documents posted to one account.

        Settlements are left out: they are what clears the account, and a
        reversed one would otherwise read as tax owed again.
        """
        value = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(JournalLine.credit_amount - JournalLine.debit_amount), 0
                )
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.status == JournalStatus.POSTED.value,
                JournalEntry.is_deleted.is_(False),
                JournalEntry.journal_date >= first,
                JournalEntry.journal_date <= last,
                or_(
                    JournalEntry.source_module.is_(None),
                    JournalEntry.source_module != SOURCE_MODULE,
                ),
                JournalLine.ledger_account_id == account_id,
                JournalLine.is_deleted.is_(False),
            )
        )
        return quantize_ledger(Decimal(str(value or 0)))

    def _expense_account(
        self, firm_id: UUID, account_id: UUID | None, amount: Decimal, what: str
    ) -> UUID | None:
        if amount == ZERO:
            return None
        if account_id is None:
            raise ValidationError(
                f"Choose the expense account the {what} is booked to."
            )
        account = self._session.get(LedgerAccount, account_id)
        if (
            account is None
            or account.firm_id != firm_id
            or account.is_deleted
            or account.account_type != AccountType.EXPENSE.value
        ):
            raise ValidationError(
                f"The {what} must go to one of the firm's expense accounts."
            )
        return account.id


def _heads(section: object) -> dict[str, Decimal]:
    """Read IGST, CGST, SGST and cess off one GSTR-3B section."""
    values = section if isinstance(section, dict) else {}
    keys = {
        "igst": "integrated_tax",
        "cgst": "central_tax",
        "sgst": "state_tax",
        "cess": "cess",
    }
    return {
        head: quantize_ledger(Decimal(str(values.get(key, 0) or 0)))
        for head, key in keys.items()
    }
