"""Generate several years of transactional history for every firm.

``generate_sample_data.py`` builds the master data -- firms, users, products,
tax framework, territories -- and a handful of documents dated in the current
month. That is enough to open a screen and see something, and not enough to
test anything that depends on *history*: an ageing report with nothing older
than a fortnight, a trial balance covering one month, a customer whose whole
trading record is three rows.

This fills that in. For every firm in the registry, across the financial years
you ask for, it drives real documents through the real services -- purchase
order, goods receipt, purchase invoice, sales order, delivery note, sales
invoice -- so stock moves, valuations shift, receivables build and the general
ledger balances, exactly as they would in use.

It goes through the services and not the tables on purpose. Anything that would
be refused in the application is refused here too, which means the data it
produces is data the application could actually have produced. It also means
this script is a fairly brutal integration test: a defect in any of the seven
transactional modules stops it.

Three things it is careful about:

* **Every store.** Firms are enumerated from the registry and resolved through
  the tenancy provider, so SHARED, SCHEMA and DATABASE firms are all covered.
  A hardcoded list would silently miss the dedicated ones.
* **The finance calendar.** Posting needs an *open* accounting period covering
  the document's date, so each historical year gets its financial year and
  twelve periods before any document dated in it is written.
* **Business profile features.** Feature gating is enforced, so a firm whose
  profile lacks EXPIRY_TRACKING must not be given batches with expiry dates.
  The generator reads each firm's enabled features and shapes its documents to
  them rather than assuming.

Usage::

    uv run python scripts/generate_transaction_history.py --dry-run
    uv run python scripts/generate_transaction_history.py --years 2 --yes

``--dry-run`` reports what it would create, per firm and per year, and writes
nothing.
"""

from __future__ import annotations

import argparse
import sys
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Inspector
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.business.gating import resolve_capabilities
from app.commission.schemas import (
    CommissionBasisEnum,
    CommissionRuleCreate,
    CommissionSlabWrite,
)
from app.commission.schemas.payout import (
    CommissionPayoutAccrue,
    CommissionPayoutPay,
)
from app.commission.services import CommissionPayoutService, CommissionService
from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager, EngineFactory
from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    ValidationError,
)
from app.core.tenancy import (
    DeploymentMode,
    FirmConnectionResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantContext,
)
from app.core.utils.dates import utc_now
from app.credit_note.schemas import (
    CreditNoteCreate,
    CreditNoteLineWrite,
    CreditNoteReasonEnum,
)
from app.credit_note.services import CreditNoteService
from app.customers.models import Customer
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.finance.models import FinancialYear
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm, FirmStorageMapping
from app.goods_receipt.models import GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate, GoodsReceiptLineWrite
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.models import InventoryTransaction
from app.products.models import Product
from app.promotions.models import (
    Promotion,
    PromotionAction,
    PromotionCondition,
)
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate, PurchaseOrderStatus
from app.purchase.services import PurchaseService
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
    PurchaseInvoiceSourceWrite,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services import PurchaseReturnService
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceResponse,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services import SalesReturnService
from app.sales_targets.schemas import (
    SalesTargetBasis,
    SalesTargetPeriod,
    SalesTargetWrite,
)
from app.sales_targets.services import SalesTargetService
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import ReceiptService
from app.vendors.models import Vendor

ACTOR = UUID("00000000-0000-0000-0000-0000000000aa")

#: Quantity and price patterns, cycled so no two months look identical and the
#: reports have something to actually rank.
PURCHASE_SHAPES: tuple[tuple[str, str], ...] = (
    ("120", "100"),
    ("80", "112.50"),
    ("200", "96.25"),
    ("60", "134"),
    ("150", "88"),
)
SALE_SHAPES: tuple[tuple[str, str], ...] = (
    ("30", "165"),
    ("18", "180"),
    ("45", "158.75"),
    ("12", "195"),
    ("25", "172.40"),
)


#: Transactional tables, in an order that respects the foreign keys between
#: them. Masters are deliberately absent: this clears trading history, never
#: the customers, products or vendors it trades with.
RESET_ORDER: tuple[str, ...] = (
    # Sales returns first: they hang off the delivery notes and invoices
    # below, and leaving them behind while the numbering counters are cleared
    # makes the next return collide with a number the surviving rows already
    # hold -- which is exactly how a fresh WHOLE01 answered 409 to the first
    # return raised against it.
    # Commission payouts before anything else: they reference the journal
    # entries the history clears, and a payout that outlives its journal is a
    # debt the books can no longer explain.
    "commission_payouts",
    # Targets go with the history and not with the masters, unlike commission
    # rules. A rule is an arrangement that outlives any particular year; a
    # seeded target is *derived from* what was sold, so leaving it behind
    # while the trading is rebuilt leaves a number measured against sales that
    # no longer exist -- and the met-or-missed story it exists to show becomes
    # arbitrary.
    "sales_targets",
    "sales_quotation_attachments",
    "sales_quotation_notes",
    "sales_quotation_lines",
    "sales_quotations",
    "credit_note_lines",
    "credit_notes",
    "sales_return_attachments",
    "sales_return_notes",
    "sales_return_lines",
    "sales_return_sources",
    "sales_returns",
    # Settlements next: their allocations reference the invoices below, so
    # clearing history without them fails on a foreign key. They arrived with
    # the receipts and payments module and this list did not know about them.
    "settlement_allocations",
    "settlements",
    "sales_invoice_accounting_events",
    "sales_invoice_attachments",
    "sales_invoice_notes",
    "sales_invoice_lines",
    "sales_invoices",
    "delivery_note_attachments",
    "delivery_note_notes",
    "delivery_note_lines",
    "delivery_notes",
    "sales_order_attachments",
    "sales_order_notes",
    "sales_order_lines",
    "sales_orders",
    "purchase_return_accounting_events",
    "purchase_return_attachments",
    "purchase_return_notes",
    "purchase_return_lines",
    "purchase_returns",
    "purchase_invoice_accounting_events",
    "purchase_invoice_attachments",
    "purchase_invoice_notes",
    "purchase_invoice_lines",
    "purchase_invoices",
    "goods_receipt_attachments",
    "goods_receipt_notes",
    "goods_receipt_lines",
    "goods_receipts",
    "purchase_attachments",
    "purchase_notes",
    "purchase_order_lines",
    "purchase_orders",
    "gl_postings",
    "journal_lines",
    "journal_entries",
    "ledger_balances",
    "customer_receivable_transactions",
    "opening_stock_batches",
    "stock_ledger_entries",
    "inventory_transactions",
    "inventories",
    "product_valuations",
    "document_lifecycle_events",
    "document_number_sequences",
    # The offers and what they gave away. Children first: a promotion's
    # conditions and actions reference it, and a superseded revision
    # references the one it replaced.
    #
    # `promotion_redemptions` and `promotion_coupons` arrived with the coupon
    # work and this list did not know about them, so `--reset` failed outright
    # on any firm whose documents had claimed an offer -- the same shape as
    # the settlements omission recorded above, and found the same way.
    "promotion_redemptions",
    "promotion_coupons",
    "promotion_execution_logs",
    "promotion_actions",
    "promotion_conditions",
    "promotions",
)


#: Child tables with no ``firm_id`` of their own, and the parent that has
#: one. ``opening_stock_lines`` points at the inventory transaction that
#: created it, so it has to go before the transactions or the delete trips its
#: foreign key -- and it cannot be found by firm without going through its
#: batch.
CHILD_TABLES: tuple[tuple[str, str, str], ...] = (
    ("opening_stock_lines", "opening_stock_batch_id", "opening_stock_batches"),
)


def _assert_reset_tables_exist(inspector: Inspector) -> None:
    """Refuse to reset when a configured table name is not a real table.

    The loops below used to skip a name the store did not have, silently. Three
    names were wrong and nobody could tell: ``purchase_order_attachments`` and
    ``purchase_order_notes`` (really ``purchase_attachments`` /
    ``purchase_notes``, and harmless because they cascade from the order) and
    ``inventory_records`` -- really ``inventories``, and not harmless at all.

    That one meant every regeneration deleted the movements, the ledger and the
    valuation while leaving the stock projection standing, so a firm's on-hand
    quantity grew by a run's worth each time and no ledger entry explained the
    balance. One store had 4,547 units on hand with 700 accounted for.

    A wrong name is a bug in this file, not a property of the database, so it
    stops the run rather than quietly doing less than it says.
    """
    configured = {table for table in RESET_ORDER}
    configured.update(table for table, _, _ in CHILD_TABLES)
    configured.update(parent for _, _, parent in CHILD_TABLES)
    missing = sorted(name for name in configured if not inspector.has_table(name))
    if missing:
        raise RuntimeError(
            "reset_history is configured with table(s) that do not exist: "
            f"{', '.join(missing)}. Correct the name -- skipping it would "
            "leave the rows it was meant to clear."
        )


def reset_history(session: Session, firm_id: UUID) -> int:
    """Delete one firm's trading history, leaving its master data alone.

    Numbering counters go too. Without that, regenerating would reuse numbers
    the deleted documents had issued, and the unique constraint would refuse
    them -- the counter has to be cleared with the documents it counted.
    """
    # inspect(session.connection()), not the engine: a tenant session sets
    # search_path on its own connection, and an inspector opened on the
    # engine gets a fresh one without it -- it then finds none of the
    # tables and deletes nothing, silently.
    inspector = inspect(session.connection())
    _assert_reset_tables_exist(inspector)
    removed = 0
    for table, parent_column, parent_table in CHILD_TABLES:
        result = session.execute(
            text(
                f"DELETE FROM {table} WHERE {parent_column} IN "  # noqa: S608
                f"(SELECT id FROM {parent_table} WHERE firm_id = :firm)"
            ),
            {"firm": firm_id},
        )
        removed += result.rowcount or 0
    for table in RESET_ORDER:
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "firm_id" not in columns:
            continue
        result = session.execute(
            text(f"DELETE FROM {table} WHERE firm_id = :firm"),  # noqa: S608
            {"firm": firm_id},
        )
        removed += result.rowcount or 0
    # The rule's own counter is the template a fresh scope starts from.
    session.execute(
        text(
            "UPDATE document_numbering_rules "
            "SET next_sequence = 1, last_scope_signature = NULL "
            "WHERE firm_id = :firm"
        ),
        {"firm": firm_id},
    )
    session.execute(
        text(
            "UPDATE customers SET current_outstanding = 0, "
            "unapplied_advance_balance = 0 WHERE firm_id = :firm"
        ),
        {"firm": firm_id},
    )
    session.commit()
    return removed


@dataclass(frozen=True, slots=True)
class FirmTarget:
    """One firm, and the store its business data lives in."""

    firm_id: UUID
    code: str
    context: TenantContext
    label: str


@dataclass
class Tally:
    """What was created, so the run can report itself honestly."""

    years: int = 0
    purchase_orders: int = 0
    goods_receipts: int = 0
    purchase_invoices: int = 0
    purchase_returns: int = 0
    sales_orders: int = 0
    delivery_notes: int = 0
    quotations: int = 0
    promotions: int = 0
    sales_invoices: int = 0
    sales_returns: int = 0
    credit_notes: int = 0
    receipts: int = 0
    targets: int = 0
    payouts: int = 0
    skipped: list[str] = field(default_factory=list)

    def line(self) -> str:
        """Render the tally as one reportable line."""
        return (
            # "financial", because --years 2 populates the current financial
            # year plus the two before it, so the honest count is three.
            f"{self.years} financial year(s) | PO {self.purchase_orders} | "
            f"GRN {self.goods_receipts} | PINV {self.purchase_invoices} | "
            f"PRET {self.purchase_returns} | "
            f"PROMO {self.promotions} | "
            f"QT {self.quotations} | SO {self.sales_orders} | "
            f"DN {self.delivery_notes} | INV {self.sales_invoices} | "
            f"RCPT {self.receipts} | SRET {self.sales_returns} | "
            f"CN {self.credit_notes} | "
            f"TGT {self.targets} | PAY {self.payouts}"
        )


def _firm_targets(platform: DatabaseManager, settings: Settings) -> list[FirmTarget]:
    """Return every live firm with the store its rows belong in.

    Unlike the retention script, firms are **not** collapsed by store: two
    SHARED firms share tables but own separate data, and each needs its own
    history.
    """
    targets: list[FirmTarget] = []
    with platform.sessions(schema=platform.config.default_schema).session() as session:
        rows = session.execute(
            select(Firm, FirmStorageMapping)
            .join(FirmStorageMapping, FirmStorageMapping.firm_id == Firm.id)
            .where(
                Firm.is_deleted.is_(False),
                FirmStorageMapping.is_deleted.is_(False),
                FirmStorageMapping.is_active.is_(True),
            )
            .order_by(Firm.code)
        ).all()
        for firm, mapping in rows:
            mode = DeploymentMode(mapping.deployment_mode)
            if mode is DeploymentMode.SHARED:
                database_name = settings.tenancy.shared_database_name
                schema_name = settings.tenancy.shared_schema_name
            else:
                database_name = mapping.database_name
                schema_name = mapping.schema_name
            targets.append(
                FirmTarget(
                    firm_id=firm.id,
                    code=firm.code,
                    label=(
                        f"{firm.code} ({mode.value} -> "
                        f"{database_name}/{schema_name})"
                    ),
                    context=TenantContext(
                        firm_id=firm.id,
                        deployment_mode=mode,
                        database_name=database_name,
                        schema_name=schema_name,
                        database_type=mapping.database_type,
                    ),
                )
            )
    return targets


def _financial_years(count: int, today: date) -> list[date]:
    """Return the start date of each financial year to populate, oldest first.

    Indian financial years start on 1 April, which is what the rest of this
    codebase assumes.
    """
    current_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    return [
        date(current_start.year - offset, 4, 1) for offset in reversed(range(count + 1))
    ]


def _month_starts(year_start: date, until: date) -> list[date]:
    """Return the first of each month in a financial year, up to ``until``."""
    months: list[date] = []
    for index in range(12):
        year = year_start.year + (year_start.month - 1 + index) // 12
        month = (year_start.month - 1 + index) % 12 + 1
        first = date(year, month, 1)
        if first > until:
            break
        months.append(first)
    return months


def _day_in(month_start: date, day: int, until: date) -> date | None:
    """Return a safe day inside the month, or nothing if it is in the future."""
    last = monthrange(month_start.year, month_start.month)[1]
    chosen = month_start.replace(day=min(day, last))
    return None if chosen > until else chosen


class HistoryBuilder:
    """Drive documents through the real services for one firm."""

    def __init__(self, session: Session, target: FirmTarget) -> None:
        """Bind to one firm's store and read the capabilities it operates with."""
        self._session = session
        self._target = target
        self._tally = Tally()
        self._features = resolve_capabilities(session, target.firm_id).features
        #: Which invoices get collected, and how much of each. A counter
        #: rather than randomness: a seed run has to be reproducible, and
        #: `Math.random`-shaped data makes two runs impossible to compare.
        self._collection_cycle = 0
        #: Which lapsed offers were turned down rather than left unanswered.
        self._quotation_cycle = 0
        #: Which invoices see part of the goods come back.
        self._return_cycle = 0
        self._credit_cycle = 0
        #: Which receipts send part of the goods back to the supplier.
        self._vendor_return_cycle = 0
        self._today = utc_now().date()

    @property
    def tally(self) -> Tally:
        """Return what has been created so far."""
        return self._tally

    # -- masters -------------------------------------------------------

    def masters(
        self,
    ) -> tuple[Branch, Warehouse, Vendor, list[Customer], list[Product]]:
        """Return the master records the documents will reference.

        Raises:
            BusinessRuleError: If the firm has no masters to trade with. This
                script deliberately does not invent them -- ``generate_sample_
                data.py`` owns master data, and a firm with no products is a
                setup problem worth surfacing rather than papering over.

        """
        firm_id = self._target.firm_id
        branch = self._session.scalar(
            select(Branch)
            .where(Branch.firm_id == firm_id, Branch.is_deleted.is_(False))
            .order_by(Branch.code)
        )
        warehouse = self._session.scalar(
            select(Warehouse)
            .where(Warehouse.firm_id == firm_id, Warehouse.is_deleted.is_(False))
            .order_by(Warehouse.code)
        )
        vendor = self._session.scalar(
            select(Vendor)
            .where(Vendor.firm_id == firm_id, Vendor.is_deleted.is_(False))
            .order_by(Vendor.code)
        )
        customers = list(
            self._session.scalars(
                select(Customer)
                .where(Customer.firm_id == firm_id, Customer.is_deleted.is_(False))
                .order_by(Customer.code)
            ).all()
        )
        products = list(
            self._session.scalars(
                select(Product)
                .where(Product.firm_id == firm_id, Product.is_deleted.is_(False))
                .order_by(Product.code)
            ).all()
        )
        missing = [
            name
            for name, value in (
                ("branch", branch),
                ("warehouse", warehouse),
                ("vendor", vendor),
                ("customers", customers),
                ("products", products),
            )
            if not value
        ]
        if missing:
            raise BusinessRuleError(
                f"{self._target.code} has no {', '.join(missing)}. "
                "Run generate_sample_data.py first."
            )
        assert branch is not None and warehouse is not None and vendor is not None
        # One customer trades on a standing discount, so every sale to them
        # picks it up server-side without any document asking for it. Set here
        # rather than in the master seed because it is a fact about trading:
        # without it nothing in the demo exercised the rule, and nothing on
        # screen showed a discount.
        if customers[0].default_discount_percent <= Decimal("0"):
            customers[0].default_discount_percent = Decimal("7.5")
            self._session.commit()
        return branch, warehouse, vendor, customers, products

    # -- calendar ------------------------------------------------------

    def promotions(self, first_year_start: date) -> None:
        """Put three offers on the firm, so the engine prices real documents.

        Chosen to exercise the parts of the engine that arithmetic alone does
        not. `BULK5` is quantity-based and **stacks**; `CLEARANCE` stacks
        behind it; and `BIGORDER` sits between them and refuses to stack, so a
        large order demonstrably gets `BULK5` and `BIGORDER` and **not**
        `CLEARANCE`. A seed where every offer stacked would leave that rule
        exercised by nothing.

        `BULK5` is also seeded as two revisions with adjoining windows -- the
        rate improves half way through the history -- because superseding
        leaves the predecessor ACTIVE, and an engine that failed to collapse to
        one live version per offer would hand the customer both. That is the
        trap a stacking engine inherits from copying the tax query, and a
        seeded document is what makes it visible.

        Rows are built directly rather than through `PromotionCrudService`,
        which refuses a second promotion carrying an existing code -- exactly
        what a superseded revision is.
        """
        midpoint = date(first_year_start.year + 1, first_year_start.month, 1)
        bulk_group = uuid4()

        # The rate a bulk buyer gets, improved half way through. Adjoining
        # windows, so only one revision is ever in force on a given day.
        self._promotion(
            code="BULK5",
            name="Five percent on a bulk line",
            priority=10,
            allow_stacking=True,
            effective_from=first_year_start,
            effective_to=midpoint - timedelta(days=1),
            version_group_id=bulk_group,
            version_number=1,
            actions=[("LINE_DISCOUNT_PERCENT", {"percent": "5"})],
            conditions=[("line_quantity", "GREATER_OR_EQUAL", Decimal("25"))],
        )
        self._promotion(
            code="BULK5",
            name="Seven and a half percent on a bulk line",
            priority=10,
            allow_stacking=True,
            effective_from=midpoint,
            effective_to=None,
            version_group_id=bulk_group,
            version_number=2,
            actions=[("LINE_DISCOUNT_PERCENT", {"percent": "7.5"})],
            conditions=[("line_quantity", "GREATER_OR_EQUAL", Decimal("25"))],
        )
        # Off the whole bill on a large order, and nothing after it applies.
        self._promotion(
            code="BIGORDER",
            name="Two hundred off a large order",
            priority=20,
            allow_stacking=False,
            effective_from=first_year_start,
            effective_to=None,
            version_group_id=uuid4(),
            version_number=1,
            actions=[("BILL_DISCOUNT_AMOUNT", {"amount": "200"})],
            conditions=[("document_gross", "GREATER_OR_EQUAL", Decimal("4500"))],
        )
        # Behind the one that does not stack, so a large order proves it was
        # skipped rather than merely absent.
        self._promotion(
            code="CLEARANCE",
            name="One percent, when nothing has ended the stack",
            priority=30,
            allow_stacking=True,
            effective_from=first_year_start,
            effective_to=None,
            version_group_id=uuid4(),
            version_number=1,
            actions=[("LINE_DISCOUNT_PERCENT", {"percent": "1"})],
            conditions=[],
        )
        self._session.commit()

    def _promotion(
        self,
        *,
        code: str,
        name: str,
        priority: int,
        allow_stacking: bool,
        effective_from: date,
        effective_to: date | None,
        version_group_id: UUID,
        version_number: int,
        actions: list[tuple[str, dict[str, str]]],
        conditions: list[tuple[str, str, Decimal]],
    ) -> None:
        """Write one promotion with its actions and conditions."""
        firm_id = self._target.firm_id
        row = Promotion(
            firm_id=firm_id,
            code=code,
            name=name,
            priority=priority,
            status="ACTIVE",
            allow_stacking=allow_stacking,
            effective_from=effective_from,
            effective_to=effective_to,
            version_group_id=version_group_id,
            version_number=version_number,
            created_by=ACTOR,
            updated_by=ACTOR,
        )
        self._session.add(row)
        self._session.flush()
        for index, (action_type, parameters) in enumerate(actions, start=1):
            self._session.add(
                PromotionAction(
                    firm_id=firm_id,
                    promotion_id=row.id,
                    sequence=index,
                    action_type=action_type,
                    parameters=parameters,
                    created_by=ACTOR,
                    updated_by=ACTOR,
                )
            )
        for index, (field_key, operator, value) in enumerate(conditions, start=1):
            self._session.add(
                PromotionCondition(
                    firm_id=firm_id,
                    promotion_id=row.id,
                    sequence=index,
                    field_key=field_key,
                    operator=operator,
                    value_number=value,
                    created_by=ACTOR,
                    updated_by=ACTOR,
                )
            )
        self._tally.promotions += 1

    def ensure_year(self, year_start: date) -> None:
        """Create the financial year and its periods if they are not there.

        Posting refuses a date no open period covers, so this has to run before
        any document dated inside the year. ``seed_finance_setup`` is not
        idempotent over periods -- it raises on the second call for a year it
        already built -- so the year is checked first rather than relying on it.

        The tally counts years of history **generated**, which is what its
        label claims and what the caller prints. It used to be incremented
        after the early return below, so it counted years whose accounting
        setup this call happened to create: a re-run reported "0 year(s)"
        beside the 29 purchase orders it had just written, because ``--reset``
        clears documents and leaves financial years alone.
        """
        self._tally.years += 1
        existing = self._session.scalar(
            select(FinancialYear).where(
                FinancialYear.firm_id == self._target.firm_id,
                FinancialYear.starts_on == year_start,
                FinancialYear.is_deleted.is_(False),
            )
        )
        if existing is not None:
            return
        seed_finance_setup(
            self._session,
            firm_id=self._target.firm_id,
            year_starts_on=year_start,
            actor_id=ACTOR,
        )
        self._session.commit()

    # -- cycles --------------------------------------------------------

    def warn_if_the_shelf_is_empty(self) -> None:
        """Say so when the firm starts trading with no day-one stock.

        **Opening stock is history, and `--reset` deletes it.** Only
        `seed_multi_firm_demo.py` lays it back down, because only it holds the
        blueprint that says which products sit on the shelf and how many. So a
        firm regenerated on its own starts from an empty warehouse, trades from
        goods receipts alone, and quietly loses the dispatches those receipts
        cannot cover -- WHOLE01 came out at 57 delivery notes against 58 sales
        orders while its three siblings, seeded the other way, all read 58.

        Nothing here can fix that without the blueprint, so it is reported
        rather than papered over: a count that differs between firms is the
        signal this seeder exists to raise, and the reader deserves to know it
        is the tool and not the application.
        """
        movements = self._session.scalar(
            select(func.count())
            .select_from(InventoryTransaction)
            .where(
                InventoryTransaction.firm_id == self._target.firm_id,
                InventoryTransaction.transaction_type == "OPENING_STOCK",
            )
        )
        if movements:
            return
        self._tally.skipped.append(
            "no opening stock: --reset clears the day-one shelf and only "
            "seed_multi_firm_demo.py lays it down again, so this firm trades "
            "from goods receipts alone and may lose dispatches its siblings "
            "make. Run scripts/seed_multi_firm_demo.py to restore it."
        )

    # -- incentives ----------------------------------------------------

    def incentives(self, years_in_scope: list[date]) -> None:
        """Put the incentive arrangements on the firm, and run one payout.

        Everything below is deliberately *after* the trading, because none of
        it changes a document: commission is a report over invoices and
        receipts that already exist, and a target is a number to measure them
        against. Running it first would only mean the same rows read later.

        Four arrangements rather than one, because the whole module is about
        precedence and a demo where everybody earns the same shows none of it:

        - the firm-wide default and one person's own flat rate, both already
          seeded as masters;
        - a **product** rule for that same person, which takes the lines it
          names while their flat rate still covers the rest -- the "3% on
          everything, 5% on the cold chain" shape;
        - a **ladder with a floor and a target bonus** for the second person,
          so slabs, `minimum_amount` and `bonus_percentage` all appear in a
          store rather than only in a test.

        The targets are set from what each person **actually** sold: one
        below, so it is met, and one above, so it is missed. That is a demo
        deciding what to show rather than a measurement -- and it is the only
        way both states are on screen, which is what makes the bonus rule
        legible at all.
        """
        salesmen = self._salesmen_who_sold()
        if len(salesmen) < 2:
            self._tally.skipped.append(
                "incentives: fewer than two salesmen carried invoices"
            )
            return
        self._incentive_rules(salesmen)
        self._targets(salesmen, years_in_scope)
        self._payout_run(years_in_scope)

    def _salesmen_who_sold(self) -> list[UUID]:
        """Return the people whose name is actually on an invoice.

        Read from the documents rather than from the territory assignments:
        somebody who covers a round but sold nothing has no commission to
        report and no target worth setting.
        """
        rows = self._session.scalars(
            select(SalesInvoice.salesman_id)
            .where(
                SalesInvoice.firm_id == self._target.firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.salesman_id.is_not(None),
                SalesInvoice.status.in_(("APPROVED", "CLOSED")),
            )
            .distinct()
            .order_by(SalesInvoice.salesman_id)
        ).all()
        return [row for row in rows if row is not None]

    def _incentive_rules(self, salesmen: list[UUID]) -> None:
        """Add the two arrangements the masters seeder does not create."""
        service = CommissionService(self._session)
        existing, _total = service.list_rules(
            firm_id=self._target.firm_id, page=1, page_size=100
        )
        # Who gets which arrangement is chosen from the rules that exist, not
        # by position. Picking positionally read the salesmen in id order, so
        # in two firms of four the ladder landed on somebody who already had a
        # flat rate, the overlap guard refused it, and those stores seeded
        # with no slabs at all -- a count that differed between firms, which
        # is exactly the signal this seeder exists to raise.
        # Only *unscoped* rules count as owning a rate. The overlap guard
        # compares scope as well as person, so a category rule and a ladder
        # can sit on one salesman quite happily -- treating any rule at all as
        # ownership left both shared-store firms with no ladder, because a
        # previous run had put the category rule on the second person.
        owned = {
            rule.salesman_id
            for rule in existing
            if rule.salesman_id
            and rule.product_id is None
            and rule.product_category_id is None
        }
        # The category rule goes to somebody who already has a rate of their
        # own, so "the narrower rule wins for its lines and the broader one
        # covers the rest" is visible on one person rather than described.
        with_rate = next((who for who in salesmen if who in owned), salesmen[0])
        # The ladder goes to somebody with no unscoped rate, because that is
        # the one a ladder would collide with.
        without_rate = next((who for who in salesmen if who not in owned), None)
        # Scoped to one **product**, not to a category. These firms carry a
        # single category, so a category rule would cover every line and be
        # indistinguishable from an unscoped one -- the precedence it exists
        # to show would be invisible in the very data seeded to show it. A
        # product rule covers some lines and leaves the person's own flat rate
        # to cover the rest, which is the thing worth seeing.
        product = self._session.scalar(
            select(Product)
            .where(
                Product.firm_id == self._target.firm_id,
                Product.is_deleted.is_(False),
            )
            .order_by(Product.code.asc())
        )
        if product is not None and not any(
            rule.product_id == product.id for rule in existing
        ):
            service.create_rule(
                CommissionRuleCreate(
                    salesman_id=with_rate,
                    percentage=Decimal("6"),
                    effective_from=date(2024, 4, 1),
                    product_id=product.id,
                ),
                firm_id=self._target.firm_id,
                actor_id=ACTOR,
            )
        if without_rate is None:
            self._tally.skipped.append(
                "incentives: everybody already has a rule, so no ladder was seeded"
            )
        else:
            service.create_rule(
                CommissionRuleCreate(
                    salesman_id=without_rate,
                    # Ignored: a rule with slabs pays the ladder, and this
                    # column is here only because every rule carries it.
                    percentage=Decimal("0"),
                    effective_from=date(2024, 4, 1),
                    basis=CommissionBasisEnum.COLLECTED,
                    minimum_amount=Decimal("1000"),
                    bonus_percentage=Decimal("2"),
                    slabs=[
                        CommissionSlabWrite(
                            from_amount=Decimal("0"),
                            to_amount=Decimal("50000"),
                            percentage=Decimal("2"),
                        ),
                        CommissionSlabWrite(
                            from_amount=Decimal("50000"),
                            percentage=Decimal("4"),
                        ),
                    ],
                ),
                firm_id=self._target.firm_id,
                actor_id=ACTOR,
            )
        self._session.commit()

    def _targets(self, salesmen: list[UUID], years_in_scope: list[date]) -> None:
        """Set one target somebody met and one somebody missed.

        Over the most recent financial year in scope, because a target over a
        year the history never reached would be neither.
        """
        service = SalesTargetService(self._session)
        year_start = years_in_scope[-1]
        year_end = min(date(year_start.year + 1, 3, 31), self._today)
        if year_end <= year_start:
            return
        for index, salesman_id in enumerate(salesmen[:2]):
            sold = self._session.scalar(
                select(func.coalesce(func.sum(SalesInvoice.grand_total), 0)).where(
                    SalesInvoice.firm_id == self._target.firm_id,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.salesman_id == salesman_id,
                    SalesInvoice.status.in_(("APPROVED", "CLOSED")),
                    SalesInvoice.invoice_date >= year_start,
                    SalesInvoice.invoice_date <= year_end,
                )
            )
            sold = Decimal(str(sold or 0))
            if sold <= Decimal(0):
                continue
            # The first person's number is one they beat and the second's is
            # one they missed, so the report shows Met and Missed rather than
            # a column of the same word.
            share = Decimal("0.8") if index == 0 else Decimal("1.3")
            try:
                service.create_target(
                    SalesTargetWrite(
                        salesman_id=salesman_id,
                        period_start=year_start,
                        period_end=year_end,
                        period_type=SalesTargetPeriod.YEARLY,
                        basis=SalesTargetBasis.INVOICED,
                        target_amount=(sold * share).quantize(Decimal("1")),
                    ),
                    firm_id=self._target.firm_id,
                    actor_id=ACTOR,
                )
                self._tally.targets += 1
            except (ValidationError, BusinessRuleError, ConflictError) as error:
                self._tally.skipped.append(f"target: {error}")
        self._session.commit()

    def _payout_run(self, years_in_scope: list[date]) -> None:
        """Accrue one quarter, approve it all, and pay the first of them.

        Not every quarter: a store where every payout is settled has nothing
        for the "what do we still owe" question to show, which is the same
        reason one invoice in four is left uncollected.
        """
        service = CommissionPayoutService(self._session)
        year_start = years_in_scope[-1]
        period_start = year_start
        period_end = min(
            date(year_start.year, 6, 30) if year_start.month == 4 else year_start,
            self._today,
        )
        if period_end <= period_start:
            return
        try:
            payouts = service.accrue(
                CommissionPayoutAccrue(
                    period_start=period_start, period_end=period_end
                ),
                firm_id=self._target.firm_id,
                actor_id=ACTOR,
            )
            self._session.commit()
        except (ValidationError, BusinessRuleError, ConflictError) as error:
            self._tally.skipped.append(f"payout accrual: {error}")
            self._session.rollback()
            return
        money_account = ControlAccountService(self._session).resolve(
            self._target.firm_id, ControlAccountPurpose.CASH
        )
        for index, payout in enumerate(payouts):
            try:
                service.approve(
                    payout.id,
                    firm_id=self._target.firm_id,
                    actor_id=ACTOR,
                )
                self._session.commit()
                self._tally.payouts += 1
                if index == 0:
                    service.pay(
                        payout.id,
                        CommissionPayoutPay(
                            paid_on=period_end,
                            money_account_id=money_account,
                        ),
                        firm_id=self._target.firm_id,
                        actor_id=ACTOR,
                    )
                    self._session.commit()
            except (ValidationError, BusinessRuleError, ConflictError) as error:
                self._tally.skipped.append(f"payout: {error}")
                self._session.rollback()

    def _batch_for(self, product: Product, on: date) -> tuple[str | None, date | None]:
        """Name the batch a delivery arrives in, if this firm works that way.

        Seeded history had no batches at all, so nothing in the demo stores
        exercised batch-grained stock: no receipt created a batch, every stock
        row was the untracked one, and a dispatch never had two batches to
        choose between. The receipt path is what registers a batch, so this is
        where it has to start.

        Both switches have to be on. The firm's BATCH_TRACKING feature says the
        firm may use batches at all; the product's ``require_batch_on_receipt``
        says these particular goods cannot be taken in unidentified. A firm
        that tracks batches still buys things nobody traces, and seeding those
        without a batch is what keeps untracked stock in the demo data beside
        the tracked kind.

        One batch per product per month, which is how a monthly delivery
        actually arrives, and it gives a dispatch several batches to rank by
        expiry once a few months have run.

        Returns:
            The batch number and its expiry date, either of which may be None.
            The expiry is only set where the firm has EXPIRY_TRACKING -- the
            field is gated, and sending it to a firm without the feature is
            refused when the receipt completes.

        """
        if "BATCH_TRACKING" not in self._features:
            return None, None
        if not product.require_batch_on_receipt:
            return None, None
        number = f"{product.code}-{on:%Y%m}"
        if "EXPIRY_TRACKING" not in self._features:
            return number, None
        # Eighteen months is a plausible shelf life for a medicine or a
        # packaged food, and it puts the expiry far enough out that a two-year
        # history has both live and expired batches to look at.
        return number, on + timedelta(days=548)

    def buy(
        self,
        *,
        on: date,
        branch: Branch,
        warehouse: Warehouse,
        vendor: Vendor,
        product: Product,
        quantity: str,
        unit_price: str,
    ) -> None:
        """Raise a purchase order and receive it into stock."""
        purchase = PurchaseService(self._session)
        order = purchase.create_order(
            PurchaseOrderCreate(
                vendor_id=vendor.id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                purchase_date=on,
                status=PurchaseOrderStatus.APPROVED,
                lines=[
                    {
                        "product_id": str(product.id),
                        "ordered_quantity": quantity,
                        "unit_price": unit_price,
                    }
                ],
            ),
            firm_id=self._target.firm_id,
            actor_id=ACTOR,
        )
        self._tally.purchase_orders += 1

        line = self._session.scalar(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == order.id
            )
        )
        assert line is not None
        batch_number, expiry_date = self._batch_for(product, on)
        receipts = GoodsReceiptService(self._session)
        receipt = receipts.create_receipt(
            GoodsReceiptCreate(
                purchase_order_id=order.id,
                receipt_date=on,
                lines=[
                    GoodsReceiptLineWrite(
                        purchase_order_line_id=line.id,
                        line_number=1,
                        current_receipt_quantity=Decimal(quantity),
                        unit_price=Decimal(unit_price),
                        warehouse_id=warehouse.id,
                        batch_number=batch_number,
                        expiry_date=expiry_date,
                    )
                ],
            ),
            firm_id=self._target.firm_id,
            actor_id=ACTOR,
        )
        receipts.complete_receipt(
            receipt.id, firm_scope=self._target.firm_id, actor_id=ACTOR
        )
        self._tally.goods_receipts += 1
        self._session.commit()

        # The supplier bills for what arrived. This step was missing entirely,
        # so the demo firm had 29 goods receipts and no purchase invoices: the
        # payables side of the ledger stayed at zero, nothing was ever owed to
        # a vendor, and a payment had nothing to be applied to.
        self._bill(receipt_id=receipt.id, on=on)
        # And send a little of it back. `purchase_returns` held zero rows in
        # every store: goods came in and none ever went out again, so the
        # module that takes stock off and reverses the payable was exercised
        # by nothing -- including the cancel path, which had no journal at all
        # until 2026-08-22 and was found by hand rather than by any test.
        self._return_to_vendor(
            receipt_id=receipt.id,
            vendor=vendor,
            branch=branch,
            warehouse=warehouse,
            on=on + timedelta(days=3),
        )

    def _return_to_vendor(
        self,
        *,
        receipt_id: UUID,
        vendor: Vendor,
        branch: Branch,
        warehouse: Warehouse,
        on: date,
    ) -> None:
        """Send part of one receipt back to the supplier.

        One receipt in five, and part of the line rather than all of it: a
        return of everything is the easy case and the one that hides whether
        the payable and the input tax are reduced proportionally. Driven to
        COMPLETED, because an approved-but-uncompleted return moves no stock
        and posts no journal.
        """
        self._vendor_return_cycle += 1
        if self._vendor_return_cycle % 5 != 0:
            return
        line = self._session.scalar(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt_id
            )
        )
        if line is None:
            return
        received = Decimal(str(line.accepted_quantity or "0"))
        quantity = (received / 4).quantize(Decimal("1"))
        if quantity <= 0:
            return
        returns = PurchaseReturnService(self._session)
        try:
            row = returns.create_return(
                PurchaseReturnCreate(
                    vendor_id=vendor.id,
                    branch_id=branch.id,
                    warehouse_id=warehouse.id,
                    return_date=on,
                    return_reason="QUALITY_REJECTED",
                    lines=[
                        PurchaseReturnLineWrite(
                            source_document_type=(
                                PurchaseReturnSourceType.GOODS_RECEIPT
                            ),
                            source_document_id=receipt_id,
                            source_document_line_id=line.id,
                            line_number=1,
                            current_return_quantity=quantity,
                            # A traced product may only be issued from a
                            # batch, so a return has to say which one is going
                            # back. The receipt line already knows; on the two
                            # batch-tracked firms, not carrying it across is
                            # what made four returns in five refuse.
                            batch_number=line.batch_number,
                            expiry_date=line.expiry_date,
                        )
                    ],
                ),
                firm_id=self._target.firm_id,
                actor_id=ACTOR,
            )
            returns.approve_return(
                row.id, firm_scope=self._target.firm_id, actor_id=ACTOR
            )
            returns.complete_return(
                row.id, firm_scope=self._target.firm_id, actor_id=ACTOR
            )
        except (ValidationError, BusinessRuleError) as error:
            self._tally.skipped.append(f"{on} purchase return: {error}")
            self._session.rollback()
            return
        self._tally.purchase_returns += 1
        self._session.commit()

    def _bill(self, *, receipt_id: UUID, on: date) -> None:
        """Raise and approve the supplier's invoice for one goods receipt."""
        receipt_lines = self._session.scalars(
            select(GoodsReceiptLine)
            .where(GoodsReceiptLine.goods_receipt_id == receipt_id)
            .order_by(GoodsReceiptLine.line_number.asc())
        ).all()
        if not receipt_lines:
            self._tally.skipped.append("purchase invoice with no receipt lines")
            return
        invoices = PurchaseInvoiceService(self._session)
        invoice = invoices.create_invoice(
            PurchaseInvoiceCreate(
                invoice_date=on,
                # A supplier's own number, which is what the firm keys from the
                # paperwork. It has to be unique per vendor, so it carries the
                # receipt it came with.
                supplier_invoice_number=f"SUP-{str(receipt_id)[:8].upper()}",
                supplier_invoice_date=on,
                source_documents=[
                    PurchaseInvoiceSourceWrite(
                        source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                        source_document_id=receipt_id,
                    )
                ],
                lines=[
                    PurchaseInvoiceLineWrite(
                        source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                        source_document_id=receipt_id,
                        source_document_line_id=line.id,
                        line_number=line.line_number,
                        current_invoice_quantity=line.current_receipt_quantity,
                        unit_price=line.unit_price,
                    )
                    for line in receipt_lines
                ],
            ),
            firm_id=self._target.firm_id,
            actor_id=ACTOR,
        )
        invoices.approve_invoice(
            invoice.id, firm_scope=self._target.firm_id, actor_id=ACTOR
        )
        self._tally.purchase_invoices += 1
        self._session.commit()

    def sell(
        self,
        *,
        on: date,
        branch: Branch,
        warehouse: Warehouse,
        customer: Customer,
        product: Product,
        quantity: str,
        unit_price: str,
        invoice: bool = True,
        bill_discount_percent: str | None = None,
        free_quantity: str = "0",
        quote_first: bool = False,
    ) -> None:
        """Take an order, dispatch it, and invoice it.

        ``invoice=False`` leaves the order dispatched but unbilled, which is
        what a real ledger looks like at a period end and what the pending and
        ageing reports need in order to have anything to show.

        ``bill_discount_percent`` is passed to all three documents rather than
        to the order alone: each one resolves and apportions it for itself, so
        sending it to all three is what proves the three agree. ``free_quantity``
        is goods thrown in -- real stock leaving the warehouse, outside the
        gross and outside the tax base, and inherited by the invoice from the
        line it bills.

        ``quote_first`` offers the sale before taking it, and the order is then
        the *conversion* of that offer rather than a document typed from
        nothing. Every store held zero quotations until 2026-08-24 -- a whole
        module with its own lifecycle, its own numbering and the only desktop
        screen that types sales lines, and nothing in the demo had ever raised
        one, so nothing had ever converted one either.
        """
        firm_id = self._target.firm_id
        orders = SalesOrderService(self._session)
        order: SalesOrder | None = None
        if quote_first:
            order = self._quote_and_convert(
                on=on,
                branch=branch,
                warehouse=warehouse,
                customer=customer,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                bill_discount_percent=bill_discount_percent,
                free_quantity=free_quantity,
            )
        if order is None:
            order = orders.create_order(
                SalesOrderCreate(
                    customer_id=customer.id,
                    branch_id=branch.id,
                    warehouse_id=warehouse.id,
                    order_date=on,
                    bill_discount_percent=(
                        None
                        if bill_discount_percent is None
                        else Decimal(bill_discount_percent)
                    ),
                    lines=[
                        SalesOrderLineWrite(
                            line_number=1,
                            product_id=product.id,
                            quantity=Decimal(quantity),
                            free_quantity=Decimal(free_quantity),
                            unit_price=Decimal(unit_price),
                        )
                    ],
                ),
                firm_id=firm_id,
                actor_id=ACTOR,
            )
            orders.approve_order(order.id, firm_scope=firm_id, actor_id=ACTOR)
        self._tally.sales_orders += 1

        so_line = self._session.scalar(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        )
        assert so_line is not None
        notes = DeliveryNoteService(self._session)
        note = notes.create_note(
            DeliveryNoteCreate(
                sales_order_id=order.id,
                delivery_date=on,
                bill_discount_percent=(
                    None
                    if bill_discount_percent is None
                    else Decimal(bill_discount_percent)
                ),
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=so_line.id,
                        line_number=1,
                        current_delivery_quantity=Decimal(quantity),
                        free_quantity=Decimal(free_quantity),
                        unit_price=Decimal(unit_price),
                        warehouse_id=warehouse.id,
                    )
                ],
            ),
            firm_id=firm_id,
            actor_id=ACTOR,
        )
        notes.approve_note(note.id, firm_scope=firm_id, actor_id=ACTOR)
        notes.dispatch_note(note.id, firm_scope=firm_id, actor_id=ACTOR)
        self._tally.delivery_notes += 1
        self._session.commit()

        if not invoice:
            return

        from app.delivery_note.models import DeliveryNoteLine

        dn_line = self._session.scalar(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
        )
        assert dn_line is not None
        invoices = SalesInvoiceService(self._session)
        raised = invoices.create_invoice(
            SalesInvoiceCreate(
                customer_id=customer.id,
                branch_id=branch.id,
                invoice_date=on,
                bill_discount_percent=(
                    None
                    if bill_discount_percent is None
                    else Decimal(bill_discount_percent)
                ),
                lines=[
                    SalesInvoiceLineWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                        source_document_line_id=dn_line.id,
                        line_number=1,
                        current_invoice_quantity=Decimal(quantity),
                        unit_price=Decimal(unit_price),
                    )
                ],
            ),
            firm_id=firm_id,
            actor_id=ACTOR,
        )
        approved = invoices.approve_invoice(
            raised.id, firm_scope=firm_id, actor_id=ACTOR
        )
        self._tally.sales_invoices += 1
        self._session.commit()
        self._collect(invoice=approved, customer=customer, on=on, firm_id=firm_id)
        # After the collection, so a return credits an invoice that has
        # already been partly settled -- which is the case that proves the
        # outstanding figure is derived from the allocations rather than
        # stored on the invoice.
        self._return_some(
            invoice=approved,
            customer=customer,
            warehouse=warehouse,
            branch=branch,
            on=on + timedelta(days=7),
            firm_id=firm_id,
        )
        self._credit_something(
            invoice=approved,
            on=on + timedelta(days=11),
            firm_id=firm_id,
        )

    def _quote_and_convert(
        self,
        *,
        on: date,
        branch: Branch,
        warehouse: Warehouse,
        customer: Customer,
        product: Product,
        quantity: str,
        unit_price: str,
        bill_discount_percent: str | None,
        free_quantity: str,
    ) -> SalesOrder | None:
        """Offer the sale, and convert it into the order when the offer stands.

        Driven through the whole lifecycle -- DRAFT, SENT, ACCEPTED, CONVERTED
        -- rather than created and converted, because each transition is a
        rule the module enforces and a timeline event it records, and none of
        them had ever run outside the unit suite.

        **An offer whose window has closed is left as an offer.** `is_expired`
        is judged against today, correctly and deliberately: nobody may send,
        accept or convert a quotation that has lapsed. A history generator
        backdating documents therefore cannot drive the lifecycle for any
        month older than the validity window, and trying to gave 28 refusals
        in one run. Those sales become a quotation nobody took up, which is
        the ordinary fate of an offer and what makes the demo's quotation list
        realistic -- EXPIRED is derived from `valid_until`, so the row shows
        that state without anything storing it. The caller raises the order
        directly, exactly as a phone order does.

        The conversion is what builds the order: `convert_quotation` calls
        `SalesOrderService.create_order` itself, so credit control, tax at the
        order's date and unit conversion all happen on the order rather than
        being frozen at whatever was true when the offer was typed.

        Returns:
            The order the offer became, or None when the offer had lapsed and
            the caller should raise the order itself.

        """
        firm_id = self._target.firm_id
        quotes = QuotationService(self._session)
        quotation = quotes.create_quotation(
            QuotationCreate(
                customer_id=customer.id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                quotation_date=on,
                # An offer with a life: `send_quotation` refuses an expired
                # one, so a window that has already closed cannot be sent.
                valid_until=on + timedelta(days=30),
                bill_discount_percent=(
                    None
                    if bill_discount_percent is None
                    else Decimal(bill_discount_percent)
                ),
                lines=[
                    QuotationLineWrite(
                        line_number=1,
                        product_id=product.id,
                        quantity=Decimal(quantity),
                        free_quantity=Decimal(free_quantity),
                        unit_price=Decimal(unit_price),
                    )
                ],
            ),
            firm_id=firm_id,
            actor_id=ACTOR,
        )
        self._tally.quotations += 1
        if quotes.is_expired(quotation):
            # A lapsed offer can still be declined -- `decline_quotation` is
            # deliberately not expiry-gated, because "the customer said no" is
            # what actually happens to most quotes and is worth recording
            # whenever it is heard. Declining every other one leaves the demo
            # with all three honest outcomes: offers that lapsed unanswered,
            # offers that were turned down, and offers that became orders.
            if self._quotation_cycle % 2 == 0:
                quotes.decline_quotation(
                    quotation.id,
                    firm_scope=firm_id,
                    actor_id=ACTOR,
                    reason="Bought elsewhere on price.",
                )
            self._quotation_cycle += 1
            self._session.commit()
            return None
        self._quotation_cycle += 1
        quotes.send_quotation(quotation.id, firm_scope=firm_id, actor_id=ACTOR)
        quotes.accept_quotation(quotation.id, firm_scope=firm_id, actor_id=ACTOR)
        _quotation, order = quotes.convert_quotation(
            quotation.id,
            firm_scope=firm_id,
            actor_id=ACTOR,
            order_date=on,
        )
        SalesOrderService(self._session).approve_order(
            order.id, firm_scope=firm_id, actor_id=ACTOR
        )
        self._session.commit()
        return order

    def _return_some(
        self,
        *,
        invoice: SalesInvoiceResponse,
        customer: Customer,
        warehouse: Warehouse,
        branch: Branch,
        on: date,
        firm_id: UUID,
    ) -> None:
        """Take a little of it back, the way a distributor actually does.

        `sales_returns` held zero rows in every store -- a complete module
        with a lifecycle, a credit note, stock coming back and a journal
        reversing the sale, and nothing in the demo had ever raised one. The
        cancel path of this very module was one of three ledger defects fixed
        on 2026-08-22, all found by hand because no seeded document exercised
        them.

        One invoice in six, and only part of the line: a return of everything
        is the easy case, and the one that hides whether the credit is
        pro-rated properly. Driven to COMPLETED so the stock actually comes
        back and the journal actually posts -- an approved-but-not-completed
        return moves neither.
        """
        self._return_cycle += 1
        if self._return_cycle % 6 != 0:
            return
        line = self._session.scalar(
            select(SalesInvoiceLine).where(
                SalesInvoiceLine.sales_invoice_id == invoice.id
            )
        )
        if line is None:
            return
        # Half of what was billed, rounded down, and never less than one --
        # a partial return is what proves the credit is apportioned rather
        # than copied.
        billed = Decimal(str(line.current_invoice_quantity or "0"))
        quantity = (billed / 2).quantize(Decimal("1"))
        if quantity <= 0:
            return
        returns = SalesReturnService(self._session)
        try:
            row = returns.create_return(
                SalesReturnCreate(
                    customer_id=customer.id,
                    branch_id=branch.id,
                    warehouse_id=warehouse.id,
                    return_date=on,
                    return_reason="DAMAGED_IN_TRANSIT",
                    lines=[
                        SalesReturnLineWrite(
                            source_document_type=SalesReturnSourceType.SALES_INVOICE,
                            source_document_id=invoice.id,
                            source_document_line_id=line.id,
                            line_number=1,
                            current_return_quantity=quantity,
                        )
                    ],
                ),
                firm_id=firm_id,
                actor_id=ACTOR,
            )
            returns.approve_return(row.id, firm_scope=firm_id, actor_id=ACTOR)
            returns.complete_return(row.id, firm_scope=firm_id, actor_id=ACTOR)
        except (ValidationError, BusinessRuleError) as error:
            self._tally.skipped.append(f"{on} sales return: {error}")
            self._session.rollback()
            return
        self._tally.sales_returns += 1
        self._session.commit()

    def _credit_something(
        self,
        *,
        invoice: SalesInvoiceResponse,
        on: date,
        firm_id: UUID,
    ) -> None:
        """Credit a little value back without any goods moving.

        `credit_notes` held zero rows in every store the day the module
        shipped, and the GSTR-1 CDNR section reads that table -- so a whole
        return section was answering empty everywhere, which looks identical
        to a firm that issued no credit notes. Every defect this repo has
        found in a sales module was found because a seeded document reached
        it.

        Deliberately **not** a sales return. A return moves stock; this is a
        rate agreed after the bill went out, so value and its tax come off and
        the warehouse never hears about it. Seeding both is what makes the
        difference visible in the data rather than only in the docs.

        One invoice in five, and a small slice of one line, because a credit
        for the whole line is the case that hides whether the tax is reversed
        in proportion to what is being credited.
        """
        self._credit_cycle += 1
        if self._credit_cycle % 5 != 0:
            return
        line = self._session.scalar(
            select(SalesInvoiceLine).where(
                SalesInvoiceLine.sales_invoice_id == invoice.id
            )
        )
        if line is None:
            return
        charged = (
            Decimal(str(line.gross_amount or "0"))
            - Decimal(str(line.discount_amount or "0"))
            - Decimal(str(line.bill_discount_amount or "0"))
        )
        # A tenth of the line, to the paisa, and never nothing.
        credited = (charged / 10).quantize(Decimal("0.01"))
        if credited <= 0:
            return
        notes = CreditNoteService(self._session)
        try:
            row = notes.create_note(
                CreditNoteCreate(
                    sales_invoice_id=invoice.id,
                    credit_note_date=on,
                    reason=CreditNoteReasonEnum.RATE_DIFFERENCE,
                    remarks="Rate revised after the bill was raised.",
                    lines=[
                        CreditNoteLineWrite(
                            sales_invoice_line_id=line.id,
                            line_number=1,
                            quantity=Decimal("0"),
                            taxable_amount=credited,
                        )
                    ],
                ),
                firm_id=firm_id,
                actor_id=ACTOR,
            )
            notes.approve_note(row.id, firm_scope=firm_id, actor_id=ACTOR)
        except (ValidationError, BusinessRuleError) as error:
            self._tally.skipped.append(f"{on} credit note: {error}")
            self._session.rollback()
            return
        self._tally.credit_notes += 1
        self._session.commit()

    def _collect(
        self,
        *,
        invoice: SalesInvoiceResponse,
        customer: Customer,
        on: date,
        firm_id: UUID,
    ) -> None:
        """Take some of the money in, the way a distributor actually does.

        Two years of trading used to produce **zero** settlements in every
        store. Three things followed and none of them looked like a seeding
        gap. Receivables only ever grew, so every ageing and outstanding
        figure in the demo was the whole trading value. `app/settlements` --
        the module handling every rupee in and out -- was exercised by nothing,
        so the seed run could not act as the blunt integration test it is for
        the other seven. And commission, which is earned on money *collected*,
        could only ever report zero however many invoices were raised.

        Not everything is collected, because a demo where every bill is paid
        has nothing for an ageing report to show: one invoice in four is left
        outstanding and one in four is paid in part, so the books hold a
        realistic mix of settled, partly settled and open.
        """
        self._collection_cycle += 1
        share = self._collection_cycle % 4
        if share == 0:
            return
        total = Decimal(str(invoice.grand_total or "0")).quantize(Decimal("0.01"))
        if total <= 0:
            return
        amount = (total / 2).quantize(Decimal("0.01")) if share == 2 else total
        if amount <= 0:
            return
        # Money arrives after the bill, not with it. Thirty days is the
        # ordinary term here and keeps the settlement inside the same
        # accounting period as the invoice for all but the month end.
        received_on = min(on + timedelta(days=30), self._today)
        if received_on < on:
            received_on = on
        try:
            ReceiptService(self._session).create(
                SettlementCreate(
                    party_id=customer.id,
                    settlement_date=received_on,
                    amount=amount,
                    method=SettlementMethodEnum.BANK,
                    narration=f"Collection against {invoice.invoice_number}",
                    allocations=[
                        SettlementAllocationWrite(invoice_id=invoice.id, amount=amount)
                    ],
                ),
                firm_id=firm_id,
                actor_id=ACTOR,
            )
        except (ValidationError, BusinessRuleError) as error:
            self._tally.skipped.append(f"{received_on} collection: {error}")
            self._session.rollback()
            return
        self._tally.receipts += 1
        self._session.commit()


def build_for_firm(
    session: Session, target: FirmTarget, years: int, today: date
) -> Tally:
    """Populate one firm across the requested financial years."""
    builder = HistoryBuilder(session, target)
    branch, warehouse, vendor, customers, products = builder.masters()
    builder.warn_if_the_shelf_is_empty()

    years_in_scope = _financial_years(years, today)
    # Before a single document is priced: an offer agreed after the order it
    # was meant to discount is an offer that discounts nothing.
    builder.promotions(years_in_scope[0])

    cycle = 0
    for year_start in years_in_scope:
        builder.ensure_year(year_start)
        for month_index, month_start in enumerate(_month_starts(year_start, today)):
            buy_on = _day_in(month_start, 4, today)
            if buy_on is None:
                continue
            quantity, price = PURCHASE_SHAPES[cycle % len(PURCHASE_SHAPES)]
            product = products[cycle % len(products)]
            try:
                builder.buy(
                    on=buy_on,
                    branch=branch,
                    warehouse=warehouse,
                    vendor=vendor,
                    product=product,
                    quantity=quantity,
                    unit_price=price,
                )
            except (ValidationError, BusinessRuleError) as error:
                builder.tally.skipped.append(f"{buy_on} purchase: {error}")
                cycle += 1
                continue

            # Two sales per month against different customers, so the by-customer
            # reports rank something and receivables are not all one name.
            for offset, sale_day in enumerate((12, 22)):
                sell_on = _day_in(month_start, sale_day, today)
                if sell_on is None:
                    continue
                sale_qty, sale_price = SALE_SHAPES[(cycle + offset) % len(SALE_SHAPES)]
                customer = customers[(cycle + offset) % len(customers)]
                # Leave the last sale of every third month unbilled so ageing and
                # pending reports have live rows rather than a clean sheet.
                bill = not (offset == 1 and month_index % 3 == 2)
                # A discount on the whole bill every fourth month, and one
                # unit thrown in every third. Neither is on every document on
                # purpose: a report that cannot tell a discounted sale from an
                # ordinary one is not being tested by data where they are all
                # the same.
                whole_bill = "5" if month_index % 4 == 1 and offset == 0 else None
                gift = "1" if month_index % 3 == 0 and offset == 1 else "0"
                # Every second sale is offered before it is taken, so the
                # order is the conversion of a quotation rather than a
                # document typed from nothing -- and the other half still
                # covers the phone-order path, which is the one the desktop
                # could not raise at all until 2026-08-23.
                quoted = offset == 0
                try:
                    builder.sell(
                        on=sell_on,
                        branch=branch,
                        warehouse=warehouse,
                        customer=customer,
                        product=product,
                        quantity=sale_qty,
                        unit_price=sale_price,
                        invoice=bill,
                        bill_discount_percent=whole_bill,
                        free_quantity=gift,
                        quote_first=quoted,
                    )
                except (ValidationError, BusinessRuleError) as error:
                    builder.tally.skipped.append(f"{sell_on} sale: {error}")
            cycle += 1

    # Last, because none of it changes a document: commission reports over
    # invoices and receipts that already exist, and a target is a number to
    # measure them against.
    builder.incentives(years_in_scope)
    return builder.tally


def generate_history(
    session: Session,
    *,
    firm_id: UUID,
    firm_code: str,
    years: int = 2,
    today: date | None = None,
    reset: bool = False,
) -> Tally:
    """Populate one firm's trading history on a session the caller owns.

    The entry point ``seed_multi_firm_demo.py`` uses, so one command seeds the
    demo firms and gives them a history. The standalone CLI below is for
    regenerating one firm without rebuilding everything else.
    """
    on = today or date.today()
    target = FirmTarget(
        firm_id=firm_id,
        code=firm_code,
        label=firm_code,
        context=TenantContext(
            firm_id=firm_id,
            deployment_mode=DeploymentMode.SHARED,
            database_name="",
            schema_name="",
            database_type="postgresql",
        ),
    )
    if reset:
        reset_history(session, firm_id)
    return build_for_firm(session, target, years, on)


def main() -> int:
    """Generate history across every firm, or report what would be generated."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        type=int,
        default=2,
        help="How many *prior* financial years to populate, plus the current one.",
    )
    parser.add_argument(
        "--firm",
        action="append",
        help="Limit to one firm code; repeatable. Default is every firm.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete each firm's existing trading history first. Masters are kept.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report and change nothing."
    )
    parser.add_argument("--yes", action="store_true", help="Apply without prompting.")
    args = parser.parse_args()

    if args.years < 0:
        print("--years cannot be negative.", file=sys.stderr)
        return 2

    settings = Settings()
    if settings.environment not in {"development", "test", "local"}:
        print(
            f"Refusing to run against environment '{settings.environment}'. "
            "This script writes business documents.",
            file=sys.stderr,
        )
        return 2

    platform = DatabaseManager(EngineFactory.database_config_from_settings(settings))
    targets = _firm_targets(platform, settings)
    if args.firm:
        wanted = {code.upper() for code in args.firm}
        targets = [target for target in targets if target.code.upper() in wanted]
    if not targets:
        print("No firms matched.", file=sys.stderr)
        return 1

    today = date.today()
    span = _financial_years(args.years, today)
    print(f"Firms: {len(targets)}")
    for target in targets:
        print(f"  - {target.label}")
    print(f"Financial years: {', '.join(str(start.year) for start in span)}")

    if args.dry_run:
        print("\nDry run: nothing written.")
        platform.dispose()
        return 0
    if not args.yes:
        print("\nPass --yes to write. Nothing done.", file=sys.stderr)
        platform.dispose()
        return 1

    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    failures = 0
    try:
        for target in targets:
            manager = provider.manager_for(target.context)
            schema = provider.schema_for(target.context)
            print(f"\n{target.label}")
            with manager.sessions(schema=schema).session() as session:
                if args.reset:
                    removed = reset_history(session, target.firm_id)
                    print(f"  reset: {removed} row(s) removed")
                try:
                    tally = build_for_firm(session, target, args.years, today)
                except BusinessRuleError as error:
                    print(f"  skipped: {error}")
                    failures += 1
                    continue
                print(f"  {tally.line()}")
                for note in tally.skipped[:5]:
                    print(f"  note: {note}")
                if len(tally.skipped) > 5:
                    print(f"  note: ...and {len(tally.skipped) - 5} more")
    finally:
        provider.dispose()
        platform.dispose()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
