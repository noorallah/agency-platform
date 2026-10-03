"""Kits and combo packs (STK-15, decision A134).

A gift pack is two soaps and one towel. Twenty soaps and ten towels are on
the shelf. Assembling three packs takes six soaps and three towels; a note
shipping five packs assembles the two it lacks from the components first, so
the shelf ends with ten soaps, five towels and no packs. Breaking a pack
gives its components back. A kit cannot hold a kit.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.inventory.models import InventoryRecord
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.products.services.kits import (
    KitAssemblyWrite,
    KitComponentsWrite,
    KitService,
)
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_delivery_note_module import (
    _branch,
    _customer,
    _firm,
    _session_factory,
    _warehouse,
)

D = Decimal
ON = date(2026, 8, 3)


class _Shop:
    """Soaps and towels on the shelf, and a gift pack made of them."""

    def __init__(self, session: Session) -> None:
        """Stock the components and list the pack's contents."""
        self.session = session
        self.actor = uuid4()
        self.firm = _firm(session)
        self.branch = _branch(session, firm_id=self.firm.id)
        self.warehouse = _warehouse(
            session, firm_id=self.firm.id, branch_id=self.branch.id
        )
        self.customer = _customer(session, firm_id=self.firm.id)
        self.soap = self._product("SOAP", "STOCK_ITEM", "20")
        self.towel = self._product("TOWEL", "STOCK_ITEM", "80")
        self.pack = self._product("GIFT", "BUNDLE", None)
        for product, quantity in ((self.soap, "20"), (self.towel, "10")):
            InventoryService(session).create_adjustment(
                InventoryAdjustmentCreate(
                    branch_id=self.branch.id,
                    warehouse_id=self.warehouse.id,
                    product_id=product.id,
                    quantity=D(quantity),
                    reference_number=f"ADJ-{product.code}",
                    reference_type="ADJUSTMENT",
                    transaction_date=ON,
                ),
                firm_scope=self.firm.id,
                actor_id=self.actor,
            )
        KitService(session).replace(
            self.pack.id,
            KitComponentsWrite.model_validate(
                {
                    "components": [
                        {"component_product_id": self.soap.id, "quantity": "2"},
                        {"component_product_id": self.towel.id, "quantity": "1"},
                    ]
                }
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )

    def _product(self, code: str, kind: str, price: str | None) -> Product:
        row = Product(
            firm_id=self.firm.id,
            code=code,
            name=code.title(),
            product_type=kind,
            status="ACTIVE",
            purchase_price=D(price) if price else None,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def held(self, product: Product) -> Decimal:
        total = self.session.scalar(
            select(func.coalesce(func.sum(InventoryRecord.current_quantity), 0)).where(
                InventoryRecord.product_id == product.id
            )
        )
        return D(str(total or 0))

    def assembly(self, quantity: str) -> KitAssemblyWrite:
        return KitAssemblyWrite(
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            quantity=D(quantity),
            on=ON,
        )


def test_assembling_and_breaking_kits_moves_their_components() -> None:
    shop = _Shop(_session_factory()())
    kits = KitService(shop.session)
    kits.assemble(
        shop.pack.id, shop.assembly("3"), firm_id=shop.firm.id, actor_id=shop.actor
    )
    assert (shop.held(shop.pack), shop.held(shop.soap), shop.held(shop.towel)) == (
        D("3"),
        D("14"),
        D("7"),
    )
    kits.assemble(
        shop.pack.id,
        shop.assembly("1"),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
        disassemble=True,
    )
    assert (shop.held(shop.pack), shop.held(shop.soap), shop.held(shop.towel)) == (
        D("2"),
        D("16"),
        D("8"),
    )
    with pytest.raises(ValidationError, match="needed to assemble 9 of GIFT"):
        kits.assemble(
            shop.pack.id,
            shop.assembly("9"),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
        )


def test_a_note_shipping_more_packs_than_assembled_assembles_the_rest() -> None:
    shop = _Shop(_session_factory()())
    KitService(shop.session).assemble(
        shop.pack.id, shop.assembly("3"), firm_id=shop.firm.id, actor_id=shop.actor
    )
    orders = SalesOrderService(shop.session)
    order = orders.create_order(
        SalesOrderCreate(
            customer_id=shop.customer.id,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            order_date=ON,
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=shop.pack.id,
                    quantity=D("5"),
                    unit_price=D("250"),
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    orders.approve_order(order.id, firm_scope=shop.firm.id, actor_id=shop.actor)
    line = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    notes = DeliveryNoteService(shop.session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=line.id,
                    line_number=1,
                    current_delivery_quantity=D("5"),
                    free_quantity=D("0"),
                    unit_price=D("250"),
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    notes.approve_note(note.id, firm_scope=shop.firm.id, actor_id=shop.actor)
    notes.dispatch_note(note.id, firm_scope=shop.firm.id, actor_id=shop.actor)
    assert (shop.held(shop.pack), shop.held(shop.soap), shop.held(shop.towel)) == (
        D("0"),
        D("10"),
        D("5"),
    )


def test_a_kit_holds_no_kit_and_only_a_bundle_has_components() -> None:
    shop = _Shop(_session_factory()())
    other = shop._product("HAMPER", "BUNDLE", None)
    kits = KitService(shop.session)
    with pytest.raises(ValidationError, match="not a component of another kit"):
        kits.replace(
            other.id,
            KitComponentsWrite.model_validate(
                {
                    "components": [
                        {"component_product_id": shop.pack.id, "quantity": "1"}
                    ]
                }
            ),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
        )
    with pytest.raises(ValidationError, match="is not a kit"):
        kits.replace(
            shop.soap.id,
            KitComponentsWrite(),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
        )
    assert isinstance(other.id, UUID)
