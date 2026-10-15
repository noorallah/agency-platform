"""Stock rows carry the item's pack where a box switch is on (L5, step 11).

A stock screen shows "7 x 12 + 5" with no call of its own, so each stock row
answers ``pack_size`` and ``pack_unit_code`` -- the item's selling pack on the
firm's today -- but only where the firm has switched boxes and pieces on for
selling or for buying. Everywhere else, and for an item with no pack, both
are null (``docs/design/BOX_AND_PIECE_LINE_DESIGN.md``).
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.batch_serial.models import BatchRecord
from app.batch_serial.services import BatchSerialService
from app.inventory.api.router import _count_response, stock_statement, stock_valuation
from app.inventory.models import InventoryRecord, StockLedgerEntry
from app.inventory.schemas import InventoryAdjustmentCreate, PhysicalCountCreate
from app.inventory.services import InventoryService, PhysicalCountService
from app.products.models import Product
from app.purchase.api.router import below_reorder_level
from app.purchase.models import PurchaseWorkflowSettings
from app.sales_order.models import SalesWorkflowSettings
from app.uom.models import ConversionRule, Uom
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session

_BOXED = "SKU-001"
_PLAIN = "SKU-PLAIN"


class _Stock:
    """A firm holding a boxed item (12 to a box) and a plain one, both in stock."""

    def __init__(self, *, selling: bool | None, buying: bool | None) -> None:
        """Build the firm; ``None`` leaves that side's settings row out."""
        self.setup = _Firm(_request_session())
        session = self.setup.session
        pcs, box = (
            Uom(code=code, name=code.title(), dimension="COUNT", status="ACTIVE")
            for code in ("PCS", "BOX")
        )
        session.add_all([pcs, box])
        session.flush()
        self.boxed = self.setup.product
        self.boxed.inventory_uom_id = pcs.id
        self.boxed.sales_uom_id = box.id
        session.add(
            ConversionRule(
                firm_id=self.setup.firm.id,
                product_id=self.boxed.id,
                from_uom_id=box.id,
                to_uom_id=pcs.id,
                conversion_factor=Decimal("12"),
                effective_from=date(2020, 1, 1),
                version_number=1,
                status="ACTIVE",
            )
        )
        self.plain = Product(
            firm_id=self.setup.firm.id,
            code=_PLAIN,
            name="Product SKU-PLAIN",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            inventory_uom_id=pcs.id,
        )
        session.add(self.plain)
        session.commit()
        InventoryService(session).create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.setup.branch.id,
                warehouse_id=self.setup.warehouse.id,
                product_id=self.plain.id,
                quantity=Decimal("30"),
                reference_number="ADJ-PLAIN",
                reference_type="ADJUSTMENT",
                transaction_date=date(2026, 8, 1),
            ),
            firm_scope=self.setup.firm.id,
            actor_id=uuid4(),
        )
        firm_id = self.setup.firm.id
        if selling is not None:
            session.add(
                SalesWorkflowSettings(firm_id=firm_id, box_and_piece_entry=selling)
            )
        if buying is not None:
            session.add(
                PurchaseWorkflowSettings(firm_id=firm_id, box_and_piece_entry=buying)
            )
        session.commit()
        self.session = session
        self.scope = SimpleNamespace(
            firm_id=firm_id,
            actor_id=uuid4(),
            principal=SimpleNamespace(has_permission=lambda code: True),
        )

    def packs_by_code(self, rows: list[object]) -> dict[str, tuple[object, object]]:
        """Return each row's pack fields by its product code."""
        return {
            str(getattr(row, "product_code", "")): (
                getattr(row, "pack_size", None),
                getattr(row, "pack_unit_code", None),
            )
            for row in rows
        }

    def packs_by_id(self, rows: list[object]) -> dict[str, tuple[object, object]]:
        """Return each row's pack fields by its product's code, read from the id."""
        codes = {self.boxed.id: _BOXED, self.plain.id: _PLAIN}
        return {
            codes[getattr(row, "product_id")]: (  # noqa: B009
                getattr(row, "pack_size", None),
                getattr(row, "pack_unit_code", None),
            )
            for row in rows
        }

    def inventory(self) -> list[object]:
        """Return the stock list's rows."""
        rows = self.session.scalars(select(InventoryRecord)).all()
        return list(InventoryService(self.session).inventory_responses(rows))

    def ledger(self) -> list[object]:
        """Return the stock ledger's rows."""
        rows = self.session.scalars(select(StockLedgerEntry)).all()
        return list(InventoryService(self.session).ledger_responses(rows))

    def statement(self) -> list[object]:
        """Return the stock statement's rows."""
        return list(
            stock_statement(
                scope=self.scope,  # type: ignore[arg-type]
                from_date=date(2026, 7, 1),
                to_date=date(2026, 12, 31),
                warehouse_id=None,
                page=1,
                page_size=100,
                db=self.session,
            ).data
        )

    def valuation(self) -> list[object]:
        """Return the stock valuation's rows."""
        return list(
            stock_valuation(
                scope=self.scope,  # type: ignore[arg-type]
                to_date=None,
                from_date=None,
                warehouse_id=None,
                include_zero=False,
                page=1,
                page_size=100,
                db=self.session,
            ).data
        )

    def batches(self) -> list[object]:
        """Return the batch list's rows, one batch of each item."""
        firm_id = self.setup.firm.id
        records = [
            BatchRecord(
                firm_id=firm_id,
                product_id=product.id,
                batch_number=number,
                lot_reference=number,
            )
            for product, number in ((self.boxed, "B-BOX"), (self.plain, "B-PLAIN"))
        ]
        self.session.add_all(records)
        self.session.commit()
        return list(
            BatchSerialService(self.session).batch_responses(
                records, firm_scope=firm_id
            )
        )

    def below_reorder(self) -> list[object]:
        """Return the below-reorder rows, with both items under their level."""
        for row in self.session.scalars(select(InventoryRecord)):
            row.reorder_level = Decimal("500")
        self.session.commit()
        return list(
            below_reorder_level(
                scope=self.scope,  # type: ignore[arg-type]
                warehouse_id=None,
                page=1,
                page_size=100,
                db=self.session,
            ).data
        )

    def count_lines(self) -> list[object]:
        """Return the lines of a count sheet drawn from the warehouse."""
        service = PhysicalCountService(self.session)
        sheet = service.create(
            PhysicalCountCreate(
                branch_id=self.setup.branch.id,
                warehouse_id=self.setup.warehouse.id,
                count_date=date(2026, 9, 1),
            ),
            firm_id=self.setup.firm.id,
            actor_id=uuid4(),
        )
        self.session.commit()
        return list(_count_response(service, sheet).lines)


_FILLED = {_BOXED: (Decimal("12"), "BOX"), _PLAIN: (None, None)}
_EMPTY = {_BOXED: (None, None), _PLAIN: (None, None)}

_BY_CODE = ("statement", "valuation")
_BY_ID = ("inventory", "ledger", "batches", "below_reorder", "count_lines")


def _read(stock: _Stock, rows_of: str) -> dict[str, tuple[object, object]]:
    """Read one kind of stock row and key its pack fields by item."""
    rows = getattr(stock, rows_of)()
    if rows_of in _BY_CODE:
        items = [row for row in rows if row.product_code in (_BOXED, _PLAIN)]
        assert all(
            (row.pack_size, row.pack_unit_code) == (None, None)
            for row in rows
            if row not in items
        ), "a total row names no item and carries no pack"
        return stock.packs_by_code(items)
    return stock.packs_by_id(rows)


@pytest.mark.parametrize("rows_of", _BY_ID + _BY_CODE)
def test_no_switch_on_leaves_every_row_without_a_pack(rows_of: str) -> None:
    """A firm with no settings rows, or both switches off, shows pieces only."""
    assert _read(_Stock(selling=None, buying=None), rows_of) == _EMPTY
    assert _read(_Stock(selling=False, buying=False), rows_of) == _EMPTY


@pytest.mark.parametrize("rows_of", _BY_ID + _BY_CODE)
def test_the_selling_switch_fills_the_boxed_item_only(rows_of: str) -> None:
    """The item sold by the box of 12 answers 12 and BOX; the plain one null."""
    assert _read(_Stock(selling=True, buying=None), rows_of) == _FILLED


@pytest.mark.parametrize("rows_of", ("inventory", "ledger", "statement"))
def test_the_buying_switch_alone_fills_it_too(rows_of: str) -> None:
    """Either side's switch is enough; the pack is still the selling one."""
    assert _read(_Stock(selling=False, buying=True), rows_of) == _FILLED


def test_a_single_row_answers_what_the_page_does() -> None:
    """The one-row builder is the page builder with a list of one."""
    stock = _Stock(selling=True, buying=None)
    service = InventoryService(stock.session)
    rows = stock.session.scalars(select(InventoryRecord)).all()
    page = {row.id: row for row in service.inventory_responses(rows)}
    for row in rows:
        assert service.inventory_response(row) == page[row.id]
