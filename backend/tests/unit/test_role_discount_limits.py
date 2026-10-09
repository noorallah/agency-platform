"""The largest discount a role may give on its own (BACKLOG 64 row 3).

A salesman limited to 5% types 10% on an order: it saves, but their approval
is refused naming the 10% it needs, and a manager allowed 15% approves it with
both figures on the timeline. Only a typed discount counts -- the customer's
standing rate is an arrangement the firm made -- and a bill line that inherited
its order's discount was judged with the order.
"""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.document_framework.models import DocumentLifecycleEvent
from app.identity.models import PlatformAdmin, Role, User, UserRole
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.schemas import RoleDiscountLimitsWrite
from app.sales_order.services import SalesOrderService
from app.sales_order.services.discount_limit import (
    DiscountedLine,
    DiscountLimitService,
    order_discounts,
)
from tests.unit.test_price_floor import _Shop


class _Desk(_Shop):
    """The firm, with a salesman (5%) and a manager (15%)."""

    def __init__(self) -> None:
        """Build the firm and its two people."""
        super().__init__()
        self.limits = DiscountLimitService(self.session)
        self.salesman = self.person("SALES_EXECUTIVE")
        self.manager = self.person("SALES_MANAGER")
        self.limits.replace_limits(
            [("SALES_EXECUTIVE", Decimal("5")), ("SALES_MANAGER", Decimal("15"))],
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def person(self, *role_codes: str, firm_wide: bool = True) -> UUID:
        """Create a user holding the given roles in this firm."""
        user = User(
            email=f"{uuid4().hex[:8]}@desk.test",
            full_name="Desk person",
            password_hash="x",
        )
        self.session.add(user)
        self.session.flush()
        for code in role_codes:
            role = self.session.scalar(select(Role).where(Role.code == code))
            if role is None:
                role = Role(code=code, name=code.title())
                self.session.add(role)
                self.session.flush()
            self.session.add(
                UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    firm_id=self.firm.id if firm_wide else uuid4(),
                )
            )
        self.session.commit()
        return user.id

    def approve_as(self, order_id: UUID, user_id: UUID) -> str:
        """Approve an order as somebody; return its status."""
        return (
            SalesOrderService(self.session)
            .approve_order(order_id, firm_scope=self.firm.id, actor_id=user_id)
            .status
        )


@pytest.fixture
def desk() -> _Desk:
    """Build the firm."""
    return _Desk()


def test_above_the_limit_is_saved_but_refused_naming_what_it_needs(
    desk: _Desk,
) -> None:
    """10% saves as a draft; the 5% salesman cannot approve it."""
    order_id = desk.order("100", discount_percent="10")
    with pytest.raises(
        ValidationError, match=r"10.00%, above your limit of 5.00%.*at least 10.00%"
    ):
        desk.approve_as(order_id, desk.salesman)
    desk.session.rollback()
    orders = SalesOrderService(desk.session)
    assert orders.get_order(order_id, firm_scope=desk.firm.id).status == "DRAFT"


def test_a_higher_limit_approves_and_the_timeline_says_who_allowed_what(
    desk: _Desk,
) -> None:
    """The manager's 15% clears it; the figures go on the APPROVED event."""
    order_id = desk.order("100", discount_percent="10")
    assert desk.approve_as(order_id, desk.manager) == "APPROVED"
    event = desk.event(order_id)
    assert event.actor_id == desk.manager
    assert event.details_json is not None
    assert event.details_json["discount_approval"] == {
        "typed_discount_percent": "10.00",
        "approver_limit_percent": "15.00",
    }


def test_within_the_limit_the_salesman_approves(desk: _Desk) -> None:
    """5% is exactly the limit, not above it."""
    assert desk.approve_as(desk.order("100", discount_percent="5"), desk.salesman) == (
        "APPROVED"
    )


def test_a_standing_rate_is_not_typed() -> None:
    """The customer's or a price list's rate is the firm's arrangement."""
    line = type(
        "L",
        (),
        {
            "line_number": 1,
            "gross_amount": Decimal("100"),
            "discount_amount": Decimal("20"),
            "discount_source": "customer",
            "bill_discount_amount": Decimal("0"),
        },
    )()
    (judged,) = order_discounts([line], bill_discount_source="none")
    assert judged.percent == Decimal("0")


def test_a_typed_bill_discount_adds_to_the_line_s(desk: _Desk) -> None:
    """9% on the line and a 2-point bill share is 11% off that line."""
    with pytest.raises(ValidationError, match="11.00%"):
        desk.limits.enforce(
            desk.firm.id,
            desk.salesman,
            [DiscountedLine(1, Decimal("100"), Decimal("11"))],
        )


def test_the_largest_limit_among_a_person_s_roles_counts(desk: _Desk) -> None:
    """A salesman who is also a manager may give 15%."""
    both = desk.person("SALES_EXECUTIVE", "SALES_MANAGER")
    assert desk.limits.limit_for(desk.firm.id, both) == Decimal("15.00")


def test_nobody_is_limited_until_the_firm_says_so(desk: _Desk) -> None:
    """A role with no row, another firm's role, an administrator: no limit."""
    assert desk.limits.limit_for(desk.firm.id, desk.person("CASHIER")) is None
    elsewhere = desk.person("SALES_EXECUTIVE", firm_wide=False)
    assert desk.limits.limit_for(desk.firm.id, elsewhere) is None
    admin = desk.person("SALES_EXECUTIVE")
    desk.session.add(PlatformAdmin(user_id=admin, scope="ALL_FIRMS"))
    desk.session.commit()
    assert desk.limits.limit_for(desk.firm.id, admin) is None


def test_replacing_the_list_removes_what_it_leaves_out(desk: _Desk) -> None:
    """The salesman's row goes; the manager's changes; both are audited."""
    rows = desk.limits.replace_limits(
        [("SALES_MANAGER", Decimal("12.5"))],
        firm_id=desk.firm.id,
        actor_id=desk.actor_id,
    )
    assert [(row.role_code, row.max_discount_percent) for row in rows] == [
        ("SALES_MANAGER", Decimal("12.50"))
    ]
    assert desk.limits.limit_for(desk.firm.id, desk.salesman) is None
    with pytest.raises(ValidationError, match="listed twice"):
        desk.limits.replace_limits(
            [("SALES_MANAGER", Decimal("1")), ("sales_manager", Decimal("2"))],
            firm_id=desk.firm.id,
            actor_id=desk.actor_id,
        )


def test_the_write_schema_bounds_the_percentage() -> None:
    """Over 100 is refused before it reaches the service."""
    with pytest.raises(ValueError, match="less than or equal to 100"):
        RoleDiscountLimitsWrite(
            limits=[{"role_code": "X", "max_discount_percent": "101"}]  # type: ignore[list-item]
        )


def test_a_counter_bill_judges_what_the_bill_typed(desk: _Desk) -> None:
    """The order the bill raises is not judged; the bill's typed rate is."""
    desk.stages(quotation=False, sales_order=False, delivery_note=False)
    bills = SalesInvoiceService(desk.session)
    draft = bills.create_invoice(
        SalesInvoiceCreate(
            customer_id=desk.customer.id,
            invoice_date=desk.bare_bill().invoice_date,
            lines=[
                SalesInvoiceLineWrite(
                    product_id=desk.product.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("2"),
                    unit_price=Decimal("100"),
                    discount_percent=Decimal("8"),
                )
            ],
        ),
        firm_id=desk.firm.id,
        actor_id=desk.salesman,
    )
    with pytest.raises(ValidationError, match="8.00%, above your limit of 5.00%"):
        bills.approve_invoice(draft.id, firm_scope=desk.firm.id, actor_id=desk.salesman)
    desk.session.rollback()
    approved = bills.approve_invoice(
        draft.id, firm_scope=desk.firm.id, actor_id=desk.manager
    )
    assert approved.status == "APPROVED"


def test_a_bill_inheriting_its_order_s_discount_is_not_judged_again(
    desk: _Desk,
) -> None:
    """Approved by the manager on the order; billed by the salesman."""
    order_id = desk.order("100", discount_percent="10")
    desk.approve_as(order_id, desk.manager)
    event = desk.session.scalar(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == order_id
        )
    )
    assert event is not None
    line = order_discounts(
        [
            type(
                "L",
                (),
                {
                    "line_number": 1,
                    "gross_amount": Decimal("200"),
                    "discount_amount": Decimal("20"),
                    "discount_source": "inherited",
                    "bill_discount_amount": Decimal("0"),
                },
            )()
        ],
        bill_discount_source=None,
    )
    assert desk.limits.enforce(desk.firm.id, desk.salesman, line) is None


def test_a_limit_on_a_role_nobody_holds_is_refused(desk: _Desk) -> None:
    """D-CFG-27: a mistyped role was kept, bound nobody and said nothing."""
    with pytest.raises(ValidationError, match="not a role of this firm"):
        desk.limits.replace_limits(
            [("SALES_EXEC", Decimal("5"))],
            firm_id=desk.firm.id,
            actor_id=desk.actor_id,
        )
    desk.session.rollback()
    assert [row.role_code for row in desk.limits.limits(desk.firm.id)] == [
        "SALES_EXECUTIVE",
        "SALES_MANAGER",
    ]
    rows = desk.limits.replace_limits(
        [("sales_executive", Decimal("7"))],
        firm_id=desk.firm.id,
        actor_id=desk.actor_id,
    )
    assert [row.role_code for row in rows] == ["SALES_EXECUTIVE"]
    assert desk.limits.limit_for(desk.firm.id, desk.salesman) == Decimal("7.00")
