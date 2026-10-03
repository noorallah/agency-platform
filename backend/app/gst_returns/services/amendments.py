"""Filed returns stay filed; later changes are amendments (GST-6, decision A130).

A GSTR-1 marked filed is what the portal holds. Its figures cannot change
afterwards, so asking for that period again returns the snapshot taken when
it was marked filed. A document of a filed period edited -- or first raised
-- after filing is not lost and not double-counted: the next return states it
in the amendment tables, the way Tally and ClearTax work.

* **B2BA / B2CLA / CDNRA** -- an invoice or note declared earlier whose
  figures now differ: the original number, date and period, what was
  declared and what it now is.
* **B2CSA** -- an unregistered summary row (period, place, rate) whose totals
  now differ.
* **Added** -- a document dated in a filed period that the filed return never
  carried; reported now, with its own date.

What counts as declared is never stored on its own: it is rebuilt by
replaying the snapshots in filing order -- each period's own sections, then
the amendments each later return reported -- so withdrawing a filing simply
drops its snapshot and the baseline follows.

GSTR-3B states the net difference the amendments make to the tax.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gst_returns.models import GstReturnFiling, GstReturnSnapshot

#: The figures compared; a change in any of them is an amendment.
_FIGURES = (
    "taxable_value",
    "integrated_tax",
    "central_tax",
    "state_tax",
    "cess",
)
_TAX = _FIGURES[1:]
#: The sections compared, and the amendment table each change goes to.
_TABLES = {"B2B": "b2ba", "B2CL": "b2cla", "CDNR": "cdnra", "B2CS": "b2csa"}

Row = dict[str, Any]


def _month(day: date) -> str:
    """Return the ``YYYY-MM`` a day falls in."""
    return f"{day.year:04d}-{day.month:02d}"


def documents(data: dict[str, Any], period: str) -> dict[tuple[str, ...], Row]:
    """Return a GSTR-1's comparable documents, keyed for matching.

    An invoice is matched on its number (a B2BA may change the buyer's
    GSTIN), a note on its number and type, and an unregistered summary on its
    period, place and rate.
    """
    found: dict[tuple[str, ...], Row] = {}
    for party in data.get("b2b", []) or []:
        for invoice in party.get("invoices", []) or []:
            found[("B2B", str(invoice["invoice_number"]))] = {
                **invoice,
                "gstin": party.get("gstin"),
                "period": period,
            }
    for invoice in data.get("b2cl", []) or []:
        found[("B2CL", str(invoice["invoice_number"]))] = {**invoice, "period": period}
    for note in data.get("cdnr", []) or []:
        found[("CDNR", str(note["note_number"]), str(note.get("document_type")))] = {
            **note,
            "period": period,
        }
    for row in data.get("b2cs", []) or []:
        found[
            ("B2CS", period, str(row.get("place_of_supply")), str(row.get("rate")))
        ] = {**row, "period": period}
    return found


def _differs(declared: Row, now: Row) -> bool:
    """Say whether a document's figures, place or buyer moved."""
    for name in (*_FIGURES, "place_of_supply", "gstin"):
        if name not in declared and name not in now:
            continue
        if name in _FIGURES:
            if Decimal(str(declared.get(name, 0))) != Decimal(str(now.get(name, 0))):
                return True
        elif declared.get(name) != now.get(name):
            return True
    return False


def _sign(is_note: bool, row: Row) -> Decimal:
    """Return +1 for what adds tax, -1 for a credit note, which takes it off."""
    if is_note and row.get("note_type", "C") != "D":
        return Decimal("-1")
    return Decimal("1")


class GstAmendmentService:
    """Snapshot filed GSTR-1s and find what changed since."""

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session."""
        self._session = session

    def snapshots(self, firm_id: UUID, gstin: str) -> list[GstReturnSnapshot]:
        """Return the live GSTR-1 snapshots of a GSTIN, in filing order."""
        return list(
            self._session.scalars(
                select(GstReturnSnapshot)
                .join(
                    GstReturnFiling, GstReturnFiling.id == GstReturnSnapshot.filing_id
                )
                .where(
                    GstReturnSnapshot.firm_id == firm_id,
                    GstReturnSnapshot.gstin == gstin,
                    GstReturnSnapshot.return_type == "GSTR1",
                    GstReturnSnapshot.is_deleted.is_(False),
                    GstReturnFiling.is_deleted.is_(False),
                )
                .order_by(
                    GstReturnFiling.filed_on,
                    GstReturnSnapshot.from_date,
                    GstReturnSnapshot.created_at,
                )
            ).all()
        )

    def filed(
        self, firm_id: UUID, gstin: str, from_date: date, to_date: date
    ) -> GstReturnSnapshot | None:
        """Return the snapshot filed for exactly this period, if any."""
        for snapshot in self.snapshots(firm_id, gstin):
            if snapshot.from_date == from_date and snapshot.to_date == to_date:
                return snapshot
        return None

    def record(
        self,
        filing: GstReturnFiling,
        *,
        gstin: str,
        from_date: date,
        to_date: date,
        payload: dict[str, Any],
        actor_id: UUID,
    ) -> GstReturnSnapshot:
        """Keep what a filing reported; the caller commits."""
        row = GstReturnSnapshot(
            firm_id=filing.firm_id,
            filing_id=filing.id,
            return_type=filing.return_type,
            gstin=gstin,
            from_date=from_date,
            to_date=to_date,
            payload=payload,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def declared(self, firm_id: UUID, gstin: str) -> dict[tuple[str, ...], Row]:
        """Rebuild what has been declared, document by document.

        Each snapshot's own sections first, then the amendments and late
        additions it reported, in filing order.
        """
        baseline: dict[tuple[str, ...], Row] = {}
        for snapshot in self.snapshots(firm_id, gstin):
            data: dict[str, Any] = dict(snapshot.payload or {})
            baseline.update(documents(data, _month(snapshot.from_date)))
            amendments: dict[str, Any] = data.get("amendments") or {}
            for table in _TABLES.values():
                for change in amendments.get(table, []) or []:
                    baseline[tuple(change["key"])] = change["revised"]
            for added in amendments.get("added", []) or []:
                baseline[tuple(added["key"])] = added["row"]
        return baseline

    def amendments(
        self,
        firm_id: UUID,
        gstin: str,
        *,
        before: date,
        recompute: Callable[[date, date], dict[str, Any]],
    ) -> dict[str, Any]:
        """Return what changed in filed periods ending before ``before``.

        ``recompute(from_date, to_date)`` returns that period's GSTR-1 as the
        documents now stand, without amendments.
        """
        empty: dict[str, Any] = {table: [] for table in _TABLES.values()}
        empty["added"] = []
        snapshots = [s for s in self.snapshots(firm_id, gstin) if s.to_date < before]
        if not snapshots:
            return empty
        baseline = self.declared(firm_id, gstin)
        answer = empty
        seen: set[tuple[date, date]] = set()
        for snapshot in snapshots:
            bounds = (snapshot.from_date, snapshot.to_date)
            if bounds in seen:
                continue
            seen.add(bounds)
            period = _month(snapshot.from_date)
            now = documents(recompute(*bounds), period)
            for key, row in now.items():
                declared = baseline.get(key)
                if declared is None:
                    answer["added"].append(
                        {"key": list(key), "section": key[0], "row": row}
                    )
                elif _differs(declared, row):
                    answer[_TABLES[key[0]]].append(
                        {
                            "key": list(key),
                            "original_period": declared.get("period", period),
                            "declared": declared,
                            "revised": row,
                        }
                    )
            # A summary row that no longer exists has gone to nothing.
            for key, declared in baseline.items():
                if key[0] == "B2CS" and key[1] == period and key not in now:
                    zero = {**declared, **dict.fromkeys(_FIGURES, 0.0)}
                    answer["b2csa"].append(
                        {
                            "key": list(key),
                            "original_period": period,
                            "declared": declared,
                            "revised": zero,
                        }
                    )
        return answer

    @staticmethod
    def net_effect(amendments: dict[str, Any]) -> dict[str, float]:
        """Return what the amendments add to the tax, net, for GSTR-3B.

        A note credits, so a larger credit note lowers the tax.
        """
        total = dict.fromkeys(_FIGURES, Decimal("0"))
        for table in _TABLES.values():
            for change in amendments.get(table, []) or []:
                sign = _sign(table == "cdnra", change["revised"])
                for name in _FIGURES:
                    moved = Decimal(str(change["revised"].get(name, 0))) - Decimal(
                        str(change["declared"].get(name, 0))
                    )
                    total[name] += sign * moved
        for added in amendments.get("added", []) or []:
            sign = _sign(added["section"] == "CDNR", added["row"])
            for name in _FIGURES:
                total[name] += sign * Decimal(str(added["row"].get(name, 0)))
        return {
            name: float(value.quantize(Decimal("0.01")))
            for name, value in total.items()
        }


__all__ = ["GstAmendmentService", "documents"]
