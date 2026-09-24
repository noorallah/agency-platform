"""The legacy-row repair: each repair, the dry run, and a second run.

The owner's decision of 2026-09-24 (decided by Claude, industry standard):
rows written before the rule that now forbids them are repaired once, by
``scripts/repair_legacy_rows.py``, whose work is ``repair_store``. One SQLite
database stands in for the shared store, holding two firms.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.legacy_repair import RepairFirm, StoreRepair, repair_store
from app.core.database.base import Base
from app.core.utils.dates import utc_now
from app.customers.models import Customer, CustomerGroup
from app.finance.models import JournalEntry, JournalLine, LedgerAccount
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.inventory.models import InventoryRecord
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.loyalty.schemas import LoyaltySettingsWrite
from app.loyalty.services import LoyaltyService
from app.products.models import Product, ProductCategory


def _session() -> Session:
    """Open one in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class _Store:
    """Two firms in one store, with a legacy row of every kind."""

    def __init__(self) -> None:
        """Seed both firms and the rows the repair is about."""
        self.session = _session()
        self.actor_id = uuid4()
        self.ours = self._firm("REPA")
        self.theirs = self._firm("REPB")
        seed_finance_setup(
            self.session,
            firm_id=self.ours.id,
            year_starts_on=(
                date(utc_now().year, 4, 1)
                if utc_now().month >= 4
                else date(utc_now().year - 1, 4, 1)
            ),
            actor_id=self.actor_id,
        )
        self.session.commit()

    def _firm(self, code: str) -> Firm:
        """Add one firm."""
        firm = Firm(
            name=f"{code} Firm",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.session.add(firm)
        self.session.commit()
        return firm

    @property
    def firms(self) -> list[RepairFirm]:
        """The two firms as the repair sees them."""
        return [
            RepairFirm(id=self.ours.id, code=self.ours.code),
            RepairFirm(id=self.theirs.id, code=self.theirs.code),
        ]

    def customer(
        self,
        code: str,
        *,
        outstanding: str = "0",
        deleted: bool = False,
        group_id: UUID | None = None,
    ) -> Customer:
        """Add one of our customers."""
        row = Customer(
            firm_id=self.ours.id,
            code=code,
            customer_type="BUSINESS",
            name=f"Customer {code}",
            display_name=f"Customer {code}",
            currency_code="INR",
            status="ACTIVE",
            current_outstanding=Decimal(outstanding),
            customer_group_id=group_id,
            is_deleted=deleted,
            deleted_at=utc_now() if deleted else None,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def product(
        self,
        code: str,
        *,
        deleted: bool = False,
        stock: str | None = None,
        category_id: UUID | None = None,
    ) -> Product:
        """Add one of our products, optionally holding stock."""
        row = Product(
            firm_id=self.ours.id,
            code=code,
            name=f"Product {code}",
            product_type="GOODS",
            status="ACTIVE",
            category_id=category_id,
            is_deleted=deleted,
            deleted_at=utc_now() if deleted else None,
        )
        self.session.add(row)
        self.session.flush()
        if stock is not None:
            self.session.add(
                InventoryRecord(
                    firm_id=self.ours.id,
                    branch_id=uuid4(),
                    warehouse_id=uuid4(),
                    storage_locator="MAIN",
                    product_id=row.id,
                    current_quantity=Decimal(stock),
                )
            )
        self.session.commit()
        return row

    def run(self, *, dry_run: bool = False) -> StoreRepair:
        """Run the repair over the store."""
        return repair_store(
            self.session, self.firms, dry_run=dry_run, actor_id=self.actor_id
        )

    def audits(self, action: str) -> int:
        """Count the audit rows written under one action."""
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == action)
            )
            or 0
        )


def test_a_deleted_customer_with_a_balance_is_restored() -> None:
    """A debtor cannot be deleted; one deleted before the guard comes back."""
    store = _Store()
    debtor = store.customer("DEBT", outstanding="500", deleted=True)
    settled = store.customer("PAID", outstanding="0", deleted=True)

    result = store.run()

    store.session.refresh(debtor)
    store.session.refresh(settled)
    assert debtor.is_deleted is False
    assert debtor.deleted_at is None
    assert settled.is_deleted is True, "a customer who owes nothing stays deleted"
    assert [line.split(" (")[0] for line in result.restored_customers] == ["REPA DEBT"]
    assert store.audits("customer.restored") == 1


def test_a_restore_into_a_code_taken_since_is_skipped_by_name() -> None:
    """The service's own restore refuses the clash, and the report says so."""
    store = _Store()
    debtor = store.customer("SAME", outstanding="500", deleted=True)
    store.customer("SAME")

    result = store.run()

    store.session.refresh(debtor)
    assert debtor.is_deleted is True
    assert result.restored_customers == []
    assert len(result.skipped) == 1
    assert "SAME" in result.skipped[0]


def test_a_deleted_product_holding_stock_is_restored() -> None:
    """Stock on the books under a product no screen lists is restored."""
    store = _Store()
    held = store.product("HELD", deleted=True, stock="5")
    empty = store.product("GONE", deleted=True, stock="0")

    result = store.run()

    store.session.refresh(held)
    store.session.refresh(empty)
    assert held.is_deleted is False
    assert empty.is_deleted is True, "a product holding nothing stays deleted"
    assert len(result.restored_products) == 1
    assert store.audits("product.restored") == 1


def test_a_reference_to_another_firms_master_is_cleared() -> None:
    """D-MST-3: another tenant's segment or category becomes NULL."""
    store = _Store()
    their_group = CustomerGroup(firm_id=store.theirs.id, code="HALF", name="Half")
    our_group = CustomerGroup(firm_id=store.ours.id, code="OWN", name="Own")
    their_category = ProductCategory(
        firm_id=store.theirs.id, code="CAT", name="Theirs", path="CAT"
    )
    store.session.add_all([their_group, our_group, their_category])
    store.session.commit()
    borrowed = store.customer("BORROW", group_id=their_group.id)
    own = store.customer("OWN", group_id=our_group.id)
    goods = store.product("GOODS", category_id=their_category.id)

    result = store.run()

    store.session.refresh(borrowed)
    store.session.refresh(own)
    store.session.refresh(goods)
    assert borrowed.customer_group_id is None
    assert own.customer_group_id == our_group.id, "our own segment is left alone"
    assert goods.category_id is None
    assert len(result.cleared_references) == 2
    assert store.audits("customer.foreign_reference_cleared") == 1
    assert store.audits("product.foreign_reference_cleared") == 1


def _goodwill(store: _Store, points: str) -> None:
    """Record goodwill the way it was given before #477: no value, no journal."""
    customer = store.session.scalar(select(Customer).where(Customer.code == "LOYAL"))
    if customer is None:
        customer = store.customer("LOYAL")
    store.session.add(
        LoyaltyEntry(
            firm_id=store.ours.id,
            customer_id=customer.id,
            kind=LoyaltyEntryKind.ADJUSTED.value,
            points=Decimal(points),
            amount=Decimal("0"),
            earned_on=date(2026, 5, 1),
            remarks="Goodwill, before D-SELL-19.",
        )
    )
    store.session.commit()


def _payable(store: _Store) -> Decimal:
    """Return what Loyalty Payable (2600) holds for our firm."""
    total = store.session.scalar(
        select(
            func.coalesce(
                func.sum(JournalLine.credit_amount - JournalLine.debit_amount), 0
            )
        )
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .where(LedgerAccount.firm_id == store.ours.id, LedgerAccount.code == "2600")
    )
    return Decimal(str(total)).quantize(Decimal("0.01"))


def test_goodwill_never_accrued_is_trued_up_once_per_firm() -> None:
    """D-SELL-19: what is still held of legacy goodwill becomes a liability.

    100 points given and 30 taken back, both before the fix, leave 70 held;
    at 2.00 a point that is 140.00, booked Dr 5700 / Cr 2600 in one journal.
    """
    store = _Store()
    LoyaltyService(store.session).write_settings(
        store.ours.id,
        LoyaltySettingsWrite(
            is_enabled=True,
            points_per_amount=Decimal("1"),
            amount_per_point=Decimal("2"),
        ),
        actor_id=store.actor_id,
    )
    _goodwill(store, "100")
    _goodwill(store, "-30")

    result = store.run()

    journal = store.session.scalar(
        select(JournalEntry).where(
            JournalEntry.reference_number == "LOY-GOODWILL-TRUEUP-REPA"
        )
    )
    assert journal is not None
    assert _payable(store) == Decimal("140.00")
    assert result.goodwill_trueups == [
        "REPA LOY-GOODWILL-TRUEUP-REPA: 70.0000 points at 2.0000 = 140.00"
    ]
    assert store.audits("loyalty.goodwill_trued_up") == 1


def test_a_dry_run_changes_nothing_and_reports_everything() -> None:
    """The default: every repair is listed, and the store is as it was."""
    store = _Store()
    debtor = store.customer("DEBT", outstanding="500", deleted=True)
    held = store.product("HELD", deleted=True, stock="5")
    their_group = CustomerGroup(firm_id=store.theirs.id, code="HALF", name="Half")
    store.session.add(their_group)
    store.session.commit()
    borrowed = store.customer("BORROW", group_id=their_group.id)
    LoyaltyService(store.session).write_settings(
        store.ours.id,
        LoyaltySettingsWrite(
            is_enabled=True,
            points_per_amount=Decimal("1"),
            amount_per_point=Decimal("1"),
        ),
        actor_id=store.actor_id,
    )
    _goodwill(store, "50")
    audits_before = store.session.scalar(select(func.count()).select_from(AuditLog))

    result = store.run(dry_run=True)

    store.session.refresh(debtor)
    store.session.refresh(held)
    store.session.refresh(borrowed)
    assert debtor.is_deleted is True
    assert held.is_deleted is True
    assert borrowed.customer_group_id == their_group.id
    assert _payable(store) == Decimal("0.00")
    assert result.changes == 4
    assert any("would restore customer" in line for line in result.lines(dry_run=True))
    assert (
        store.session.scalar(select(func.count()).select_from(AuditLog))
        == audits_before
    )


def test_a_second_run_finds_nothing_to_do() -> None:
    """Idempotent: restored, cleared and trued-up rows are not touched again."""
    store = _Store()
    store.customer("DEBT", outstanding="500", deleted=True)
    store.product("HELD", deleted=True, stock="5")
    their_group = CustomerGroup(firm_id=store.theirs.id, code="HALF", name="Half")
    store.session.add(their_group)
    store.session.commit()
    store.customer("BORROW", group_id=their_group.id)
    LoyaltyService(store.session).write_settings(
        store.ours.id,
        LoyaltySettingsWrite(
            is_enabled=True,
            points_per_amount=Decimal("1"),
            amount_per_point=Decimal("1"),
        ),
        actor_id=store.actor_id,
    )
    _goodwill(store, "50")

    first = store.run()
    second = store.run()

    assert first.changes == 4
    assert second.changes == 0
    assert second.skipped == []
    assert second.lines(dry_run=False) == ["store", "  nothing to repair"]
    assert _payable(store) == Decimal("50.00"), "the true-up is posted once"
