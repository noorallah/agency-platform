"""The discount limit judges the price typed, not only the discount (D-PRC-2).

With a 5% limit for the Sales Manager a typed 50% discount was refused, and
the same goods at a typed price of half the list price with no discount were
approved, delivered and billed below cost: only the discount boxes were
judged. The limit is now judged on the whole reduction from the price the
customer would otherwise pay to what the line charges.

The same PR closes the other door to a cheaper price: a customer's price
level, and a segment that carries a discount or a level, need
``CUSTOMER_MANAGE_SETTINGS`` exactly as the standing discount does.

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, ValidationError
from app.customers.api.router import create_customer, update_customer
from app.customers.models import Customer, CustomerGroup
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.services.customer_service import CustomerService
from app.delivery_note.models import DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.document_framework.models import DocumentLifecycleEvent
from app.identity.models import Role, User, UserFirm, UserRole
from app.pricing.models import PriceLevel, ProductPriceLevel
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.discount_limit import (
    DiscountedLine,
    DiscountLimitService,
)
from app.sales_order.services.sales_order_service import SalesOrderService
from tests.unit.test_customer_management import (
    _customer_data,
    _firm,
    _firm_scope,
    _principal,
    _request_like_session_factory,
)
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session

D = Decimal
DAY = date(2026, 8, 4)


class _Desk:
    """A firm selling its product at 84.00, with a 5% manager and a 60% head."""

    def __init__(self, *, counter: bool = False) -> None:
        """Build the firm, price the product and limit two roles."""
        self.session: Session = _request_session()
        self.setup = _Firm(self.session)
        if counter:
            self.setup.stages(quotation=False, sales_order=False, delivery_note=False)
        self.setup.product.selling_price = D("84")
        self.session.commit()
        self.actor = uuid4()
        self.orders = SalesOrderService(self.session)
        self.bills = SalesInvoiceService(self.session)
        self.manager = self.person("SALES_MANAGER")
        self.head = self.person("SALES_HEAD")
        DiscountLimitService(self.session).replace_limits(
            [("SALES_MANAGER", D("5")), ("SALES_HEAD", D("60"))],
            firm_id=self.firm_id,
            actor_id=self.actor,
        )

    @property
    def firm_id(self) -> UUID:
        """Return the firm."""
        return self.setup.firm.id

    def person(self, role_code: str) -> UUID:
        """Create somebody holding one role in the firm."""
        user = User(
            email=f"{uuid4().hex[:8]}@desk.test",
            full_name="Desk person",
            password_hash="x",
        )
        role = Role(code=role_code, name=role_code.title())
        self.session.add_all([user, role])
        self.session.flush()
        self.session.add(
            UserRole(user_id=user.id, role_id=role.id, firm_id=self.firm_id)
        )
        self.session.commit()
        return user.id

    def order(
        self,
        *,
        price: str | None = "84",
        discount_percent: str | None = None,
        quantity: str = "2",
        **header: object,
    ) -> UUID:
        """Save a draft order of the product at a price, or at none typed."""
        row = self.orders.create_order(
            SalesOrderCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "branch_id": self.setup.branch.id,
                    "warehouse_id": self.setup.warehouse.id,
                    "order_date": DAY,
                    "lines": [
                        SalesOrderLineWrite(
                            line_number=1,
                            product_id=self.setup.product.id,
                            quantity=D(quantity),
                            unit_price=None if price is None else D(price),
                            discount_percent=(
                                None
                                if discount_percent is None
                                else D(discount_percent)
                            ),
                        )
                    ],
                }
                | header
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        return row.id

    def approve(self, order_id: UUID, approver: UUID) -> str:
        """Approve an order as somebody; return its status."""
        try:
            return self.orders.approve_order(
                order_id, firm_scope=self.firm_id, actor_id=approver
            ).status
        except ValidationError:
            self.session.rollback()
            raise

    def level(self, rate: str) -> None:
        """Put the customer on a price level that sells the product at a rate."""
        level = PriceLevel(firm_id=self.firm_id, code="WHOLESALE", name="Wholesale")
        self.session.add(level)
        self.session.flush()
        self.session.add(
            ProductPriceLevel(
                firm_id=self.firm_id,
                price_level_id=level.id,
                product_id=self.setup.product.id,
                rate=D(rate),
            )
        )
        self.setup.customer.price_level_id = level.id
        self.session.commit()


def test_half_the_price_is_refused_as_half_off() -> None:
    """The reproduction: 2 at 42.00 with no discount, where the price is 84.00."""
    desk = _Desk()
    cut = desk.order(price="42")

    with pytest.raises(ValidationError) as refused:
        desk.approve(cut, desk.manager)

    assert str(refused.value.message) == (
        "Line 1 is priced at 42.00 where the customer's price is 84.00: 50.00% "
        "off in all, above your limit of 5.00%. It needs approval by someone "
        "allowed at least 50.00%."
    )
    assert desk.orders.get_order(cut, firm_scope=desk.firm_id).status == "DRAFT"
    # The discount box said the same thing, and still does.
    typed = desk.order(discount_percent="50")
    with pytest.raises(ValidationError, match="carries a discount of 50.00%"):
        desk.approve(typed, desk.manager)


def test_the_customers_price_and_above_it_are_not_a_discount() -> None:
    """Typed at 84.00, typed at 90.00 and left blank all approve at 5%."""
    desk = _Desk()
    for price in ("84", "90", None):
        assert desk.approve(desk.order(price=price), desk.manager) == "APPROVED"
    # A discount on a price typed above is judged on what was typed, as before.
    over = desk.order(price="90", discount_percent="6")
    with pytest.raises(ValidationError, match="carries a discount of 6.00%"):
        desk.approve(over, desk.manager)


def test_a_customers_own_cheaper_price_is_not_the_sellers_doing() -> None:
    """On a level at 70.00 the customer's price is 70.00, typed or not."""
    desk = _Desk()
    desk.level("70")

    assert desk.approve(desk.order(price=None), desk.manager) == "APPROVED"
    assert desk.approve(desk.order(price="70"), desk.manager) == "APPROVED"
    below = desk.order(price="63")
    with pytest.raises(ValidationError, match=r"63.00 where .* 70.00: 10.00% off"):
        desk.approve(below, desk.manager)


def test_a_lower_price_and_a_discount_are_judged_as_one_reduction() -> None:
    """80.00 is 4.76% off and 3% is 3%; together they are 7.62% off 168.00."""
    desk = _Desk()
    assert desk.approve(desk.order(price="80"), desk.manager) == "APPROVED"
    assert desk.approve(desk.order(discount_percent="3"), desk.manager) == "APPROVED"

    both = desk.order(price="80", discount_percent="3")
    with pytest.raises(ValidationError) as refused:
        desk.approve(both, desk.manager)

    assert str(refused.value.message) == (
        "Line 1 is priced at 80.00 where the customer's price is 84.00, with a "
        "typed discount besides: 7.62% off in all, above your limit of 5.00%. "
        "It needs approval by someone allowed at least 7.62%."
    )
    judged = DiscountedLine(
        1, D("160"), D("4.8"), quantity=D("2"), price=D("80"), customer_price=D("84")
    )
    assert (judged.price_cut, judged.percent) == (D("8"), D("7.62"))


def test_somebody_allowed_more_approves_and_the_timeline_keeps_the_price() -> None:
    """The head's 60% clears the half price; the event names both prices."""
    desk = _Desk()
    cut = desk.order(price="42")
    with pytest.raises(ValidationError):
        desk.approve(cut, desk.manager)

    assert desk.approve(cut, desk.head) == "APPROVED"

    event = desk.session.scalars(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == cut,
            DocumentLifecycleEvent.action == "APPROVED",
        )
    ).one()
    assert event.details_json is not None
    assert event.details_json["discount_approval"] == {
        "typed_discount_percent": "50.00",
        "approver_limit_percent": "60.00",
        "typed_price": "42.00",
        "customer_price": "84.00",
    }


def test_a_counter_bill_at_half_price_is_refused_at_its_approval() -> None:
    """Stages off: the bill is where the price was typed and where it is judged."""
    desk = _Desk(counter=True)
    draft = desk.bills.create_invoice(
        SalesInvoiceCreate(
            customer_id=desk.setup.customer.id,
            invoice_date=DAY,
            lines=[
                SalesInvoiceLineWrite(
                    product_id=desk.setup.product.id,
                    line_number=1,
                    current_invoice_quantity=D("2"),
                    unit_price=D("42"),
                )
            ],
        ),
        firm_id=desk.firm_id,
        actor_id=desk.actor,
    )

    with pytest.raises(ValidationError, match=r"42.00 where .* 84.00: 50.00% off"):
        desk.bills.approve_invoice(
            draft.id, firm_scope=desk.firm_id, actor_id=desk.manager
        )
    desk.session.rollback()

    approved = desk.bills.approve_invoice(
        draft.id, firm_scope=desk.firm_id, actor_id=desk.head
    )
    assert approved.status == "APPROVED"


def test_a_price_cut_on_the_bill_of_an_order_is_judged_against_the_order() -> None:
    """The order agreed 84.00; a bill of its note typed at 42.00 is 50% off."""
    desk = _Desk()
    order_id = desk.order(quantity="4")
    desk.approve(order_id, desk.manager)
    order_line = desk.session.scalars(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order_id)
    ).one()
    notes = DeliveryNoteService(desk.session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=order_id,
            delivery_date=DAY,
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=D("4"),
                )
            ],
        ),
        firm_id=desk.firm_id,
        actor_id=desk.actor,
    )
    notes.approve_note(note.id, firm_scope=desk.firm_id, actor_id=desk.actor)
    notes.dispatch_note(note.id, firm_scope=desk.firm_id, actor_id=desk.actor)
    note_line = desk.session.scalars(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    ).one()

    def bill(quantity: str, price: str | None) -> UUID:
        """Save a draft bill of part of the note, at a price or at none typed."""
        return desk.bills.create_invoice(
            SalesInvoiceCreate(
                customer_id=desk.setup.customer.id,
                invoice_date=DAY,
                lines=[
                    SalesInvoiceLineWrite(
                        source_document_type="DELIVERY_NOTE",
                        source_document_id=note.id,
                        source_document_line_id=note_line.id,
                        line_number=1,
                        current_invoice_quantity=D(quantity),
                        unit_price=None if price is None else D(price),
                    )
                ],
            ),
            firm_id=desk.firm_id,
            actor_id=desk.actor,
        ).id

    cut = bill("2", "42")
    with pytest.raises(ValidationError, match=r"42.00 where .* 84.00: 50.00% off"):
        desk.bills.approve_invoice(cut, firm_scope=desk.firm_id, actor_id=desk.manager)
    desk.session.rollback()
    desk.bills.cancel_invoice(
        cut, firm_scope=desk.firm_id, actor_id=desk.actor, reason="Priced wrongly"
    )

    kept = bill("4", None)
    assert (
        desk.bills.approve_invoice(
            kept, firm_scope=desk.firm_id, actor_id=desk.manager
        ).status
        == "APPROVED"
    )


def test_a_bill_discount_typed_on_a_counter_bill_by_an_edit_is_still_judged() -> None:
    """Typed on an edit that raises nothing again, only the bill records it."""
    desk = _Desk(counter=True)
    draft = desk.bills.create_invoice(
        desk.setup.bare_bill().model_copy(update={"invoice_date": DAY}),
        firm_id=desk.firm_id,
        actor_id=desk.actor,
    )
    line = desk.bills.invoice_response(draft).lines[0]
    desk.bills.update_invoice(
        draft.id,
        SalesInvoiceCreate.model_validate(
            {
                "customer_id": draft.customer_id,
                "invoice_date": draft.invoice_date,
                "bill_discount_percent": "20",
                "lines": [
                    {
                        "source_document_type": line.source_document_type,
                        "source_document_id": line.source_document_id,
                        "source_document_line_id": line.source_document_line_id,
                        "line_number": 1,
                        "current_invoice_quantity": "4",
                    }
                ],
            }
        ),
        firm_id=desk.firm_id,
        actor_id=desk.actor,
    )

    with pytest.raises(ValidationError, match="carries a discount of 20.00%"):
        desk.bills.approve_invoice(
            draft.id, firm_scope=desk.firm_id, actor_id=desk.manager
        )


def _desk_and_office() -> tuple[Session, object, object, UUID]:
    """Return a session, a seller who edits customers, the office and the firm."""
    factory = _request_like_session_factory()
    setup = factory()
    firm = _firm(setup, "PRICEDOOR")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    firm_id = firm.id
    setup.close()
    session = factory()
    codes = {"CUSTOMER_CREATE", "CUSTOMER_VIEW", "CUSTOMER_UPDATE", "CUSTOMER_IMPORT"}
    seller = _firm_scope(_principal(user_id, codes), session, firm_id)
    office = _firm_scope(
        _principal(user_id, codes | {"CUSTOMER_MANAGE_SETTINGS"}), session, firm_id
    )
    return session, seller, office, firm_id


def _masters(session: Session, firm_id: UUID) -> tuple[UUID, UUID, UUID]:
    """Add a price level, a segment that discounts and one that does not."""
    level = PriceLevel(firm_id=firm_id, code="WHOLESALE", name="Wholesale")
    priced = CustomerGroup(
        firm_id=firm_id,
        code="STOCKIST",
        name="Stockist",
        default_discount_percent=D("10"),
    )
    plain = CustomerGroup(firm_id=firm_id, code="RETAIL", name="Retailer")
    session.add_all([level, priced, plain])
    session.commit()
    return level.id, priced.id, plain.id


def test_a_price_level_and_a_priced_segment_move_only_for_the_office() -> None:
    """A seller's edit is refused both; resending what is stored is not a change."""
    session, seller, office, firm_id = _desk_and_office()
    level, priced, plain = _masters(session, firm_id)
    customer_id = create_customer(_customer_data(), office, session).data.id  # type: ignore[arg-type]
    form = _customer_data().model_dump(mode="json")

    def save(scope: object, **fields: object) -> Customer:
        """Save the form with some fields changed, as one role."""
        update_customer(
            customer_id,
            CustomerUpdate.model_validate({**form, **fields}),
            scope,  # type: ignore[arg-type]
            Response(),
            session,
            None,
        )
        session.expire_all()
        return session.get(Customer, customer_id)  # type: ignore[return-value]

    with pytest.raises(AuthorizationError, match="price level needs"):
        save(seller, price_level_id=str(level))
    session.rollback()
    with pytest.raises(AuthorizationError, match="segment that carries a discount"):
        save(seller, customer_group_id=str(priced))
    session.rollback()
    # A segment that prices nothing is a classification a seller may set.
    assert save(seller, customer_group_id=str(plain)).customer_group_id == plain

    held = save(office, price_level_id=str(level), customer_group_id=str(priced))
    assert (held.price_level_id, held.customer_group_id) == (level, priced)
    # Resent as stored, with another field changed, it goes through.
    resent = save(
        seller,
        name="Renamed",
        price_level_id=str(level),
        customer_group_id=str(priced),
    )
    assert resent.name == "Renamed"
    # Taking the customer off either is a price decision too.
    with pytest.raises(AuthorizationError, match="price level needs"):
        save(seller, price_level_id=None, customer_group_id=str(priced))
    session.rollback()
    with pytest.raises(AuthorizationError, match="segment that carries a discount"):
        save(seller, price_level_id=str(level), customer_group_id=str(plain))


def test_a_new_customer_starts_on_a_price_only_from_the_office() -> None:
    """The form and the import refuse a seller a level or a priced segment."""
    session, seller, office, firm_id = _desk_and_office()
    level, priced, plain = _masters(session, firm_id)

    def shop(code: str, **terms: object) -> CustomerCreate:
        """Describe a new outlet with whatever price terms are named."""
        return CustomerCreate.model_validate(
            {
                "code": code,
                "customer_type": "BUSINESS",
                "name": f"Shop {code}",
                "currency_code": "INR",
                **terms,
            }
        )

    for terms, named in (
        ({"price_level_id": str(level)}, "a price level"),
        ({"customer_group_id": str(priced)}, "segment that carries a discount"),
    ):
        with pytest.raises(AuthorizationError, match=named):
            create_customer(shop("NEW-1", **terms), seller, session)  # type: ignore[arg-type]
        session.rollback()
        with pytest.raises(AuthorizationError, match=named):
            CustomerService(session).import_customers(
                [shop("NEW-2", **terms)], firm_id=firm_id, actor_id=uuid4()
            )
        session.rollback()

    create_customer(shop("NEW-3", customer_group_id=str(plain)), seller, session)  # type: ignore[arg-type]
    create_customer(
        shop("NEW-4", price_level_id=str(level), customer_group_id=str(priced)),
        office,  # type: ignore[arg-type]
        session,
    )
    assert session.scalars(select(Customer.code).order_by(Customer.code)).all() == [
        "NEW-3",
        "NEW-4",
    ]
