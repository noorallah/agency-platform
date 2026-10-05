"""A scheme stops at its budget, in money or in free units.

A principal funds a scheme with a budget -- "up to Rs 50 of discount", "up
to 3 free units" -- and an offer could be capped only by the number of
claims. The two budgets are counted exactly as that number is: from CLAIMED
redemptions across the offer's version group, at approval, under the lock,
never while a document is priced. A document that would take the offer past
its budget is refused whole and by name; an offer with nothing left, or with
too little left for the document in hand, is not quoted.

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.products.models import Product
from app.promotions.models import Promotion, PromotionAction, PromotionRedemption
from app.promotions.schemas import (
    PromotionActionType,
    PromotionActionWrite,
    PromotionEvaluationRequest,
    PromotionLineRequest,
    PromotionStatus,
    PromotionWrite,
)
from app.promotions.services import (
    PromotionCrudService,
    PromotionReportService,
    PromotionService,
)
from app.promotions.services.promotion_copy import PromotionCopyService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine, SalesWorkflowSettings
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService
from tests.unit.test_sales_chain_synthesis import (
    _Firm,
    _request_session,
    _sent_back,
)

TEN_PERCENT = (PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})
TWO_PLUS_ONE = (
    PromotionActionType.FREE_QUANTITY,
    {"buy_quantity": "2", "free_quantity": "1"},
)


def _offer(
    setup: _Firm,
    *,
    code: str = "SCHEME",
    action: tuple[PromotionActionType, dict[str, object]] = TEN_PERCENT,
    value: str | None = None,
    free: str | None = None,
    priority: int = 10,
) -> Promotion:
    """Publish an offer with a budget in money, in free units, or neither."""
    row = Promotion(
        firm_id=setup.firm.id,
        code=code,
        name=f"Scheme {code}",
        priority=priority,
        status=PromotionStatus.ACTIVE.value,
        allow_stacking=True,
        max_benefit_amount=None if value is None else Decimal(value),
        max_free_quantity=None if free is None else Decimal(free),
        version_group_id=uuid4(),
        version_number=1,
    )
    setup.session.add(row)
    setup.session.flush()
    setup.session.add(
        PromotionAction(
            firm_id=setup.firm.id,
            promotion_id=row.id,
            sequence=1,
            action_type=action[0].value,
            parameters=action[1],
        )
    )
    setup.session.commit()
    setup.session.refresh(row)
    return row


def _order_of(
    setup: _Firm, quantity: str = "4", *, free: str | None = None
) -> SalesOrderCreate:
    """Describe an order of the firm's product at 100 each."""
    return SalesOrderCreate(
        customer_id=setup.customer.id,
        branch_id=setup.branch.id,
        warehouse_id=setup.warehouse.id,
        order_date=date(2026, 8, 4),
        lines=[
            SalesOrderLineWrite(
                line_number=1,
                product_id=setup.product.id,
                quantity=Decimal(quantity),
                free_quantity=None if free is None else Decimal(free),
                unit_price=Decimal("100"),
            )
        ],
    )


def _order(setup: _Firm, quantity: str = "4", *, free: str | None = None) -> SalesOrder:
    """Save a draft order of the firm's product at 100 each."""
    return SalesOrderService(setup.session).create_order(
        _order_of(setup, quantity, free=free),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _line(session: Session, order: SalesOrder) -> SalesOrderLine:
    """Return an order's one live line, freshly read."""
    session.expire_all()
    return session.scalars(
        select(SalesOrderLine).where(
            SalesOrderLine.sales_order_id == order.id,
            SalesOrderLine.is_deleted.is_(False),
        )
    ).one()


def _approve(setup: _Firm, order: SalesOrder) -> None:
    """Approve one order."""
    SalesOrderService(setup.session).approve_order(
        order.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )


def _resave(setup: _Firm, order: SalesOrder, quantity: str = "4") -> SalesOrder:
    """Save a draft order again with nothing on it changed."""
    return SalesOrderService(setup.session).update_order(
        order.id,
        _order_of(setup, quantity),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )


def _shop() -> tuple[Session, _Firm]:
    """Return a firm with stock on a request-shaped session."""
    session = _request_session()
    return session, _Firm(session)


def test_an_order_that_would_overrun_the_value_budget_is_refused_by_name() -> None:
    """Budget 50, two orders worth 40 each: the second approval is refused."""
    session, setup = _shop()
    _offer(setup, value="50")
    first, second = _order(setup), _order(setup)
    assert _line(session, first).discount_amount == Decimal("40.0000")
    assert _line(session, second).discount_amount == Decimal(
        "40.0000"
    ), "both were priced while the budget was whole: a draft takes nothing"

    _approve(setup, first)
    with pytest.raises(ValidationError) as refused:
        _approve(setup, second)
    session.rollback()

    assert str(refused.value) == (
        "Promotion SCHEME has 10.00 left of its budget of 50.00, and this "
        "document would take 40.00. Re-save the document to price it without."
    )
    stored = session.get(SalesOrder, second.id)
    assert stored is not None and stored.status == "DRAFT"

    # Saved again it is priced without the offer -- whole or not at all, never
    # the ten that was left -- and approves.
    _resave(setup, second)
    assert _line(session, second).discount_amount == Decimal("0.0000")
    _approve(setup, second)

    # What is left still goes to a document it covers.
    small = _order(setup, "1")
    assert _line(session, small).discount_amount == Decimal("10.0000")
    _approve(setup, small)


def test_an_order_that_would_overrun_the_free_quantity_budget_is_refused() -> None:
    """Budget 3 free units, two orders earning 2 each: the second is refused."""
    session, setup = _shop()
    _offer(setup, action=TWO_PLUS_ONE, free="3")
    first, second = _order(setup), _order(setup)
    assert _line(session, second).free_quantity == Decimal("2.0000")

    _approve(setup, first)
    claimed = session.scalars(
        select(PromotionRedemption).where(PromotionRedemption.status == "CLAIMED")
    ).one()
    assert claimed.free_quantity == Decimal("2.0000")
    assert claimed.benefit_amount == Decimal("0.0000"), "free goods cost no money"

    with pytest.raises(ValidationError) as refused:
        _approve(setup, second)
    session.rollback()
    assert str(refused.value) == (
        "Promotion SCHEME has 1 left of its budget of 3 free units, and this "
        "document would take 2. Re-save the document to price it without."
    )

    _resave(setup, second)
    assert _line(session, second).free_quantity == Decimal("0.0000")
    _approve(setup, second)


def test_cancelling_an_order_gives_its_part_of_the_budget_back() -> None:
    """A reversed claim counts for nothing, in money as in number."""
    session, setup = _shop()
    _offer(setup, value="50")
    first = _order(setup)
    _approve(setup, first)
    assert _line(session, _order(setup)).discount_amount == Decimal(
        "0.0000"
    ), "ten left does not cover forty"

    SalesOrderService(session).cancel_order(
        first.id, firm_scope=setup.firm.id, actor_id=uuid4(), reason="changed mind"
    )

    again = _order(setup)
    assert _line(session, again).discount_amount == Decimal("40.0000")
    _approve(setup, again)


def test_a_budget_that_is_spent_is_not_quoted_and_the_trace_says_why() -> None:
    """Nobody is promised a price the approval would refuse."""
    session, setup = _shop()
    _offer(setup, value="40")
    _approve(setup, _order(setup))

    later = _order(setup, "1")

    assert _line(session, later).discount_amount == Decimal("0.0000")
    outcome = PromotionService(session).evaluate(
        PromotionEvaluationRequest(
            transaction_type="SALES_ORDER",
            transaction_date=date(2026, 8, 4),
            lines=[
                PromotionLineRequest(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("1"),
                    gross=Decimal("100"),
                )
            ],
        ),
        firm_scope=setup.firm.id,
    )
    assert outcome.applied == []
    assert [item.reason for item in outcome.decisions] == [
        "This offer's budget of 40.00 has all been given."
    ]


def test_a_document_too_big_for_what_is_left_is_priced_without_and_told() -> None:
    """Whole or not at all while pricing too, with the figures in the trace."""
    session, setup = _shop()
    _offer(setup, action=TWO_PLUS_ONE, free="3")
    _approve(setup, _order(setup))

    outcome = PromotionService(session).evaluate(
        PromotionEvaluationRequest(
            transaction_type="SALES_ORDER",
            transaction_date=date(2026, 8, 4),
            lines=[
                PromotionLineRequest(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("4"),
                    gross=Decimal("400"),
                )
            ],
        ),
        firm_scope=setup.firm.id,
    )

    assert outcome.lines[0].free_quantity == Decimal("0")
    assert outcome.applied == [] and outcome.applied_promotion_codes == []
    assert [(item.matched, item.reason) for item in outcome.decisions] == [
        (
            False,
            "This offer has 1 left of its budget of 3 free units, and this "
            "document would take 2.",
        )
    ]


def test_a_counter_bill_honours_the_budget_when_the_bill_is_approved() -> None:
    """Two draft bills hold nothing; the first approved takes the budget."""
    session, setup = _shop()
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    _offer(setup, value="50")
    service = SalesInvoiceService(session)
    firm, actor = setup.firm.id, uuid4()
    first = service.create_invoice(setup.bare_bill(), firm_id=firm, actor_id=actor)
    second = service.create_invoice(setup.bare_bill(), firm_id=firm, actor_id=actor)
    assert first.grand_total == second.grand_total == Decimal("360.0000")

    service.approve_invoice(first.id, firm_scope=firm, actor_id=actor)
    with pytest.raises(ValidationError) as refused:
        service.approve_invoice(second.id, firm_scope=firm, actor_id=actor)
    session.rollback()
    assert str(refused.value) == (
        "Promotion SCHEME has 10.00 left of its budget of 50.00, and this "
        "document would take 40.00. Re-save the document to price it without."
    )
    stored = session.get(SalesInvoice, second.id)
    assert stored is not None and stored.status == "DRAFT"

    # "Re-save" is true for a bill: the same bill saved again is priced
    # without the offer, and approves.
    edit = SalesInvoiceCreate(
        **_sent_back(service, second, "4").model_dump(exclude_unset=True)
    )
    again = service.update_invoice(second.id, edit, firm_id=firm, actor_id=actor)
    assert again.grand_total == Decimal("400.0000")
    service.approve_invoice(second.id, firm_scope=firm, actor_id=actor)


def _edit(code: str = "SCHEME", **budget: object) -> PromotionWrite:
    """Describe an edit of the offer: its wording, and any budget named."""
    return PromotionWrite(
        code=code,
        name="Scheme, reworded",
        status=PromotionStatus.ACTIVE,
        actions=[
            PromotionActionWrite(
                sequence=1,
                action_type=PromotionActionType.LINE_DISCOUNT_PERCENT,
                percent=Decimal("10"),
            )
        ],
        **budget,  # type: ignore[arg-type]
    )


def test_a_new_revision_keeps_the_budget_and_what_was_taken_of_it() -> None:
    """An edit that names no budget leaves it alone, and does not refill it."""
    session, setup = _shop()
    offer = _offer(setup, value="50", free="9")
    _approve(setup, _order(setup))
    crud = PromotionCrudService(session)

    successor = crud.update_promotion(
        offer.id, _edit(), firm_scope=setup.firm.id, actor_id=uuid4()
    )

    assert successor.id != offer.id and successor.version_number == 2
    assert successor.max_benefit_amount == Decimal("50.0000")
    assert successor.max_free_quantity == Decimal("9.0000")
    shown = crud.promotion_response(successor)
    assert shown.benefit_amount_claimed == Decimal("40.0000")
    assert shown.remaining_benefit_amount == Decimal("10.0000")
    assert _line(session, _order(setup)).discount_amount == Decimal(
        "0.0000"
    ), "the forty claimed on the first revision still counts"

    # An explicit null clears it, and a new figure replaces it.
    lifted = crud.update_promotion(
        successor.id,
        _edit(max_benefit_amount=None, max_free_quantity=Decimal("5")),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    assert lifted.max_benefit_amount is None
    assert lifted.max_free_quantity == Decimal("5.0000")
    assert _line(session, _order(setup)).discount_amount == Decimal("40.0000")


def test_a_claim_priced_on_an_earlier_revision_counts_against_the_same_budget() -> None:
    """One priced before an edit, one after: the budget is the group's."""
    session, setup = _shop()
    offer = _offer(setup, value="50")
    before = _order(setup)
    PromotionCrudService(session).update_promotion(
        offer.id, _edit(), firm_scope=setup.firm.id, actor_id=uuid4()
    )
    after = _order(setup)
    assert _line(session, after).discount_amount == Decimal("40.0000")

    _approve(setup, before)
    with pytest.raises(ValidationError) as refused:
        _approve(setup, after)
    session.rollback()
    assert "has 10.00 left of its budget of 50.00" in str(refused.value)


def test_a_draft_offer_keeps_and_clears_its_budget_the_same_way() -> None:
    """Edited in place, a draft follows the same rule for a field left out."""
    session, setup = _shop()
    crud = PromotionCrudService(session)
    draft = crud.create_promotion(
        _edit(
            max_benefit_amount=Decimal("500"), max_free_quantity=Decimal("20")
        ).model_copy(update={"status": PromotionStatus.DRAFT}),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    assert draft.max_benefit_amount == Decimal("500")

    plain = _edit().model_copy(update={"status": PromotionStatus.DRAFT})
    kept = crud.update_promotion(
        draft.id, plain, firm_scope=setup.firm.id, actor_id=uuid4()
    )
    assert (kept.max_benefit_amount, kept.max_free_quantity) == (
        Decimal("500"),
        Decimal("20"),
    )

    cleared = crud.update_promotion(
        draft.id,
        PromotionWrite(
            **{
                **plain.model_dump(exclude_unset=True),
                "status": PromotionStatus.DRAFT,
                "max_free_quantity": None,
            }
        ),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    assert cleared.max_benefit_amount == Decimal("500")
    assert cleared.max_free_quantity is None


@pytest.mark.parametrize("field", ["max_benefit_amount", "max_free_quantity"])
@pytest.mark.parametrize("value", ["0", "-5"])
def test_a_budget_is_more_than_nothing(field: str, value: str) -> None:
    """Zero is not "no budget": that is null, and zero would give nothing."""
    with pytest.raises(SchemaError):
        _edit(**{field: Decimal(value)})


def test_a_copied_offer_takes_the_budget_and_starts_it_whole() -> None:
    """Next season's copy has the same budget and nothing taken from it."""
    session, setup = _shop()
    offer = _offer(setup, value="50", free="9")
    _approve(setup, _order(setup))

    [copy] = PromotionCopyService(session).copy(
        [offer.id],
        effective_from=date(2027, 1, 1),
        effective_to=date(2027, 1, 31),
        code_suffix="-27",
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    shown = PromotionCrudService(session).promotion_response(copy)
    assert (shown.max_benefit_amount, shown.max_free_quantity) == (
        Decimal("50.0000"),
        Decimal("9.0000"),
    )
    assert shown.benefit_amount_claimed == Decimal("0")
    assert shown.remaining_benefit_amount == Decimal("50.0000")


def _statements(session: Session, call: object) -> int:
    """Count the SELECTs one call sends."""
    seen: list[str] = []

    def record(*args: object) -> None:
        """Note one statement."""
        seen.append(str(args[2]))

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        call()  # type: ignore[operator]
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return len(seen)


def test_the_list_and_the_report_show_each_budget_used_and_left() -> None:
    """Both read the budgets for the whole page in one statement."""
    session, setup = _shop()
    money = _offer(setup, code="MONEY", value="50", priority=10)
    _approve(setup, _order(setup))
    money.status = PromotionStatus.INACTIVE.value
    session.commit()
    goods = _offer(setup, code="GOODS", action=TWO_PLUS_ONE, free="3", priority=20)
    _approve(setup, _order(setup))
    plain = _offer(setup, code="PLAIN", priority=30)
    crud = PromotionCrudService(session)

    rows = {row.code: row for row in crud.promotion_responses([money, goods, plain])}
    assert (
        rows["MONEY"].max_benefit_amount,
        rows["MONEY"].benefit_amount_claimed,
        rows["MONEY"].remaining_benefit_amount,
        rows["MONEY"].remaining_free_quantity,
    ) == (Decimal("50.0000"), Decimal("40.0000"), Decimal("10.0000"), None)
    assert (
        rows["GOODS"].max_free_quantity,
        rows["GOODS"].free_quantity_claimed,
        rows["GOODS"].remaining_free_quantity,
        rows["GOODS"].remaining_benefit_amount,
    ) == (Decimal("3.0000"), Decimal("2.0000"), Decimal("1.0000"), None)
    assert (
        rows["PLAIN"].max_benefit_amount,
        rows["PLAIN"].remaining_benefit_amount,
        rows["PLAIN"].remaining_free_quantity,
    ) == (None, None, None)

    one = _statements(session, lambda: crud.promotion_responses([money]))
    three = _statements(
        session, lambda: crud.promotion_responses([money, goods, plain])
    )
    assert one == three, "a longer page asks no more questions"

    report = {
        row.code: row
        for row in PromotionReportService(session).performance_report(
            firm_scope=setup.firm.id
        )
    }
    assert (
        report["MONEY"].benefit_amount,
        report["MONEY"].max_benefit_amount,
        report["MONEY"].remaining_benefit_amount,
    ) == (Decimal("40.0000"), Decimal("50.0000"), Decimal("10.0000"))
    assert (
        report["GOODS"].free_quantity,
        report["GOODS"].max_free_quantity,
        report["GOODS"].remaining_free_quantity,
    ) == (Decimal("2.0000"), Decimal("3.0000"), Decimal("1.0000"))
    assert report["PLAIN"].remaining_benefit_amount is None
    claims = PromotionReportService(session).redemption_report(firm_scope=setup.firm.id)
    assert sorted(claim.free_quantity for claim in claims) == [
        Decimal("0.0000"),
        Decimal("2.0000"),
    ]


def test_a_free_quantity_somebody_typed_takes_nothing_from_the_budget() -> None:
    """The line keeps the typed figure, so the offer gave none of it."""
    session, setup = _shop()
    _offer(setup, action=TWO_PLUS_ONE, free="3")

    typed = _order(setup, free="1")

    assert _line(session, typed).free_quantity == Decimal("1.0000")
    _approve(setup, typed)
    rows = session.scalars(select(PromotionRedemption)).all()
    assert [row.free_quantity for row in rows if not row.is_deleted] in (
        [],
        [Decimal("0.0000")],
    )
    # The whole budget is still there for an order that takes the offer.
    assert _line(session, _order(setup)).free_quantity == Decimal("2.0000")


def test_a_gift_of_another_product_counts_as_free_units() -> None:
    """Free goods are free goods, whichever product they are."""
    session, setup = _shop()
    gift = Product(
        firm_id=setup.firm.id,
        code="GIFT-001",
        name="Gift",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(gift)
    session.commit()
    _offer(
        setup,
        action=(
            PromotionActionType.FREE_PRODUCT,
            {
                "buy_quantity": "2",
                "free_quantity": "1",
                "free_product_id": str(gift.id),
            },
        ),
        free="3",
    )

    def priced(quantity: str) -> list[Decimal]:
        """Return the free units an order of that many is offered."""
        outcome = PromotionService(session).evaluate(
            PromotionEvaluationRequest(
                transaction_type="SALES_ORDER",
                transaction_date=date(2026, 8, 4),
                lines=[
                    PromotionLineRequest(
                        line_number=1,
                        product_id=setup.product.id,
                        quantity=Decimal(quantity),
                        gross=Decimal("100") * Decimal(quantity),
                    )
                ],
            ),
            firm_scope=setup.firm.id,
        )
        session.rollback()
        assert [item.quantity for item in outcome.gifts] == [
            item.free_quantity for item in outcome.applied
        ]
        return [item.free_quantity for item in outcome.applied]

    assert priced("6") == [Decimal("3")]
    assert priced("8") == [], "four gifts do not fit a budget of three"


def test_best_offer_falls_to_the_next_when_the_best_has_no_room() -> None:
    """A budget too small for this document does not leave it with nothing."""
    session, setup = _shop()
    session.add(
        SalesWorkflowSettings(firm_id=setup.firm.id, promotion_mode="BEST_OFFER")
    )
    session.commit()
    _offer(setup, code="BIG", action=(TEN_PERCENT[0], {"percent": "20"}), value="50")
    _offer(setup, code="SMALL", priority=20)

    def taken(quantity: str) -> list[tuple[UUID | str, Decimal]]:
        """Return the offers an order of that many takes, with their worth."""
        outcome = PromotionService(session).evaluate(
            PromotionEvaluationRequest(
                transaction_type="SALES_ORDER",
                transaction_date=date(2026, 8, 4),
                lines=[
                    PromotionLineRequest(
                        line_number=1,
                        product_id=setup.product.id,
                        quantity=Decimal(quantity),
                        gross=Decimal("100") * Decimal(quantity),
                    )
                ],
            ),
            firm_scope=setup.firm.id,
        )
        session.rollback()
        return [(item.code, item.benefit_amount) for item in outcome.applied]

    assert taken("2") == [("BIG", Decimal("40.0000"))]
    assert taken("4") == [("SMALL", Decimal("40.0000"))]
