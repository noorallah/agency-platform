"""An offer names only this firm's masters, and a bad one cannot stop a sale.

D-PRC-5, driven 2026-10-06: an ACTIVE offer whose free product was an id that
did not exist, or another firm's product, was accepted with 201 and every
quotation and order it matched then answered 500. Two halves: the offer is
refused where it is written -- created, revised, copied -- and an offer
already in the store with such a row is passed over by pricing, so the order
screen stays up.

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.products.models import Product
from app.promotions.models import Promotion, PromotionAction, PromotionCondition
from app.promotions.schemas import (
    PromotionActionType,
    PromotionActionWrite,
    PromotionConditionOperator,
    PromotionConditionWrite,
    PromotionField,
    PromotionStatus,
    PromotionWrite,
)
from app.promotions.schemas.promotion import ComboItem
from app.promotions.services import PromotionCrudService
from app.promotions.services.promotion_copy import PromotionCopyService
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session

ORDER_DATE = date(2026, 8, 4)


def _shop() -> tuple[Session, _Firm]:
    """Return a firm with stock on a request-shaped session."""
    session = _request_session()
    return session, _Firm(session)


def _other_firms_product(session: Session) -> Product:
    """Create a second firm in the same store, holding one product."""
    firm = Firm(
        name="Another firm",
        code="OTHER01",
        country="IN",
        currency_code="INR",
        financial_year_start=ORDER_DATE.replace(month=4, day=1),
    )
    session.add(firm)
    session.flush()
    product = Product(
        firm_id=firm.id,
        code="THEIRS",
        name="Their product",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(product)
    session.commit()
    return product


def _gift_offer(
    gift: UUID | None,
    *,
    code: str = "GIFT",
    status: PromotionStatus = PromotionStatus.ACTIVE,
    conditions: list[PromotionConditionWrite] | None = None,
    actions: list[PromotionActionWrite] | None = None,
) -> PromotionWrite:
    """Describe an offer giving one of ``gift`` away, or the given benefits."""
    return PromotionWrite(
        code=code,
        name=f"Offer {code}",
        status=status,
        conditions=conditions or [],
        actions=actions
        or [
            PromotionActionWrite(
                action_type=PromotionActionType.FREE_PRODUCT,
                free_quantity=Decimal("1"),
                free_product_id=gift,
            )
        ],
    )


def _create(setup: _Firm, data: PromotionWrite) -> Promotion:
    """Write an offer through the service the route calls."""
    return PromotionCrudService(setup.session).create_promotion(
        data, firm_id=setup.firm.id, actor_id=uuid4()
    )


def _stored_gift_offer(setup: _Firm, gift: UUID, *, code: str = "BROKEN") -> Promotion:
    """Put an ACTIVE offer in the store directly, as one written before today."""
    row = Promotion(
        firm_id=setup.firm.id,
        code=code,
        name=f"Offer {code}",
        priority=10,
        status=PromotionStatus.ACTIVE.value,
        allow_stacking=True,
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
            action_type=PromotionActionType.FREE_PRODUCT.value,
            parameters={
                "buy_quantity": "1",
                "free_quantity": "1",
                "free_product_id": str(gift),
            },
        )
    )
    setup.session.commit()
    setup.session.refresh(row)
    return row


def test_an_offer_giving_away_an_unknown_product_is_refused() -> None:
    """An id nothing answers to: 422 naming the benefit, and nothing written."""
    session, setup = _shop()

    with pytest.raises(ValidationError) as refused:
        _create(setup, _gift_offer(UUID(int=1)))
    session.rollback()

    assert refused.value.message == (
        "Benefit 1: the free product was not found in this firm."
    )
    assert session.scalars(select(Promotion)).all() == []


def test_an_offer_giving_away_another_firms_product_is_refused() -> None:
    """Another firm's row reads as not found, which is all it should."""
    session, setup = _shop()
    theirs = _other_firms_product(session)

    with pytest.raises(ValidationError) as refused:
        _create(setup, _gift_offer(theirs.id))
    session.rollback()

    assert refused.value.message == (
        "Benefit 1: the free product was not found in this firm."
    )


def test_an_offer_giving_away_a_retired_product_is_refused() -> None:
    """Live means not deleted: a retired product cannot be given away."""
    session, setup = _shop()
    setup.product.is_deleted = True
    session.commit()

    with pytest.raises(ValidationError):
        _create(setup, _gift_offer(setup.product.id))
    session.rollback()


def test_an_offer_giving_away_the_firms_own_product_is_written() -> None:
    """The ordinary case is untouched."""
    _session, setup = _shop()

    row = _create(setup, _gift_offer(setup.product.id))

    assert row.status == "ACTIVE"


@pytest.mark.parametrize(
    ("field", "label"),
    [
        (PromotionField.PRODUCT_ID, "product"),
        (PromotionField.PRODUCT_CATEGORY_ID, "product category"),
        (PromotionField.CUSTOMER_ID, "customer"),
        (PromotionField.CUSTOMER_GROUP_ID, "customer group"),
        (PromotionField.BRANCH_ID, "branch"),
        (PromotionField.TERRITORY_ID, "territory"),
        (PromotionField.ROUTE_ID, "route"),
    ],
)
def test_a_condition_naming_an_unknown_master_is_refused(
    field: PromotionField, label: str
) -> None:
    """Each id-typed condition is looked up, and the refusal names it."""
    session, setup = _shop()

    with pytest.raises(ValidationError) as refused:
        _create(
            setup,
            _gift_offer(
                setup.product.id,
                conditions=[
                    PromotionConditionWrite(
                        sequence=2,
                        field_key=field,
                        operator=PromotionConditionOperator.EQUALS,
                        value_text=str(uuid4()),
                    )
                ],
            ),
        )
    session.rollback()

    assert refused.value.message == (
        f"Condition 2: the {label} was not found in this firm."
    )


def test_a_list_condition_is_checked_entry_by_entry() -> None:
    """`IN` holds its ids in a list; one stranger among them refuses it."""
    session, setup = _shop()
    theirs = _other_firms_product(session)

    def offer(ids: list[object]) -> PromotionWrite:
        """Describe an offer for a list of products."""
        return _gift_offer(
            setup.product.id,
            conditions=[
                PromotionConditionWrite(
                    field_key=PromotionField.PRODUCT_ID,
                    operator=PromotionConditionOperator.IN,
                    value_json=ids,
                )
            ],
        )

    with pytest.raises(ValidationError) as refused:
        _create(setup, offer([str(setup.product.id), str(theirs.id)]))
    session.rollback()
    assert refused.value.message == (
        "Condition 1: the product was not found in this firm."
    )

    assert _create(setup, offer([str(setup.product.id)])).code == "GIFT"


def test_a_combo_naming_another_firms_product_is_refused() -> None:
    """The products of a combo set are the firm's own too."""
    session, setup = _shop()
    theirs = _other_firms_product(session)

    with pytest.raises(ValidationError) as refused:
        _create(
            setup,
            _gift_offer(
                None,
                actions=[
                    PromotionActionWrite(
                        action_type=PromotionActionType.COMBO_PRICE,
                        amount=Decimal("150"),
                        combo_items=[
                            ComboItem(
                                product_id=setup.product.id, quantity=Decimal("1")
                            ),
                            ComboItem(product_id=theirs.id, quantity=Decimal("1")),
                        ],
                    )
                ],
            ),
        )
    session.rollback()

    assert refused.value.message == (
        "Benefit 1: a product of the combo was not found in this firm."
    )


def test_a_revision_is_checked_as_a_new_offer_is() -> None:
    """Superseding a live offer cannot bring in a stranger's product."""
    session, setup = _shop()
    live = _create(setup, _gift_offer(setup.product.id))

    with pytest.raises(ValidationError) as refused:
        PromotionCrudService(session).update_promotion(
            live.id,
            _gift_offer(UUID(int=1)),
            firm_scope=setup.firm.id,
            actor_id=uuid4(),
        )
    session.rollback()

    assert refused.value.message == (
        "Benefit 1: the free product was not found in this firm."
    )
    assert [row.version_number for row in session.scalars(select(Promotion))] == [1]


def test_a_draft_edit_is_checked_too() -> None:
    """A draft is edited in place, on the same check."""
    session, setup = _shop()
    draft = _create(setup, _gift_offer(setup.product.id, status=PromotionStatus.DRAFT))

    with pytest.raises(ValidationError):
        PromotionCrudService(session).update_promotion(
            draft.id,
            _gift_offer(UUID(int=1), status=PromotionStatus.DRAFT),
            firm_scope=setup.firm.id,
            actor_id=uuid4(),
        )
    session.rollback()


def test_a_broken_offer_can_still_be_switched_off() -> None:
    """An offer holding a product retired since must be something one can stop."""
    session, setup = _shop()
    broken = _stored_gift_offer(setup, UUID(int=1))

    successor = PromotionCrudService(session).update_promotion(
        broken.id,
        _gift_offer(UUID(int=1), code="BROKEN", status=PromotionStatus.INACTIVE),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )

    assert successor.status == "INACTIVE"


def test_a_copy_of_an_offer_naming_a_stranger_is_refused_by_code() -> None:
    """All or nothing, and the refusal says which offer."""
    session, setup = _shop()
    good = _create(setup, _gift_offer(setup.product.id, code="GOOD"))
    broken = _stored_gift_offer(setup, UUID(int=1))
    session.add(
        PromotionCondition(
            firm_id=setup.firm.id,
            promotion_id=good.id,
            sequence=1,
            field_key=PromotionField.LINE_QUANTITY.value,
            operator=PromotionConditionOperator.GREATER_OR_EQUAL.value,
            value_number=Decimal("1"),
        )
    )
    session.commit()

    with pytest.raises(ValidationError) as refused:
        PromotionCopyService(session).copy(
            [good.id, broken.id],
            effective_from=ORDER_DATE,
            effective_to=ORDER_DATE,
            code_suffix="-27",
            firm_id=setup.firm.id,
            actor_id=uuid4(),
        )
    session.rollback()

    assert refused.value.message == (
        "BROKEN: Benefit 1: the free product was not found in this firm."
    )
    assert {row.code for row in session.scalars(select(Promotion))} == {
        "GOOD",
        "BROKEN",
    }


def _order_of(setup: _Firm) -> SalesOrderCreate:
    """Describe an order of nine of the firm's product at 100 each."""
    return SalesOrderCreate(
        customer_id=setup.customer.id,
        branch_id=setup.branch.id,
        warehouse_id=setup.warehouse.id,
        order_date=ORDER_DATE,
        lines=[
            SalesOrderLineWrite(
                line_number=1,
                product_id=setup.product.id,
                quantity=Decimal("9"),
                unit_price=Decimal("100"),
            )
        ],
    )


@pytest.mark.parametrize("stranger", ["unknown", "another firm's", "retired"])
def test_an_order_is_saved_past_a_stored_offer_with_a_bad_gift(stranger: str) -> None:
    """The row is already in the store: the order saves and gets no gift."""
    session, setup = _shop()
    if stranger == "unknown":
        gift = UUID(int=1)
    elif stranger == "another firm's":
        gift = _other_firms_product(session).id
    else:
        retired = Product(
            firm_id=setup.firm.id,
            code="RETIRED",
            name="Retired",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            is_deleted=True,
        )
        session.add(retired)
        session.commit()
        gift = retired.id
    _stored_gift_offer(setup, gift)

    order = SalesOrderService(session).create_order(
        _order_of(setup), firm_id=setup.firm.id, actor_id=uuid4()
    )

    session.expire_all()
    lines = session.scalars(
        select(SalesOrderLine).where(
            SalesOrderLine.sales_order_id == order.id,
            SalesOrderLine.is_deleted.is_(False),
        )
    ).all()
    assert [(line.product_id, line.quantity) for line in lines] == [
        (setup.product.id, Decimal("9.0000"))
    ]


def test_a_quotation_is_saved_past_a_stored_offer_with_a_bad_gift() -> None:
    """The quotation prices through the same evaluation, and stays up too."""
    session, setup = _shop()
    _stored_gift_offer(setup, UUID(int=1))

    quotation = QuotationService(session).create_quotation(
        QuotationCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            quotation_date=ORDER_DATE,
            valid_until=ORDER_DATE,
            warehouse_id=setup.warehouse.id,
            lines=[
                QuotationLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("9"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    assert quotation.id is not None


def test_the_trace_says_why_nothing_was_given() -> None:
    """A passed-over gift is explained, not silently dropped."""
    from app.promotions.schemas import (
        PromotionEvaluationRequest,
        PromotionLineRequest,
    )
    from app.promotions.services import PromotionService

    session, setup = _shop()
    _stored_gift_offer(setup, UUID(int=1))

    outcome = PromotionService(session).evaluate(
        PromotionEvaluationRequest(
            transaction_type="SALES_ORDER",
            transaction_date=ORDER_DATE,
            customer_id=setup.customer.id,
            lines=[
                PromotionLineRequest(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("9"),
                    gross=Decimal("900"),
                )
            ],
        ),
        firm_scope=setup.firm.id,
    )

    assert outcome.gifts == []
    assert outcome.decisions[-1].reason == (
        "The product this offer gives away is not one of this firm's "
        "products any more, so nothing was given."
    )


def test_an_offer_with_no_threshold_gives_once_on_a_real_order() -> None:
    """An offer written through the service with no buy quantity gives one.

    The stored shape spells a missing threshold as the text "None", and the
    engine read that as a number: the order answered 500 for an offer whose
    free product was the firm's own all along.
    """
    session, setup = _shop()
    present = Product(
        firm_id=setup.firm.id,
        code="FREE-001",
        name="Free one",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(present)
    session.commit()
    _create(setup, _gift_offer(present.id))

    order = SalesOrderService(session).create_order(
        _order_of(setup), firm_id=setup.firm.id, actor_id=uuid4()
    )

    session.expire_all()
    lines = session.scalars(
        select(SalesOrderLine)
        .where(
            SalesOrderLine.sales_order_id == order.id,
            SalesOrderLine.is_deleted.is_(False),
        )
        .order_by(SalesOrderLine.line_number)
    ).all()
    assert [(line.product_id, line.free_quantity) for line in lines] == [
        (setup.product.id, Decimal("0.0000")),
        (present.id, Decimal("1.0000")),
    ]
