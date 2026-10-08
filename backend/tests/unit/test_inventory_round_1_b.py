"""Inventory round 1, second half: what the HTTP check found and what stops it.

Each test is one finding of ``docs/qa/INVENTORY_API_CHECK_ROUND_1_2026-10-08``:

* **F2** a batch, lot or serial number that stock or a document still names
  cannot be deleted; one typed by mistake and never used still can.
* **F20 / D-STK-18** the batch summary card counts near-expiry and expired
  batches only where stock is left, as the expiry dashboard does.
* **F17** a batch, lot or serial number made of spaces is refused.
* **F8** a count sheet or a count plan refuses a warehouse, product or batch
  that is not the firm's, and a warehouse under another branch.
* **F9** a stock adjustment reason posts to an expense account kept for stock
  differences, never to Inventory, Cash, Payables or Sales.
* **F10** a goods receipt refuses an expiry before the manufacturing date, in
  the batch master's own words.
* **F15** a count, a count plan and a reason refuse a save aimed at an older
  version when the caller says which one it read.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import (
    BatchRecord,
    DocumentLineSerial,
    SerialNumber,
)
from app.batch_serial.schemas.batch_serial import (
    BatchCreate,
    BatchUpdate,
    LotCreate,
    LotUpdate,
    SerialCreate,
    SerialUpdate,
)
from app.batch_serial.services import BatchSerialService
from app.branches.models import Branch, Warehouse
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import business_today
from app.finance.models import FirmControlAccount, LedgerAccount
from app.finance.services.control_accounts import ControlAccountPurpose
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.models import InventoryRecord
from app.inventory.schemas import (
    PhysicalCountCreate,
    PhysicalCountLineWrite,
    PhysicalCountUpdate,
)
from app.inventory.services.adjustment_reasons import (
    AdjustmentReasonService,
    AdjustmentReasonWrite,
)
from app.inventory.services.count_planning import CountPlanService, CountPlanWrite
from app.products.models import Product
from tests.unit import test_batch_serial_expiry as registers
from tests.unit import test_goods_receipt as receipts
from tests.unit import test_physical_count as counts
from tests.unit.test_purchase_chain_synthesis import _Firm

WHEN = date(2026, 8, 20)


class _Register:
    """A firm with one fully tracked product, a warehouse and the service."""

    def __init__(self, code: str) -> None:
        """Build the firm and its masters on a fresh database."""
        self.session: Session = registers._session_factory()()
        self.firm = registers._firm(self.session, code)
        self.product = registers._product(self.session, self.firm.id)
        self.warehouse = registers._warehouse(
            self.session, self.firm.id, registers._branch(self.session, self.firm.id).id
        )
        self.actor_id = uuid4()
        self.service = BatchSerialService(self.session)

    def batch(self, number: str, expiry: date | None = None) -> BatchRecord:
        """Record one batch of the product."""
        return self.service.create_batch(
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
            data=BatchCreate(
                product_id=self.product.id, batch_number=number, expiry_date=expiry
            ),
        )

    def serial(self, number: str, **more: object) -> SerialNumber:
        """Record one serial number of the product by hand."""
        return self.service.create_serial(
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
            data=SerialCreate.model_validate(
                {"product_id": self.product.id, "serial_number": number} | more
            ),
        )

    def stock_row(self, batch: BatchRecord) -> InventoryRecord:
        """Return the stock row a batch is held in."""
        row = self.session.scalar(
            select(InventoryRecord).where(InventoryRecord.batch_id == batch.id)
        )
        assert row is not None
        return row


# ── F2: deleting what stock still names ──────────────────────────────────────


def test_a_batch_holding_stock_cannot_be_deleted() -> None:
    """The stock row stayed behind under a batch no screen listed."""
    books = _Register("R1BA")
    batch = books.batch("HELD-1")
    registers._stock(books.session, books.warehouse, batch, "5")

    with pytest.raises(ValidationError, match="Batch HELD-1 still holds stock"):
        books.service.delete_batch(
            firm_scope=books.firm.id, actor_id=books.actor_id, batch_id=batch.id
        )

    assert books.service.get_batch(firm_scope=books.firm.id, batch_id=batch.id)


def test_a_batch_that_has_moved_and_is_now_empty_cannot_be_deleted() -> None:
    """An emptied batch is history; its status is what changes, not its row."""
    books = _Register("R1BB")
    batch = books.batch("SOLD-OUT")
    registers._stock(books.session, books.warehouse, batch, "0")

    with pytest.raises(
        ValidationError,
        match="Batch SOLD-OUT has stock movements recorded against it",
    ) as refusal:
        books.service.delete_batch(
            firm_scope=books.firm.id, actor_id=books.actor_id, batch_id=batch.id
        )

    assert "Change its status instead" in str(refusal.value)


def test_a_batch_a_serial_number_is_filed_under_cannot_be_deleted() -> None:
    """A document that names the batch holds it as surely as stock does."""
    books = _Register("R1BC")
    batch = books.batch("WITH-UNIT")
    books.serial("UNIT-1", batch_id=batch.id)

    with pytest.raises(ValidationError, match=r"named on other records \(serial"):
        books.service.delete_batch(
            firm_scope=books.firm.id, actor_id=books.actor_id, batch_id=batch.id
        )


def test_a_batch_typed_by_mistake_and_never_used_can_still_be_deleted() -> None:
    """The guard must not turn a typing mistake into a permanent record."""
    books = _Register("R1BD")
    batch = books.batch("MISTAKE")

    books.service.delete_batch(
        firm_scope=books.firm.id, actor_id=books.actor_id, batch_id=batch.id
    )

    with pytest.raises(ResourceNotFoundError):
        books.service.get_batch(firm_scope=books.firm.id, batch_id=batch.id)


def test_a_serial_number_a_document_carried_cannot_be_deleted() -> None:
    """Deleting a received unit left the quantity and the serial count apart."""
    books = _Register("R1SA")
    unit = books.serial("RCVD-1")
    books.session.add(
        DocumentLineSerial(
            firm_id=books.firm.id,
            serial_id=unit.id,
            document_type="GOODS_RECEIPT",
            document_id=uuid4(),
            document_line_id=uuid4(),
            line_number=1,
        )
    )
    books.session.commit()

    with pytest.raises(
        ValidationError,
        match="Serial number RCVD-1 has been received or moved on a document",
    ):
        books.service.delete_serial(
            firm_scope=books.firm.id, actor_id=books.actor_id, serial_id=unit.id
        )


def test_a_serial_number_counted_in_stock_cannot_be_deleted() -> None:
    """A unit pointing at a stocked row is on the shelf, whoever recorded it."""
    books = _Register("R1SB")
    batch = books.batch("SHELF")
    registers._stock(books.session, books.warehouse, batch, "1")
    unit = books.serial("ONHAND-1", inventory_id=books.stock_row(batch).id)

    with pytest.raises(
        ValidationError, match="Serial number ONHAND-1 is counted in stock"
    ):
        books.service.delete_serial(
            firm_scope=books.firm.id, actor_id=books.actor_id, serial_id=unit.id
        )


def test_a_serial_number_typed_by_mistake_can_still_be_deleted() -> None:
    """No document, no stock: nothing is lost by removing it."""
    books = _Register("R1SC")
    unit = books.serial("TYPO-1")

    books.service.delete_serial(
        firm_scope=books.firm.id, actor_id=books.actor_id, serial_id=unit.id
    )

    with pytest.raises(ResourceNotFoundError):
        books.service.get_serial(firm_scope=books.firm.id, serial_id=unit.id)


def test_a_pick_taken_back_off_a_draft_does_not_hold_the_serial() -> None:
    """A soft-deleted pick names nothing, so the unit can still be removed."""
    books = _Register("R1SD")
    unit = books.serial("PICKED-1")
    books.session.add(
        DocumentLineSerial(
            firm_id=books.firm.id,
            serial_id=unit.id,
            document_type="DELIVERY_NOTE",
            document_id=uuid4(),
            document_line_id=uuid4(),
            line_number=1,
            is_deleted=True,
        )
    )
    books.session.commit()

    books.service.delete_serial(
        firm_scope=books.firm.id, actor_id=books.actor_id, serial_id=unit.id
    )


def test_a_lot_another_lot_was_split_from_cannot_be_deleted() -> None:
    """A parent lot is named by its children; an unused lot still goes."""
    books = _Register("R1LA")

    def lot(number: str, parent: UUID | None = None) -> UUID:
        """Record one lot and return its id."""
        return books.service.create_lot(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            data=LotCreate(
                product_id=books.product.id, lot_number=number, parent_lot_id=parent
            ),
        ).id

    parent = lot("PARENT")
    child = lot("CHILD", parent)

    with pytest.raises(ValidationError, match="Lot PARENT is named on other records"):
        books.service.delete_lot(
            firm_scope=books.firm.id, actor_id=books.actor_id, lot_id=parent
        )
    books.service.delete_lot(
        firm_scope=books.firm.id, actor_id=books.actor_id, lot_id=child
    )
    books.service.delete_lot(
        firm_scope=books.firm.id, actor_id=books.actor_id, lot_id=parent
    )


# ── F20 / D-STK-18: the summary card and the dashboard agree ─────────────────


def test_the_summary_card_counts_only_batches_that_still_hold_stock() -> None:
    """An emptied near-expiry batch read 1 on the card and 0 on the dashboard."""
    books = _Register("R1SM")
    today = business_today("IN")
    for number, expiry, quantity in (
        ("SOON-HELD", today + timedelta(days=5), "3"),
        ("SOON-EMPTY", today + timedelta(days=5), "0"),
        ("SOON-NEVER", today + timedelta(days=5), None),
        ("PAST-HELD", today - timedelta(days=5), "2"),
        ("PAST-EMPTY", today - timedelta(days=5), "0"),
    ):
        batch = books.batch(number, expiry)
        if quantity is not None:
            registers._stock(books.session, books.warehouse, batch, quantity)

    summary = books.service.batch_summary(firm_scope=books.firm.id)
    dashboard = books.service.expiry_dashboard(firm_scope=books.firm.id)

    assert summary.total_batches == 5, "the register itself is still counted whole"
    assert (summary.near_expiry, summary.expired) == (1, 1)
    assert summary.near_expiry == dashboard.expire_in_30_days
    assert summary.expired == dashboard.total_expired


# ── F17: a number made of spaces ─────────────────────────────────────────────


def test_a_batch_number_of_spaces_is_refused_on_create_and_on_update() -> None:
    """One space satisfied the schema's one-character minimum."""
    books = _Register("R1BL")

    with pytest.raises(ValidationError, match="Batch number is required"):
        books.batch("   ")
    kept = books.batch("  B-KEEP  ")
    assert kept.batch_number == "B-KEEP", "and a real number is stored trimmed"
    with pytest.raises(ValidationError, match="Batch number is required"):
        books.service.update_batch(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            batch_id=kept.id,
            data=BatchUpdate(batch_number="  "),
        )
    assert kept.batch_number == "B-KEEP"


def test_a_lot_or_serial_number_of_spaces_is_refused() -> None:
    """The lot and the serial register had the same hole."""
    books = _Register("R1LS")

    with pytest.raises(ValidationError, match="Lot number is required"):
        books.service.create_lot(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            data=LotCreate(product_id=books.product.id, lot_number="  "),
        )
    with pytest.raises(ValidationError, match="Serial number is required"):
        books.serial("   ")
    lot = books.service.create_lot(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        data=LotCreate(product_id=books.product.id, lot_number="L-1"),
    )
    with pytest.raises(ValidationError, match="Lot number is required"):
        books.service.update_lot(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            lot_id=lot.id,
            data=LotUpdate(lot_number=" "),
        )
    unit = books.serial("S-1")
    with pytest.raises(ValidationError, match="Serial number is required"):
        books.service.update_serial(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            serial_id=unit.id,
            data=SerialUpdate(serial_number=" "),
        )


# ── F8: a count names only the firm's own places and goods ───────────────────


def _other_firms(books: counts._Warehouse) -> tuple[Warehouse, Product, Warehouse]:
    """Add another firm's warehouse and product, and a second branch's warehouse.

    Returns the other firm's warehouse, the other firm's product, and this
    firm's warehouse under a branch other than ``books.branch``.
    """
    other_firm_id = uuid4()
    session = books.session

    def branch(firm_id: UUID, code: str) -> Branch:
        """Add one branch."""
        row = Branch(
            firm_id=firm_id,
            code=code,
            name=code,
            display_name=code,
            working_hours={},
            status="ACTIVE",
            created_by=books.actor_id,
            updated_by=books.actor_id,
        )
        session.add(row)
        session.flush()
        return row

    def warehouse(firm_id: UUID, branch_id: UUID, code: str) -> Warehouse:
        """Add one warehouse under a branch."""
        row = Warehouse(
            firm_id=firm_id,
            branch_id=branch_id,
            code=code,
            name=code,
            display_name=code,
            status="ACTIVE",
            created_by=books.actor_id,
            updated_by=books.actor_id,
        )
        session.add(row)
        session.flush()
        return row

    foreign = warehouse(other_firm_id, branch(other_firm_id, "OTH").id, "OTHW")
    second = warehouse(books.firm.id, branch(books.firm.id, "BR2").id, "WH2")
    product = Product(
        firm_id=other_firm_id,
        code="SKU-OTHER",
        name="Another firm's item",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    session.add(product)
    session.commit()
    return foreign, product, second


def _open(
    books: counts._Warehouse,
    *,
    warehouse_id: UUID | None = None,
    lines: list[PhysicalCountLineWrite] | None = None,
) -> object:
    """Open a count sheet on the books' branch."""
    return books.counts.create(
        PhysicalCountCreate(
            branch_id=books.branch.id,
            warehouse_id=warehouse_id or books.warehouse.id,
            count_date=WHEN,
            lines=lines or [],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )


def test_a_count_refuses_a_warehouse_that_is_not_under_the_branch_named() -> None:
    """Another firm's warehouse, and this firm's under a different branch."""
    books = counts._Warehouse(counts._session_factory()())
    foreign, _, second = _other_firms(books)

    for warehouse in (foreign, second):
        with pytest.raises(
            ValidationError, match="Warehouse does not belong to the selected branch"
        ):
            _open(books, warehouse_id=warehouse.id)

    assert _open(books) is not None, "the firm's own warehouse still opens a sheet"


def test_a_count_refuses_a_line_naming_another_firms_product_or_batch() -> None:
    """The post was refused later for the product; the sheet said nothing."""
    books = counts._Warehouse(counts._session_factory()())
    _, product, _ = _other_firms(books)
    stranger = BatchRecord(
        firm_id=books.firm.id,
        product_id=product.id,
        batch_number="NOT-MINE",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(stranger)
    books.session.commit()

    with pytest.raises(ValidationError, match="Line 2 names a product that is not"):
        _open(
            books,
            lines=[
                PhysicalCountLineWrite(product_id=books.product.id),
                PhysicalCountLineWrite(product_id=product.id),
            ],
        )
    with pytest.raises(ValidationError, match="Line 1 names a batch that is not"):
        _open(
            books,
            lines=[
                PhysicalCountLineWrite(
                    product_id=books.product.id, batch_id=stranger.id
                )
            ],
        )
    books.product.is_deleted = True
    books.session.commit()
    with pytest.raises(ValidationError, match="Line 1 names a product that is not"):
        _open(books, lines=[PhysicalCountLineWrite(product_id=books.product.id)])


def _plan(books: counts._Warehouse, warehouse_id: UUID) -> CountPlanWrite:
    """Describe a weekly plan over one warehouse of the books' branch."""
    return CountPlanWrite(
        name="Weekly",
        branch_id=books.branch.id,
        warehouse_id=warehouse_id,
        frequency_days=7,
    )


def test_a_count_plan_refuses_a_warehouse_that_is_not_the_firms() -> None:
    """A plan was saved over a place its sheet could never be drawn from."""
    books = counts._Warehouse(counts._session_factory()())
    foreign, _, second = _other_firms(books)
    plans = CountPlanService(books.session)

    for warehouse in (foreign, second):
        with pytest.raises(
            ValidationError, match="Warehouse does not belong to the selected branch"
        ):
            plans.create(
                _plan(books, warehouse.id),
                firm_id=books.firm.id,
                actor_id=books.actor_id,
            )
    plan = plans.create(
        _plan(books, books.warehouse.id), firm_id=books.firm.id, actor_id=books.actor_id
    )
    with pytest.raises(
        ValidationError, match="Warehouse does not belong to the selected branch"
    ):
        plans.update(
            plan.id,
            _plan(books, foreign.id),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    with pytest.raises(ValidationError, match="Storage node does not belong"):
        plans.update(
            plan.id,
            _plan(books, books.warehouse.id).model_copy(
                update={"storage_node_id": uuid4()}
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    sheet = plans.draw_sheet(
        plan.id, count_date=WHEN, firm_id=books.firm.id, actor_id=books.actor_id
    )
    assert len(books.counts.lines_for(sheet.id)) == 1, "a good plan still draws"


# ── F9: where a reason may post ──────────────────────────────────────────────


def _books() -> _Firm:
    """Build a firm with its chart of accounts and control accounts seeded."""
    return _Firm(registers._session_factory()(), code="R1RS")


def _control(firm: _Firm, purpose: ControlAccountPurpose) -> UUID:
    """Return the account the firm posts one purpose to."""
    account = firm.session.scalar(
        select(FirmControlAccount.ledger_account_id).where(
            FirmControlAccount.firm_id == firm.firm.id,
            FirmControlAccount.purpose == purpose.value,
        )
    )
    assert account is not None
    return account


def _reason(firm: _Firm, code: str, account_id: UUID) -> object:
    """Add one reason pointed at an account."""
    return AdjustmentReasonService(firm.session).create(
        AdjustmentReasonWrite(code=code, name=code, ledger_account_id=account_id),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


@pytest.mark.parametrize(
    ("purpose", "says"),
    [
        (ControlAccountPurpose.INVENTORY, "is an asset account"),
        (ControlAccountPurpose.CASH, "is an asset account"),
        (ControlAccountPurpose.ACCOUNTS_PAYABLE, "is a liability account"),
        (ControlAccountPurpose.SALES_REVENUE, "is the firm's Sales revenue account"),
        (
            ControlAccountPurpose.COST_OF_GOODS_SOLD,
            "is the firm's Cost of goods sold account",
        ),
    ],
)
def test_a_reason_cannot_post_to_a_balance_sheet_or_trading_account(
    purpose: ControlAccountPurpose, says: str
) -> None:
    """Pointed at Inventory a write-off lowered the valuation and not the books."""
    firm = _books()
    account = firm.session.get(LedgerAccount, _control(firm, purpose))
    assert account is not None

    with pytest.raises(ValidationError) as refusal:
        _reason(firm, "WRONG", account.id)

    message = str(refusal.value)
    assert says in message
    assert f"{account.code} {account.name}" in message, "the account is named"
    assert "expense account" in message, "and the kind that is needed"


@pytest.mark.parametrize(
    "purpose",
    [
        ControlAccountPurpose.INVENTORY_ADJUSTMENT,
        ControlAccountPurpose.INTERNAL_USE,
        ControlAccountPurpose.STAFF_WELFARE,
        ControlAccountPurpose.SAMPLES_AND_DISPLAY,
        ControlAccountPurpose.PROMOTIONAL_EXPENSE,
    ],
)
def test_a_reason_may_post_where_stock_differences_already_do(
    purpose: ControlAccountPurpose,
) -> None:
    """The accounts the seeded reasons use are control accounts, and stay allowed."""
    firm = _books()

    reason = _reason(firm, "FINE", _control(firm, purpose))

    assert reason.ledger_account_id == _control(firm, purpose)  # type: ignore[attr-defined]


def test_a_reason_may_post_to_an_expense_account_of_the_firms_own() -> None:
    """An ordinary expense account no control purpose uses is the usual choice."""
    firm = _books()
    like = firm.session.get(
        LedgerAccount, _control(firm, ControlAccountPurpose.STAFF_WELFARE)
    )
    assert like is not None
    own = LedgerAccount(
        firm_id=firm.firm.id,
        account_group_id=like.account_group_id,
        code="6999",
        name="Breakage in Transit",
        account_type="EXPENSE",
        is_balance_sheet=False,
        is_profit_loss=True,
        created_by=firm.actor_id,
        updated_by=firm.actor_id,
    )
    firm.session.add(own)
    firm.session.commit()

    reason = _reason(firm, "BREAKAGE", own.id)

    assert reason.ledger_account_name == "Breakage in Transit"  # type: ignore[attr-defined]


# ── F10: a receipt's dates in the batch master's words ───────────────────────


def _receive(fixture: receipts._Fixture, **line: object) -> object:
    """Create a draft receipt with the first line overridden."""
    payload = fixture.receipt_payload("4")
    data = payload.model_dump()
    data["lines"][0].update(line)
    return GoodsReceiptService(fixture.session).create_receipt(
        type(payload).model_validate(data),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


@pytest.mark.typed_document_numbers
def test_a_receipt_refuses_an_expiry_before_the_manufacturing_date() -> None:
    """The batch master refused these dates and the receipt made the batch."""
    fixture = receipts._Fixture(receipts._session_factory()(), "R1GR")
    fixture.product.track_expiry = True
    fixture.product.track_manufacturing_date = True
    fixture.session.commit()

    with pytest.raises(ValidationError) as refusal:
        _receive(
            fixture,
            batch_number="B-BACKWARDS",
            manufacturing_date=date(2026, 8, 10),
            expiry_date=date(2026, 8, 5),
        )

    assert str(refusal.value) == (
        "The expiry date 2026-08-05 is before the manufacturing date "
        "2026-08-10. Check the two dates."
    )
    assert (
        fixture.session.scalar(
            select(BatchRecord).where(BatchRecord.batch_number == "B-BACKWARDS")
        )
        is None
    )


@pytest.mark.typed_document_numbers
def test_a_receipt_still_takes_the_same_day_and_no_dates_at_all() -> None:
    """Only the contradiction is refused; a receipt with no dates still saves."""
    fixture = receipts._Fixture(receipts._session_factory()(), "R1GS")
    fixture.product.track_expiry = True
    fixture.product.track_manufacturing_date = True
    fixture.session.commit()

    same_day = _receive(
        fixture,
        batch_number="B-SAME",
        manufacturing_date=date(2026, 8, 5),
        expiry_date=date(2026, 8, 5),
    )

    assert same_day is not None


def test_a_batch_made_from_a_delivery_is_held_to_the_same_order() -> None:
    """Opening stock reaches the same resolver, so it is guarded there too."""
    books = _Register("R1RV")

    with pytest.raises(ValidationError, match="is before the manufacturing date"):
        books.service.resolve_for_receipt(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            product_id=books.product.id,
            batch_number="B-OPEN",
            manufacturing_date=date(2026, 8, 10),
            expiry_date=date(2026, 8, 5),
        )


# ── F15: a save aimed at an older version ────────────────────────────────────


def test_a_reason_a_plan_and_a_count_refuse_a_stale_version() -> None:
    """Each update takes the version the caller read; silence is still accepted."""
    books = counts._Warehouse(counts._session_factory()())
    firm_id, actor_id = books.firm.id, books.actor_id

    reasons = AdjustmentReasonService(books.session)
    reason = reasons.create(
        AdjustmentReasonWrite(code="MINE", name="Mine"),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    renamed = reasons.update(
        reason.id,
        AdjustmentReasonWrite(code="MINE", name="Mine, renamed"),
        firm_id=firm_id,
        actor_id=actor_id,
        expected_version=reason.version,
    )
    assert renamed.version > reason.version
    with pytest.raises(ConflictError):
        reasons.update(
            reason.id,
            AdjustmentReasonWrite(code="MINE", name="Laid over"),
            firm_id=firm_id,
            actor_id=actor_id,
            expected_version=reason.version,
        )

    plans = CountPlanService(books.session)
    plan = plans.create(
        _plan(books, books.warehouse.id), firm_id=firm_id, actor_id=actor_id
    )
    with pytest.raises(ConflictError):
        plans.update(
            plan.id,
            _plan(books, books.warehouse.id),
            firm_id=firm_id,
            actor_id=actor_id,
            expected_version=plan.version + 1,
        )
    assert plans.update(
        plan.id, _plan(books, books.warehouse.id), firm_id=firm_id, actor_id=actor_id
    ), "no version named is still accepted"

    sheet_id = books.sheet(None)
    sheet = books.counts.get(sheet_id, firm_id=firm_id)
    counted = PhysicalCountUpdate(
        lines=[
            PhysicalCountLineWrite(
                product_id=books.product.id, counted_quantity=Decimal("9")
            )
        ]
    )
    with pytest.raises(ConflictError):
        books.counts.update(
            sheet_id,
            counted,
            firm_id=firm_id,
            actor_id=actor_id,
            expected_version=sheet.version + 1,
        )
    books.counts.update(
        sheet_id,
        counted,
        firm_id=firm_id,
        actor_id=actor_id,
        expected_version=sheet.version,
    )


# ── S6: a warranty that ends before it starts ────────────────────────────────


def test_a_warranty_cannot_end_before_it_starts() -> None:
    """Seen on the serial form and over HTTP in the screen round."""
    books = _Register("R1WA")
    with pytest.raises(ValidationError, match="warranty end 2026-01-01 is before"):
        books.serial("WAR-1", warranty_start="2026-06-01", warranty_end="2026-01-01")
    books.session.rollback()
    unit = books.serial("WAR-2", warranty_start="2026-06-01")
    with pytest.raises(ValidationError, match="is before the warranty start"):
        books.service.update_serial(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            serial_id=unit.id,
            data=SerialUpdate.model_validate({"warranty_end": "2026-05-01"}),
        )
