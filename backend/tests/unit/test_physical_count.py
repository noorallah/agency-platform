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

from app.branches.models import Branch, Warehouse
from app.business.models import BusinessProfile, FirmBusinessProfile
from app.core.database.base import Base
from app.core.exceptions import ConflictError
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.inventory.models import InventoryRecord
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
            .where(JournalEntry.source_module == "inventory")
        ).all()
    }
    assert postings["1200"] == (Decimal("0.00"), Decimal("75.00")), "3 at 25.00"
    assert postings["5500"] == (Decimal("75.00"), Decimal("0.00"))


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
    """Treating an uncounted line as zero would write off unreached stock."""
    books = _Warehouse(_session_factory()())
    count_id = books.sheet(None)

    books.counts.post(count_id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    line = books.counts.lines_for(count_id)[0]
    assert line.variance_quantity is None
    assert line.transaction_id is None
    assert books.on_hand() == Decimal("10.0000"), "untouched"


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
