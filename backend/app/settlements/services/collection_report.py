"""Collections: money received from customers, by day, salesman and mode (67 row 9).

Read from the receipts themselves (``settlements`` of direction RECEIPT) and
what they cleared (``settlement_allocations``); nothing is stored.

**A receipt counts on its own date and a reversal on the reversal's date**,
netted -- a receipt of 500 on the 3rd reversed on the 9th is +500 on the 3rd
and -500 on the 9th, so each day agrees with the cash and bank books, which
carry the receipt and the mirror journal on those days. The reversal's date
is the date of the mirror journal that undid it.

**The amount is what the receipt settled** -- the customer's balance came down
by it -- tax deducted at source, rounding, bank charges and discount included,
as Tally's receipt voucher and the commission report count a collection.

**By salesman**, money allocated to a bill belongs to the bill's salesman;
what was allocated to no bill is *On account* -- an advance, held against
the customer -- and a bill or an opening bill with no salesman is *No
salesman*. The split is the receipt's allocations as they stand, so an
advance later applied to a bill moves from *On account* to that bill's
salesman.

Every grouping is done in SQL; the rows merged here are a few per day.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.pagination.reports import ReportWindow
from app.finance.models import JournalEntry
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import (
    Settlement,
    SettlementAllocation,
    SettlementDirection,
    SettlementStatus,
)
from app.settlements.schemas import MODE_LABELS

ZERO = Decimal("0.00")
GROUPINGS = ("day", "salesman", "method")
ON_ACCOUNT = "On account"
NO_SALESMAN = "No salesman"
#: By mode, a receipt counts under how the money moved (ACC-3); a bank
#: receipt recorded before the mode was asked for counts as *Bank*.
MODE = func.coalesce(Settlement.payment_mode, Settlement.method)


@dataclass(frozen=True)
class CollectionRow:
    """One day's, salesman's or mode's collections over the period."""

    key: str
    label: str
    receipts: int
    collected: Decimal
    reversals: int
    reversed: Decimal
    net_collected: Decimal


@dataclass
class _Tally:
    receipts: int = 0
    collected: Decimal = ZERO
    reversals: int = 0
    reversed: Decimal = ZERO


def _money(value: object) -> Decimal:
    """Read a summed figure to two places; NULL is nothing."""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


class CollectionReportService:
    """Read a firm's collections over a window."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def by(
        self, firm_id: UUID, grouping: str, window: ReportWindow
    ) -> list[CollectionRow]:
        """Return the collections per day, salesman or mode.

        Days and modes come in their own order; salesmen by the most
        collected, with *On account* and *No salesman* after the people.

        Raises:
            ValidationError: If ``grouping`` is not one of ``GROUPINGS``.

        """
        if grouping not in GROUPINGS:
            raise ValidationError(f"Collections are read by {', '.join(GROUPINGS)}.")
        tallies: dict[str, _Tally] = {}
        if grouping == "salesman":
            self._by_salesman(firm_id, window, tallies)
        else:
            self._by_receipt(firm_id, grouping, window, tallies)
        labels = self._labels(firm_id, grouping, list(tallies))
        rows = [
            CollectionRow(
                key=key,
                label=labels.get(key, key),
                receipts=tally.receipts,
                collected=tally.collected,
                reversals=tally.reversals,
                reversed=tally.reversed,
                net_collected=tally.collected - tally.reversed,
            )
            for key, tally in tallies.items()
        ]
        if grouping == "salesman":
            people = sorted(
                (row for row in rows if row.key not in (ON_ACCOUNT, NO_SALESMAN)),
                key=lambda row: (-row.net_collected, row.label),
            )
            rest = [
                row
                for key in (NO_SALESMAN, ON_ACCOUNT)
                for row in rows
                if row.key == key
            ]
            return people + rest
        return sorted(rows, key=lambda row: row.key)

    # ------------------------------------------------------------------

    def _receipts(self, firm_id: UUID) -> tuple[ColumnElement[bool], ...]:
        """Return the clauses that pick the firm's receipts."""
        return (
            Settlement.firm_id == firm_id,
            Settlement.is_deleted.is_(False),
            Settlement.direction == SettlementDirection.RECEIPT.value,
        )

    def _reversal_date(self) -> InstrumentedAttribute[date]:
        """Return the date a reversed receipt was undone on: its mirror journal's."""
        return JournalEntry.journal_date

    def _by_receipt(
        self,
        firm_id: UUID,
        grouping: str,
        window: ReportWindow,
        tallies: dict[str, _Tally],
    ) -> None:
        """Tally receipts and reversals by day or by mode, both in SQL."""
        received_key = Settlement.settlement_date if grouping == "day" else MODE
        for key, count, amount in self._session.execute(
            select(received_key, func.count(Settlement.id), func.sum(Settlement.amount))
            .where(
                *self._receipts(firm_id),
                *window.dated(Settlement.settlement_date),
            )
            .group_by(received_key)
        ).all():
            tally = tallies.setdefault(str(key), _Tally())
            tally.receipts += int(count)
            tally.collected += _money(amount)
        reversed_key = self._reversal_date() if grouping == "day" else MODE
        for key, count, amount in self._session.execute(
            select(reversed_key, func.count(Settlement.id), func.sum(Settlement.amount))
            .join(JournalEntry, JournalEntry.id == Settlement.reversal_journal_entry_id)
            .where(
                *self._receipts(firm_id),
                Settlement.status == SettlementStatus.REVERSED.value,
                *window.dated(self._reversal_date()),
            )
            .group_by(reversed_key)
        ).all():
            tally = tallies.setdefault(str(key), _Tally())
            tally.reversals += int(count)
            tally.reversed += _money(amount)

    def _by_salesman(
        self, firm_id: UUID, window: ReportWindow, tallies: dict[str, _Tally]
    ) -> None:
        """Tally what each salesman's bills received, and what stayed on account."""
        received = self._split(
            firm_id,
            dated=window.dated(Settlement.settlement_date),
            reversals=False,
        )
        reversed_ = self._split(
            firm_id,
            dated=window.dated(self._reversal_date()),
            reversals=True,
        )
        for key, (count, amount) in received.items():
            tally = tallies.setdefault(key, _Tally())
            tally.receipts += count
            tally.collected += amount
        for key, (count, amount) in reversed_.items():
            tally = tallies.setdefault(key, _Tally())
            tally.reversals += count
            tally.reversed += amount

    def _split(
        self,
        firm_id: UUID,
        *,
        dated: list[ColumnElement[bool]],
        reversals: bool,
    ) -> dict[str, tuple[int, Decimal]]:
        """Split the window's receipts (or reversals) by the bills they cleared.

        Two grouped reads: the allocations by the bill's salesman, and the
        receipts' whole amounts, whose remainder over their allocations is
        on account.
        """
        clauses: list[ColumnElement[bool]] = [*self._receipts(firm_id), *dated]
        if reversals:
            clauses.append(Settlement.status == SettlementStatus.REVERSED.value)

        def scoped(statement: Select[Any]) -> Select[Any]:
            """Join the mirror journal where reversals are dated by it."""
            if reversals:
                statement = statement.join(
                    JournalEntry,
                    JournalEntry.id == Settlement.reversal_journal_entry_id,
                )
            return statement.where(*clauses)

        split: dict[str, tuple[int, Decimal]] = {}
        allocated_total = ZERO
        for salesman_id, count, amount in self._session.execute(
            scoped(
                select(
                    SalesInvoice.salesman_id,
                    func.count(func.distinct(Settlement.id)),
                    func.sum(SettlementAllocation.amount),
                )
                .select_from(SettlementAllocation)
                .join(Settlement, Settlement.id == SettlementAllocation.settlement_id)
                .outerjoin(
                    SalesInvoice,
                    SalesInvoice.id == SettlementAllocation.sales_invoice_id,
                )
            )
            .where(SettlementAllocation.is_deleted.is_(False))
            .group_by(SalesInvoice.salesman_id)
        ).all():
            key = NO_SALESMAN if salesman_id is None else str(salesman_id)
            value = _money(amount)
            allocated_total += value
            split[key] = (int(count), value)
        count, whole = self._session.execute(
            scoped(select(func.count(Settlement.id), func.sum(Settlement.amount)))
        ).one()
        on_account = _money(whole) - allocated_total
        if on_account:
            unallocated = int(
                self._session.scalar(
                    scoped(
                        select(func.count(Settlement.id)).where(
                            Settlement.amount
                            > func.coalesce(
                                select(func.sum(SettlementAllocation.amount))
                                .where(
                                    SettlementAllocation.settlement_id == Settlement.id,
                                    SettlementAllocation.is_deleted.is_(False),
                                )
                                .scalar_subquery(),
                                0,
                            )
                        )
                    )
                )
                or 0
            )
            split[ON_ACCOUNT] = (unallocated, on_account)
        return split

    def _labels(self, firm_id: UUID, grouping: str, keys: list[str]) -> dict[str, str]:
        """Name each row: a day as itself, a mode in words, a salesman by name."""
        if grouping == "method":
            return {key: MODE_LABELS.get(key, key.title()) for key in keys}
        if grouping == "day":
            return {key: date.fromisoformat(key[:10]).isoformat() for key in keys}
        members = {
            str(member.user_id): member.full_name or member.email
            for member in FirmMetadataReader(self._session).active_members(firm_id)
        }
        return {
            key: (
                key
                if key in (ON_ACCOUNT, NO_SALESMAN)
                else members.get(key, "Former member")
            )
            for key in keys
        }
