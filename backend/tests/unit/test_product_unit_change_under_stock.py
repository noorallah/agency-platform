"""A product's unit and tracking mode do not change while stock exists.

D-MST-7: ``update_product`` checked only that the unit ids exist, so
`T09193238-P` moved PIECE -> BOX and gained ``track_serial`` with 50 on hand
and 1 reserved. Stock is held in the base unit, so 50 pieces became 50 boxes
without a movement, and the serial picker then refused to dispatch units
received without serials.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Warehouse
from app.business.models import BusinessProfile
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.inventory.models import InventoryRecord
from app.products.models import Product
from app.products.schemas import ProductCreate, ProductUpdate
from app.products.services import ProductService
from app.products.services.brands import BrandService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.uom.models import Uom


class _Setup:
    """A firm, two units and one product counted in the first of them."""

    def __init__(self, *, base_unit: bool = True) -> None:
        """Build the masters; ``base_unit`` False leaves the product unitless."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session: Session = sessionmaker(bind=engine, expire_on_commit=False)()
        self.firm = Firm(
            name="Units Firm",
            code="UNITS",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.piece = Uom(code="PIECE", name="Piece", symbol="pc")
        self.box = Uom(code="BOX", name="Box", symbol="bx")
        self.session.add_all(
            [
                self.firm,
                self.piece,
                self.box,
                BusinessProfile(
                    code="GENERIC",
                    name="Generic",
                    industry_type="GENERIC",
                    status="ACTIVE",
                    is_default=True,
                    default_settings={},
                ),
            ]
        )
        self.session.commit()
        BrandService(self.session).ensure_brand(
            "Test Brand", firm_id=self.firm.id, actor_id=self.firm.id
        )
        self.session.commit()
        self.service = ProductService(self.session)
        self.fields: dict[str, object] = {
            "code": "UNIT-P",
            "name": "Counted",
            "product_type": "STOCK_ITEM",
            "brand": "Test Brand",
        }
        if base_unit:
            self.fields["base_uom_id"] = self.piece.id
            self.fields["inventory_uom_id"] = self.piece.id
        self.product: Product = self.service.create_product(
            ProductCreate.model_validate(self.fields),
            firm_id=self.firm.id,
            actor_id=uuid4(),
        )

    def stock(self, on_hand: str, reserved: str = "0") -> InventoryRecord:
        """Put a quantity of the product in a warehouse called MAIN."""
        warehouse = Warehouse(
            firm_id=self.firm.id,
            branch_id=uuid4(),
            code="MAIN",
            name="Main",
            display_name="Main",
        )
        self.session.add(warehouse)
        self.session.flush()
        row = InventoryRecord(
            firm_id=self.firm.id,
            branch_id=warehouse.branch_id,
            warehouse_id=warehouse.id,
            storage_locator="MAIN",
            product_id=self.product.id,
            current_quantity=Decimal(on_hand),
            reserved_quantity=Decimal(reserved),
            available_quantity=Decimal(on_hand) - Decimal(reserved),
        )
        self.session.add(row)
        self.session.commit()
        return row

    def open_order(self, number: str) -> None:
        """Put the product on an approved sales order."""
        order = SalesOrder(
            firm_id=self.firm.id,
            customer_id=uuid4(),
            branch_id=uuid4(),
            warehouse_id=uuid4(),
            order_number=number,
            order_date=date(2026, 9, 19),
            status="APPROVED",
        )
        self.session.add(order)
        self.session.flush()
        self.session.add(
            SalesOrderLine(
                sales_order_id=order.id,
                firm_id=self.firm.id,
                line_number=1,
                product_id=self.product.id,
                quantity=Decimal("1"),
            )
        )
        self.session.commit()

    def save(self, **changes: object) -> Product:
        """Save the full form with the named fields changed."""
        return self.service.update_product(
            self.product.id,
            ProductUpdate.model_validate({**self.fields, **changes}),
            firm_scope=self.firm.id,
            actor_id=uuid4(),
        )


def _id(value: object) -> UUID:
    """Read a unit id back as a UUID."""
    return UUID(str(value))


def test_the_base_unit_cannot_move_under_stock() -> None:
    """The refusal names the field, the quantity and the place."""
    setup = _Setup()
    setup.stock("50", reserved="1")

    with pytest.raises(ValidationError) as refused:
        setup.save(base_uom_id=setup.box.id, inventory_uom_id=setup.box.id)
    setup.session.rollback()

    message = str(refused.value)
    assert "UNIT-P: the base unit, inventory unit cannot be changed" in message
    assert "50 in MAIN (1 reserved)" in message
    setup.session.refresh(setup.product)
    assert _id(setup.product.base_uom_id) == setup.piece.id


@pytest.mark.parametrize(
    ("field", "label"),
    [
        ("track_serial", "serial tracking"),
        ("track_batch", "batch tracking"),
        ("require_serial_on_issue", "serial-on-issue rule"),
        ("require_batch_on_issue", "batch-on-issue rule"),
    ],
)
def test_a_tracking_mode_cannot_change_under_stock(field: str, label: str) -> None:
    """Units received without serials or batches cannot be asked for them."""
    setup = _Setup()
    setup.stock("50")

    with pytest.raises(ValidationError, match=label):
        setup.save(**{field: True})
    setup.session.rollback()
    setup.session.refresh(setup.product)
    assert getattr(setup.product, field) is False


def test_an_open_document_alone_holds_the_unit() -> None:
    """Nothing on hand, but an approved order is still counted in pieces."""
    setup = _Setup()
    setup.open_order("SO-UNITS")

    with pytest.raises(ValidationError, match="1 sales order \\(SO-UNITS\\)"):
        setup.save(base_uom_id=setup.box.id)


def test_a_save_that_changes_none_of_them_goes_through_under_stock() -> None:
    """A form resending what is stored is not a change."""
    setup = _Setup()
    setup.stock("50")

    saved = setup.save(name="Renamed", selling_price="10")

    assert saved.name == "Renamed"
    assert _id(saved.base_uom_id) == setup.piece.id


def test_everything_may_change_once_the_product_is_back_at_nothing() -> None:
    """No stock, no reservation, no open document: settle it how you like."""
    setup = _Setup()
    row = setup.stock("50")
    row.current_quantity = Decimal("0")
    row.available_quantity = Decimal("0")
    setup.session.commit()

    saved = setup.save(
        base_uom_id=setup.box.id, inventory_uom_id=setup.box.id, track_serial=True
    )

    assert _id(saved.base_uom_id) == setup.box.id
    assert saved.track_serial is True


def test_naming_a_unit_for_a_product_that_had_none_is_not_a_change_of_unit() -> None:
    """How a product created without a unit is repaired, stock or no stock."""
    setup = _Setup(base_unit=False)
    setup.stock("50")

    saved = setup.save(base_uom_id=setup.piece.id, inventory_uom_id=setup.piece.id)

    assert _id(saved.base_uom_id) == setup.piece.id


def test_a_body_naming_three_fields_is_not_tracking_off_and_units_cleared() -> None:
    """Code, name and type alone leave a stocked, batch-tracked product whole.

    The guard read the whole write model, so every field the caller left out
    arrived at its schema default -- tracking off, no units -- and the save was
    refused as a change to the batch tracking and the units of a product in
    stock (D-MST-22).
    """
    setup = _Setup()
    setup.save(
        track_batch=True,
        require_batch_on_issue=True,
        purchase_uom_id=setup.box.id,
        selling_price="12.50",
        hsn_sac="3401",
    )
    setup.stock("50", reserved="1")
    setup.session.refresh(setup.product)
    before = {
        column.name: getattr(setup.product, column.name)
        for column in Product.__table__.columns
    }

    saved = setup.service.update_product(
        setup.product.id,
        ProductUpdate.model_validate(
            {"code": "UNIT-P", "name": "Renamed", "product_type": "STOCK_ITEM"}
        ),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )

    setup.session.refresh(saved)
    after = {
        column.name: getattr(saved, column.name) for column in Product.__table__.columns
    }
    moved = {name for name in before if before[name] != after[name]}
    assert moved - {"updated_at"} == {"name", "version", "updated_by"}
    assert saved.name == "Renamed"
    assert saved.track_batch is True
    assert saved.require_batch_on_issue is True
    assert _id(saved.base_uom_id) == setup.piece.id
    assert _id(saved.inventory_uom_id) == setup.piece.id
    assert _id(saved.purchase_uom_id) == setup.box.id


@pytest.mark.parametrize(
    ("change", "label"),
    [
        ({"track_batch": False}, "batch tracking"),
        ({"require_batch_on_issue": False}, "batch-on-issue rule"),
        ({"base_uom_id": None}, "base unit"),
        ({"inventory_uom_id": None}, "inventory unit"),
    ],
)
def test_saying_off_or_null_is_still_a_change_under_stock(
    change: dict[str, object], label: str
) -> None:
    """Leaving a field out is silence; ``false`` and ``null`` are instructions."""
    setup = _Setup()
    setup.save(track_batch=True, require_batch_on_issue=True)
    setup.stock("50")

    with pytest.raises(ValidationError, match=label):
        setup.service.update_product(
            setup.product.id,
            ProductUpdate.model_validate(
                {
                    "code": "UNIT-P",
                    "name": "Counted",
                    "product_type": "STOCK_ITEM",
                    **change,
                }
            ),
            firm_scope=setup.firm.id,
            actor_id=uuid4(),
        )
    setup.session.rollback()
    setup.session.refresh(setup.product)
    assert setup.product.track_batch is True
    assert _id(setup.product.base_uom_id) == setup.piece.id


def test_the_whole_form_with_tracking_left_off_is_refused_as_before() -> None:
    """A client that sends every field still switches off what it sends off."""
    setup = _Setup()
    setup.save(track_batch=True)
    setup.stock("50")
    whole = ProductUpdate.model_validate(setup.fields).model_dump(mode="json")

    with pytest.raises(ValidationError, match="batch tracking"):
        setup.service.update_product(
            setup.product.id,
            ProductUpdate.model_validate(whole),
            firm_scope=setup.firm.id,
            actor_id=uuid4(),
        )
