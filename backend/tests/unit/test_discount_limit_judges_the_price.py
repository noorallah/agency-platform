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
from types import SimpleNamespace
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
    note_reduction,
)
from app.sales_order.services.sales_order_service import SalesOrderService
from tests.unit.test_customer_management import (
    _customer_data,
    _firm,
    _firm_scope,
    _principal,
    _request_like_session_factory,
)
from tests.unit.test_lines_in_another_unit import box_of_twelve
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
        units: dict[str, object] | None = None,
        **header: object,
    ) -> UUID:
        """Save a draft order of the product at a price, or at none typed.

        ``units`` names what else the line says: its selling and stock
        units, or its free goods.
        """
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
                            **(units or {}),
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


class _Counter(_Desk):
    """The desk, raising delivery notes and bills of an order of 10 at 100.00."""

    def __init__(self, *, notes: bool = True) -> None:
        """Build the desk; ``notes`` off leaves the delivery note to the bill."""
        super().__init__()
        if not notes:
            self.setup.stages(quotation=False, sales_order=True, delivery_note=False)
        self.notes = DeliveryNoteService(self.session)

    def agreed(self, approver: UUID | None = None, **typed: object) -> UUID:
        """Raise an order of 10 at 100.00 and have somebody approve it."""
        discount = typed.pop("discount_percent", None)
        order_id = self.order(
            price="100",
            quantity="10",
            discount_percent=None if discount is None else str(discount),
            **typed,
        )
        self.approve(order_id, approver or self.manager)
        return order_id

    def order_line(self, order_id: UUID) -> SalesOrderLine:
        """Return the order's one line."""
        return self.session.scalars(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order_id)
        ).one()

    def note(
        self, order_id: UUID, *, header: dict[str, object] | None = None, **line: object
    ) -> UUID:
        """Save a draft note of the whole order, typing what is named."""
        return self.notes.create_note(
            DeliveryNoteCreate.model_validate(
                {
                    "sales_order_id": order_id,
                    "delivery_date": DAY,
                    "lines": [
                        {
                            "sales_order_line_id": self.order_line(order_id).id,
                            "line_number": 1,
                            "current_delivery_quantity": "10",
                        }
                        | line
                    ],
                }
                | (header or {})
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        ).id

    def approve_note(self, note_id: UUID, approver: UUID) -> str:
        """Approve a note as somebody; return its status."""
        try:
            return self.notes.approve_note(
                note_id, firm_scope=self.firm_id, actor_id=approver
            ).status
        except ValidationError:
            self.session.rollback()
            raise

    def number(self, note_id: UUID) -> str:
        """Return a note's number."""
        return self.notes.get_note(
            note_id, firm_scope=self.firm_id
        ).delivery_note_number

    def bill(self, note_id: UUID, **header: object) -> UUID:
        """Dispatch a note and save a draft bill of all of it, typing nothing."""
        self.notes.dispatch_note(note_id, firm_scope=self.firm_id, actor_id=self.actor)
        note_line = self.session.scalars(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note_id)
        ).one()
        return self.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "invoice_date": DAY,
                    "lines": [
                        {
                            "source_document_type": "DELIVERY_NOTE",
                            "source_document_id": note_id,
                            "source_document_line_id": note_line.id,
                            "line_number": 1,
                            "current_invoice_quantity": "10",
                        }
                    ],
                }
                | header
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        ).id

    def bill_of_order(self, order_id: UUID, **header: object) -> UUID:
        """Save a draft bill straight off an order, for a firm typing no notes."""
        return self.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "invoice_date": DAY,
                    "lines": [
                        {
                            "source_document_type": "SALES_ORDER",
                            "source_document_id": order_id,
                            "source_document_line_id": self.order_line(order_id).id,
                            "line_number": 1,
                            "current_invoice_quantity": "10",
                        }
                    ],
                }
                | header
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        ).id

    def approve_bill(self, bill_id: UUID, approver: UUID) -> str:
        """Approve a bill as somebody; return its status."""
        try:
            return self.bills.approve_invoice(
                bill_id, firm_scope=self.firm_id, actor_id=approver
            ).status
        except ValidationError:
            self.session.rollback()
            raise


@pytest.mark.parametrize(
    ("line", "header"),
    [
        ({"discount_percent": "30"}, {}),
        ({"discount_amount": "300"}, {}),
        ({}, {"bill_discount_percent": "30"}),
    ],
)
def test_a_discount_typed_on_a_delivery_note_is_judged_at_its_approval(
    line: dict[str, str], header: dict[str, str]
) -> None:
    """D-PRC-23: 30% typed on the note of an order at 100.00, by a 5% manager.

    The note was saved, approved and dispatched, and its bill approved, by
    the same sales manager: the discount reached the bill as inherited.
    """
    desk = _Counter()
    order_id = desk.agreed()
    note_id = desk.note(order_id, header=header, **line)

    with pytest.raises(ValidationError) as refused:
        desk.approve_note(note_id, desk.manager)

    assert str(refused.value.message) == (
        f"Line 1 of delivery note {desk.number(note_id)} carries a discount of "
        "30.00%, above your limit of 5.00%. It needs approval by someone "
        "allowed at least 30.00%."
    )
    assert desk.notes.get_note(note_id, firm_scope=desk.firm_id).status == "DRAFT"

    # Somebody allowed more approves it, and the timeline keeps who and what.
    assert desk.approve_note(note_id, desk.head) == "APPROVED"
    event = desk.session.scalars(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == note_id,
            DocumentLifecycleEvent.action == "APPROVED",
        )
    ).one()
    assert event.details_json is not None
    assert event.details_json["typed_reduction_judged"] is True
    assert event.details_json["discount_approval"] == {
        "typed_discount_percent": "30.00",
        "approver_limit_percent": "60.00",
    }
    # Judged once: the manager bills what the note now holds.
    assert desk.approve_bill(desk.bill(note_id), desk.manager) == "APPROVED"


def test_a_price_typed_on_a_delivery_note_is_judged_at_its_approval() -> None:
    """50.00 typed on the note where the order agreed 100.00 is half off."""
    desk = _Counter()
    note_id = desk.note(desk.agreed(), unit_price="50")

    with pytest.raises(ValidationError) as refused:
        desk.approve_note(note_id, desk.manager)

    assert str(refused.value.message) == (
        f"Line 1 of delivery note {desk.number(note_id)} is priced at 50.00 "
        "where the customer's price is 100.00: 50.00% off in all, above your "
        "limit of 5.00%. It needs approval by someone allowed at least 50.00%."
    )
    assert desk.approve_note(note_id, desk.head) == "APPROVED"
    # The head agreed 50.00, so a bill at 50.00 cuts nothing further.
    assert desk.approve_bill(desk.bill(note_id), desk.manager) == "APPROVED"


def test_a_note_that_types_nothing_is_never_refused_for_its_order() -> None:
    """The head agreed 30% and 10% off the order; the manager ships and bills it."""
    desk = _Counter()
    order_id = desk.agreed(desk.head, discount_percent="30", bill_discount_percent="10")

    note_id = desk.note(order_id)

    assert desk.approve_note(note_id, desk.manager) == "APPROVED"
    event = desk.session.scalars(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == note_id,
            DocumentLifecycleEvent.action == "APPROVED",
        )
    ).one()
    assert "typed_reduction_judged" not in (event.details_json or {})
    assert desk.approve_bill(desk.bill(note_id), desk.manager) == "APPROVED"


def test_a_note_within_the_limit_or_dearer_than_its_order_is_approved() -> None:
    """4% typed passes at 5%; the order's own 30% typed again is not a change."""
    desk = _Counter()
    within = desk.note(desk.agreed(), discount_percent="4")
    assert desk.approve_note(within, desk.manager) == "APPROVED"

    agreed = desk.agreed(desk.head, discount_percent="30")
    same = desk.note(agreed, discount_percent="30")
    assert desk.approve_note(same, desk.manager) == "APPROVED"

    # A smaller discount, and a higher price, give nothing away.
    less = desk.note(
        desk.agreed(desk.head, discount_percent="30"), discount_percent="2"
    )
    assert desk.approve_note(less, desk.manager) == "APPROVED"
    dearer = desk.note(desk.agreed(), unit_price="110")
    assert desk.approve_note(dearer, desk.manager) == "APPROVED"


@pytest.mark.parametrize(
    ("line", "header"),
    [({"discount_percent": "30"}, {}), ({}, {"bill_discount_percent": "30"})],
)
def test_a_note_reduction_nobody_judged_is_caught_at_the_bill(
    line: dict[str, str], header: dict[str, str]
) -> None:
    """A note approved before notes were judged: its bill answers for the 30%."""
    desk = _Counter()
    note_id = desk.note(desk.agreed(), header=header, **line)
    # As a note approved before D-PRC-23 was: approved, with nothing judged.
    desk.notes.stage_approval(
        note_id, firm_scope=desk.firm_id, actor_id=desk.actor, check_licences=False
    )
    desk.session.commit()
    bill_id = desk.bill(note_id)

    with pytest.raises(ValidationError, match="carries a discount of 30.00%"):
        desk.approve_bill(bill_id, desk.manager)

    assert desk.approve_bill(bill_id, desk.head) == "APPROVED"


def test_a_bill_that_ships_an_order_itself_does_not_judge_the_order_again() -> None:
    """Note stage off: the head's 30% order is billed by the manager.

    The discount on the bill is the order's, judged when the head approved
    it. A discount the manager types on that bill is the manager's.
    """
    desk = _Counter(notes=False)

    kept = desk.bill_of_order(desk.agreed(desk.head, discount_percent="30"))
    assert desk.approve_bill(kept, desk.manager) == "APPROVED"

    typed = desk.bill_of_order(desk.agreed(), bill_discount_percent="30")
    with pytest.raises(ValidationError, match="carries a discount of 30.00%"):
        desk.approve_bill(typed, desk.manager)
    assert desk.approve_bill(typed, desk.head) == "APPROVED"


def test_what_a_note_line_types_is_read_against_its_order_line() -> None:
    """Silence is the order's; a larger discount or a lower price is the note's."""

    def line(**fields: str) -> SimpleNamespace:
        """Describe a line by the figures the judge reads."""
        return SimpleNamespace(
            line_number=1, **{name: D(value) for name, value in fields.items()}
        )

    order = line(
        quantity="10",
        unit_price="100",
        discount_amount="100",
        discount_percent="10",
        bill_discount_amount="90",
    )

    def note(**fields: str) -> SimpleNamespace:
        """Describe a note line of 4 of the order's 10."""
        base = {
            "current_delivery_quantity": "4",
            "unit_price": "100",
            "gross_amount": "400",
            "discount_amount": "40",
            "bill_discount_amount": "36",
        }
        return line(**(base | fields))

    assert note_reduction(note(), order) is None
    # A ten-thousandth of rounding in a slice is still the inheritance.
    assert note_reduction(note(discount_amount="40.0001"), order) is None
    typed = note_reduction(note(discount_amount="120"), order)
    assert typed is not None
    assert (typed.typed_line, typed.typed_bill) == (True, False)
    assert typed.line.percent == D("30.00")
    shared = note_reduction(note(bill_discount_amount="76"), order)
    assert shared is not None
    assert (shared.typed_line, shared.typed_bill) == (False, True)
    # At another price the order's rate is what silence inherits.
    cut = note_reduction(
        note(unit_price="50", gross_amount="200", discount_amount="20"), order
    )
    assert cut is not None
    assert (cut.typed_line, cut.line.price_cut, cut.line.percent) == (
        False,
        D("200"),
        D("50.00"),
    )


@pytest.mark.parametrize("stock_unit_named", [True, False])
def test_half_the_price_of_a_box_is_refused_as_half_off(
    stock_unit_named: bool,
) -> None:
    """D-PRC-24: 2 BOX of 12 at 600.00 a box, where a piece is 100.00.

    A line in another unit than its stock was not judged on price at all, so
    the sales manager approved it, delivered 24 pieces and billed 1,416.00.
    """
    desk = _Desk()
    piece, box, _ = box_of_twelve(desk.session, desk.setup)
    units = {"sales_uom_id": box} | (
        {"inventory_uom_id": piece} if stock_unit_named else {}
    )

    cut = desk.order(price="600", units=units)
    with pytest.raises(ValidationError) as refused:
        desk.approve(cut, desk.manager)

    assert str(refused.value.message) == (
        "Line 1 is priced at 600.00 where the customer's price is 1200.00: "
        "50.00% off in all, above your limit of 5.00%. It needs approval by "
        "someone allowed at least 50.00%."
    )
    assert desk.approve(cut, desk.head) == "APPROVED"
    # The box's own price, 5% under it, and no price typed are not refused.
    for price in ("1200", "1140", None):
        assert desk.approve(desk.order(price=price, units=units), desk.manager) == (
            "APPROVED"
        )
    # A cut in the box's price and a typed discount are one reduction.
    both = desk.order(price="1176", discount_percent="4", units=units)
    with pytest.raises(ValidationError, match="with a typed discount besides: 5.92%"):
        desk.approve(both, desk.manager)


def test_a_counter_bill_by_the_box_at_half_price_is_refused() -> None:
    """Stages off: the bill's own order is judged in boxes at its approval."""
    desk = _Desk(counter=True)
    _, box, _ = box_of_twelve(desk.session, desk.setup)
    draft = desk.bills.create_invoice(
        SalesInvoiceCreate(
            customer_id=desk.setup.customer.id,
            invoice_date=DAY,
            lines=[
                SalesInvoiceLineWrite(
                    product_id=desk.setup.product.id,
                    line_number=1,
                    current_invoice_quantity=D("2"),
                    invoice_uom_id=box,
                    unit_price=D("600"),
                )
            ],
        ),
        firm_id=desk.firm_id,
        actor_id=desk.actor,
    )

    with pytest.raises(ValidationError, match=r"600.00 where .* 1200.00: 50.00% off"):
        desk.bills.approve_invoice(
            draft.id, firm_scope=desk.firm_id, actor_id=desk.manager
        )


def test_a_line_with_free_goods_is_still_judged_on_its_price() -> None:
    """2 + 1 free at half price: the free unit does not hide the price cut."""
    desk = _Desk()
    cut = desk.order(price="42", units={"free_quantity": D("1")})

    with pytest.raises(ValidationError, match=r"42.00 where .* 84.00: 50.00% off"):
        desk.approve(cut, desk.manager)


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
