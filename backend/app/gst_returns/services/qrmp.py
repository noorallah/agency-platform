"""GSTR-1 for a quarterly filer: the IFF, and the quarter's return (GST-7).

A quarterly filer may furnish its B2B invoices of months 1 and 2 early, on the
Invoice Furnishing Facility (rule 59(2)), so its buyers can claim the credit
that month rather than waiting for the quarter. The IFF carries only B2B
invoices and the credit and debit notes issued to registered buyers (tables
4A, 4B, 6B, 6C and 9B), up to 50 lakh of value a month.

Whatever was furnished on an IFF is not furnished again: the quarter's GSTR-1
leaves out the B2B invoices and registered notes of every month whose IFF is
recorded as filed, and says which months those were. A month whose IFF was
not filed has its invoices in the quarter's return, as usual.

Both are views of the documents, derived on every read, like GSTR-1 itself.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO
from app.gst_returns.models import GstReturnFiling, GstReturnType
from app.gst_returns.services.filing_frequency import (
    IFF_MONTHLY_LIMIT,
    FilingFrequencyService,
    position_in_quarter,
    quarter_label,
    quarter_months,
)
from app.gst_returns.services.gst_payment_service import period_bounds
from app.gst_returns.services.gstr_service import GstReturnService


def _b2b_total(b2b: object) -> Decimal:
    """Return the invoice value of a GSTR-1 ``b2b`` section."""
    total = ZERO
    for party in b2b if isinstance(b2b, list) else []:
        for invoice in party.get("invoices", []):
            total += Decimal(str(invoice.get("invoice_value", 0) or 0))
    return total


class QrmpReturnService:
    """The IFF of a month, and a quarterly filer's GSTR-1."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session
        self._returns = GstReturnService(session)

    def b2b_value(self, firm_id: UUID, month: str) -> Decimal:
        """Return the value of a month's B2B invoices; zero with no GSTIN."""
        first, last = period_bounds(month)
        try:
            data = self._returns.gstr1(
                firm_scope=firm_id, from_date=first, to_date=last
            )
        except ValidationError:
            return ZERO
        return _b2b_total(data["b2b"])

    def iff(self, firm_id: UUID, month: str) -> dict[str, object]:
        """Return what month 1 or 2's IFF furnishes.

        Raises:
            ValidationError: For a month filed monthly, or a quarter's last
                month, whose invoices go on the quarter's GSTR-1.

        """
        plan = FilingFrequencyService(self._session).plan(firm_id)
        if not plan.is_quarterly(month) or position_in_quarter(month) == 3:
            raise ValidationError(
                "The IFF is furnished only for the first two months of a "
                f"quarter filed quarterly, not for {month}."
            )
        first, last = period_bounds(month)
        data = self._returns.gstr1(firm_scope=firm_id, from_date=first, to_date=last)
        value = _b2b_total(data["b2b"])
        return {
            "gstin": data["gstin"],
            "return_period": month,
            "from_date": first.isoformat(),
            "to_date": last.isoformat(),
            "due_date": plan.iff_due(month).isoformat(),
            "b2b": data["b2b"],
            "cdnr": data["cdnr"],
            "b2b_value": float(value),
            "limit": IFF_MONTHLY_LIMIT,
            # Over the limit, the rest waits for the quarter's GSTR-1: the
            # portal refuses an IFF worth more than 50 lakh.
            "over_limit": value > IFF_MONTHLY_LIMIT,
            "filed": self._filing(firm_id, month) is not None,
            "unplaced_invoices": data["unplaced_invoices"],
        }

    def gstr1_quarter(self, firm_id: UUID, month: str) -> dict[str, object]:
        """Return the quarter's GSTR-1, less what its filed IFFs furnished.

        Raises:
            ValidationError: For a month filed monthly.

        """
        plan = FilingFrequencyService(self._session).plan(firm_id)
        if not plan.is_quarterly(month):
            raise ValidationError(
                f"{month} is filed monthly: ask for its GSTR-1 by its dates."
            )
        first_month, second_month, last_month = quarter_months(month)
        first, last = plan.span(last_month)
        data = self._returns.gstr1(firm_scope=firm_id, from_date=first, to_date=last)
        furnished = [
            early
            for early in (first_month, second_month)
            if self._filing(firm_id, early) is not None
        ]
        if furnished:
            data["b2b"] = [
                {**party, "invoices": kept}
                for party in data["b2b"]  # type: ignore[attr-defined]
                if (
                    kept := [
                        invoice
                        for invoice in party["invoices"]
                        if str(invoice["invoice_date"])[:7] not in furnished
                    ]
                )
            ]
            data["cdnr"] = [
                note
                for note in data["cdnr"]  # type: ignore[attr-defined]
                if str(note["note_date"])[:7] not in furnished
            ]
        data["return_period"] = last_month
        data["quarter"] = quarter_label(last_month)
        data["due_date"] = plan.gstr1_due(last_month).isoformat()
        data["furnished_in_iff"] = furnished
        return data

    def _filing(self, firm_id: UUID, month: str) -> GstReturnFiling | None:
        """Return the month's IFF recorded as filed, if any."""
        return self._session.scalar(
            select(GstReturnFiling).where(
                GstReturnFiling.firm_id == firm_id,
                GstReturnFiling.return_type == GstReturnType.IFF.value,
                GstReturnFiling.return_period == month,
                GstReturnFiling.is_deleted.is_(False),
            )
        )


__all__ = ["QrmpReturnService"]
