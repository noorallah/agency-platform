"""Promotions: what a customer earns, in what order, and why.

The engine is the tax engine's with one deliberate difference -- promotions
stack rather than stopping at the first match -- so most of what is worth
testing here is the arithmetic of stacking and the totality of the ordering.

The cases that matter: the same document must always price the same, a
promotion that refuses to stack must actually stop the ones behind it, stacked
percentages must compound rather than add, and no configuration may produce a
discount larger than the line -- `resolve_line_discount` refuses one, so a
promotion that could cause it would make a document unsaveable rather than
cheap.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.core.database.base import Base
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.products.models import Product
from app.promotions.models import (
    Promotion,
    PromotionAction,
    PromotionCondition,
    PromotionExecutionLog,
)
from app.promotions.schemas import (
    PromotionActionType,
    PromotionConditionOperator,
    PromotionEvaluationRequest,
    PromotionField,
    PromotionLineRequest,
    PromotionStatus,
)
from app.promotions.services import PromotionService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService


def _session_factory() -> sessionmaker[Session]:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str = "PROMO01") -> Firm:
    """Create the owning firm."""
    row = Firm(
        name=f"Firm {code}",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _product(session: Session, *, firm_id: UUID, code: str = "SKU-001") -> Product:
    """Create a product to sell."""
    row = Product(
        firm_id=firm_id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _promotion(
    session: Session,
    *,
    firm_id: UUID,
    code: str,
    priority: int = 100,
    allow_stacking: bool = True,
    status: PromotionStatus = PromotionStatus.ACTIVE,
    effective_from: date | None = None,
    effective_to: date | None = None,
    actions: list[tuple[PromotionActionType, dict[str, object]]] | None = None,
    conditions: (
        list[tuple[PromotionField, PromotionConditionOperator, dict]] | None
    ) = None,
) -> Promotion:
    """Create one promotion with its actions and conditions."""
    row = Promotion(
        firm_id=firm_id,
        code=code,
        name=f"Promotion {code}",
        priority=priority,
        status=status.value,
        allow_stacking=allow_stacking,
        effective_from=effective_from,
        effective_to=effective_to,
        version_group_id=uuid4(),
        version_number=1,
    )
    session.add(row)
    session.flush()
    for index, (action_type, params) in enumerate(actions or [], start=1):
        session.add(
            PromotionAction(
                firm_id=firm_id,
                promotion_id=row.id,
                sequence=index,
                action_type=action_type.value,
                parameters=params,
            )
        )
    for index, (field_key, operator, values) in enumerate(conditions or [], start=1):
        session.add(
            PromotionCondition(
                firm_id=firm_id,
                promotion_id=row.id,
                sequence=index,
                field_key=field_key.value,
                operator=operator.value,
                **values,
            )
        )
    session.commit()
    session.refresh(row)
    return row


def _request(
    *,
    lines: list[tuple[int, UUID | None, str, str]],
    on: date = date(2026, 8, 4),
    customer_id: UUID | None = None,
) -> PromotionEvaluationRequest:
    """Describe a document to be priced: (line_number, product, qty, gross)."""
    return PromotionEvaluationRequest(
        transaction_type="SALES_ORDER",
        transaction_date=on,
        customer_id=customer_id,
        lines=[
            PromotionLineRequest(
                line_number=number,
                product_id=product_id,
                quantity=Decimal(quantity),
                gross=Decimal(gross),
            )
            for number, product_id, quantity, gross in lines
        ],
    )


def test_a_percentage_promotion_discounts_the_line() -> None:
    """The simplest case, and the one every other case builds on."""
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="TEN",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "4", "1000")]), firm_scope=firm.id
    )

    assert result.lines[0].discount_amount == Decimal("100.00")
    assert result.applied_promotion_codes == ["TEN"]


def test_stacked_percentages_compound_rather_than_add() -> None:
    """Two ten percent offers take nineteen percent, not twenty.

    Compounding is what a shop means by stacking, and it is also what makes it
    arithmetically impossible for stacked benefits to exceed the line.
    """
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="AAA",
        priority=10,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )
    _promotion(
        session,
        firm_id=firm.id,
        code="BBB",
        priority=20,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=firm.id
    )

    assert result.lines[0].discount_amount == Decimal("190.00")
    assert result.applied_promotion_codes == ["AAA", "BBB"]


def test_a_promotion_that_does_not_stack_stops_the_ones_behind_it() -> None:
    """`allow_stacking = false` means instead of, not on top of."""
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="EXCLUSIVE",
        priority=10,
        allow_stacking=False,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "25"})],
    )
    _promotion(
        session,
        firm_id=firm.id,
        code="ALSO",
        priority=20,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=firm.id
    )

    assert result.lines[0].discount_amount == Decimal("250.00")
    assert result.applied_promotion_codes == ["EXCLUSIVE"]


def test_the_order_is_total_so_equal_priorities_never_swap() -> None:
    """Two promotions of equal priority resolve by code, every run.

    An amount then a percentage prices differently from a percentage then an
    amount, so an unstable order would make the same document price two ways.
    """
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    # Created in the reverse of their code order on purpose: if creation order
    # leaked into evaluation order, this is the test that would catch it.
    _promotion(
        session,
        firm_id=firm.id,
        code="ZZZ",
        priority=50,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "50"})],
    )
    _promotion(
        session,
        firm_id=firm.id,
        code="AAA",
        priority=50,
        actions=[(PromotionActionType.LINE_DISCOUNT_AMOUNT, {"amount": "100"})],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=firm.id
    )

    # AAA first: 100 off, leaving 900; then ZZZ takes half of what is left.
    assert result.applied_promotion_codes == ["AAA", "ZZZ"]
    assert result.lines[0].discount_amount == Decimal("550.00")


def test_stacked_discounts_can_never_exceed_the_line() -> None:
    """Whatever is configured, the line cannot go below nothing.

    `resolve_line_discount` refuses a discount larger than the line, so a
    promotion that could produce one would make the document unsaveable.
    """
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    for index in range(5):
        _promotion(
            session,
            firm_id=firm.id,
            code=f"HALF{index}",
            priority=10 + index,
            actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "90"})],
        )
    _promotion(
        session,
        firm_id=firm.id,
        code="FLAT",
        priority=99,
        actions=[(PromotionActionType.LINE_DISCOUNT_AMOUNT, {"amount": "99999"})],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=firm.id
    )

    assert result.lines[0].discount_amount <= Decimal("1000.00")


def test_free_goods_are_whole_multiples_of_what_was_bought() -> None:
    """Buying nineteen on a "ten get one" earns one, not one and nine tenths."""
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="BUY10",
        actions=[
            (
                PromotionActionType.FREE_QUANTITY,
                {"buy_quantity": "10", "free_quantity": "1"},
            )
        ],
    )

    service = PromotionService(session)
    nineteen = service.evaluate(
        _request(lines=[(1, product.id, "19", "1900")]), firm_scope=firm.id
    )
    twenty = service.evaluate(
        _request(lines=[(1, product.id, "20", "2000")]), firm_scope=firm.id
    )

    assert nineteen.lines[0].free_quantity == Decimal("1")
    assert twenty.lines[0].free_quantity == Decimal("2")


def test_a_promotion_only_touches_the_lines_it_names() -> None:
    """A product-scoped offer leaves the rest of the order alone."""
    session = _session_factory()()
    firm = _firm(session)
    wanted = _product(session, firm_id=firm.id, code="SKU-001")
    other = _product(session, firm_id=firm.id, code="SKU-002")
    _promotion(
        session,
        firm_id=firm.id,
        code="ONEPROD",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
        conditions=[
            (
                PromotionField.PRODUCT_ID,
                PromotionConditionOperator.EQUALS,
                {"value_text": str(wanted.id)},
            )
        ],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, wanted.id, "1", "1000"), (2, other.id, "1", "1000")]),
        firm_scope=firm.id,
    )

    assert result.lines[0].discount_amount == Decimal("100.00")
    assert result.lines[1].discount_amount == Decimal("0.00")


def test_a_minimum_order_value_is_read_across_the_whole_document() -> None:
    """The condition every "spend 5,000 and save" offer is built from."""
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="BIGORDER",
        actions=[(PromotionActionType.BILL_DISCOUNT_PERCENT, {"percent": "5"})],
        conditions=[
            (
                PromotionField.DOCUMENT_GROSS,
                PromotionConditionOperator.GREATER_OR_EQUAL,
                {"value_number": Decimal("5000")},
            )
        ],
    )

    service = PromotionService(session)
    small = service.evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=firm.id
    )
    large = service.evaluate(
        _request(lines=[(1, product.id, "1", "3000"), (2, product.id, "1", "3000")]),
        firm_scope=firm.id,
    )

    assert small.bill_discount_amount == Decimal("0.00")
    assert large.bill_discount_amount == Decimal("300.00")


def test_a_window_is_judged_on_the_document_date_not_today() -> None:
    """An offer that ran in April still explains an April order in September."""
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="APRIL",
        effective_from=date(2026, 4, 1),
        effective_to=date(2026, 4, 30),
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    service = PromotionService(session)
    inside = service.evaluate(
        _request(lines=[(1, product.id, "1", "1000")], on=date(2026, 4, 15)),
        firm_scope=firm.id,
    )
    outside = service.evaluate(
        _request(lines=[(1, product.id, "1", "1000")], on=date(2026, 9, 2)),
        firm_scope=firm.id,
    )

    assert inside.lines[0].discount_amount == Decimal("100.00")
    assert outside.lines[0].discount_amount == Decimal("0.00")


def test_a_draft_promotion_gives_nothing() -> None:
    """Only ACTIVE promotions are evaluated."""
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="NOTYET",
        status=PromotionStatus.DRAFT,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=firm.id
    )

    assert result.lines[0].discount_amount == Decimal("0.00")


def test_one_firm_s_promotion_never_prices_another_firm_s_document() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    session = _session_factory()()
    generous = _firm(session, code="GEN01")
    other = _firm(session, code="OTH01")
    product = _product(session, firm_id=generous.id)
    _promotion(
        session,
        firm_id=generous.id,
        code="GENEROUS",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "50"})],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=other.id
    )

    assert result.lines[0].discount_amount == Decimal("0.00")
    assert result.applied_promotion_codes == []


def test_evaluate_does_not_commit_the_caller_transaction() -> None:
    """It runs mid-document, so committing would publish a half-written order.

    The same guard `tests/unit/test_tax_framework.py` keeps over
    `TaxRuleService.simulate`, and for the same reason.
    """
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="ANY",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    pending = Product(
        firm_id=firm.id,
        code="SKU-PENDING",
        name="Half written",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(pending)
    PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=firm.id
    )
    session.rollback()

    assert (
        session.scalar(select(Product).where(Product.code == "SKU-PENDING")) is None
    ), "evaluate must not commit the caller's work"


def test_the_log_records_every_promotion_considered_not_only_the_winners() -> None:
    """The promotions that did nothing are what explain the price.

    A trace holding only what applied cannot answer why a promotion the firm
    expected did nothing, which is the question support actually gets.
    """
    session = _session_factory()()
    firm = _firm(session)
    wanted = _product(session, firm_id=firm.id, code="SKU-001")
    other = _product(session, firm_id=firm.id, code="SKU-002")
    _promotion(
        session,
        firm_id=firm.id,
        code="APPLIES",
        priority=10,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )
    _promotion(
        session,
        firm_id=firm.id,
        code="MISSES",
        priority=20,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
        conditions=[
            (
                PromotionField.PRODUCT_ID,
                PromotionConditionOperator.EQUALS,
                {"value_text": str(other.id)},
            )
        ],
    )

    result = PromotionService(session).evaluate(
        _request(lines=[(1, wanted.id, "1", "1000")]), firm_scope=firm.id
    )
    session.commit()

    codes = {item.code: item.matched for item in result.decisions}
    assert codes == {"APPLIES": True, "MISSES": False}
    log = session.scalar(select(PromotionExecutionLog))
    assert log is not None
    assert len(log.evaluation_trace["decisions"]) == 2


def test_a_promotion_reaches_a_real_sales_order() -> None:
    """The engine is wired, not merely written.

    The tax review's lesson was that a flag the engine records has to change an
    outcome -- two were stored, returned and read by nobody, so configuring
    either silently produced wrong money. This is that proof for promotions:
    the discount has to arrive on a saved line, and the tax has to fall with it.
    """
    session = _session_factory()()
    firm = _firm(session, code="WIRED01")
    branch = Branch(
        firm_id=firm.id,
        code="BR-001",
        name="Branch BR-001",
        display_name="Branch BR-001",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(branch)
    session.commit()
    warehouse = Warehouse(
        firm_id=firm.id,
        branch_id=branch.id,
        code="WH-001",
        name="Warehouse WH-001",
        display_name="Warehouse WH-001",
        status="ACTIVE",
    )
    session.add(warehouse)
    customer = Customer(
        firm_id=firm.id,
        code="CUS-001",
        customer_type="RETAIL",
        name="Customer CUS-001",
        display_name="Customer CUS-001",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(customer)
    session.commit()
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="TENOFF",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    order = SalesOrderService(session).create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 4),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    assert line.gross_amount == Decimal("1000.0000")
    assert line.discount_amount == Decimal(
        "100.0000"
    ), "the promotion has to reach the saved line, not merely the engine"
    assert line.discount_percent == Decimal("10.0000")


def test_a_typed_discount_beats_a_promotion() -> None:
    """A person deciding beats a rule -- the module's own stated precedence."""
    session = _session_factory()()
    firm = _firm(session, code="TYPED01")
    branch = Branch(
        firm_id=firm.id,
        code="BR-001",
        name="Branch BR-001",
        display_name="Branch BR-001",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(branch)
    session.commit()
    warehouse = Warehouse(
        firm_id=firm.id,
        branch_id=branch.id,
        code="WH-001",
        name="Warehouse WH-001",
        display_name="Warehouse WH-001",
        status="ACTIVE",
    )
    session.add(warehouse)
    customer = Customer(
        firm_id=firm.id,
        code="CUS-001",
        customer_type="RETAIL",
        name="Customer CUS-001",
        display_name="Customer CUS-001",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(customer)
    session.commit()
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="TENOFF",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    order = SalesOrderService(session).create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 4),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                    discount_percent=Decimal("25"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    assert line.discount_amount == Decimal("250.0000")


def test_two_live_versions_of_one_promotion_apply_once() -> None:
    """A promotion is one offer however many revisions it has had.

    The tax engine survives leaving a superseded rule ACTIVE only because it
    stops at the first match. A stacking engine that copied that query would
    apply every live version of the same promotion, so the customer would get
    the same ten percent twice for no reason anybody could explain.
    """
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    first = _promotion(
        session,
        firm_id=firm.id,
        code="TWICE",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )
    # A second live revision of the same offer, which is the state a
    # supersede would leave behind if it forgot to retire its predecessor.
    second = Promotion(
        firm_id=firm.id,
        code="TWICE",
        name="Promotion TWICE",
        priority=first.priority,
        status=PromotionStatus.ACTIVE.value,
        allow_stacking=True,
        version_group_id=first.version_group_id,
        version_number=2,
        supersedes_promotion_id=first.id,
    )
    session.add(second)
    session.flush()
    session.add(
        PromotionAction(
            firm_id=firm.id,
            promotion_id=second.id,
            sequence=1,
            action_type=PromotionActionType.LINE_DISCOUNT_PERCENT.value,
            parameters={"percent": "10"},
        )
    )
    session.commit()

    result = PromotionService(session).evaluate(
        _request(lines=[(1, product.id, "1", "1000")]), firm_scope=firm.id
    )

    assert result.lines[0].discount_amount == Decimal(
        "100.00"
    ), "one offer, however many revisions -- not 190.00"
    assert result.applied_promotion_codes == ["TWICE"]


def test_a_hand_priced_line_is_left_alone_and_the_trace_says_so() -> None:
    """A promotion the line never received must not be reported as applied.

    The shared pricing rule discards it downstream either way -- a person
    deciding beats a rule -- but a trace claiming the benefit was given is a
    lie told to exactly the person trying to work out why the price is what it
    is.
    """
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="TEN",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )

    request = _request(lines=[(1, product.id, "1", "1000")])
    request.lines[0].caller_priced = True
    result = PromotionService(session).evaluate(request, firm_scope=firm.id)

    assert result.lines[0].discount_amount == Decimal("0.00")
    assert result.applied_promotion_codes == []
    assert result.decisions[0].matched is False
    assert "priced by hand" in result.decisions[0].reason
