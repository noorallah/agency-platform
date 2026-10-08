"""What inventory round 1 found over HTTP, held (2026-10-08).

Each test is one finding of
``docs/qa/INVENTORY_API_CHECK_ROUND_1_2026-10-08.md``: a stock row re-pointed
at another product by an edit (F1), a repack and an adjustment taking more
than is there (F3, F4), the firm's and the branch's summary reading no
incoming (F6), a draft opening stock that could not be edited (F7), an export
that ran a name as a formula and stopped at one page (F11, F12), a filter the
list could not read answering 500 (F14) and a pipeline figure with fourteen
decimals (F19).
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.utils.csv_text import csv_text, sheet_text
from app.core.validation.payloads import parse_filters
from app.inventory.models import InventoryRecord
from app.inventory.schemas import (
    InventoryAdjustmentCreate,
    InventoryListFilters,
    InventoryUpdate,
    OpeningStockBatchCreate,
    OpeningStockUpdate,
)
from app.inventory.services import inventory_service as module
from app.inventory.services import pipeline
from app.inventory.services.inventory_service import InventoryService
from app.inventory.services.repacking import RepackService, RepackWrite
from app.products.models import Product
from tests.unit.test_inventory_foundation import (
    _branch_warehouse_product,
    _firm,
    _profile,
    _session_factory,
)

D = Decimal


class _Stocked:
    """A firm holding five of one product in one warehouse."""

    def __init__(self, code: str, *, post: bool = True) -> None:
        self.session: Session = _session_factory()()
        self.firm = _firm(self.session, code)
        profile = _profile(self.session, self.firm.id)
        self.branch, self.warehouse, self.product = _branch_warehouse_product(
            self.session, self.firm, profile
        )
        self.service = InventoryService(self.session)
        self.actor_id = uuid4()
        self.batch = self.service.create_opening_stock_batch(
            OpeningStockBatchCreate(
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                reference_number=f"OS-{code}",
                posting_date=date(2026, 8, 1),
                lines=[{"product_id": self.product.id, "quantity": "5"}],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        if post:
            self.service.post_opening_stock_batch(
                self.batch.id, firm_scope=self.firm.id, actor_id=self.actor_id
            )

    def row(self) -> InventoryRecord:
        return self.session.query(InventoryRecord).one()

    def second_product(self, code: str = "SKU-002") -> Product:
        product = Product(
            firm_id=self.firm.id,
            code=code,
            name="Another Item",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(product)
        self.session.commit()
        return product


def _levels(stocked: _Stocked, **changes: object) -> InventoryUpdate:
    row = stocked.row()
    values: dict[str, object] = {
        "branch_id": row.branch_id,
        "warehouse_id": row.warehouse_id,
        "storage_node_id": row.storage_node_id,
        "product_id": row.product_id,
        "reorder_level": "2",
    }
    values.update(changes)
    return InventoryUpdate.model_validate(values)


def test_an_edit_of_a_stock_row_cannot_make_it_another_product() -> None:
    stocked = _Stocked("F1A")
    other = stocked.second_product()
    row = stocked.row()
    with pytest.raises(ValidationError, match="Move the goods with a transfer"):
        stocked.service.update_inventory_record(
            row.id,
            _levels(stocked, product_id=other.id),
            firm_scope=stocked.firm.id,
            actor_id=stocked.actor_id,
        )
    stocked.session.rollback()
    assert stocked.row().product_id == stocked.product.id


def test_an_edit_of_a_stock_row_still_changes_its_levels() -> None:
    stocked = _Stocked("F1B")
    row = stocked.row()
    saved = stocked.service.update_inventory_record(
        row.id, _levels(stocked), firm_scope=stocked.firm.id, actor_id=stocked.actor_id
    )
    assert saved.reorder_level == D("2")
    assert saved.current_quantity == D("5")


def _adjust(stocked: _Stocked, quantity: str, reference: str) -> None:
    stocked.service.create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=stocked.branch.id,
            warehouse_id=stocked.warehouse.id,
            product_id=stocked.product.id,
            quantity=D(quantity),
            reference_number=reference,
            transaction_date=date(2026, 8, 2),
        ),
        firm_scope=stocked.firm.id,
        actor_id=stocked.actor_id,
    )


def test_an_adjustment_cannot_take_off_more_than_is_held() -> None:
    stocked = _Stocked("F4A")
    with pytest.raises(ValidationError, match="holds 5, so 8 cannot"):
        _adjust(stocked, "-8", "ADJ-F4")
    stocked.session.rollback()
    assert stocked.row().current_quantity == D("5")
    # Everything that is there may be taken off, promised to an order or not.
    _adjust(stocked, "-5", "ADJ-F4-ALL")
    assert stocked.row().current_quantity == D("0")


def test_a_product_allowed_below_zero_still_goes_below_zero() -> None:
    stocked = _Stocked("F4B")
    stocked.product.allow_negative_stock = True
    stocked.session.commit()
    _adjust(stocked, "-8", "ADJ-F4-NEG")
    assert stocked.row().current_quantity == D("-3")


def test_a_repack_cannot_consume_more_than_is_free() -> None:
    stocked = _Stocked("F3")
    pack = stocked.second_product("PACK")
    with pytest.raises(ValidationError, match="has free 5, so 999 cannot"):
        RepackService(stocked.session).post(
            RepackWrite(
                repack_date=date(2026, 8, 12),
                branch_id=stocked.branch.id,
                warehouse_id=stocked.warehouse.id,
                lines=[
                    {
                        "kind": "CONSUME",
                        "product_id": stocked.product.id,
                        "quantity": "999",
                    },
                    {"kind": "PRODUCE", "product_id": pack.id, "quantity": "1"},
                ],
            ),
            firm_id=stocked.firm.id,
            actor_id=stocked.actor_id,
        )
    stocked.session.rollback()
    assert stocked.row().current_quantity == D("5")


def test_the_firm_and_the_branch_carry_what_is_coming_and_going(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stocked = _Stocked("F6")
    key = (stocked.warehouse.id, stocked.product.id)
    monkeypatch.setattr(pipeline, "incoming", lambda *_, **__: {key: D("7")})
    monkeypatch.setattr(
        pipeline, "outgoing", lambda *_, **__: {key: D("2.00000000000000")}
    )
    (firm_row,) = stocked.service.stock_by_firm(firm_scope=stocked.firm.id)
    (branch_row,) = stocked.service.stock_by_branch(firm_scope=stocked.firm.id)
    (warehouse_row,) = stocked.service.stock_by_warehouse(firm_scope=stocked.firm.id)
    for summary in (firm_row, branch_row, warehouse_row):
        assert (
            summary.incoming_quantity,
            summary.outgoing_quantity,
            summary.projected_quantity,
        ) == (D("7"), D("2"), D("10"))
        # Four places, like every other quantity (F19).
        assert str(summary.outgoing_quantity) == "2.0000"


def test_a_draft_opening_stock_can_be_edited() -> None:
    stocked = _Stocked("F7", post=False)
    saved = stocked.service.update_opening_stock_batch(
        stocked.batch.id,
        OpeningStockUpdate(
            branch_id=stocked.branch.id,
            warehouse_id=stocked.warehouse.id,
            reference_number="OS-F7",
            posting_date=date(2026, 8, 1),
            lines=[{"product_id": stocked.product.id, "quantity": "6"}],
        ),
        firm_scope=stocked.firm.id,
        actor_id=stocked.actor_id,
    )
    assert [line.quantity for line in saved.lines] == [D("6")]


def test_a_name_is_shown_in_an_export_and_never_run() -> None:
    assert sheet_text("=1+1 probe") == "'=1+1 probe"
    assert sheet_text("@cmd") == "'@cmd"
    assert sheet_text("Soap 100 g") == "Soap 100 g"
    assert sheet_text(None) == ""
    assert csv_text('Tea, "gold"') == '"Tea, ""gold"""'
    stocked = _Stocked("F11")
    stocked.product.name = "=1+1, export probe"
    stocked.session.commit()
    text = stocked.service.export_inventory_csv(firm_scope=stocked.firm.id, search=None)
    assert '"\'=1+1, export probe"' in text.splitlines()[1]


def test_an_export_reads_past_its_first_page(monkeypatch: pytest.MonkeyPatch) -> None:
    stocked = _Stocked("F12")
    for number in range(3):
        product = stocked.second_product(f"SKU-9{number}")
        stocked.service.create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=stocked.branch.id,
                warehouse_id=stocked.warehouse.id,
                product_id=product.id,
                quantity=D("1"),
                reference_number=f"ADJ-F12-{number}",
                transaction_date=date(2026, 8, 2),
            ),
            firm_scope=stocked.firm.id,
            actor_id=stocked.actor_id,
        )
    monkeypatch.setattr(module, "EXPORT_PAGE_SIZE", 2)
    stock = stocked.service.export_inventory_csv(
        firm_scope=stocked.firm.id, search=None
    )
    ledger = stocked.service.export_ledger_csv(firm_scope=stocked.firm.id, search=None)
    assert len(stock.splitlines()) == 1 + 4
    assert len(ledger.splitlines()) == 1 + 4


def test_a_filter_that_cannot_be_read_is_refused_by_name() -> None:
    with pytest.raises(ValidationError, match="A filter could not be read. status"):
        parse_filters(InventoryListFilters, {"status": "NOT-A-STATUS"})
    assert parse_filters(InventoryListFilters, {"status": None}).status is None
