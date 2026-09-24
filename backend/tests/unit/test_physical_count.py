"""Counting a warehouse.

A count is a document rather than an action: the sheet is drawn up from what
the warehouse holds, walked over hours by people with a clipboard, and posted
once at the end. Everything interesting here is about the gap between those two
moments -- stock moves while a warehouse is being counted, and a sheet that
posts what it was drawn up with would undo it.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import BatchRecord
from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.business.models import BusinessProfile, FirmBusinessProfile
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.inventory.models import (
    InventoryRecord,
    InventoryTransaction,
    StockLedgerEntry,
)
from app.inventory.schemas import (
    PhysicalCountCreate,
    PhysicalCountLineWrite,
    PhysicalCountUpdate,
)
from app.inventory.services import InventoryService, PhysicalCountService
from app.products.models import Product

WHEN = date(2026, 8, 20)


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Warehouse:
    """A firm with one warehouse holding ten of one product."""

    def __init__(self, session: Session) -> None:
        """Seed the firm, its chart of accounts, and costed stock."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Count Firm",
            code="COUNT",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
        seed_finance_setup(
            session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        profile = BusinessProfile(
            code="GENERIC",
            name="Generic",
            industry_type="GENERIC",
            status="ACTIVE",
            created_by=self.actor_id,
        )
        session.add(profile)
        session.commit()
        session.add(
            FirmBusinessProfile(
                firm_id=self.firm.id,
                business_profile_id=profile.id,
                is_active=True,
                effective_from=date(2026, 4, 1),
                created_by=self.actor_id,
            )
        )
        self.branch = Branch(
            firm_id=self.firm.id,
            code="HO",
            name="Head Office",
            display_name="Head Office",
            business_profile_id=profile.id,
            working_hours={},
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        session.add(self.branch)
        session.flush()
        self.warehouse = Warehouse(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            code="MAIN",
            name="Main Warehouse",
            display_name="Main Warehouse",
            business_profile_id=profile.id,
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-001",
            name="Enterprise Stock Item",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        session.add_all([self.warehouse, self.product])
        session.commit()
        self.service = InventoryService(session)
        self.service.record_goods_receipt(
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=self.product.id,
            reference_number="GRN-COUNT",
            transaction_date=date(2026, 8, 1),
            total_quantity=Decimal("10"),
            unit_cost=Decimal("25.00"),
        )
        self.counts = PhysicalCountService(session)

    def on_hand(self) -> Decimal:
        """Return what the system currently holds."""
        return Decimal(
            str(
                self.session.scalar(
                    select(InventoryRecord.current_quantity).where(
                        InventoryRecord.product_id == self.product.id
                    )
                )
            )
        )

    def sheet(self, counted: str | None) -> UUID:
        """Open a sheet over the whole warehouse and write one count on it."""
        row = self.counts.create(
            PhysicalCountCreate(
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                count_date=WHEN,
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        if counted is not None:
            self.counts.update(
                row.id,
                PhysicalCountUpdate(
                    lines=[
                        PhysicalCountLineWrite(
                            product_id=self.product.id,
                            counted_quantity=Decimal(counted),
                        )
                    ]
                ),
                firm_id=self.firm.id,
                actor_id=self.actor_id,
            )
            self.session.commit()
        return row.id


def test_a_sheet_is_drawn_up_from_what_the_warehouse_holds() -> None:
    """A counter walks out with the system's list, not a blank page."""
    books = _Warehouse(_session_factory()())
    count_id = books.sheet(None)

    lines = books.counts.lines_for(count_id)
    assert len(lines) == 1
    assert lines[0].product_id == books.product.id
    assert lines[0].expected_quantity == Decimal("10.0000")
    assert lines[0].counted_quantity is None, "nobody has walked it yet"


def test_a_count_that_finds_less_writes_the_difference_off() -> None:
    """And it reaches the ledger, because a variance is an adjustment.

    A count that finds twenty missing cartons puts their value in the profit
    and loss without anybody keying a journal.
    """
    books = _Warehouse(_session_factory()())
    count_id = books.sheet("7")

    books.counts.post(count_id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    line = books.counts.lines_for(count_id)[0]
    assert line.variance_quantity == Decimal("-3.0000")
    assert line.transaction_id is not None
    assert books.on_hand() == Decimal("7.0000"), "the shelf is the truth"

    postings = {
        code: (debit, credit)
        for code, debit, credit in books.session.execute(
            select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
            .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .where(JournalEntry.source_module == "physical_count")
        ).all()
    }
    assert postings["1200"] == (Decimal("0.00"), Decimal("75.00")), "3 at 25.00"
    assert postings["5500"] == (Decimal("75.00"), Decimal("0.00"))


def test_a_batch_line_corrects_the_batch_it_counted() -> None:
    """Not the product's untracked row beside it (D-STK-1).

    The variance is measured against the batch's own stock row, so the
    adjustment has to land there too. Posted without the batch, it moved the
    untracked row instead -- ten loose units became eight while the batch
    that was actually two short still read ten, and the stock ledger and the
    journal described a movement on a row nobody had counted.
    """
    books = _Warehouse(_session_factory()())
    batch = BatchRecord(
        firm_id=books.firm.id,
        product_id=books.product.id,
        batch_number="B-2405",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(batch)
    books.session.commit()
    books.service.record_goods_receipt(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        branch_id=books.branch.id,
        warehouse_id=books.warehouse.id,
        storage_node_id=None,
        product_id=books.product.id,
        reference_number="GRN-BATCH",
        transaction_date=date(2026, 8, 2),
        total_quantity=Decimal("10"),
        unit_cost=Decimal("25.00"),
        batch_id=batch.id,
    )
    books.session.commit()
    sheet = books.counts.create(
        PhysicalCountCreate(
            branch_id=books.branch.id,
            warehouse_id=books.warehouse.id,
            count_date=WHEN,
            lines=[
                PhysicalCountLineWrite(
                    product_id=books.product.id,
                    batch_id=batch.id,
                    counted_quantity=Decimal("8"),
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    books.counts.post(sheet.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    held = {
        row.batch_id: row.current_quantity
        for row in books.session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.product_id == books.product.id
            )
        ).all()
    }
    assert held == {
        batch.id: Decimal("8.0000"),
        None: Decimal("10.0000"),
    }, "the batch counted two short is two short; the loose stock is untouched"

    line = books.counts.lines_for(sheet.id)[0]
    assert line.variance_quantity == Decimal("-2.0000")
    movement = books.session.get(InventoryTransaction, line.transaction_id)
    assert movement is not None
    assert movement.batch_id == batch.id
    entry = books.session.scalar(
        select(StockLedgerEntry).where(StockLedgerEntry.transaction_id == movement.id)
    )
    assert entry is not None
    assert entry.batch_id == batch.id
    assert entry.total_cost == Decimal("50.0000"), "2 at 25.00"
    journal = books.session.scalar(
        select(JournalEntry).where(JournalEntry.source_id == sheet.id)
    )
    assert journal is not None
    assert journal.total_debit == Decimal("50.00")


def test_the_variance_is_measured_when_the_sheet_is_posted() -> None:
    """Not against the snapshot it was drawn up from.

    Stock moves while a warehouse is being counted. A sheet drawn up at 10,
    counted at 10, and posted after 4 were dispatched must write the 4 off --
    posting against the snapshot would say there was no difference and put the
    dispatched stock back.
    """
    books = _Warehouse(_session_factory()())
    count_id = books.sheet("10")

    # Four leave the building while the count is being walked.
    books.service.record_delivery_note_dispatch(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        branch_id=books.branch.id,
        warehouse_id=books.warehouse.id,
        storage_node_id=None,
        product_id=books.product.id,
        reference_number="DN-1",
        transaction_date=WHEN,
        dispatch_quantity=Decimal("4"),
    )
    books.session.commit()
    assert books.on_hand() == Decimal("6.0000")

    books.counts.post(count_id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    line = books.counts.lines_for(count_id)[0]
    assert line.expected_quantity == Decimal("10.0000"), "what we expected, kept"
    assert line.variance_quantity == Decimal("4.0000"), "measured against six"
    assert books.on_hand() == Decimal("10.0000"), "the count is what is there"


def test_a_line_nobody_walked_is_not_a_line_that_found_nothing() -> None:
    """Treating an uncounted line as zero would write off unreached stock.

    And a sheet on which nobody counted anything is not posted at all: it read
    POSTED with nothing adjusted, which says the warehouse was counted and
    agreed when nobody walked it (D-STK-5).
    """
    books = _Warehouse(_session_factory()())
    count_id = books.sheet(None)

    with pytest.raises(ValidationError, match="no counted line"):
        books.counts.post(count_id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.rollback()

    assert books.counts.get(count_id, firm_id=books.firm.id).status == "DRAFT"
    line = books.counts.lines_for(count_id)[0]
    assert line.variance_quantity is None
    assert line.transaction_id is None
    assert books.on_hand() == Decimal("10.0000"), "untouched"


def test_saving_progress_on_a_count_leaves_a_named_audit_row() -> None:
    """Save progress is a write, and the trail says what it wrote (D-STK-6)."""
    books = _Warehouse(_session_factory()())
    count_id = books.sheet("9")

    row = books.session.scalar(
        select(AuditLog).where(
            AuditLog.action == "inventory.physical_count.progress_saved",
            AuditLog.entity_id == count_id,
        )
    )
    assert row is not None
    assert row.after_data is not None
    assert row.after_data["lines_counted"] == "1"


def test_a_count_that_agrees_writes_no_adjustment() -> None:
    """Finding what was expected is the normal outcome and is not an event."""
    books = _Warehouse(_session_factory()())
    count_id = books.sheet("10")

    books.counts.post(count_id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    line = books.counts.lines_for(count_id)[0]
    assert line.variance_quantity == Decimal("0.0000")
    assert line.transaction_id is None, "nothing moved, so nothing was written"


def test_a_posted_sheet_cannot_be_changed_or_posted_again() -> None:
    """The second posting would double every difference the first applied."""
    books = _Warehouse(_session_factory()())
    count_id = books.sheet("8")
    books.counts.post(count_id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    with pytest.raises(ConflictError, match="posted"):
        books.counts.post(count_id, firm_id=books.firm.id, actor_id=books.actor_id)

    with pytest.raises(ConflictError, match="posted"):
        books.counts.update(
            count_id,
            PhysicalCountUpdate(
                lines=[
                    PhysicalCountLineWrite(
                        product_id=books.product.id, counted_quantity=Decimal("1")
                    )
                ]
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_sheet_names_its_products_by_code_and_name() -> None:
    """The person walking the shelf reads a code and a name, not an id.

    The line stores the product's id, and the desktop printed exactly that
    in the Product column -- found on the 2026-09-12 manual pass (plan item
    8.4). The response carries the code and the name beside the id.
    """
    from app.inventory.api.router import _count_response

    books = _Warehouse(_session_factory()())
    count_id = books.sheet(None)
    response = _count_response(
        books.counts, books.counts.get(count_id, firm_id=books.firm.id)
    )
    assert [line.product_code for line in response.lines] == [books.product.code]
    assert [line.product_name for line in response.lines] == [books.product.name]


def test_a_sheet_whose_second_line_fails_writes_nothing() -> None:
    """A count is posted whole or not at all (D-STK-3).

    Each adjustment used to commit on its own, so a sheet whose second line
    failed had already moved the first line's stock and posted its journal,
    while the sheet itself stayed DRAFT. Posting again after fixing the second
    line then measured the first against the stock it had already moved, found
    no difference, and recorded a variance of zero beside a movement and a
    journal written under the sheet's number.

    The session is request-shaped -- no autoflush, and rolled back rather than
    committed when the post raises, which is what the router does.
    """
    books = _Warehouse(_session_factory()(autoflush=False))
    withdrawn = Product(
        firm_id=books.firm.id,
        code="SKU-002",
        name="Withdrawn Item",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(withdrawn)
    books.session.commit()
    sheet = books.counts.create(
        PhysicalCountCreate(
            branch_id=books.branch.id,
            warehouse_id=books.warehouse.id,
            count_date=WHEN,
            lines=[
                PhysicalCountLineWrite(
                    product_id=books.product.id, counted_quantity=Decimal("7")
                ),
                PhysicalCountLineWrite(
                    product_id=withdrawn.id, counted_quantity=Decimal("1")
                ),
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    # Deleted while the sheet was being walked, so its line cannot be posted.
    withdrawn.is_deleted = True
    books.session.commit()

    with pytest.raises(ValidationError, match="Product does not belong"):
        books.counts.post(sheet.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.rollback()

    assert books.on_hand() == Decimal("10.0000"), "the first line moved nothing"
    assert (
        books.session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.reference_number == sheet.count_number
            )
        ).all()
        == []
    ), "no adjustment under the sheet's number"
    assert (
        books.session.scalars(
            select(StockLedgerEntry).where(
                StockLedgerEntry.reference_number == sheet.count_number
            )
        ).all()
        == []
    ), "no stock ledger row"
    assert (
        books.session.scalars(
            select(JournalEntry).where(JournalEntry.source_module == "physical_count")
        ).all()
        == []
    ), "no journal"
    books.session.refresh(sheet)
    assert sheet.status == "DRAFT"
    first = books.counts.lines_for(sheet.id)[0]
    assert first.variance_quantity is None
    assert first.transaction_id is None

    # Leave the withdrawn line uncounted and post again: the first line is
    # adjusted once, against the stock that was really there.
    books.counts.update(
        sheet.id,
        PhysicalCountUpdate(
            lines=[
                PhysicalCountLineWrite(product_id=withdrawn.id, counted_quantity=None)
            ]
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    books.counts.post(sheet.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    first = books.counts.lines_for(sheet.id)[0]
    assert first.variance_quantity == Decimal("-3.0000")
    assert first.transaction_id is not None
    assert books.on_hand() == Decimal("7.0000")
    assert (
        len(
            books.session.scalars(
                select(JournalEntry).where(
                    JournalEntry.source_module == "physical_count"
                )
            ).all()
        )
        == 1
    )


def test_a_count_with_several_differences_posts_one_journal() -> None:
    """D-STK-11: each difference posted a journal under the count's number.

    A journal reference is unique per firm, so a count with two or more
    differences was refused on the second line and could never be posted
    (driven on 2026-09-19: PC-2026-2027-000003 answered 409). The owner chose
    one journal per count: one voucher per stock-take, a pair of lines per
    difference -- a shortage and a surplus each still read on their own.
    """
    books = _Warehouse(_session_factory()(autoflush=False))
    second = Product(
        firm_id=books.firm.id,
        code="SKU-002",
        name="Second Item",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(second)
    books.session.commit()
    books.service.record_goods_receipt(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        branch_id=books.branch.id,
        warehouse_id=books.warehouse.id,
        storage_node_id=None,
        product_id=second.id,
        reference_number="GRN-SECOND",
        transaction_date=date(2026, 8, 1),
        total_quantity=Decimal("4"),
        unit_cost=Decimal("10.00"),
    )
    sheet = books.counts.create(
        PhysicalCountCreate(
            branch_id=books.branch.id,
            warehouse_id=books.warehouse.id,
            count_date=WHEN,
            lines=[
                PhysicalCountLineWrite(
                    product_id=books.product.id, counted_quantity=Decimal("7")
                ),
                PhysicalCountLineWrite(
                    product_id=second.id, counted_quantity=Decimal("6")
                ),
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    books.counts.post(sheet.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    journals = books.session.scalars(
        select(JournalEntry).where(JournalEntry.source_id == sheet.id)
    ).all()
    assert len(journals) == 1, "one voucher for the whole stock-take"
    journal = journals[0]
    assert journal.reference_number == sheet.count_number
    assert len(journal.lines) == 4, "a pair of lines per difference"
    by_account: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for code, debit, credit in books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == journal.id)
    ).all():
        by_account.setdefault(code, []).append((debit, credit))
    # 3 short at 25.00 written off; 2 over at 10.00 taken on.
    assert sorted(by_account["1200"]) == [
        (Decimal("0.00"), Decimal("75.00")),
        (Decimal("20.00"), Decimal("0.00")),
    ]
    assert sorted(by_account["5500"]) == [
        (Decimal("0.00"), Decimal("20.00")),
        (Decimal("75.00"), Decimal("0.00")),
    ]
    assert books.counts.get(sheet.id, firm_id=books.firm.id).status == "POSTED"


def _stock_in_a_bin(books: _Warehouse) -> WarehouseStorageNode:
    """Add a bin to the warehouse and put 5 of the product in it at 25.00.

    The warehouse then holds 10 on its unlocated ROOT row and 5 in BIN-A.
    """
    bin_a = WarehouseStorageNode(
        warehouse_id=books.warehouse.id,
        node_type="BIN",
        code="BIN-A",
        name="Bin A",
        path="/BIN-A",
        is_active=True,
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(bin_a)
    books.session.commit()
    books.service.record_goods_receipt(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        branch_id=books.branch.id,
        warehouse_id=books.warehouse.id,
        storage_node_id=bin_a.id,
        product_id=books.product.id,
        reference_number="GRN-BIN-A",
        transaction_date=date(2026, 8, 2),
        total_quantity=Decimal("5"),
        unit_cost=Decimal("25.00"),
    )
    books.session.commit()
    return bin_a


def _held_by_location(books: _Warehouse) -> dict[UUID | None, Decimal]:
    """Return what each of the product's stock rows holds, by storage node."""
    return {
        row.storage_node_id: row.current_quantity
        for row in books.session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.product_id == books.product.id
            )
        ).all()
    }


def test_a_sheet_draws_a_line_per_storage_location() -> None:
    """D-STK-13: one line per stock row, as the stock is held.

    The same product in ROOT and in BIN-A is two rows, so it is two lines,
    each expecting what its own row holds. Keyed on the product alone, the
    sheet drew two indistinguishable lines each expecting the warehouse's 15,
    and a count written against the product landed on both.
    """
    from app.inventory.api.router import _count_response

    books = _Warehouse(_session_factory()())
    bin_a = _stock_in_a_bin(books)
    count_id = books.sheet(None)

    lines = books.counts.lines_for(count_id)
    assert {line.storage_node_id: line.expected_quantity for line in lines} == {
        None: Decimal("10.0000"),
        bin_a.id: Decimal("5.0000"),
    }

    response = _count_response(
        books.counts, books.counts.get(count_id, firm_id=books.firm.id)
    )
    assert {
        line.storage_node_id: (line.storage_node_code, line.storage_node_name)
        for line in response.lines
    } == {None: (None, None), bin_a.id: ("BIN-A", "Bin A")}


def test_a_bin_counted_short_is_corrected_in_that_bin() -> None:
    """D-STK-13: the bin that was short goes down, and ROOT does not.

    Measured against the whole warehouse and posted onto ROOT, three found in
    BIN-A against five held took two off ROOT -- which could go negative --
    while BIN-A kept the two that were not there. Driven on 2026-09-19:
    PC-2026-2027-000002 in TEST01 left ROOT at 8 and BIN-A at 5.
    """
    books = _Warehouse(_session_factory()(autoflush=False))
    bin_a = _stock_in_a_bin(books)
    count_id = books.sheet(None)
    books.counts.update(
        count_id,
        PhysicalCountUpdate(
            lines=[
                PhysicalCountLineWrite(
                    product_id=books.product.id,
                    storage_node_id=bin_a.id,
                    counted_quantity=Decimal("3"),
                )
            ]
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    books.counts.post(count_id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    assert _held_by_location(books) == {
        None: Decimal("10.0000"),
        bin_a.id: Decimal("3.0000"),
    }, "BIN-A is two short; ROOT, which nobody found wrong, is untouched"
    counted = next(
        line
        for line in books.counts.lines_for(count_id)
        if line.storage_node_id == bin_a.id
    )
    assert counted.variance_quantity == Decimal("-2.0000"), "3 against BIN-A's 5"
    movement = books.session.get(InventoryTransaction, counted.transaction_id)
    assert movement is not None
    assert movement.storage_node_id == bin_a.id
    journals = books.session.scalars(
        select(JournalEntry).where(JournalEntry.source_id == count_id)
    ).all()
    assert len(journals) == 1
    assert journals[0].total_debit == Decimal("50.00"), "2 at 25.00"


def test_a_count_is_written_against_its_location() -> None:
    """A count naming a row the sheet does not hold is refused, not dropped.

    Lines are found again by product, batch and location. A count sent for
    a location the sheet does not hold would otherwise match no line and
    vanish while the save reported success.
    """
    books = _Warehouse(_session_factory()())
    _stock_in_a_bin(books)
    count_id = books.sheet(None)

    with pytest.raises(ValidationError, match="not on"):
        books.counts.update(
            count_id,
            PhysicalCountUpdate(
                lines=[
                    PhysicalCountLineWrite(
                        product_id=books.product.id,
                        storage_node_id=uuid4(),
                        counted_quantity=Decimal("3"),
                    )
                ]
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_named_line_must_be_a_location_of_the_warehouse() -> None:
    """A sheet cannot be drawn up over a bin that is not in its warehouse."""
    books = _Warehouse(_session_factory()())

    with pytest.raises(ValidationError, match="Storage node"):
        books.counts.create(
            PhysicalCountCreate(
                branch_id=books.branch.id,
                warehouse_id=books.warehouse.id,
                count_date=WHEN,
                lines=[
                    PhysicalCountLineWrite(
                        product_id=books.product.id, storage_node_id=uuid4()
                    )
                ],
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
