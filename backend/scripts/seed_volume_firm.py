"""Build PERF01, a firm at a mid-size distributor's volume, for timing.

Backlog 56 C, step 5 (``docs/PERFORMANCE_AT_VOLUME.md``). The targets -- a
list opens in under a second, a report in under three -- mean nothing until
something holds the volume they are about, and running two years of trading
through the services would take hours. So this inserts the rows directly, in
bulk, reproducing what the services write: the same columns, statuses,
numbering, stock movements and journals.

    uv run python scripts/seed_volume_firm.py                 # scale 1.0
    uv run python scripts/seed_volume_firm.py --scale 0.1     # a quick run
    uv run python scripts/seed_volume_firm.py --reset         # rebuild PERF01

The firm lives in its **own dedicated schema** (``perf01``), provisioned the
way every SCHEMA firm is, so it never mixes with another firm's rows and
``--reset`` can drop it whole. Its set-up goes through the real services --
the firm, its storage, the GST template, the books, the branch, the document
series -- and only the trading is inserted directly.

At ``--scale 1.0``: 5,000 products (one in ten batch and expiry tracked),
2,000 customers, 300 suppliers, and two years of trading at about 150
invoices a day, each with its sales order and delivery note. Purchases are
driven by the stock: each supplier is ordered from once a week for whatever
of theirs has fallen below the reorder level. About 80% of invoices and bills
are settled; a few invoices get a sales return or a credit note.

What is kept consistent, and how:

* **Stock.** Every movement is written with the before-and-after quantities
  of its stock row, in date order, and ``inventories`` holds the final
  position -- so the balance equals the movements. A product costs the same
  at every receipt, so the moving average never moves and the valuation is
  quantity times cost.
* **Ledger.** Every journal is balanced at the ledger's two decimals, posted,
  mirrored into ``gl_postings``, and summed into ``ledger_balances`` period
  by period with each opening carried from the last closing -- what
  ``JournalEntryEngine`` maintains row by row.
* **Receivables.** Each customer's balance is walked through
  ``customer_receivable_transactions`` with the rule
  ``CustomerService.post_receivable_transaction`` applies, and the final
  figures are written onto the customer.
* **Numbers.** Each series is bootstrapped by the document framework itself
  and its counter moved past the last number used, so the next document a
  person raises is numbered correctly.

What is simplified, deliberately: no salesman, territory or route on any
document; one batch per tracked product; returns and credit notes only on
invoices that are never paid, so an allocation can never exceed what an
invoice still owes; no purchase returns; one lifecycle event pair and one
audit row per document rather than the full trail.

Remove the firm with ``--reset`` (rebuild) or, to drop it for good, delete
it on the Firms screen and ``DROP SCHEMA perf01 CASCADE``.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Table, bindparam, insert, text, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.database import all_models  # noqa: F401  -- every table registered
from app.core.database.base import Base
from app.core.utils.dates import financial_year_label
from app.core.utils.money import quantize_ledger, quantize_money
from app.document_framework.services.transactional_document_service import (
    DocumentTypeSpec,
)

FIRM_CODE = "PERF01"
FIRM_NAME = "Performance test firm"
SCHEMA_NAME = "perf01"
ADMIN_EMAIL = "perf01.admin@agency.local"
DEFAULT_PASSWORD = "PerfAdmin@12345"
BATCH_SIZE = 5_000
TRADING_DAYS = 730
STATE_NAME = "Karnataka"
STATE_CODE = "29"

ZERO = Decimal("0")
Row = dict[str, Any]

#: Every document series the seeder numbers, by the key it uses internally.
SERIES_KEYS = ("SO", "DN", "SI", "PO", "GRN", "PI", "SR", "CN", "RC", "PY")


# ---------------------------------------------------------------------------
# Money and dates
# ---------------------------------------------------------------------------


def q4(value: Decimal) -> Decimal:
    """Round to the four decimals every document amount is stored at."""
    return quantize_money(value)


def q2(value: Decimal) -> Decimal:
    """Round to the two decimals the ledger and receivables hold."""
    return quantize_ledger(value)


def fy_label(on: date) -> str:
    """Return the financial-year label (April start) a date belongs to."""
    return financial_year_label(on, start_month=4)


def fy_start(on: date) -> date:
    """Return the first day of the April financial year a date falls in."""
    return date(on.year if on.month >= 4 else on.year - 1, 4, 1)


# ---------------------------------------------------------------------------
# The bulk writer
# ---------------------------------------------------------------------------


class Sink:
    """Buffer rows per table and write them in batches, parents first.

    Rows go to a buffer per table. When any buffer reaches ``batch_size``
    every buffer is written, in the metadata's dependency order, and the
    batch is committed -- one transaction per batch, and a child row never
    reaches the database before the parent its foreign key names.

    On PostgreSQL the rows go through ``COPY``; elsewhere (the unit test's
    SQLite) through a Core ``insert()`` of the list of dicts. Both fill any
    column a row leaves out from the column's Python default, so a row
    builder names only what the service it copies would set.
    """

    def __init__(
        self,
        connection: Connection,
        *,
        schema: str | None = None,
        batch_size: int = BATCH_SIZE,
        use_copy: bool = False,
    ) -> None:
        """Bind to one connection; ``schema`` qualifies COPY targets."""
        self._connection = connection
        self._schema = schema
        self._batch_size = batch_size
        self._use_copy = use_copy
        self._buffers: dict[str, list[Row]] = defaultdict(list)
        self._order = [table.name for table in Base.metadata.sorted_tables]
        self.counts: Counter[str] = Counter()

    def add(self, table: str, row: Row) -> None:
        """Queue one row, writing everything once this table's buffer is full."""
        buffer = self._buffers[table]
        buffer.append(row)
        if len(buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        """Write every buffered row, parents before children, and commit."""
        pending = [name for name in self._order if self._buffers.get(name)]
        if not pending:
            return
        for name in pending:
            rows = self._buffers.pop(name)
            self._write(Base.metadata.tables[name], rows)
            self.counts[name] += len(rows)
        self._connection.commit()

    def _write(self, table: Table, rows: list[Row]) -> None:
        """Write one table's rows through COPY or a Core insert."""
        columns, defaults = _column_plan(table, rows)
        if not self._use_copy:
            self._connection.execute(
                insert(table),
                [
                    {name: row.get(name, defaults.get(name)) for name in columns}
                    for row in rows
                ],
            )
            return
        json_columns = {
            column.name for column in table.columns if isinstance(column.type, JSON)
        }
        target = f'"{self._schema}"."{table.name}"' if self._schema else table.name
        column_list = ", ".join(f'"{name}"' for name in columns)
        raw = self._connection.connection.driver_connection
        statement = f"COPY {target} ({column_list}) FROM STDIN"
        with raw.cursor() as cursor, cursor.copy(statement) as copy:  # type: ignore[union-attr]
            for row in rows:
                values = []
                for name in columns:
                    value = row.get(name, defaults.get(name))
                    if name in json_columns and value is not None:
                        value = json.dumps(value)
                    values.append(value)
                copy.write_row(values)


def _column_plan(table: Table, rows: list[Row]) -> tuple[list[str], Row]:
    """Return the columns to write and the Python defaults for missing ones.

    A column no row names is written only when it has a Python-side default
    (``default=False``, ``default=Decimal("0")``); one with only a server
    default is left to the database.
    """
    named: set[str] = set()
    for row in rows:
        named.update(row)
    columns: list[str] = []
    defaults: Row = {}
    for column in table.columns:
        default = column.default
        value: Any = None
        has_default = False
        if default is not None and getattr(default, "is_scalar", False):
            value, has_default = default.arg, True  # type: ignore[attr-defined]
        elif default is not None and getattr(default, "is_callable", False):
            value, has_default = default.arg(None), True  # type: ignore[attr-defined]
        if column.name in named or has_default:
            columns.append(column.name)
            if has_default:
                defaults[column.name] = value
    return columns, defaults


# ---------------------------------------------------------------------------
# What the trading is built from
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    """One open accounting period."""

    id: UUID
    starts_on: date
    ends_on: date


@dataclass(frozen=True)
class TaxSlab:
    """A local GST slab: the profile a line names and its two components."""

    rate: Decimal
    profile_id: UUID
    group_code: str
    cgst_id: UUID
    sgst_id: UUID


@dataclass
class FirmContext:
    """Every id the trading needs, read from the store the set-up built.

    The unit test builds one of these from made-up ids; the seeder builds it
    from the real store (`read_context`).
    """

    firm_id: UUID
    actor_id: UUID
    branch_id: UUID
    warehouse_ids: list[UUID]
    business_profile_id: UUID | None
    accounts: dict[str, UUID]
    account_types: dict[UUID, str]
    journal_type_id: UUID
    voucher_type_id: UUID
    periods: list[Period]
    slabs: list[TaxSlab]
    #: Number prefix per series key and financial-year label, everything up
    #: to the sequence digits -- ``{"SI": {"2025-2026": "SI-2025-2026-"}}``.
    prefixes: dict[str, dict[str, str]]
    padding: dict[str, int]
    document_types: dict[str, UUID]
    uom_id: UUID | None
    start: date
    end: date
    place_of_supply: str = f"{STATE_NAME} ({STATE_CODE})"


@dataclass
class ProductSeed:
    """A product as the trading uses it."""

    id: UUID
    code: str
    name: str
    price: Decimal
    cost: Decimal
    slab: TaxSlab
    vendor_index: int
    batch_id: UUID | None = None
    batch_number: str | None = None
    expiry: date | None = None


@dataclass
class PartySeed:
    """A customer or supplier as the trading uses it."""

    id: UUID
    code: str
    name: str
    order_weekday: int = 0
    outstanding: Decimal = ZERO
    advance: Decimal = ZERO


@dataclass
class Slot:
    """One stock row: a product in a warehouse."""

    inventory_id: UUID
    product_index: int
    warehouse_index: int
    current: int = 0
    reserved: int = 0
    last: date | None = None


@dataclass(frozen=True)
class Scale:
    """How much of everything to make."""

    factor: float

    def count(self, full: int, minimum: int = 1) -> int:
        """Return ``full`` scaled, never below ``minimum``."""
        return max(minimum, round(full * self.factor))

    @property
    def products(self) -> int:
        """Products at this scale."""
        return self.count(5_000, 20)

    @property
    def customers(self) -> int:
        """Customers at this scale."""
        return self.count(2_000, 10)

    @property
    def suppliers(self) -> int:
        """Suppliers at this scale."""
        return self.count(300, 3)

    @property
    def invoices_per_day(self) -> float:
        """Average sales invoices a day at this scale."""
        return max(1.0, 150 * self.factor)


# ---------------------------------------------------------------------------
# The trading
# ---------------------------------------------------------------------------


@dataclass
class _Sale:
    """What a receipt, return or credit note later needs of an invoice."""

    invoice_id: UUID
    number: str
    on: date
    customer_index: int
    warehouse_index: int
    total: Decimal
    first_line: Row
    first_line_product: int


@dataclass
class _Bill:
    """What a payment later needs of a supplier bill."""

    invoice_id: UUID
    number: str
    vendor_index: int
    total: Decimal


@dataclass
class TradeSimulator:
    """Walk the trading days and write what the services would have written.

    Nothing here touches a service or a session: every row goes to the
    ``Sink``, so the same code runs against the unit test's SQLite and the
    real store.
    """

    ctx: FirmContext
    sink: Sink
    scale: Scale
    rng: random.Random = field(default_factory=lambda: random.Random(56))
    products: list[ProductSeed] = field(default_factory=list)
    customers: list[PartySeed] = field(default_factory=list)
    vendors: list[PartySeed] = field(default_factory=list)
    slots: dict[tuple[int, int], Slot] = field(default_factory=dict)
    counters: Counter[tuple[str, str]] = field(default_factory=Counter)
    ledger: dict[tuple[UUID, UUID], list[Decimal]] = field(default_factory=dict)
    tally: Counter[str] = field(default_factory=Counter)
    _tick: int = 0
    _receipts_due: dict[date, list[_Sale]] = field(default_factory=dict)
    _payments_due: dict[date, list[_Bill]] = field(default_factory=dict)
    _returns_due: dict[date, list[_Sale]] = field(default_factory=dict)
    _notes_due: dict[date, list[_Sale]] = field(default_factory=dict)
    _vendor_products: dict[int, list[int]] = field(default_factory=dict)

    REORDER_LEVEL = 40
    OPENING_RANGE = (80, 160)
    REORDER_RANGE = (80, 140)
    PAID_SHARE = 0.8
    RETURN_SHARE = 0.03
    CREDIT_NOTE_SHARE = 0.02

    # ---- plumbing -------------------------------------------------------------------

    def _stamp(self, on: date) -> datetime:
        """Return a creation time on ``on``, strictly after the previous one."""
        self._tick += 1
        return datetime(on.year, on.month, on.day, 4, 30, tzinfo=UTC) + timedelta(
            microseconds=self._tick
        )

    def _base(self, on: date, row_id: UUID | None = None) -> Row:
        """Return the columns every ``BaseEntity`` row carries."""
        stamp = self._stamp(on)
        return {
            "id": row_id or uuid4(),
            "created_at": stamp,
            "updated_at": stamp,
            "created_by": self.ctx.actor_id,
            "updated_by": self.ctx.actor_id,
        }

    def _number(self, key: str, on: date) -> str:
        """Issue the next number of a series for a date's financial year."""
        label = fy_label(on)
        self.counters[(key, label)] += 1
        sequence = self.counters[(key, label)]
        return f"{self.ctx.prefixes[key][label]}{sequence:0{self.ctx.padding[key]}d}"

    def _period(self, on: date) -> Period:
        """Return the accounting period covering a date."""
        for period in self.ctx.periods:
            if period.starts_on <= on <= period.ends_on:
                return period
        raise ValueError(f"No accounting period covers {on}.")

    def _events(
        self,
        key: str,
        module: str,
        document_id: UUID,
        number: str,
        on: date,
        final: str,
    ) -> None:
        """Record the creation and the approval of a document, and audit it."""
        for action, from_state, to_state in (
            ("CREATED", None, "DRAFT"),
            ("APPROVED", "DRAFT", final),
        ):
            stamp = self._stamp(on)
            self.sink.add(
                "document_lifecycle_events",
                {
                    **self._base(on),
                    "firm_id": self.ctx.firm_id,
                    "document_type_id": self.ctx.document_types[key],
                    "source_document_id": document_id,
                    "source_module_code": module,
                    "document_number": number,
                    "action": action,
                    "from_state": from_state,
                    "to_state": to_state,
                    "details_json": {},
                    "snapshot_json": {},
                    "actor_id": self.ctx.actor_id,
                    "occurred_at": stamp,
                },
            )
        self.sink.add(
            "audit_logs",
            {
                "id": uuid4(),
                "created_at": self._stamp(on),
                "action": f"{module.lower()}.created",
                "entity_type": module.lower(),
                "entity_id": document_id,
                "actor_id": self.ctx.actor_id,
                "firm_id": self.ctx.firm_id,
                "after_data": {"number": number, "status": final},
            },
        )

    # ---- stock ----------------------------------------------------------------------

    def _move(
        self,
        key: tuple[int, int],
        *,
        kind: str,
        reference_type: str,
        reference_number: str,
        on: date,
        quantity: int,
        current_delta: int = 0,
        reserved_delta: int = 0,
        remarks: str | None = None,
        valued: bool = False,
    ) -> UUID:
        """Write one movement and its stock-ledger twin; return the movement id."""
        slot = self.slots[key]
        product = self.products[slot.product_index]
        before_current, before_reserved = slot.current, slot.reserved
        slot.current += current_delta
        slot.reserved += reserved_delta
        slot.last = on
        if slot.current < 0 or slot.reserved < 0 or slot.reserved > slot.current:
            raise ValueError(f"Stock went wrong on {product.code}: {slot}.")
        quantities: Row = {
            "quantity": Decimal(quantity),
            "current_quantity_delta": Decimal(current_delta),
            "reserved_quantity_delta": Decimal(reserved_delta),
            "blocked_quantity_delta": ZERO,
            "damaged_quantity_delta": ZERO,
            "quarantine_quantity_delta": ZERO,
            "in_transit_quantity_delta": ZERO,
            "previous_current_quantity": Decimal(before_current),
            "new_current_quantity": Decimal(slot.current),
            "previous_reserved_quantity": Decimal(before_reserved),
            "new_reserved_quantity": Decimal(slot.reserved),
            "previous_available_quantity": Decimal(before_current - before_reserved),
            "new_available_quantity": Decimal(slot.current - slot.reserved),
        }
        for name in ("blocked", "damaged", "quarantine", "in_transit"):
            quantities[f"previous_{name}_quantity"] = ZERO
            quantities[f"new_{name}_quantity"] = ZERO
        common: Row = {
            "inventory_id": slot.inventory_id,
            "firm_id": self.ctx.firm_id,
            "branch_id": self.ctx.branch_id,
            "warehouse_id": self.ctx.warehouse_ids[slot.warehouse_index],
            "product_id": product.id,
            "business_profile_id": self.ctx.business_profile_id,
            "transaction_type": kind,
            "reference_number": reference_number,
            "reference_type": reference_type,
            "transaction_date": on,
            "remarks": remarks,
            "batch_id": product.batch_id,
            **quantities,
        }
        movement = self._base(on)
        self.sink.add(
            "inventory_transactions",
            {**movement, **common, "entered_quantity": Decimal(quantity)},
        )
        cost = product.cost
        self.sink.add(
            "stock_ledger_entries",
            {
                **self._base(on),
                **common,
                "transaction_id": movement["id"],
                "original_quantity": Decimal(quantity),
                "base_quantity": Decimal(quantity),
                "unit_cost": cost if valued else None,
                "total_cost": q4(cost * quantity) if valued else None,
                "average_cost_after": cost,
            },
        )
        return movement["id"]  # type: ignore[no-any-return]

    # ---- ledger ---------------------------------------------------------------------

    def _journal(
        self,
        *,
        on: date,
        reference: str,
        description: str,
        source_module: str,
        source_id: UUID,
        legs: list[tuple[str | UUID, Decimal, Decimal, str]],
    ) -> UUID:
        """Write one posted, balanced journal with its lines and postings.

        Each leg is ``(purpose or account id, debit, credit, description)``,
        at the ledger's two decimals; legs of nil are dropped, as the posting
        service drops them.
        """
        legs = [leg for leg in legs if leg[1] != ZERO or leg[2] != ZERO]
        debit = sum((leg[1] for leg in legs), ZERO)
        credit = sum((leg[2] for leg in legs), ZERO)
        if debit != credit or debit == ZERO:
            raise ValueError(f"Journal {reference} does not balance: {debit}/{credit}")
        period = self._period(on)
        entry = self._base(on)
        posted_at = entry["created_at"]
        self.sink.add(
            "journal_entries",
            {
                **entry,
                "firm_id": self.ctx.firm_id,
                "journal_type_id": self.ctx.journal_type_id,
                "voucher_type_id": self.ctx.voucher_type_id,
                "accounting_period_id": period.id,
                "journal_date": on,
                "reference_number": reference,
                "description": description,
                "status": "POSTED",
                "posted_at": posted_at,
                "total_debit": debit,
                "total_credit": credit,
                "is_balanced": True,
                "source_module": source_module,
                "source_id": source_id,
            },
        )
        for number, (target, leg_debit, leg_credit, narrative) in enumerate(
            legs, start=1
        ):
            account = target if isinstance(target, UUID) else self.ctx.accounts[target]
            line = self._base(on)
            self.sink.add(
                "journal_lines",
                {
                    **line,
                    "journal_entry_id": entry["id"],
                    "ledger_account_id": account,
                    "line_number": number,
                    "debit_amount": leg_debit,
                    "credit_amount": leg_credit,
                    "description": narrative,
                },
            )
            self.sink.add(
                "gl_postings",
                {
                    **self._base(on),
                    "firm_id": self.ctx.firm_id,
                    "journal_entry_id": entry["id"],
                    "journal_line_id": line["id"],
                    "ledger_account_id": account,
                    "accounting_period_id": period.id,
                    "posting_date": posted_at,
                    "debit_amount": leg_debit,
                    "credit_amount": leg_credit,
                    "status": "POSTED",
                    "posted_by": self.ctx.actor_id,
                },
            )
            totals = self.ledger.setdefault((account, period.id), [ZERO, ZERO])
            totals[0] += leg_debit
            totals[1] += leg_credit
        self.tally["journals"] += 1
        return entry["id"]  # type: ignore[no-any-return]

    # ---- receivables ----------------------------------------------------------------

    def _receivable(
        self,
        customer_index: int,
        *,
        kind: str,
        on: date,
        amount: Decimal,
        reference_type: str,
        reference_id: UUID,
        reference_number: str,
        journal_entry_id: UUID | None = None,
    ) -> UUID:
        """Move a customer's balance the way ``post_receivable_transaction`` does."""
        customer = self.customers[customer_index]
        if kind == "INVOICE":
            outstanding_delta, advance_delta = amount, ZERO
        else:
            applied = min(amount, customer.outstanding)
            outstanding_delta, advance_delta = -applied, amount - applied
        customer.outstanding += outstanding_delta
        customer.advance += advance_delta
        row = self._base(on)
        self.sink.add(
            "customer_receivable_transactions",
            {
                **row,
                "firm_id": self.ctx.firm_id,
                "customer_id": customer.id,
                "transaction_type": kind,
                "transaction_date": on,
                "amount": amount,
                "outstanding_delta": outstanding_delta,
                "advance_delta": advance_delta,
                "outstanding_after": customer.outstanding,
                "advance_after": customer.advance,
                "reference_type": reference_type,
                "reference_id": reference_id,
                "reference_number": reference_number,
                "journal_entry_id": journal_entry_id,
            },
        )
        return row["id"]  # type: ignore[no-any-return]

    # ---- line arithmetic ------------------------------------------------------------

    def _priced(
        self, product: ProductSeed, quantity: int, price: Decimal, discount: Decimal
    ) -> Row:
        """Return a line's money, the way the pricing and tax services round it."""
        gross = q4(price * quantity)
        discount_amount = q4(gross * discount / 100)
        taxable = gross - discount_amount
        tax = q4(taxable * product.slab.rate / 100)
        cgst = q4(taxable * product.slab.rate / 200)
        return {
            "unit_price": price,
            "discount_percent": discount,
            "discount_amount": discount_amount,
            "gross_amount": gross,
            "taxable": taxable,
            "tax_amount": tax,
            "net_amount": taxable + tax,
            "cgst": cgst,
            "sgst": tax - cgst,
        }

    def _line_taxes(
        self,
        table: str,
        parent_key: str,
        line_id: UUID,
        money: Row,
        on: date,
        slab: TaxSlab,
    ) -> None:
        """Write the CGST and SGST rows of one line."""
        for sequence, (code, label, component, amount) in enumerate(
            (
                ("CGST", "CGST", slab.cgst_id, money["cgst"]),
                ("SGST", "SGST", slab.sgst_id, money["sgst"]),
            ),
            start=1,
        ):
            self.sink.add(
                table,
                {
                    **self._base(on),
                    parent_key: line_id,
                    "firm_id": self.ctx.firm_id,
                    "sequence": sequence,
                    "tax_component_id": component,
                    "component_code": code,
                    "component_label": label,
                    "percentage": slab.rate / 2,
                    "base_amount": money["taxable"],
                    "amount": amount,
                    "included_in_price": False,
                    "recoverable": True,
                },
            )

    # ---- masters --------------------------------------------------------------------

    def build_masters(self) -> None:
        """Write categories, products and batches, parties and stock rows."""
        ctx, rng, on = self.ctx, self.rng, self.ctx.start
        categories = []
        for index in range(20):
            row = {
                **self._base(on),
                "firm_id": ctx.firm_id,
                "code": f"CAT{index + 1:02d}",
                "name": f"Category {index + 1:02d}",
                "path": f"CAT{index + 1:02d}",
                "level": 0,
                "is_active": True,
            }
            categories.append(row["id"])
            self.sink.add("product_categories", row)
        for index in range(self.scale.suppliers):
            vendor = PartySeed(
                id=uuid4(),
                code=f"V{index + 1:05d}",
                name=f"Supplier {index + 1:05d}",
                order_weekday=index % 6,
            )
            self.vendors.append(vendor)
            self.sink.add(
                "vendors",
                {
                    **self._base(on, vendor.id),
                    "firm_id": ctx.firm_id,
                    "code": vendor.code,
                    "name": vendor.name,
                    "legal_name": f"{vendor.name} Private Limited",
                    "display_name": vendor.name,
                    "status": "ACTIVE",
                    "gst_registration": True,
                    "gstin": _gstin(f"V{index:05d}", index),
                    "business_attributes": {},
                },
            )
        for index in range(self.scale.customers):
            customer = PartySeed(
                id=uuid4(), code=f"C{index + 1:05d}", name=f"Customer {index + 1:05d}"
            )
            self.customers.append(customer)
            self.sink.add(
                "customers",
                {
                    **self._base(on, customer.id),
                    "firm_id": ctx.firm_id,
                    "code": customer.code,
                    "customer_type": "BUSINESS",
                    "name": customer.name,
                    "display_name": customer.name,
                    "gst_number": _gstin(f"C{index:05d}", index),
                    "credit_limit": Decimal("500000.00"),
                    "opening_balance": ZERO,
                    "payment_terms_days": 30,
                    "currency_code": "INR",
                    "status": "ACTIVE",
                    "current_outstanding": ZERO,
                    "unapplied_advance_balance": ZERO,
                },
            )
        for index in range(self.scale.products):
            slab = ctx.slabs[index % len(ctx.slabs)]
            cost = Decimal(rng.randint(2_000, 90_000)) / 100
            product = ProductSeed(
                id=uuid4(),
                code=f"P{index + 1:05d}",
                name=f"Product {index + 1:05d}",
                price=q4(cost * Decimal("1.25")),
                cost=cost,
                slab=slab,
                vendor_index=index % len(self.vendors),
            )
            tracked = index % 10 == 0
            self.products.append(product)
            self._vendor_products.setdefault(product.vendor_index, []).append(index)
            self.sink.add(
                "products",
                {
                    **self._base(on, product.id),
                    "firm_id": ctx.firm_id,
                    "code": product.code,
                    "name": product.name,
                    "product_type": "STOCK_ITEM",
                    "category_id": categories[index % len(categories)],
                    "hsn_sac": "330610",
                    "purchase_price": cost,
                    "selling_price": product.price,
                    "mrp": q4(product.price * Decimal("1.3")),
                    "status": "ACTIVE",
                    "track_batch": tracked,
                    "track_expiry": tracked,
                    "require_batch_on_receipt": tracked,
                    "require_batch_on_issue": tracked,
                    "base_uom_id": ctx.uom_id,
                    "inventory_uom_id": ctx.uom_id,
                    "purchase_uom_id": ctx.uom_id,
                    "sales_uom_id": ctx.uom_id,
                    "tax_profile_group_code": slab.group_code,
                },
            )
            if tracked:
                product.batch_id = uuid4()
                product.batch_number = f"B-{product.code}"
                product.expiry = ctx.end + timedelta(days=365 + index % 300)
                self.sink.add(
                    "batches",
                    {
                        **self._base(on, product.batch_id),
                        "firm_id": ctx.firm_id,
                        "product_id": product.id,
                        "vendor_id": self.vendors[product.vendor_index].id,
                        "batch_number": product.batch_number,
                        "manufacturing_date": ctx.start - timedelta(days=30),
                        "expiry_date": product.expiry,
                        "status": "ACTIVE",
                    },
                )
            for warehouse_index, warehouse_id in enumerate(ctx.warehouse_ids):
                slot = Slot(uuid4(), index, warehouse_index)
                self.slots[(index, warehouse_index)] = slot
                self.sink.add(
                    "inventories",
                    {
                        **self._base(on, slot.inventory_id),
                        "firm_id": ctx.firm_id,
                        "branch_id": ctx.branch_id,
                        "warehouse_id": warehouse_id,
                        "storage_locator": "ROOT",
                        "product_id": product.id,
                        "batch_id": product.batch_id,
                        "business_profile_id": ctx.business_profile_id,
                        "display_uom_id": ctx.uom_id,
                        "status": "ACTIVE",
                    },
                )
        self.tally.update(
            products=len(self.products),
            customers=len(self.customers),
            suppliers=len(self.vendors),
        )

    def opening_stock(self) -> None:
        """Lay down day-one stock per warehouse, posted as the service posts it."""
        on = self.ctx.start
        for warehouse_index, warehouse_id in enumerate(self.ctx.warehouse_ids):
            reference = f"OS-{FIRM_CODE}-W{warehouse_index + 1}"
            batch = self._base(on)
            self.sink.add(
                "opening_stock_batches",
                {
                    **batch,
                    "firm_id": self.ctx.firm_id,
                    "branch_id": self.ctx.branch_id,
                    "warehouse_id": warehouse_id,
                    "reference_number": reference,
                    "posting_date": on,
                    "source_format": "MANUAL",
                    "status": "POSTED",
                    "posted_at": on,
                },
            )
            value = ZERO
            for index, product in enumerate(self.products):
                quantity = self.rng.randint(*self.OPENING_RANGE)
                movement = self._move(
                    (index, warehouse_index),
                    kind="OPENING_STOCK",
                    reference_type="OPENING_STOCK",
                    reference_number=reference,
                    on=on,
                    quantity=quantity,
                    current_delta=quantity,
                    valued=True,
                )
                value += q4(product.cost * quantity)
                self.sink.add(
                    "opening_stock_lines",
                    {
                        **self._base(on),
                        "opening_stock_batch_id": batch["id"],
                        "line_number": index + 1,
                        "product_id": product.id,
                        "storage_locator": "ROOT",
                        "business_profile_id": self.ctx.business_profile_id,
                        "quantity": Decimal(quantity),
                        "unit_cost": product.cost,
                        "entered_quantity": Decimal(quantity),
                        "batch_number": product.batch_number,
                        "batch_id": product.batch_id,
                        "expiry_date": product.expiry,
                        "reorder_level": Decimal(self.REORDER_LEVEL),
                        "transaction_id": movement,
                    },
                )
            self._journal(
                on=on,
                reference=reference,
                description=f"Opening stock {reference}",
                source_module="inventory",
                source_id=batch["id"],
                legs=[
                    ("INVENTORY", q2(value), ZERO, f"Opening stock {reference}"),
                    (
                        "OPENING_BALANCE_EQUITY",
                        ZERO,
                        q2(value),
                        f"Opening stock {reference}",
                    ),
                ],
            )

    # ---- one day --------------------------------------------------------------------

    def run(self, progress: Callable[[str], None] | None = None) -> None:
        """Trade every day from the start date to the end date."""
        self.build_masters()
        self.opening_stock()
        day = self.ctx.start
        started = time.monotonic()
        while day <= self.ctx.end:
            self._purchase(day)
            self._sell_day(day)
            self._settle(day)
            day += timedelta(days=1)
            if progress is not None and day.day == 1:
                progress(
                    f"  traded to {day - timedelta(days=1)}: "
                    f"{self.tally['sales_invoices']:,} invoices, "
                    f"{self.tally['purchase_invoices']:,} bills, "
                    f"{sum(self.sink.counts.values()):,} rows written "
                    f"({time.monotonic() - started:,.0f}s)"
                )

    def _sell_day(self, on: date) -> None:
        """Raise the day's sales: order, delivery note and invoice each."""
        mean = self.scale.invoices_per_day
        count = max(0, round(self.rng.gauss(mean, mean * 0.2)))
        for _ in range(count):
            self._sell(on)

    def _sell(self, on: date) -> None:
        """Raise one sale through the whole chain."""
        rng, ctx = self.rng, self.ctx
        customer_index = rng.randrange(len(self.customers))
        customer = self.customers[customer_index]
        warehouse_index = rng.choices(
            range(len(ctx.warehouse_ids)),
            weights=[5, 3, 2][: len(ctx.warehouse_ids)],
        )[0]
        warehouse_id = ctx.warehouse_ids[warehouse_index]
        picks: list[tuple[int, int]] = []
        for product_index in rng.sample(
            range(len(self.products)), k=min(rng.randint(1, 9), len(self.products))
        ):
            slot = self.slots[(product_index, warehouse_index)]
            available = slot.current - slot.reserved
            if available > 0:
                picks.append((product_index, min(rng.randint(1, 10), available)))
        if not picks:
            return
        discount = Decimal(rng.choice(("0", "0", "2.5", "5")))
        so_number = self._number("SO", on)
        dn_number = self._number("DN", on)
        si_number = self._number("SI", on)
        so_id, dn_id, si_id = uuid4(), uuid4(), uuid4()
        money = [
            self._priced(self.products[p], q, self.products[p].price, discount)
            for p, q in picks
        ]
        totals = {
            "line_discount_total": sum((m["discount_amount"] for m in money), ZERO),
            "subtotal": sum((m["taxable"] for m in money), ZERO),
            "tax_total": sum((m["tax_amount"] for m in money), ZERO),
        }
        grand = totals["subtotal"] + totals["tax_total"]
        quantity_total = Decimal(sum(q for _, q in picks))
        stamp = self._stamp(on)
        self.sink.add(
            "sales_orders",
            {
                **self._base(on, so_id),
                "version": 3,
                "firm_id": ctx.firm_id,
                "customer_id": customer.id,
                "branch_id": ctx.branch_id,
                "warehouse_id": warehouse_id,
                "order_number": so_number,
                "order_date": on,
                "credit_limit_snapshot": Decimal("500000.00"),
                "outstanding_balance_snapshot": customer.outstanding,
                "status": "DELIVERED",
                **totals,
                "additional_charges": ZERO,
                "round_off": ZERO,
                "grand_total": grand,
                "approved_at": stamp,
                "customer_discount_percent": ZERO,
                "bill_discount_percent": ZERO,
                "bill_discount_amount": ZERO,
                "freight_amount": ZERO,
                "bill_discount_source": "none",
                "freight_waived_amount": ZERO,
            },
        )
        self.sink.add(
            "delivery_notes",
            {
                **self._base(on, dn_id),
                "version": 2,
                "firm_id": ctx.firm_id,
                "sales_order_id": so_id,
                "customer_id": customer.id,
                "branch_id": ctx.branch_id,
                "warehouse_id": warehouse_id,
                "delivery_note_number": dn_number,
                "delivery_date": on,
                "sales_order_reference": so_number,
                "status": "DISPATCHED",
                "total_ordered_quantity": quantity_total,
                "total_previously_delivered_quantity": ZERO,
                "total_current_delivery_quantity": quantity_total,
                "total_free_quantity": ZERO,
                **totals,
                "additional_charges": ZERO,
                "round_off": ZERO,
                "grand_total": grand,
                "approved_at": stamp,
                "dispatched_at": stamp,
            },
        )
        self.sink.add(
            "sales_invoices",
            {
                **self._base(on, si_id),
                "version": 3,
                "firm_id": ctx.firm_id,
                "customer_id": customer.id,
                "branch_id": ctx.branch_id,
                "invoice_number": si_number,
                "invoice_date": on,
                "due_date": on + timedelta(days=30),
                "status": "APPROVED",
                "total_source_quantity": quantity_total,
                "total_already_invoiced_quantity": ZERO,
                "total_current_invoice_quantity": quantity_total,
                **totals,
                "additional_charges": ZERO,
                "round_off": ZERO,
                "grand_total": grand,
                "approved_at": stamp,
                "place_of_supply": ctx.place_of_supply,
                "bill_discount_percent": ZERO,
                "bill_discount_amount": ZERO,
                "total_free_quantity": ZERO,
                "freight_amount": ZERO,
            },
        )
        self.sink.add(
            "sales_invoice_sources",
            {
                **self._base(on),
                "sales_invoice_id": si_id,
                "firm_id": ctx.firm_id,
                "source_document_type": "DELIVERY_NOTE",
                "source_document_id": dn_id,
                "source_document_number": dn_number,
                "source_document_date": on,
                "customer_id": customer.id,
                "branch_id": ctx.branch_id,
            },
        )
        cost_total = ZERO
        first_line: Row = {}
        for number, ((product_index, quantity), line_money) in enumerate(
            zip(picks, money, strict=True), start=1
        ):
            product = self.products[product_index]
            key = (product_index, warehouse_index)
            so_line_id, dn_line_id, si_line_id = uuid4(), uuid4(), uuid4()
            amounts = {
                name: line_money[name]
                for name in (
                    "unit_price",
                    "discount_percent",
                    "discount_amount",
                    "gross_amount",
                    "tax_amount",
                    "net_amount",
                )
            }
            self._move(
                key,
                kind="RESERVE",
                reference_type="SALES_ORDER",
                reference_number=so_number,
                on=on,
                quantity=quantity,
                reserved_delta=quantity,
                remarks=f"sales_order reserve line {number}",
            )
            released = self._move(
                key,
                kind="UNRESERVE",
                reference_type="SALES_ORDER",
                reference_number=so_number,
                on=on,
                quantity=quantity,
                reserved_delta=-quantity,
                remarks=f"sales_order release line {number}",
            )
            dispatched = self._move(
                key,
                kind="DISPATCH",
                reference_type="DELIVERY_NOTE",
                reference_number=dn_number,
                on=on,
                quantity=quantity,
                current_delta=-quantity,
                remarks="delivery_note dispatch",
                valued=True,
            )
            cost = q4(product.cost * quantity)
            cost_total += cost
            common = {
                "firm_id": ctx.firm_id,
                "line_number": number,
                "product_id": product.id,
                "description": product.name,
                "conversion_factor": Decimal("1"),
                **amounts,
                "tax_profile_id": product.slab.profile_id,
                "bill_discount_amount": ZERO,
                "freight_amount": ZERO,
            }
            q = Decimal(quantity)
            self.sink.add(
                "sales_order_lines",
                {
                    **self._base(on, so_line_id),
                    **common,
                    "sales_order_id": so_id,
                    "quantity": q,
                    "free_quantity": ZERO,
                    "base_quantity": q,
                    "reservable_quantity": q,
                    "reserved_quantity": ZERO,
                    "warehouse_id": warehouse_id,
                    "sales_uom_id": ctx.uom_id,
                    "inventory_uom_id": ctx.uom_id,
                    "discount_source": "manual" if discount else "none",
                },
            )
            self.sink.add(
                "delivery_note_lines",
                {
                    **self._base(on, dn_line_id),
                    **common,
                    "delivery_note_id": dn_id,
                    "sales_order_line_id": so_line_id,
                    "ordered_quantity": q,
                    "reserved_quantity": q,
                    "previously_delivered_quantity": ZERO,
                    "current_delivery_quantity": q,
                    "free_quantity": ZERO,
                    "delivered_quantity": q,
                    "remaining_quantity": ZERO,
                    "damaged_quantity": ZERO,
                    "short_shipment_quantity": ZERO,
                    "warehouse_id": warehouse_id,
                    "batch_number": product.batch_number,
                    "batch_id": product.batch_id,
                    "expiry_date": product.expiry,
                    "released_reservation_transaction_id": released,
                    "inventory_transaction_id": dispatched,
                },
            )
            si_line = {
                **self._base(on, si_line_id),
                **common,
                "sales_invoice_id": si_id,
                "source_document_type": "DELIVERY_NOTE",
                "source_document_id": dn_id,
                "source_document_number": dn_number,
                "source_document_line_id": dn_line_id,
                "source_document_line_number": number,
                "delivered_quantity": q,
                "already_invoiced_quantity": ZERO,
                "current_invoice_quantity": q,
                "charges_amount": ZERO,
                "batch_number": product.batch_number,
                "expiry_date": product.expiry,
                "accounting_event_reference": f"{si_number}:{number}",
                "free_quantity": ZERO,
                "cost_amount": cost,
            }
            self.sink.add("sales_invoice_lines", si_line)
            self._line_taxes(
                "sales_invoice_line_taxes",
                "sales_invoice_line_id",
                si_line_id,
                line_money,
                on,
                product.slab,
            )
            if number == 1:
                first_line = {**si_line, **line_money, "quantity": quantity}
        for event_type, account, direction, amount in (
            ("SALES_REVENUE", "Sales Revenue", "CREDIT", totals["subtotal"]),
            ("OUTPUT_TAX", "Output Tax", "CREDIT", totals["tax_total"]),
            ("ACCOUNTS_RECEIVABLE", "Accounts Receivable", "DEBIT", grand),
        ):
            self.sink.add(
                "sales_invoice_accounting_events",
                {
                    **self._base(on),
                    "sales_invoice_id": si_id,
                    "firm_id": ctx.firm_id,
                    "event_type": event_type,
                    "account_name": account,
                    "direction": direction,
                    "amount": amount,
                    "narration": f"Placeholder accounting event for {si_number}",
                },
            )
        self._journal(
            on=on,
            reference=dn_number,
            description=f"Cost of goods issued on {dn_number}",
            source_module="delivery_note",
            source_id=dn_id,
            legs=[
                (
                    "COST_OF_GOODS_SOLD",
                    q2(cost_total),
                    ZERO,
                    f"Cost of goods sold {dn_number}",
                ),
                ("INVENTORY", ZERO, q2(cost_total), f"Stock released on {dn_number}"),
            ],
        )
        ledger_total, ledger_tax = q2(grand), q2(totals["tax_total"])
        self._journal(
            on=on,
            reference=si_number,
            description=f"Sales invoice {si_number}",
            source_module="sales_invoice",
            source_id=si_id,
            legs=[
                ("ACCOUNTS_RECEIVABLE", ledger_total, ZERO, f"Invoice {si_number}"),
                (
                    "SALES_REVENUE",
                    ZERO,
                    ledger_total - ledger_tax,
                    f"Invoice {si_number}",
                ),
                ("OUTPUT_TAX", ZERO, ledger_tax, f"Output tax on {si_number}"),
            ],
        )
        self._receivable(
            customer_index,
            kind="INVOICE",
            on=on,
            amount=ledger_total,
            reference_type="SALES_INVOICE",
            reference_id=si_id,
            reference_number=si_number,
        )
        self._events("SO", "SALES_ORDER", so_id, so_number, on, "DELIVERED")
        self._events("DN", "DELIVERY_NOTE", dn_id, dn_number, on, "DISPATCHED")
        self._events("SI", "SALES_INVOICE", si_id, si_number, on, "APPROVED")
        self.tally["sales_invoices"] += 1
        sale = _Sale(
            si_id,
            si_number,
            on,
            customer_index,
            warehouse_index,
            ledger_total,
            first_line,
            picks[0][0],
        )
        roll = rng.random()
        if roll < self.PAID_SHARE:
            self._due(self._receipts_due, on + timedelta(days=rng.randint(0, 45)), sale)
        elif roll < self.PAID_SHARE + self.RETURN_SHARE:
            self._due(self._returns_due, on + timedelta(days=rng.randint(1, 20)), sale)
        elif roll < self.PAID_SHARE + self.RETURN_SHARE + self.CREDIT_NOTE_SHARE:
            self._due(self._notes_due, on + timedelta(days=rng.randint(1, 20)), sale)

    @staticmethod
    def _due(book: dict[date, list[Any]], on: date, item: object) -> None:
        """File something to happen on a later day."""
        book.setdefault(on, []).append(item)

    # ---- purchases ------------------------------------------------------------------

    def _purchase(self, on: date) -> None:
        """Order, receive and be billed for whatever this day's suppliers owe."""
        weekday = on.weekday()
        for vendor_index, vendor in enumerate(self.vendors):
            if vendor.order_weekday != weekday:
                continue
            for warehouse_index in range(len(self.ctx.warehouse_ids)):
                low = [
                    product_index
                    for product_index in self._vendor_products.get(vendor_index, [])
                    if self.slots[(product_index, warehouse_index)].current
                    < self.REORDER_LEVEL
                ]
                for start in range(0, len(low), 12):
                    self._buy(
                        on, vendor_index, warehouse_index, low[start : start + 12]
                    )

    def _buy(
        self,
        on: date,
        vendor_index: int,
        warehouse_index: int,
        product_indices: list[int],
    ) -> None:
        """Raise one purchase order, its goods receipt and the supplier's bill."""
        ctx, rng = self.ctx, self.rng
        vendor = self.vendors[vendor_index]
        warehouse_id = ctx.warehouse_ids[warehouse_index]
        po_number = self._number("PO", on)
        grn_number = self._number("GRN", on)
        pi_number = self._number("PI", on)
        po_id, grn_id, pi_id = uuid4(), uuid4(), uuid4()
        picks = [(index, rng.randint(*self.REORDER_RANGE)) for index in product_indices]
        money = [
            self._priced(self.products[p], q, self.products[p].cost, ZERO)
            for p, q in picks
        ]
        subtotal = sum((m["taxable"] for m in money), ZERO)
        tax_total = sum((m["tax_amount"] for m in money), ZERO)
        grand = subtotal + tax_total
        quantity_total = Decimal(sum(q for _, q in picks))
        stamp = self._stamp(on)
        header_totals = {
            "subtotal": subtotal,
            "line_discount_total": ZERO,
            "tax_total": tax_total,
            "additional_charges": ZERO,
            "round_off": ZERO,
            "grand_total": grand,
        }
        self.sink.add(
            "purchase_orders",
            {
                **self._base(on, po_id),
                "version": 4,
                "firm_id": ctx.firm_id,
                "branch_id": ctx.branch_id,
                "warehouse_id": warehouse_id,
                "vendor_id": vendor.id,
                "po_number": po_number,
                "purchase_type": "STANDARD_PURCHASE",
                "purchase_date": on,
                "priority": "NORMAL",
                "status": "RECEIVED",
                **header_totals,
                "header_discount_amount": ZERO,
            },
        )
        self.sink.add(
            "goods_receipts",
            {
                **self._base(on, grn_id),
                "version": 3,
                "firm_id": ctx.firm_id,
                "purchase_order_id": po_id,
                "purchase_order_number": po_number,
                "vendor_id": vendor.id,
                "branch_id": ctx.branch_id,
                "warehouse_id": warehouse_id,
                "grn_number": grn_number,
                "receipt_date": on,
                "status": "COMPLETED",
                "total_ordered_quantity": quantity_total,
                "total_previous_received_quantity": ZERO,
                "total_current_receipt_quantity": quantity_total,
                "total_accepted_quantity": quantity_total,
                "total_rejected_quantity": ZERO,
                "total_damaged_quantity": ZERO,
                "total_free_quantity": ZERO,
                **header_totals,
                "completed_at": stamp,
            },
        )
        self.sink.add(
            "purchase_invoices",
            {
                **self._base(on, pi_id),
                "version": 3,
                "firm_id": ctx.firm_id,
                "vendor_id": vendor.id,
                "branch_id": ctx.branch_id,
                "invoice_number": pi_number,
                "invoice_date": on,
                "supplier_invoice_number": f"SUP-{vendor.code}-{grn_number[-6:]}",
                "supplier_invoice_date": on,
                "due_date": on + timedelta(days=45),
                "status": "APPROVED",
                "total_source_quantity": quantity_total,
                "total_already_invoiced_quantity": ZERO,
                "total_current_invoice_quantity": quantity_total,
                **header_totals,
                "approved_at": stamp,
            },
        )
        self.sink.add(
            "purchase_invoice_sources",
            {
                **self._base(on),
                "purchase_invoice_id": pi_id,
                "firm_id": ctx.firm_id,
                "source_document_type": "GOODS_RECEIPT",
                "source_document_id": grn_id,
                "source_document_number": grn_number,
                "source_document_date": on,
                "vendor_id": vendor.id,
                "branch_id": ctx.branch_id,
            },
        )
        cgst_total = sgst_total = ZERO
        for number, ((product_index, quantity), line_money) in enumerate(
            zip(picks, money, strict=True), start=1
        ):
            product = self.products[product_index]
            q = Decimal(quantity)
            po_line_id, grn_line_id, pi_line_id = uuid4(), uuid4(), uuid4()
            amounts = {
                name: line_money[name]
                for name in (
                    "unit_price",
                    "discount_percent",
                    "discount_amount",
                    "gross_amount",
                    "tax_amount",
                    "net_amount",
                )
            }
            received = self._move(
                (product_index, warehouse_index),
                kind="GOODS_RECEIPT",
                reference_type="GOODS_RECEIPT",
                reference_number=grn_number,
                on=on,
                quantity=quantity,
                current_delta=quantity,
                valued=True,
            )
            common = {
                "firm_id": ctx.firm_id,
                "line_number": number,
                "product_id": product.id,
                "description": product.name,
                "conversion_factor": Decimal("1"),
                **amounts,
                "tax_profile_id": product.slab.profile_id,
                "bill_discount_amount": ZERO,
            }
            self.sink.add(
                "purchase_order_lines",
                {
                    **self._base(on, po_line_id),
                    **common,
                    "purchase_order_id": po_id,
                    "purchase_uom_id": ctx.uom_id,
                    "inventory_uom_id": ctx.uom_id,
                    "ordered_quantity": q,
                    "free_quantity": ZERO,
                    "base_quantity": q,
                    "batch_required": product.batch_id is not None,
                    "expiry_required": product.batch_id is not None,
                    "warehouse_id": warehouse_id,
                },
            )
            self.sink.add(
                "goods_receipt_lines",
                {
                    **self._base(on, grn_line_id),
                    **common,
                    "goods_receipt_id": grn_id,
                    "purchase_order_line_id": po_line_id,
                    "purchase_order_line_number": number,
                    "ordered_quantity": q,
                    "previously_received_quantity": ZERO,
                    "current_receipt_quantity": q,
                    "accepted_quantity": q,
                    "rejected_quantity": ZERO,
                    "damaged_quantity": ZERO,
                    "free_quantity": ZERO,
                    "purchase_uom_id": ctx.uom_id,
                    "inventory_uom_id": ctx.uom_id,
                    "warehouse_id": warehouse_id,
                    "batch_number": product.batch_number,
                    "batch_id": product.batch_id,
                    "expiry_date": product.expiry,
                    "inventory_transaction_id": received,
                },
            )
            self.sink.add(
                "purchase_invoice_lines",
                {
                    **self._base(on, pi_line_id),
                    **common,
                    "purchase_invoice_id": pi_id,
                    "source_document_type": "GOODS_RECEIPT",
                    "source_document_id": grn_id,
                    "source_document_number": grn_number,
                    "source_document_line_id": grn_line_id,
                    "source_document_line_number": number,
                    "received_quantity": q,
                    "already_invoiced_quantity": ZERO,
                    "current_invoice_quantity": q,
                    "charges_amount": ZERO,
                    "batch_number": product.batch_number,
                    "expiry_date": product.expiry,
                    "accounting_event_reference": f"{pi_number}:{number}",
                },
            )
            self._line_taxes(
                "purchase_invoice_line_taxes",
                "purchase_invoice_line_id",
                pi_line_id,
                line_money,
                on,
                product.slab,
            )
            cgst_total += line_money["cgst"]
            sgst_total += line_money["sgst"]
        for event_type, account, direction, amount in (
            ("PURCHASE_EXPENSE", "Purchase Expense", "DEBIT", subtotal),
            ("INPUT_TAX", "Input Tax", "DEBIT", tax_total),
            ("ACCOUNTS_PAYABLE", "Accounts Payable", "CREDIT", grand),
        ):
            self.sink.add(
                "purchase_invoice_accounting_events",
                {
                    **self._base(on),
                    "purchase_invoice_id": pi_id,
                    "firm_id": ctx.firm_id,
                    "event_type": event_type,
                    "account_name": account,
                    "direction": direction,
                    "amount": amount,
                    "narration": f"Placeholder accounting event for {pi_number}",
                },
            )
        self._journal(
            on=on,
            reference=grn_number,
            description=f"Goods received on {grn_number}",
            source_module="goods_receipt",
            source_id=grn_id,
            legs=[
                ("INVENTORY", q2(subtotal), ZERO, f"Stock received on {grn_number}"),
                (
                    "GOODS_RECEIVED_NOT_INVOICED",
                    ZERO,
                    q2(subtotal),
                    f"Awaiting supplier invoice for {grn_number}",
                ),
            ],
        )
        ledger_total, ledger_tax = q2(grand), q2(tax_total)
        goods = ledger_total - ledger_tax
        cgst, sgst = q2(cgst_total), q2(sgst_total)
        residual = ledger_tax - cgst - sgst
        if cgst >= sgst:
            cgst += residual
        else:
            sgst += residual
        self._journal(
            on=on,
            reference=pi_number,
            description=f"Purchase invoice {pi_number}",
            source_module="purchase_invoice",
            source_id=pi_id,
            legs=[
                (
                    "GOODS_RECEIVED_NOT_INVOICED",
                    q2(subtotal),
                    ZERO,
                    f"Clearing receipt accrual for {pi_number}",
                ),
                ("INPUT_TAX_CGST", cgst, ZERO, f"Input CGST on {pi_number}"),
                ("INPUT_TAX_SGST", sgst, ZERO, f"Input SGST on {pi_number}"),
                (
                    "ACCOUNTS_PAYABLE",
                    ZERO,
                    ledger_total,
                    f"Supplier invoice {pi_number}",
                ),
                (
                    "PURCHASE_PRICE_VARIANCE",
                    max(goods - q2(subtotal), ZERO),
                    max(q2(subtotal) - goods, ZERO),
                    f"Price variance on {pi_number}",
                ),
            ],
        )
        for key, module, number, document_id in (
            ("PO", "PURCHASE_ORDER", po_number, po_id),
            ("GRN", "GOODS_RECEIPT", grn_number, grn_id),
            ("PI", "PURCHASE_INVOICE", pi_number, pi_id),
        ):
            final = {"PO": "RECEIVED", "GRN": "COMPLETED", "PI": "APPROVED"}[key]
            self._events(key, module, document_id, number, on, final)
        self.tally["purchase_invoices"] += 1
        if rng.random() < self.PAID_SHARE:
            self._due(
                self._payments_due,
                on + timedelta(days=rng.randint(15, 60)),
                _Bill(pi_id, pi_number, vendor_index, ledger_total),
            )

    # ---- money in and out, returns and notes ----------------------------------------

    def _settle(self, on: date) -> None:
        """Record the day's receipts, payments, returns and credit notes."""
        for sale in self._receipts_due.pop(on, []):
            self._settlement(on, sale=sale)
        for bill in self._payments_due.pop(on, []):
            self._settlement(on, bill=bill)
        for sale in self._returns_due.pop(on, []):
            self._sales_return(on, sale)
        for sale in self._notes_due.pop(on, []):
            self._credit_note(on, sale)

    def _settlement(
        self, on: date, *, sale: _Sale | None = None, bill: _Bill | None = None
    ) -> None:
        """Record money settling one invoice in full, posted and allocated."""
        is_receipt = sale is not None
        key = "RC" if is_receipt else "PY"
        number = self._number(key, on)
        settlement_id = uuid4()
        amount = sale.total if sale is not None else bill.total  # type: ignore[union-attr]
        kind = "Receipt" if is_receipt else "Payment"
        bank, party = (
            "BANK",
            "ACCOUNTS_RECEIVABLE" if is_receipt else "ACCOUNTS_PAYABLE",
        )
        legs: list[tuple[str | UUID, Decimal, Decimal, str]] = (
            [
                (bank, amount, ZERO, f"{kind} {number}"),
                (party, ZERO, amount, f"{kind} {number}"),
            ]
            if is_receipt
            else [
                (party, amount, ZERO, f"{kind} {number}"),
                (bank, ZERO, amount, f"{kind} {number}"),
            ]
        )
        journal = self._journal(
            on=on,
            reference=number,
            description=f"{kind} {number}",
            source_module="settlements",
            source_id=settlement_id,
            legs=legs,
        )
        self.sink.add(
            "settlements",
            {
                **self._base(on, settlement_id),
                "firm_id": self.ctx.firm_id,
                "direction": "RECEIPT" if is_receipt else "PAYMENT",
                "customer_id": self.customers[sale.customer_index].id if sale else None,
                "vendor_id": self.vendors[bill.vendor_index].id if bill else None,
                "settlement_number": number,
                "settlement_date": on,
                "amount": amount,
                "allocated_amount": amount,
                "unallocated_amount": ZERO,
                "method": "BANK",
                "ledger_account_id": self.ctx.accounts["BANK"],
                "status": "POSTED",
                "journal_entry_id": journal,
            },
        )
        self.sink.add(
            "settlement_allocations",
            {
                **self._base(on),
                "firm_id": self.ctx.firm_id,
                "settlement_id": settlement_id,
                "sales_invoice_id": sale.invoice_id if sale else None,
                "purchase_invoice_id": bill.invoice_id if bill else None,
                "amount": amount,
                "allocated_on": on,
            },
        )
        if sale is not None:
            self._receivable(
                sale.customer_index,
                kind="RECEIPT",
                on=on,
                amount=amount,
                reference_type="settlement",
                reference_id=settlement_id,
                reference_number=number,
            )
        self._events(
            key,
            "RECEIPT" if is_receipt else "PAYMENT",
            settlement_id,
            number,
            on,
            "POSTED",
        )
        self.tally["receipts" if is_receipt else "payments"] += 1

    def _sales_return(self, on: date, sale: _Sale) -> None:
        """Take back part of an unpaid invoice's first line into stock."""
        ctx = self.ctx
        line = sale.first_line
        product = self.products[sale.first_line_product]
        quantity = max(1, int(line["quantity"]) // 2)
        money = self._priced(
            product, quantity, line["unit_price"], line["discount_percent"]
        )
        number = self._number("SR", on)
        return_id, line_id = uuid4(), uuid4()
        movement = self._move(
            (sale.first_line_product, sale.warehouse_index),
            kind="SALES_RETURN",
            reference_type="SALES_RETURN",
            reference_number=number,
            on=on,
            quantity=quantity,
            current_delta=quantity,
            valued=True,
        )
        cost = q2(q4(product.cost * quantity))
        ledger_total, ledger_tax = q2(money["net_amount"]), q2(money["tax_amount"])
        journal = self._journal(
            on=on,
            reference=number,
            description=f"Sales return {number}",
            source_module="sales_return",
            source_id=return_id,
            legs=[
                (
                    "SALES_RETURNS",
                    ledger_total - ledger_tax,
                    ZERO,
                    f"Sales return {number}",
                ),
                ("OUTPUT_TAX", ledger_tax, ZERO, f"Output tax reversed on {number}"),
                (
                    "ACCOUNTS_RECEIVABLE",
                    ZERO,
                    ledger_total,
                    f"Credit for sales return {number}",
                ),
            ],
        )
        cost_journal = self._journal(
            on=on,
            reference=f"{number}-COST",
            description=f"Cost of goods returned on {number}",
            source_module="sales_return",
            source_id=return_id,
            legs=[
                ("INVENTORY", cost, ZERO, f"Stock returned on {number}"),
                (
                    "COST_OF_GOODS_SOLD",
                    ZERO,
                    cost,
                    f"Cost of goods sold reversed {number}",
                ),
            ],
        )
        q = Decimal(quantity)
        stamp = self._stamp(on)
        self.sink.add(
            "sales_returns",
            {
                **self._base(on, return_id),
                "version": 4,
                "firm_id": ctx.firm_id,
                "customer_id": self.customers[sale.customer_index].id,
                "branch_id": ctx.branch_id,
                "warehouse_id": ctx.warehouse_ids[sale.warehouse_index],
                "return_number": number,
                "return_date": on,
                "reference_invoice_number": sale.number,
                "status": "COMPLETED",
                "total_source_quantity": Decimal(line["quantity"]),
                "total_already_returned_quantity": ZERO,
                "total_current_return_quantity": q,
                "total_restock_quantity": q,
                "line_discount_total": money["discount_amount"],
                "subtotal": money["taxable"],
                "tax_total": money["tax_amount"],
                "additional_charges": ZERO,
                "round_off": ZERO,
                "grand_total": money["net_amount"],
                "journal_entry_id": journal,
                "cost_journal_entry_id": cost_journal,
                "approved_at": stamp,
                "completed_at": stamp,
            },
        )
        self.sink.add(
            "sales_return_sources",
            {
                **self._base(on),
                "sales_return_id": return_id,
                "firm_id": ctx.firm_id,
                "source_document_type": "SALES_INVOICE",
                "source_document_id": sale.invoice_id,
                "source_document_number": sale.number,
                "source_document_date": sale.on,
                "customer_id": self.customers[sale.customer_index].id,
                "branch_id": ctx.branch_id,
            },
        )
        self.sink.add(
            "sales_return_lines",
            {
                **self._base(on, line_id),
                "sales_return_id": return_id,
                "firm_id": ctx.firm_id,
                "line_number": 1,
                "source_document_type": "SALES_INVOICE",
                "source_document_id": sale.invoice_id,
                "source_document_number": sale.number,
                "source_document_line_id": line["id"],
                "source_document_line_number": 1,
                "product_id": product.id,
                "dispatched_quantity": Decimal(line["quantity"]),
                "already_returned_quantity": ZERO,
                "current_return_quantity": q,
                "restock_quantity": q,
                "damaged_quantity": ZERO,
                "scrap_quantity": ZERO,
                "unit_price": money["unit_price"],
                "discount_percent": money["discount_percent"],
                "discount_amount": money["discount_amount"],
                "charges_amount": ZERO,
                "gross_amount": money["gross_amount"],
                "tax_profile_id": product.slab.profile_id,
                "tax_amount": money["tax_amount"],
                "net_amount": money["net_amount"],
                "conversion_factor": Decimal("1"),
                "warehouse_id": ctx.warehouse_ids[sale.warehouse_index],
                "batch_number": product.batch_number,
                "batch_id": product.batch_id,
                "expiry_date": product.expiry,
                "inventory_transaction_id": movement,
                "bill_discount_amount": ZERO,
            },
        )
        self._line_taxes(
            "sales_return_line_taxes",
            "sales_return_line_id",
            line_id,
            money,
            on,
            product.slab,
        )
        self._receivable(
            sale.customer_index,
            kind="CREDIT_NOTE",
            on=on,
            amount=ledger_total,
            reference_type="SALES_RETURN",
            reference_id=return_id,
            reference_number=number,
            journal_entry_id=journal,
        )
        self._events("SR", "SALES_RETURN", return_id, number, on, "COMPLETED")
        self.tally["sales_returns"] += 1

    def _credit_note(self, on: date, sale: _Sale) -> None:
        """Credit a tenth of an unpaid invoice's first line as a rate difference."""
        ctx = self.ctx
        line = sale.first_line
        product = self.products[sale.first_line_product]
        taxable = q2(line["taxable"] / 10)
        tax = q2(taxable * product.slab.rate / 100)
        total = taxable + tax
        number = self._number("CN", on)
        note_id = uuid4()
        journal = self._journal(
            on=on,
            reference=number,
            description=f"Credit note {number}",
            source_module="credit_note",
            source_id=note_id,
            legs=[
                ("SALES_RETURNS", taxable, ZERO, f"Credit note {number}"),
                ("OUTPUT_TAX", tax, ZERO, f"Output tax reversed on {number}"),
                ("ACCOUNTS_RECEIVABLE", ZERO, total, f"Credit note {number}"),
            ],
        )
        receivable = self._receivable(
            sale.customer_index,
            kind="CREDIT_NOTE",
            on=on,
            amount=total,
            reference_type="CREDIT_NOTE",
            reference_id=note_id,
            reference_number=number,
            journal_entry_id=journal,
        )
        self.sink.add(
            "credit_notes",
            {
                **self._base(on, note_id),
                "version": 3,
                "firm_id": ctx.firm_id,
                "customer_id": self.customers[sale.customer_index].id,
                "branch_id": ctx.branch_id,
                "sales_invoice_id": sale.invoice_id,
                "credit_note_number": number,
                "credit_note_date": on,
                "reason": "RATE_DIFFERENCE",
                "status": "APPROVED",
                "taxable_amount": taxable,
                "tax_amount": tax,
                "total_amount": total,
                "journal_entry_id": journal,
                "receivable_transaction_id": receivable,
            },
        )
        self.sink.add(
            "credit_note_lines",
            {
                **self._base(on),
                "credit_note_id": note_id,
                "firm_id": ctx.firm_id,
                "line_number": 1,
                "sales_invoice_line_id": line["id"],
                "product_id": product.id,
                "quantity": ZERO,
                "taxable_amount": taxable,
                "tax_amount": tax,
                "total_amount": total,
                "tax_profile_id": product.slab.profile_id,
                "tax_rate_percent": product.slab.rate,
            },
        )
        self._events("CN", "CREDIT_NOTE", note_id, number, on, "APPROVED")
        self.tally["credit_notes"] += 1

    # ---- the maintained balances ----------------------------------------------------

    def ledger_balance_rows(self) -> Iterator[Row]:
        """Yield ``ledger_balances`` as the journal engine would have left them.

        A row exists for each account in each period it was posted in; its
        opening is the previous row's closing, and the closing moves by the
        period's movement on the account's normal side.
        """
        periods = sorted(self.ctx.periods, key=lambda period: period.starts_on)
        accounts = sorted({account for account, _ in self.ledger}, key=str)
        for account in accounts:
            debit_side = self.ctx.account_types[account] in {"ASSET", "EXPENSE"}
            running = ZERO
            for period in periods:
                totals = self.ledger.get((account, period.id))
                if totals is None:
                    continue
                debit, credit = totals
                movement = debit - credit if debit_side else credit - debit
                yield {
                    **self._base(period.ends_on),
                    "firm_id": self.ctx.firm_id,
                    "ledger_account_id": account,
                    "accounting_period_id": period.id,
                    "opening_balance": running,
                    "period_debit": debit,
                    "period_credit": credit,
                    "closing_balance": running + movement,
                }
                running += movement

    def valuation_rows(self) -> Iterator[Row]:
        """Yield ``product_valuations``: quantity on hand at the one cost."""
        on_hand: Counter[int] = Counter()
        for (product_index, _), slot in self.slots.items():
            on_hand[product_index] += slot.current
        for index, product in enumerate(self.products):
            quantity = Decimal(on_hand[index])
            yield {
                **self._base(self.ctx.end),
                "firm_id": self.ctx.firm_id,
                "product_id": product.id,
                "costing_method": "WEIGHTED_AVERAGE",
                "quantity_on_hand": quantity,
                "average_cost": product.cost,
                "total_value": q4(quantity * product.cost),
            }

    def finish(self, connection: Connection) -> None:
        """Write the maintained balances and settle the stock and customer rows."""
        for row in self.ledger_balance_rows():
            self.sink.add("ledger_balances", row)
        for row in self.valuation_rows():
            self.sink.add("product_valuations", row)
        self.sink.flush()
        inventories = Base.metadata.tables["inventories"]
        stock = [
            {
                "b_id": slot.inventory_id,
                "b_current": Decimal(slot.current),
                "b_reserved": Decimal(slot.reserved),
                "b_available": Decimal(slot.current - slot.reserved),
                "b_last": slot.last,
            }
            for slot in self.slots.values()
        ]
        statement = (
            update(inventories)
            .where(inventories.c.id == bindparam("b_id"))
            .values(
                current_quantity=bindparam("b_current"),
                reserved_quantity=bindparam("b_reserved"),
                available_quantity=bindparam("b_available"),
                display_quantity=bindparam("b_current"),
                last_transaction_at=bindparam("b_last"),
            )
        )
        for start in range(0, len(stock), BATCH_SIZE):
            connection.execute(statement, stock[start : start + BATCH_SIZE])
        customers = Base.metadata.tables["customers"]
        connection.execute(
            update(customers)
            .where(customers.c.id == bindparam("b_id"))
            .values(
                current_outstanding=bindparam("b_outstanding"),
                unapplied_advance_balance=bindparam("b_advance"),
            ),
            [
                {
                    "b_id": customer.id,
                    "b_outstanding": customer.outstanding,
                    "b_advance": customer.advance,
                }
                for customer in self.customers
            ],
        )
        connection.commit()


def _gstin(seed_code: str, seed: int) -> str:
    """Return a GSTIN-shaped number in the firm's state (29)."""
    body = "".join(c for c in seed_code.upper() if c.isalnum()).ljust(10, "0")[:10]
    return f"{STATE_CODE}{body}{seed % 9 + 1}Z5"


# ---------------------------------------------------------------------------
# PostgreSQL: the firm, its storage, its set-up
# ---------------------------------------------------------------------------


def _say(message: str) -> None:
    """Print a progress line straight away."""
    print(message, flush=True)


def setup_firm(reset: bool, password: str) -> tuple[Any, Any, FirmContext]:
    """Create or rebuild PERF01 through the services and return its context.

    Returns the store's ``DatabaseManager``, the tenant schema name, and the
    context. Everything here is the real set-up path: ``FirmService.create``
    and ``provision``, the identity service for the admin, the GST template,
    ``FirmReadinessService.open_books`` for each year, the branch service,
    and each document module's own series bootstrap.
    """
    from sqlalchemy import select

    from app.api.dependencies.settings import get_settings
    from app.branches.schemas import BranchCreate, WarehouseCreate
    from app.branches.services.branch_warehouse_service import (
        BranchWarehouseService,
    )
    from app.business.models import BusinessProfile, FirmBusinessProfile
    from app.core.database.engine import DatabaseManager
    from app.core.tenancy import (
        DeploymentMode,
        FirmConnectionResolver,
        FirmSchemaResolver,
        MultiTenantDatabaseProvider,
        TenantContext,
        TenantStorageLifecycleService,
    )
    from app.core.utils.dates import utc_now
    from app.firms.models import Firm
    from app.firms.schemas import FirmCreate
    from app.firms.services.firm_service import FirmService
    from app.firms.services.readiness import FirmReadinessService
    from app.identity.models import Role, User
    from app.identity.schemas.api import UserCreate, UserFirmAssignment
    from app.identity.services.identity_service import IdentityService
    from app.tax.services.gst_template import apply_india_gst_template

    settings = get_settings()
    platform = DatabaseManager.from_settings(settings)
    lifecycle = TenantStorageLifecycleService(
        platform, settings.tenancy.connection_profiles
    )
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    today = utc_now().date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=TRADING_DAYS - 1)
    with platform.sessions(schema=platform.config.default_schema).session() as session:
        actor = session.scalar(
            select(User).where(User.email == "platform-admin@agency.local")
        )
        if actor is None:
            raise SystemExit("platform-admin@agency.local is needed to create PERF01.")
        actor_id = actor.id
        service = FirmService(
            session, storage_lifecycle=lifecycle, tenancy_settings=settings.tenancy
        )
        firm = session.scalar(
            select(Firm).where(Firm.code == FIRM_CODE, Firm.is_deleted.is_(False))
        )
        if firm is None:
            firm = service.create(
                FirmCreate(
                    name=FIRM_NAME,
                    code=FIRM_CODE,
                    address_line1="Performance Park",
                    city="Bengaluru",
                    postal_code="560001",
                    country="IN",
                    state=STATE_NAME,
                    contact_name="PERF01 Admin Desk",
                    contact_email="hello@perf01.agency.local",
                    contact_phone="+919900056056",
                    currency_code="INR",
                    gst_number=_gstin("PERF01", 1),
                    financial_year_start=fy_start(start),
                    deployment_mode=DeploymentMode.SCHEMA,
                    database_name=settings.tenancy.shared_database_name,
                    schema_name=SCHEMA_NAME,
                    database_type="postgresql",
                    notes="Volume test firm (backlog 56 C, step 5).",
                ),
                actor_id=actor_id,
            )
            _say(f"created firm {FIRM_CODE}")
        mapping = next(
            row for row in firm.storage_mappings if row.is_active and not row.is_deleted
        )
        if mapping.schema_name != SCHEMA_NAME:
            raise SystemExit(
                f"{FIRM_CODE} is routed to schema {mapping.schema_name!r}, not "
                f"{SCHEMA_NAME!r}; refusing to touch it."
            )
        if reset:
            with platform.engine.begin() as connection:
                connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{SCHEMA_NAME}" CASCADE')
                )
            _say(f"dropped schema {SCHEMA_NAME}")
            lifecycle.provision_new_firm(firm)
            mapping.provisioned_at = utc_now()
            session.commit()
        else:
            service.provision(firm.id, actor_id)
        _say(f"storage ready: schema {SCHEMA_NAME}")
        identity = IdentityService(session, settings)
        admin = session.scalar(
            select(User).where(User.email == ADMIN_EMAIL, User.is_deleted.is_(False))
        )
        if admin is None:
            admin = identity.create_user(
                UserCreate(
                    email=ADMIN_EMAIL,
                    full_name="PERF01 Admin",
                    password=password,
                    is_active=True,
                    force_password_change=False,
                ),
                actor_id=actor_id,
                firm_scope=firm.id,
            )
        identity.set_user_firms(
            admin.id,
            [UserFirmAssignment(firm_id=firm.id, is_primary=True, is_active=True)],
            actor_id,
        )
        role = session.scalar(select(Role).where(Role.code == "FIRM_ADMIN"))
        if role is None:
            raise SystemExit("The FIRM_ADMIN role is missing.")
        identity.set_user_roles(admin.id, [role.id], actor_id, firm_scope=firm.id)
        tenant = TenantContext(
            firm_id=firm.id,
            deployment_mode=DeploymentMode.SCHEMA,
            database_name=mapping.database_name
            or settings.tenancy.shared_database_name,
            schema_name=SCHEMA_NAME,
            database_type=mapping.database_type,
        )
        manager = provider.manager_for(tenant)
        schema = provider.schema_for(tenant)
        with manager.sessions(schema=schema).session() as store:
            if store.execute(text("select count(*) from sales_invoices")).scalar():
                raise SystemExit(
                    f"{FIRM_CODE} already holds trading; pass --reset to rebuild it."
                )
            profile = store.scalar(
                select(BusinessProfile).where(BusinessProfile.code == "WHOLESALE")
            )
            if (
                profile is not None
                and store.scalar(
                    select(FirmBusinessProfile.id).where(
                        FirmBusinessProfile.firm_id == firm.id
                    )
                )
                is None
            ):
                store.add(
                    FirmBusinessProfile(
                        firm_id=firm.id,
                        business_profile_id=profile.id,
                        is_active=True,
                        effective_from=utc_now(),
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            apply_india_gst_template(store, firm_id=firm.id, actor_id=actor_id)
            store.commit()
            readiness = FirmReadinessService(session)
            year = fy_start(start)
            while year <= end:
                readiness.open_books(firm, store, actor_id, year_starts_on=year)
                year = date(year.year + 1, 4, 1)
            branches = BranchWarehouseService(store)
            branch = branches.create_branch(
                BranchCreate(
                    code="HO",
                    name="Head Office",
                    display_name="Head Office",
                    currency_code="INR",
                    is_default=True,
                ),
                firm_id=firm.id,
                actor_id=actor_id,
            )
            warehouses = [
                branches.create_warehouse(
                    WarehouseCreate(
                        branch_id=branch.id,
                        code=code,
                        name=name,
                        display_name=name,
                        is_default=code == "MAIN",
                    ),
                    firm_id=firm.id,
                    actor_id=actor_id,
                )
                for code, name in (
                    ("MAIN", "Main Warehouse"),
                    ("NORTH", "North Depot"),
                    ("SOUTH", "South Depot"),
                )
            ]
            store.commit()
            ctx = read_context(
                store,
                firm_id=firm.id,
                actor_id=actor_id,
                branch_id=branch.id,
                warehouse_ids=[row.id for row in warehouses],
                business_profile_id=profile.id if profile is not None else None,
                start=start,
                end=end,
            )
            store.commit()
        session.commit()
    return manager, schema, ctx


#: The document type spec of each series, imported where the service keeps it.
def _series_specs() -> dict[str, Any]:
    """Return each series key's ``DocumentTypeSpec``, from its own service."""
    from app.credit_note.services.credit_note_service import CreditNoteService
    from app.delivery_note.services.delivery_note_service import DeliveryNoteService
    from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
    from app.purchase.services.purchase_service import PurchaseService
    from app.purchase_invoice.services.purchase_invoice_service import (
        PurchaseInvoiceService,
    )
    from app.sales_invoice.services.sales_invoice_service import SalesInvoiceService
    from app.sales_order.services.sales_order_service import SalesOrderService
    from app.sales_return.services.sales_return_service import SalesReturnService
    from app.settlements.services.settlement_service import (
        PaymentService,
        ReceiptService,
    )

    return {
        "SO": SalesOrderService.DOCUMENT,
        "DN": DeliveryNoteService.DOCUMENT,
        "SI": SalesInvoiceService.DOCUMENT,
        "PO": PurchaseService.DOCUMENT,
        "GRN": GoodsReceiptService.DOCUMENT,
        "PI": PurchaseInvoiceService.DOCUMENT,
        "SR": SalesReturnService.DOCUMENT,
        "CN": CreditNoteService.DOCUMENT,
        "RC": ReceiptService.DOCUMENT,
        "PY": PaymentService.DOCUMENT,
    }


def read_context(
    store: Session,
    *,
    firm_id: UUID,
    actor_id: UUID,
    branch_id: UUID,
    warehouse_ids: list[UUID],
    business_profile_id: UUID | None,
    start: date,
    end: date,
) -> FirmContext:
    """Read every id the trading needs, and bootstrap each document series.

    Each series is set up by the document framework exactly as the module's
    first document would set it up, and one number is reserved per financial
    year -- which yields the real prefix (``DN-PERF01-HO-2025-2026-``) and
    creates the counter ``finish_numbering`` later moves on.
    """
    from sqlalchemy import select

    from app.document_framework.services.transactional_document_service import (
        TransactionalDocumentService,
    )
    from app.finance.models import AccountingPeriod, FirmControlAccount, LedgerAccount
    from app.finance.services.document_posting import DocumentPostingService
    from app.tax.models import TaxComponent, TaxProfile
    from app.uom.models import Uom

    class _Series(TransactionalDocumentService):
        """A module's numbering, without the module."""

        def __init__(self, session: Session, spec: DocumentTypeSpec) -> None:
            """Bind to the session and the spec of the module being copied."""
            super().__init__(session)
            self.DOCUMENT = spec

    accounts = {
        purpose: account
        for purpose, account in store.execute(
            select(
                FirmControlAccount.purpose, FirmControlAccount.ledger_account_id
            ).where(
                FirmControlAccount.firm_id == firm_id,
                FirmControlAccount.is_deleted.is_(False),
            )
        )
    }
    account_types = {
        account_id: kind
        for account_id, kind in store.execute(
            select(LedgerAccount.id, LedgerAccount.account_type).where(
                LedgerAccount.firm_id == firm_id
            )
        )
    }
    periods = [
        Period(row.id, row.starts_on, row.ends_on)
        for row in store.scalars(
            select(AccountingPeriod).where(
                AccountingPeriod.firm_id == firm_id,
                AccountingPeriod.is_deleted.is_(False),
            )
        )
    ]
    posting = DocumentPostingService(store).context_for(firm_id, end)
    components = {
        row.code: row.id
        for row in store.scalars(
            select(TaxComponent).where(TaxComponent.firm_id == firm_id)
        )
    }
    profiles = {
        row.code: row.id
        for row in store.scalars(
            select(TaxProfile).where(TaxProfile.firm_id == firm_id)
        )
    }
    slabs = [
        TaxSlab(
            Decimal(rate),
            profiles[f"GST_{rate}_LOCAL"],
            f"GST_{rate}_LOCAL",
            components["CGST"],
            components["SGST"],
        )
        for rate in (5, 12, 18, 18)
    ]
    uom_id = store.scalar(select(Uom.id).where(Uom.code == "UNIT"))
    prefixes: dict[str, dict[str, str]] = {}
    padding: dict[str, int] = {}
    document_types: dict[str, UUID] = {}
    years: list[date] = []
    year = fy_start(start)
    while year <= end:
        years.append(max(year, start))
        year = date(year.year + 1, 4, 1)
    for key, spec in _series_specs().items():
        series = _Series(store, spec)
        document_type, rule = series._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        branch_code, company_code = series._scope_codes(
            firm_id=firm_id, branch_id=branch_id
        )
        document_types[key] = document_type.id
        padding[key] = rule.sequence_padding
        prefixes[key] = {}
        for first_day in years:
            number = series._documents.reserve_number(
                rule.id,
                firm_id=firm_id,
                financial_year_label=fy_label(first_day),
                branch_code=branch_code,
                company_code=company_code,
                document_date=first_day,
                actor_id=actor_id,
            )
            if not number.endswith("1".rjust(rule.sequence_padding, "0")):
                raise SystemExit(f"Series {key} did not start at 1: {number}.")
            prefixes[key][fy_label(first_day)] = number[: -rule.sequence_padding]
    return FirmContext(
        firm_id=firm_id,
        actor_id=actor_id,
        branch_id=branch_id,
        warehouse_ids=warehouse_ids,
        business_profile_id=business_profile_id,
        accounts=accounts,
        account_types=account_types,
        journal_type_id=posting.journal_type_id,
        voucher_type_id=posting.voucher_type_id,
        periods=periods,
        slabs=slabs,
        prefixes=prefixes,
        padding=padding,
        document_types=document_types,
        uom_id=uom_id,
        start=start,
        end=end,
    )


def finish_numbering(connection: Connection, simulator: TradeSimulator) -> None:
    """Move every series counter past the last number the trading used.

    ``read_context`` reserved number 1 of each series and year, so each
    counter exists and reads 2; it is set to one past the count here, and the
    rule's own figure kept in step as ``reserve_number`` keeps it.
    """
    for (key, label), used in simulator.counters.items():
        connection.execute(
            text(
                """
                update document_number_sequences s
                   set next_sequence = :next
                  from document_numbering_rules r
                 where r.id = s.numbering_rule_id
                   and r.document_type_id = :type_id
                   and s.is_deleted = false
                   and s.scope_signature like :label
                """
            ),
            {
                "next": used + 1,
                "type_id": simulator.ctx.document_types[key],
                "label": f"{label}%",
            },
        )
    connection.commit()


def _print_counts(sink: Sink, elapsed: float) -> None:
    """Print the rows written per table, largest first."""
    _say(f"\nRows written in {elapsed / 60:,.1f} minutes:")
    for table, count in sorted(sink.counts.items(), key=lambda item: -item[1]):
        _say(f"  {table:<40} {count:>12,}")
    _say(f"  {'total':<40} {sum(sink.counts.values()):>12,}")


def main() -> int:
    """Build PERF01 and its two years of trading."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Volume relative to the target distributor (default 1.0).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=f"Drop and rebuild the {SCHEMA_NAME} schema first.",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("PERF01_PASSWORD", DEFAULT_PASSWORD),
        help=f"Password for {ADMIN_EMAIL} when it is created.",
    )
    args = parser.parse_args()
    started = time.monotonic()
    manager, schema, ctx = setup_firm(args.reset, args.password)
    _say(
        f"set-up done in {time.monotonic() - started:,.0f}s; trading "
        f"{ctx.start} to {ctx.end} at scale {args.scale}"
    )
    # One connection for the whole run, its search path set once: a session
    # hands its connection back to the pool at each commit, and the next one
    # it takes may not be looking at this schema.
    with manager.engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        sink = Sink(connection, schema=schema, use_copy=True)
        simulator = TradeSimulator(ctx, sink, Scale(args.scale))
        simulator.run(progress=_say)
        simulator.finish(connection)
        finish_numbering(connection, simulator)
        # Fresh statistics, as autovacuum would give them in time: a plan made
        # before it does would time the planner's ignorance, not the query.
        for table in sorted(sink.counts):
            connection.execute(text(f'ANALYZE "{schema}"."{table}"'))
        connection.commit()
    _print_counts(sink, time.monotonic() - started)
    _say(f"tally: {dict(simulator.tally)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
