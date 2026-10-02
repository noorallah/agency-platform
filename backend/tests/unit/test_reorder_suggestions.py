"""Below reorder level, and the draft orders that put it right (backlog 42.9).

`reorder_level` and `maximum_level` sat on the stock rows with nothing reading
them but a list filter. The report says what is short, what is already on
order, from whom it was last bought and how much to order; the action raises
drafts through the order's own save path, one per supplier per warehouse.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.inventory.models import InventoryRecord
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.services.reorder import ReorderPick, ReorderService
from app.purchase_invoice.services import PurchaseInvoiceService
from app.vendors.models import Vendor
from tests.unit.test_purchase_invoice_module import (
    _bill_of,
    _branch,
    _firm,
    _purchase_order,
    _received,
    _session_factory,
    _vendor,
    _warehouse,
)

pytestmark = pytest.mark.typed_document_numbers


class _Shop:
    """A firm that bought SKU-001 from one supplier and stocks it in one place."""

    def __init__(self) -> None:
        """Bill SKU-001 at 100 from the supplier, and receive all of it."""
        self.session: Session = _session_factory()()
        self.firm: Firm = _firm(self.session)
        self.branch = _branch(self.session, firm_id=self.firm.id)
        self.warehouse = _warehouse(
            self.session, firm_id=self.firm.id, branch_id=self.branch.id
        )
        self.vendor: Vendor = _vendor(self.session, firm_id=self.firm.id)
        order = _purchase_order(
            self.session,
            firm_id=self.firm.id,
            vendor_id=self.vendor.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
        )
        po_line = self.session.scalar(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == order.id
            )
        )
        assert po_line is not None
        receipt, receipt_line = _received(self.session, po_line)
        bill = PurchaseInvoiceService(self.session).create_invoice(
            _bill_of(
                receipt,
                receipt_line,
                number="SUP-1",
                quantity="10",
                on=date(2026, 8, 3),
            ),
            firm_id=self.firm.id,
            actor_id=uuid4(),
        )
        bill.status = "APPROVED"
        self.session.commit()
        self.product = self.session.get(Product, po_line.product_id)
        assert self.product is not None

    def stock(
        self,
        product: Product,
        *,
        available: str,
        reorder: str | None,
        maximum: str | None = None,
        locator: str = "A-1",
    ) -> None:
        """Put one stock row for the product in the warehouse."""
        self.session.add(
            InventoryRecord(
                firm_id=self.firm.id,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                storage_locator=locator,
                product_id=product.id,
                current_quantity=Decimal(available),
                available_quantity=Decimal(available),
                reorder_level=None if reorder is None else Decimal(reorder),
                maximum_level=None if maximum is None else Decimal(maximum),
            )
        )
        self.session.commit()

    def other_product(self) -> Product:
        """Add a product nobody has billed yet."""
        row = Product(
            firm_id=self.firm.id,
            code="SKU-002",
            name="Product SKU-002",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            purchase_price=Decimal("40"),
        )
        self.session.add(row)
        self.session.commit()
        return row


def test_a_product_below_its_level_is_listed_with_supplier_and_suggestion() -> None:
    shop = _Shop()
    # Two stock rows in one warehouse add up: 2 + 1 available against 5.
    shop.stock(shop.product, available="2", reorder="5", maximum="20")
    shop.stock(shop.product, available="1", reorder=None, locator="A-2")

    [row] = ReorderService(shop.session).below_reorder(shop.firm.id)

    assert row.available_quantity == Decimal("3.0000")
    assert row.reorder_level == Decimal("5")
    # The order behind the bill was received in full, so nothing is coming.
    assert row.on_order_quantity == Decimal("0.0000")
    assert row.suggested_quantity == Decimal("17.0000")
    assert row.supplier_id == shop.vendor.id
    assert row.unit_price == Decimal("100")


def test_stock_above_its_level_or_with_no_level_is_not_listed() -> None:
    shop = _Shop()
    shop.stock(shop.product, available="9", reorder="5")
    shop.stock(shop.other_product(), available="0", reorder=None, locator="B-1")

    assert ReorderService(shop.session).below_reorder(shop.firm.id) == []


def test_without_a_maximum_the_suggestion_is_the_shortfall() -> None:
    shop = _Shop()
    shop.stock(shop.product, available="2", reorder="5")

    [row] = ReorderService(shop.session).below_reorder(shop.firm.id)

    assert row.suggested_quantity == Decimal("3.0000")


def test_raising_drafts_orders_once_and_counts_what_is_on_order() -> None:
    shop = _Shop()
    shop.stock(shop.product, available="3", reorder="5", maximum="20")
    service = ReorderService(shop.session)

    [order] = service.raise_drafts(
        shop.firm.id,
        [ReorderPick(warehouse_id=shop.warehouse.id, product_id=shop.product.id)],
        actor_id=uuid4(),
    )

    assert order.status == "DRAFT"
    assert order.vendor_id == shop.vendor.id
    line = shop.session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert line is not None
    assert line.ordered_quantity == Decimal("17")
    assert line.unit_price == Decimal("100")

    # The draft now counts as on order, so nothing more is suggested ...
    [row] = service.below_reorder(shop.firm.id)
    assert row.on_order_quantity == Decimal("17.0000")
    assert row.suggested_quantity == Decimal("0.0000")
    # ... and asking again refuses rather than ordering twice.
    with pytest.raises(ValidationError, match="already on order"):
        service.raise_drafts(
            shop.firm.id,
            [ReorderPick(warehouse_id=shop.warehouse.id, product_id=shop.product.id)],
            actor_id=uuid4(),
        )


def test_a_product_never_billed_needs_a_supplier_named() -> None:
    shop = _Shop()
    fresh = shop.other_product()
    shop.stock(fresh, available="1", reorder="4", locator="B-1")
    service = ReorderService(shop.session)

    [row] = service.below_reorder(shop.firm.id)
    assert row.supplier_id is None
    assert row.unit_price == Decimal("40")

    with pytest.raises(ValidationError, match="SKU-002"):
        service.raise_drafts(
            shop.firm.id,
            [ReorderPick(warehouse_id=shop.warehouse.id, product_id=fresh.id)],
            actor_id=uuid4(),
        )
    assert (
        shop.session.scalar(
            select(PurchaseOrder).where(PurchaseOrder.status == "DRAFT")
        )
        is None
    )

    [order] = service.raise_drafts(
        shop.firm.id,
        [
            ReorderPick(
                warehouse_id=shop.warehouse.id,
                product_id=fresh.id,
                quantity=Decimal("6"),
                supplier_id=shop.vendor.id,
            )
        ],
        actor_id=uuid4(),
    )
    assert order.vendor_id == shop.vendor.id


def test_one_draft_per_supplier_carries_every_line_for_it() -> None:
    shop = _Shop()
    fresh = shop.other_product()
    shop.stock(shop.product, available="3", reorder="5", maximum="20")
    shop.stock(fresh, available="1", reorder="4", locator="B-1")

    orders = ReorderService(shop.session).raise_drafts(
        shop.firm.id,
        [
            ReorderPick(warehouse_id=shop.warehouse.id, product_id=shop.product.id),
            ReorderPick(
                warehouse_id=shop.warehouse.id,
                product_id=fresh.id,
                supplier_id=shop.vendor.id,
            ),
        ],
        actor_id=uuid4(),
    )

    assert len(orders) == 1
    lines = shop.session.scalars(
        select(PurchaseOrderLine).where(
            PurchaseOrderLine.purchase_order_id == orders[0].id
        )
    ).all()
    assert {line.product_id for line in lines} == {shop.product.id, fresh.id}


def _second_vendor(shop: _Shop, *, status: str = "ACTIVE") -> Vendor:
    """Add a supplier nothing was ever billed by."""
    row = Vendor(
        firm_id=shop.firm.id,
        code="VEN-002",
        name="Vendor VEN-002",
        display_name="Vendor VEN-002",
        status=status,
    )
    shop.session.add(row)
    shop.session.commit()
    return row


def test_the_preferred_supplier_wins_over_the_one_last_billed() -> None:
    """Decision A18: reorder orders from the supplier the product names.

    The last bill's rate was VEN-001's, so it does not travel to VEN-002:
    the product's purchase price stands in.
    """
    shop = _Shop()
    preferred = _second_vendor(shop)
    shop.product.preferred_vendor_id = preferred.id
    shop.product.purchase_price = Decimal("90")
    shop.session.commit()
    shop.stock(shop.product, available="2", reorder="5")

    [row] = ReorderService(shop.session).below_reorder(shop.firm.id)

    assert row.supplier_id == preferred.id
    assert row.supplier_name == "Vendor VEN-002"
    assert row.unit_price == Decimal("90")


def test_a_preferred_supplier_that_has_gone_falls_back_to_the_last_bill() -> None:
    """An inactive or deleted preferred supplier is passed over, not ordered from."""
    shop = _Shop()
    gone = _second_vendor(shop, status="INACTIVE")
    shop.product.preferred_vendor_id = gone.id
    shop.session.commit()
    shop.stock(shop.product, available="2", reorder="5")

    [row] = ReorderService(shop.session).below_reorder(shop.firm.id)

    assert row.supplier_id == shop.vendor.id
    assert row.unit_price == Decimal("100")


def test_a_product_never_billed_orders_from_its_preferred_supplier() -> None:
    """The case that needed a supplier named by hand now has one."""
    shop = _Shop()
    preferred = _second_vendor(shop)
    fresh = shop.other_product()
    fresh.preferred_vendor_id = preferred.id
    shop.session.commit()
    shop.stock(fresh, available="1", reorder="4", locator="B-1")
    service = ReorderService(shop.session)

    [row] = service.below_reorder(shop.firm.id)
    assert row.supplier_id == preferred.id

    service.raise_drafts(
        shop.firm.id,
        [ReorderPick(warehouse_id=shop.warehouse.id, product_id=fresh.id)],
        actor_id=uuid4(),
    )
    order = shop.session.scalar(
        select(PurchaseOrder).where(PurchaseOrder.status == "DRAFT")
    )
    assert order is not None and order.vendor_id == preferred.id
