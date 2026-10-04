"""Rule 42: the share of common credit that exempt supplies take (GST-4, A84).

A firm that makes exempt supplies beside taxable ones may keep only the share
of its input credit that its taxable turnover bears. CGST rule 42(1): each
return period, ``D1 = C2 x E / F``, where

* **C2**, the common credit -- here the credit the period claimed (4(A)(3)
  reverse charge and 4(A)(5) all other), less blocked credit (4(B)(1)) and the
  period's other permanent reversals (returns and debit notes in 4(B)(2)).
  Rule 37 movements are left out: they are temporary, and come back.
* **E**, exempt turnover -- nil-rated, exempt and non-GST supplies (3.1(c) and
  3.1(e); the rule's explanation counts non-taxable supplies as exempt).
* **F**, total turnover -- E plus taxable (3.1(a)) and zero-rated (3.1(b)).

Every eligible credit is treated as common. Rule 42 also lets credit used
only for taxable supplies (T4) be kept whole and makes credit used only for
exempt ones (T2) go back whole; the platform cannot yet say which a bill is,
so the CA confirms the turnover definitions at hand-over and a firm with such
bills adjusts by journal. Rule 43 (capital goods) is not built -- nothing marks
a purchase as capital goods.

After the year, rule 42(2) works the same out on the year's figures and the
difference against what the periods reversed is put right: more reversed, or
claimed back, reported in the return of the month the firm chooses (by 30
September). Interest on an excess reversal-shortfall is the firm's to work out.

The firm chooses (``gst_compliance_settings.rule42_mode``): OFF, REPORT (the
default -- the figures, for the CA) or POST (the figures, and posting them).
A posted reversal moves the credit from the input-tax accounts to *Input Tax
Not Claimable*, as rule 37 does, and GSTR-3B reports it in 4(B)(1); a true-up
reclaim moves it back and is reported in 4(A)(5).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.gst_returns.models import (
    HEADS,
    CommonCreditKind,
    CommonCreditStatus,
    ItcCommonReversal,
)
from app.gst_returns.services.filing_frequency import (
    FilingFrequencyService,
    month_bounds,
    month_of,
    shift,
)
from app.tax.services.gst_buckets import GstBuckets
from app.tax.services.gst_compliance import GstComplianceService

_KEYS = {
    "igst": "integrated_tax",
    "cgst": "central_tax",
    "sgst": "state_tax",
    "cess": "cess",
}


def _value(section: object, key: str = "taxable_value") -> Decimal:
    """Read one figure off a GSTR-3B section."""
    values = section if isinstance(section, dict) else {}
    return Decimal(str(values.get(key, 0) or 0))


def _heads(section: object) -> dict[str, Decimal]:
    """Read the four heads off a GSTR-3B section."""
    return {head: _value(section, key) for head, key in _KEYS.items()}


def financial_year_bounds(label: str) -> tuple[date, date]:
    """Return 1 April and 31 March of a GST year named ``2026-27``.

    Raises:
        ValidationError: If the label is not a year of that shape.

    """
    try:
        start = int(label[:4])
        valid = len(label) == 7 and label[4] == "-"
        valid = valid and int(label[5:]) == (start + 1) % 100
    except ValueError:
        valid = False
    if not valid:
        raise ValidationError("A financial year is named like 2026-27.")
    return date(start, 4, 1), date(start + 1, 3, 31)


@dataclass(frozen=True, slots=True)
class Rule42Figures:
    """What one period's rule 42 arithmetic comes to."""

    period_from: date
    period_to: date
    exempt_turnover: Decimal
    total_turnover: Decimal
    common: dict[str, Decimal]
    #: D1 per head: what to give back for the period.
    reversal: dict[str, Decimal]

    @property
    def share(self) -> Decimal:
        """Return E / F, the exempt share of turnover; zero with no turnover."""
        if self.total_turnover <= ZERO:
            return ZERO
        return self.exempt_turnover / self.total_turnover


@dataclass(frozen=True, slots=True)
class AnnualTrueUp:
    """A year worked out whole, against what its periods reversed."""

    figures: Rule42Figures
    #: What the year's standing period reversals gave back, per head.
    already: dict[str, Decimal]
    #: The difference: positive reverses more, negative claims back.
    difference: dict[str, Decimal]


def _apply(
    first: date,
    last: date,
    exempt: Decimal,
    total: Decimal,
    common: dict[str, Decimal],
) -> Rule42Figures:
    """Return the figures for E, F and C2, D1 rounded to the paisa."""
    share = exempt / total if total > ZERO else ZERO
    return Rule42Figures(
        period_from=first,
        period_to=last,
        exempt_turnover=quantize_ledger(exempt),
        total_turnover=quantize_ledger(total),
        common={head: quantize_ledger(common[head]) for head in HEADS},
        reversal={
            head: quantize_ledger(max(common[head], ZERO) * share) for head in HEADS
        },
    )


class Rule42Service:
    """Work out, post and take back rule 42 reversals."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def mode(self, firm_id: UUID) -> str:
        """Return OFF, REPORT or POST, as the firm chose."""
        return (
            GstComplianceService(self._session).settings_response(firm_id).rule42_mode
        )

    def figures(self, firm_id: UUID, first: date, last: date) -> Rule42Figures:
        """Return E, F, C2 and D1 for a window of at most three months."""
        from app.gst_returns.services.gstr_service import GstReturnService

        summary = GstReturnService(self._session).gstr3b(
            firm_scope=firm_id, from_date=first, to_date=last
        )
        exempt = _value(summary.get("nil_rated_and_exempt_supplies")) + _value(
            summary.get("non_gst_supplies")
        )
        total = (
            exempt
            + _value(summary.get("outward_taxable_supplies"))
            + _value(summary.get("zero_rated_supplies"))
        )
        claimed = _heads(summary.get("eligible_itc"))
        reclaimed = _heads(summary.get("itc_reclaimed"))
        reverse_charge = _heads(summary.get("itc_reverse_charge"))
        # 4(A)(1): IGST on imports is credit like any other (PG-12).
        imports = _heads(summary.get("itc_import_goods"))
        blocked = _heads(summary.get("itc_reversed_blocked"))
        reversed_ = _heads(summary.get("itc_reversed"))
        rule37 = _heads(summary.get("itc_reversed_rule37"))
        common = {
            head: claimed[head]
            - reclaimed[head]
            + reverse_charge[head]
            + imports[head]
            - blocked[head]
            - (reversed_[head] - rule37[head])
            for head in HEADS
        }
        return _apply(first, last, exempt, total, common)

    def period(self, firm_id: UUID, return_period: str) -> Rule42Figures:
        """Return the figures of a return period: a month, or a quarter."""
        plan = FilingFrequencyService(self._session).plan(firm_id)
        period = plan.return_period(return_period)
        first, last = plan.span(period)
        return self.figures(firm_id, first, last)

    def annual(self, firm_id: UUID, financial_year: str) -> AnnualTrueUp:
        """Return the year worked out whole, against its period reversals."""
        start, end = financial_year_bounds(financial_year)
        exempt = total = ZERO
        common = {head: ZERO for head in HEADS}
        month = month_of(start)
        while month <= month_of(end):
            first, last = month_bounds(month)
            found = self.figures(firm_id, first, last)
            exempt += found.exempt_turnover
            total += found.total_turnover
            for head in HEADS:
                common[head] += found.common[head]
            month = shift(month, 1)
        figures = _apply(start, end, exempt, total, common)
        already = {head: ZERO for head in HEADS}
        for row in self._standing(firm_id, CommonCreditKind.MONTHLY):
            if start <= row.period_from <= end:
                for head in HEADS:
                    already[head] += Decimal(str(getattr(row, f"reversed_{head}")))
        return AnnualTrueUp(
            figures=figures,
            already=already,
            difference={
                head: quantize_ledger(figures.reversal[head] - already[head])
                for head in HEADS
            },
        )

    def post_period(
        self,
        firm_id: UUID,
        return_period: str,
        *,
        posting_date: date | None,
        actor_id: UUID,
    ) -> ItcCommonReversal:
        """Post a period's reversal, dated within it; the caller commits.

        Raises:
            ValidationError: Unless the firm chose POST, when the period is
                already posted or gives nothing back, or the date falls
                outside the period.

        """
        self._require_post(firm_id)
        figures = self.period(firm_id, return_period)
        on = posting_date or figures.period_to
        if not figures.period_from <= on <= figures.period_to:
            raise ValidationError(
                "A period's rule 42 reversal is dated inside the period, so "
                f"its GSTR-3B reports it: {figures.period_from.isoformat()} to "
                f"{figures.period_to.isoformat()}."
            )
        return self._post(
            firm_id,
            CommonCreditKind.MONTHLY,
            figures,
            figures.reversal,
            on=on,
            actor_id=actor_id,
            label=f"{figures.period_from:%b %Y}",
        )

    def post_annual(
        self,
        firm_id: UUID,
        financial_year: str,
        *,
        posting_date: date,
        actor_id: UUID,
    ) -> ItcCommonReversal:
        """Post a year's true-up, dated after the year; the caller commits.

        Raises:
            ValidationError: Unless the firm chose POST, when the year is not
                over, already trued up, or there is no difference.

        """
        self._require_post(firm_id)
        _, end = financial_year_bounds(financial_year)
        if posting_date <= end:
            raise ValidationError(
                f"The true-up for {financial_year} is posted after the year "
                f"ends, not on {posting_date.isoformat()}."
            )
        found = self.annual(firm_id, financial_year)
        return self._post(
            firm_id,
            CommonCreditKind.ANNUAL,
            found.figures,
            found.difference,
            on=posting_date,
            actor_id=actor_id,
            label=f"year {financial_year}",
        )

    def reverse(
        self, row_id: UUID, *, firm_id: UUID, actor_id: UUID, reason: str
    ) -> ItcCommonReversal:
        """Take back a posted reversal; the caller commits.

        Raises:
            ResourceNotFoundError: If it is not the firm's.
            ValidationError: If it is already reversed, or it is a period of a
                year already trued up -- the true-up was worked from it.

        """
        row = self._session.get(ItcCommonReversal, row_id)
        if row is None or row.firm_id != firm_id or row.is_deleted:
            raise ResourceNotFoundError("Rule 42 reversal not found.")
        if row.status != CommonCreditStatus.POSTED.value:
            raise ValidationError("This reversal is already taken back.")
        if row.kind == CommonCreditKind.MONTHLY.value:
            for annual in self._standing(firm_id, CommonCreditKind.ANNUAL):
                if annual.period_from <= row.period_from <= annual.period_to:
                    raise ValidationError(
                        "The year this period belongs to is trued up from it. "
                        "Take back the true-up first."
                    )
        mirror = JournalEntryEngine(self._session).reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"R42-{str(row.id)[:8]}-REV",
            journal_date=row.movement_date,
            actor_id=actor_id,
        )
        row.status = CommonCreditStatus.REVERSED.value
        row.reversal_journal_entry_id = mirror.id
        row.reversed_at = utc_now()
        row.reversed_by = actor_id
        row.reversal_reason = reason
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="gst.rule42.taken_back",
            entity_type="itc_common_reversal",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"kind": row.kind, "reason": reason},
        )
        return row

    def list_posted(self, firm_id: UUID) -> list[ItcCommonReversal]:
        """Return every rule 42 reversal of the firm, newest period first."""
        return list(
            self._session.scalars(
                select(ItcCommonReversal)
                .where(
                    ItcCommonReversal.firm_id == firm_id,
                    ItcCommonReversal.is_deleted.is_(False),
                )
                .order_by(
                    ItcCommonReversal.period_from.desc(),
                    ItcCommonReversal.created_at.desc(),
                )
            ).all()
        )

    def movements_between(
        self, *, firm_id: UUID, from_date: date, to_date: date
    ) -> tuple[GstBuckets, GstBuckets]:
        """Return (reversed, reclaimed) a GSTR-3B window reports.

        A period's reversal by its movement date, as a true-up's; a
        negative head is credit claimed back.
        """
        reversed_, reclaimed = GstBuckets(), GstBuckets()
        for row in self._session.scalars(
            select(ItcCommonReversal).where(
                ItcCommonReversal.firm_id == firm_id,
                ItcCommonReversal.is_deleted.is_(False),
                ItcCommonReversal.status == CommonCreditStatus.POSTED.value,
                ItcCommonReversal.movement_date >= from_date,
                ItcCommonReversal.movement_date <= to_date,
            )
        ):
            values = {
                head: Decimal(str(getattr(row, f"reversed_{head}"))) for head in HEADS
            }
            reversed_ = reversed_.plus(
                GstBuckets(**{h: max(v, ZERO) for h, v in values.items()})
            )
            reclaimed = reclaimed.plus(
                GstBuckets(**{h: max(-v, ZERO) for h, v in values.items()})
            )
        return reversed_, reclaimed

    # ---- posting ---------------------------------------------------------

    def _require_post(self, firm_id: UUID) -> None:
        """Refuse posting unless the firm chose to post."""
        if self.mode(firm_id) != "POST":
            raise ValidationError(
                "Rule 42 reversals are reported, not posted, for this firm. "
                "Choose Report and post under Settings > Tax > GST Documents."
            )

    def _post(
        self,
        firm_id: UUID,
        kind: CommonCreditKind,
        figures: Rule42Figures,
        amounts: dict[str, Decimal],
        *,
        on: date,
        actor_id: UUID,
        label: str,
    ) -> ItcCommonReversal:
        """Post one reversal or reclaim and keep its arithmetic."""
        for row in self._standing(firm_id, kind):
            if row.period_from == figures.period_from:
                raise ValidationError(
                    f"Rule 42 for {label} is already posted. Take it back "
                    "first to post it again."
                )
        forward = {head: max(amounts[head], ZERO) for head in HEADS}
        back = {head: max(-amounts[head], ZERO) for head in HEADS}
        if sum(forward.values(), ZERO) + sum(back.values(), ZERO) == ZERO:
            raise ValidationError(f"Rule 42 gives nothing back for {label}.")
        posting = DocumentPostingService(self._session)
        not_claimable = posting._require_mapping(
            firm_id, (ControlAccountPurpose.INELIGIBLE_INPUT_TAX,)
        )[ControlAccountPurpose.INELIGIBLE_INPUT_TAX]
        describe = f"Rule 42 common credit, {label}"
        lines: list[JournalLineData] = []
        for moved, reversal in ((forward, True), (back, False)):
            total = sum(moved.values(), ZERO)
            if total == ZERO:
                continue
            lines.append(
                JournalLineData(
                    ledger_account_id=not_claimable,
                    debit_amount=total if reversal else ZERO,
                    credit_amount=ZERO if reversal else total,
                    description=describe,
                )
            )
            lines += posting._input_tax_legs(
                firm_id=firm_id,
                ledger_tax=total,
                tax_by_component={
                    head.upper(): value for head, value in moved.items() if value
                },
                describe=describe,
                credit=reversal,
            )
        journals = JournalEntryEngine(self._session)
        context = posting.context_for(firm_id, on)
        entry = journals.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=on,
            reference_number=self._reference(firm_id, kind, figures.period_from),
            description=describe,
            lines=lines,
            source_module="rule42",
            actor_id=actor_id,
        )
        journals.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)
        row = ItcCommonReversal(
            firm_id=firm_id,
            kind=kind.value,
            period_from=figures.period_from,
            period_to=figures.period_to,
            movement_date=on,
            exempt_turnover=figures.exempt_turnover,
            total_turnover=figures.total_turnover,
            status=CommonCreditStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        for head in HEADS:
            setattr(row, f"common_{head}", figures.common[head])
            setattr(row, f"reversed_{head}", quantize_ledger(amounts[head]))
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action=f"gst.rule42.{kind.value.lower()}",
            entity_type="itc_common_reversal",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "period_from": figures.period_from.isoformat(),
                "exempt_turnover": str(figures.exempt_turnover),
                "total_turnover": str(figures.total_turnover),
                **{head: str(amounts[head]) for head in HEADS},
            },
        )
        return row

    def _standing(
        self, firm_id: UUID, kind: CommonCreditKind
    ) -> list[ItcCommonReversal]:
        """Return the firm's standing reversals of one kind."""
        return list(
            self._session.scalars(
                select(ItcCommonReversal).where(
                    ItcCommonReversal.firm_id == firm_id,
                    ItcCommonReversal.is_deleted.is_(False),
                    ItcCommonReversal.status == CommonCreditStatus.POSTED.value,
                    ItcCommonReversal.kind == kind.value,
                )
            ).all()
        )

    def _reference(self, firm_id: UUID, kind: CommonCreditKind, first: date) -> str:
        """Return a journal reference no journal has used: R42-<period>-<n>."""
        journals = JournalEntryEngine(self._session)
        stem = f"R42-{'Y' if kind == CommonCreditKind.ANNUAL else 'M'}-{first:%Y%m}"
        number = 1
        while True:
            reference = f"{stem}-{number}"
            if not journals.reference_taken(reference, firm_id=firm_id):
                return reference
            number += 1


__all__ = ["AnnualTrueUp", "Rule42Figures", "Rule42Service", "financial_year_bounds"]
