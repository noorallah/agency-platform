"""The bill maker's choice carried along the sales chain (L7 step 6).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` section 3.3, step 6 of
section 6. A bill typed straight in is priced by the order raised behind it,
so its lines carry ``offer_choice`` to that order -- and through an edit,
which raises the order again. A bill of documents already priced refuses a
choice. A quotation turned into an order hands its choices over, and the
order checks them on its own date. Offers are still claimed only at the
bill's approval.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, ValidationError
from app.pricing.models import PriceList
from app.promotions.models import Promotion, PromotionRedemption
from app.promotions.schemas import (
    OfferChoice,
    PromotionActionType,
    PromotionConditionOperator,
    PromotionField,
)
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine, SalesOrderOffer
from tests.unit.test_offer_candidates import ON, _shop
from tests.unit.test_offer_choice import _city_not_tea5, _key
from tests.unit.test_promotions import _promotion
from tests.unit.test_sales_chain_synthesis import _Firm
from tests.unit.test_sales_chain_synthesis import (
    _session_factory as _chain_session_factory,
)


def _counter_firm() -> _Firm:
    """Build a firm that bills at the counter, with TEA-5 and TEA-11."""
    session = _chain_session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    _promotion(
        session,
        firm_id=setup.firm.id,
        code="TEA-5",
        priority=10,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "5"})],
        conditions=[
            (
                PromotionField.LINE_QUANTITY,
                PromotionConditionOperator.GREATER_OR_EQUAL,
                {"value_number": Decimal("5")},
            )
        ],
    )
    _promotion(
        session,
        firm_id=setup.firm.id,
        code="TEA-11",
        priority=20,
        actions=[
            (
                PromotionActionType.FREE_QUANTITY,
                {"buy_quantity": "11", "free_quantity": "1"},
            )
        ],
    )
    return setup


def _offer_key(session: Session, code: str) -> str:
    """Return the key an offer is chosen by."""
    offer = session.scalar(select(Promotion).where(Promotion.code == code))
    assert offer is not None, code
    return str(offer.version_group_id)


def _tea11_only(setup: _Firm) -> OfferChoice:
    """Untick TEA-5 and keep TEA-11: no discount, the free piece stays."""
    return OfferChoice(offers=[_offer_key(setup.session, "TEA-11")])


def _bill(
    setup: _Firm, quantity: str, choice: OfferChoice | None = None
) -> SalesInvoiceCreate:
    """Describe a counter bill of one line, with the choice if given."""
    data = setup.bare_bill(Decimal(quantity))
    if choice is not None:
        line = data.lines[0]
        data.lines[0] = SalesInvoiceLineWrite.model_validate(
            {**line.model_dump(exclude_unset=True), "offer_choice": choice}
        )
    return data


def _sent_back(
    setup: _Firm,
    invoice_id: UUID,
    quantity: str,
    **choice: OfferChoice | None,
) -> SalesInvoiceCreate:
    """Describe an edit sending the bill's first line back by its source."""
    (line,) = [
        item
        for item in SalesInvoiceService(setup.session)
        .invoice_response(
            SalesInvoiceService(setup.session).get_invoice(
                invoice_id, firm_scope=setup.firm.id
            )
        )
        .lines
        if item.current_invoice_quantity > 0
    ]
    fields: dict[str, object] = {
        "source_document_type": line.source_document_type,
        "source_document_id": line.source_document_id,
        "source_document_line_id": line.source_document_line_id,
        "line_number": 1,
        "current_invoice_quantity": Decimal(quantity),
        **choice,
    }
    return SalesInvoiceCreate(
        customer_id=setup.customer.id,
        invoice_date=date(2026, 8, 4),
        lines=[SalesInvoiceLineWrite.model_validate(fields)],
    )


def _billed(setup: _Firm, invoice_id: UUID) -> SalesInvoiceLine:
    """Return the bill's charged line."""
    line = setup.session.scalar(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == invoice_id,
            SalesInvoiceLine.is_deleted.is_(False),
            SalesInvoiceLine.current_invoice_quantity > 0,
        )
    )
    assert line is not None
    return line


def _live_order_line(setup: _Firm) -> SalesOrderLine:
    """Return the charged line of the one order still standing."""
    line = setup.session.scalar(
        select(SalesOrderLine)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(
            SalesOrder.status != "CANCELLED",
            SalesOrderLine.is_deleted.is_(False),
            SalesOrderLine.quantity > 0,
        )
    )
    assert line is not None
    return line


def _orders(setup: _Firm) -> int:
    """Count every order raised, withdrawn ones included."""
    return len(setup.session.scalars(select(SalesOrder)).all())


def test_a_counter_bill_carries_the_choice_to_its_order() -> None:
    """11 pieces, TEA-5 unticked: no discount, one free, the order chose."""
    setup = _counter_firm()
    invoice = SalesInvoiceService(setup.session).create_invoice(
        _bill(setup, "11", _tea11_only(setup)),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
        may_choose=True,
    )

    line = _billed(setup, invoice.id)
    assert line.discount_amount == Decimal("0.0000")
    assert line.free_quantity == Decimal("1.0000")
    order_line = _live_order_line(setup)
    assert order_line.offer_choice_made is True
    chosen = setup.session.scalars(
        select(SalesOrderOffer.code).where(
            SalesOrderOffer.sales_order_line_id == order_line.id,
            SalesOrderOffer.chosen.is_(True),
        )
    ).all()
    assert list(chosen) == ["TEA-11"]


def test_a_counter_bill_choice_needs_the_permission() -> None:
    """The order behind the bill asks for SALES_OFFER_CHOOSE, as its own does."""
    setup = _counter_firm()

    with pytest.raises(AuthorizationError, match="SALES_OFFER_CHOOSE"):
        SalesInvoiceService(setup.session).create_invoice(
            _bill(setup, "11", _tea11_only(setup)),
            firm_id=setup.firm.id,
            actor_id=uuid4(),
        )


def test_a_counter_bill_preview_reports_a_stale_key_and_prices_the_start() -> None:
    """The preview drops a key the line cannot take and says why."""
    setup = _counter_firm()
    stale = OfferChoice(offers=[str(uuid4())])

    preview = SalesInvoiceService(setup.session).preview_invoice(
        _bill(setup, "11", stale),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
        may_choose=True,
    )

    assert preview.lines[0].choice_refused is not None
    assert "does not apply to this line any more" in preview.lines[0].choice_refused
    assert preview.invoice.lines[0].discount_amount == Decimal("55.0000")
    assert _orders(setup) == 0


def test_an_edit_that_says_nothing_keeps_the_choice_through_a_new_order() -> None:
    """12 in place of 11: the order is raised again and still skips TEA-5."""
    setup = _counter_firm()
    service = SalesInvoiceService(setup.session)
    actor = uuid4()
    invoice = service.create_invoice(
        _bill(setup, "11", _tea11_only(setup)),
        firm_id=setup.firm.id,
        actor_id=actor,
        may_choose=True,
    )

    # No permission now: the choice is the one already made, not a new one.
    service.update_invoice(
        invoice.id,
        _sent_back(setup, invoice.id, "12"),
        firm_id=setup.firm.id,
        actor_id=actor,
    )

    assert _orders(setup) == 2, "the edit raised the order again"
    line = _billed(setup, invoice.id)
    assert line.current_invoice_quantity == Decimal("12.0000")
    assert line.discount_amount == Decimal("0.0000")
    assert _live_order_line(setup).offer_choice_made is True


def test_an_explicit_null_on_an_edit_goes_back_to_the_start() -> None:
    """The order is raised again without the choice: TEA-5 is back."""
    setup = _counter_firm()
    service = SalesInvoiceService(setup.session)
    actor = uuid4()
    invoice = service.create_invoice(
        _bill(setup, "11", _tea11_only(setup)),
        firm_id=setup.firm.id,
        actor_id=actor,
        may_choose=True,
    )

    service.update_invoice(
        invoice.id,
        _sent_back(setup, invoice.id, "11", offer_choice=None),
        firm_id=setup.firm.id,
        actor_id=actor,
    )

    assert _orders(setup) == 2
    assert _billed(setup, invoice.id).discount_amount == Decimal("55.0000")
    assert _live_order_line(setup).offer_choice_made is False


def test_sending_the_held_choice_back_changes_nothing() -> None:
    """An editor that sends back what it read raises no order again."""
    setup = _counter_firm()
    service = SalesInvoiceService(setup.session)
    actor = uuid4()
    invoice = service.create_invoice(
        _bill(setup, "11", _tea11_only(setup)),
        firm_id=setup.firm.id,
        actor_id=actor,
        may_choose=True,
    )

    service.update_invoice(
        invoice.id,
        _sent_back(setup, invoice.id, "11", offer_choice=_tea11_only(setup)),
        firm_id=setup.firm.id,
        actor_id=actor,
    )

    assert _orders(setup) == 1
    assert _billed(setup, invoice.id).discount_amount == Decimal("0.0000")


def test_a_new_choice_on_an_edit_raises_the_order_again() -> None:
    """Choosing on an edit is a choice, and is judged as one."""
    setup = _counter_firm()
    service = SalesInvoiceService(setup.session)
    actor = uuid4()
    invoice = service.create_invoice(
        _bill(setup, "11"), firm_id=setup.firm.id, actor_id=actor
    )
    assert _billed(setup, invoice.id).discount_amount == Decimal("55.0000")

    with pytest.raises(AuthorizationError):
        service.update_invoice(
            invoice.id,
            _sent_back(setup, invoice.id, "11", offer_choice=_tea11_only(setup)),
            firm_id=setup.firm.id,
            actor_id=actor,
        )
    setup.session.rollback()

    service.update_invoice(
        invoice.id,
        _sent_back(setup, invoice.id, "11", offer_choice=_tea11_only(setup)),
        firm_id=setup.firm.id,
        actor_id=actor,
        may_choose=True,
    )
    assert _orders(setup) == 2
    assert _billed(setup, invoice.id).discount_amount == Decimal("0.0000")


def test_offers_are_still_claimed_at_the_bills_approval() -> None:
    """Saving and editing claim nothing; approving claims what was taken."""
    setup = _counter_firm()
    service = SalesInvoiceService(setup.session)
    actor = uuid4()
    invoice = service.create_invoice(
        _bill(setup, "11", _tea11_only(setup)),
        firm_id=setup.firm.id,
        actor_id=actor,
        may_choose=True,
    )

    def claimed() -> list[str]:
        """Return the codes of the offers claimed so far."""
        return [
            code
            for code in setup.session.scalars(
                select(Promotion.code)
                .join(
                    PromotionRedemption,
                    PromotionRedemption.promotion_id == Promotion.id,
                )
                .where(PromotionRedemption.status == "CLAIMED")
            )
        ]

    assert claimed() == []
    service.approve_invoice(invoice.id, firm_scope=setup.firm.id, actor_id=actor)
    assert claimed() == ["TEA-11"]


def test_a_bill_of_documents_refuses_a_choice() -> None:
    """Its lines were priced by the order they continue."""
    setup = _counter_firm()
    data = SalesInvoiceCreate(
        customer_id=setup.customer.id,
        invoice_date=date(2026, 8, 4),
        lines=[
            SalesInvoiceLineWrite(
                source_document_type="DELIVERY_NOTE",
                source_document_id=uuid4(),
                source_document_line_id=uuid4(),
                line_number=1,
                current_invoice_quantity=Decimal("1"),
                offer_choice=OfferChoice(offers=[]),
            )
        ],
    )

    with pytest.raises(ValidationError, match="cannot take a choice"):
        SalesInvoiceService(setup.session).create_invoice(
            data, firm_id=setup.firm.id, actor_id=uuid4(), may_choose=True
        )


def _accepted_quote(code: str) -> tuple[QuotationService, UUID, object]:
    """Quote step 3 of the worked example with CITY chosen, and accept it."""
    shop = _shop(code)
    service = QuotationService(shop.session)
    actor = uuid4()
    row = service.create_quotation(
        QuotationCreate(
            customer_id=shop.customer.id,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            quotation_date=ON,
            valid_until=date(2027, 3, 31),
            lines=[
                QuotationLineWrite(
                    line_number=1,
                    product_id=shop.product.id,
                    quantity=Decimal("11"),
                    unit_price=Decimal("100"),
                    offer_choice=_city_not_tea5(shop),
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=actor,
        may_choose=True,
    )
    service.accept_quotation(row.id, firm_scope=shop.firm.id, actor_id=actor)
    return service, row.id, shop


def test_a_converted_quotation_hands_its_choice_to_the_order() -> None:
    """The order takes CITY as quoted, and the converter needs no permission."""
    service, quote_id, shop = _accepted_quote("CC01")
    assert hasattr(shop, "firm")

    _, order = service.convert_quotation(
        quote_id, firm_scope=shop.firm.id, actor_id=uuid4(), order_date=ON
    )

    line = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    assert line.discount_amount == Decimal("44.0000")
    assert line.free_quantity == Decimal("1.0000")
    assert line.offer_choice_made is True


def test_a_lapsed_choice_is_dropped_at_conversion_and_said_on_the_timeline() -> None:
    """CITY withdrawn since the quote: ordered from the start, and said so."""
    service, quote_id, shop = _accepted_quote("CC02")
    assert hasattr(shop, "firm")
    city = shop.session.scalar(select(PriceList).where(PriceList.code == "CITY"))
    assert city is not None
    city.status = "INACTIVE"
    shop.session.commit()

    _, order = service.convert_quotation(
        quote_id, firm_scope=shop.firm.id, actor_id=uuid4(), order_date=ON
    )

    line = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    assert line.discount_amount == Decimal("55.0000"), "TEA-5, the start"
    assert line.offer_choice_made is False
    (converted,) = [
        event
        for event in service.timeline(quote_id, firm_scope=shop.firm.id)
        if event.action == "CONVERTED"
    ]
    assert converted.remarks is not None
    assert converted.remarks.startswith(f"Became {order.order_number}. ")
    assert "Ordered without that choice." in converted.remarks
    assert _key(shop, "CITY")
