"""What a line could take, listed in the three previews (L7 step 3).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md``, sections 1, 3.1, 3.2 and
step 3 of section 6. Each previewed line lists every offer whose conditions
it meets -- applied or not, with what it is worth on the line alone and why
it is not applied -- and the customer's standing arrangements beside them.
Nothing is chosen yet, no price moves, the limits of every offer are read in
one statement, and a preview leaves nothing behind.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.pricing.models import PriceList, PriceListItem
from app.promotions.models import PromotionExecutionLog, PromotionRedemption
from app.promotions.schemas import (
    OfferCandidate,
    PromotionActionType,
    PromotionConditionOperator,
    PromotionField,
)
from app.quotation.models import SalesQuotation
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderOffer
from app.sales_order.schemas import (
    SalesOrderCreate,
    SalesOrderLineWrite,
    SalesOrderPreview,
)
from app.sales_order.services import SalesOrderService
from tests.unit.test_promotions import (
    _best_offer_only,
    _promotion,
    _session_factory,
    _Shop,
)
from tests.unit.test_sales_chain_synthesis import _Firm
from tests.unit.test_sales_chain_synthesis import (
    _session_factory as _chain_session_factory,
)

ON = date(2026, 8, 4)


def _worked_example(session: Session, firm_id: UUID, product_id: UUID) -> None:
    """Set up section 1's firm: CITY at 4%, TEA-5 and TEA-11, both combining."""
    price_list = PriceList(
        firm_id=firm_id,
        code="CITY",
        name="City rates",
        effective_from=date(2026, 1, 1),
        status="ACTIVE",
    )
    session.add(price_list)
    session.flush()
    session.add(
        PriceListItem(
            price_list_id=price_list.id,
            firm_id=firm_id,
            product_id=product_id,
            min_quantity=Decimal("0"),
            discount_percent=Decimal("4"),
        )
    )
    session.commit()
    _promotion(
        session,
        firm_id=firm_id,
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
        firm_id=firm_id,
        code="TEA-11",
        priority=20,
        actions=[
            (
                PromotionActionType.FREE_QUANTITY,
                {"buy_quantity": "11", "free_quantity": "1"},
            )
        ],
    )


def _shop(code: str) -> _Shop:
    """Build the worked example's firm, with the customer's 2% standing rate."""
    session = _session_factory()()
    shop = _Shop(session, code=code)
    _worked_example(session, shop.firm.id, shop.product.id)
    shop.customer.default_discount_percent = Decimal("2")
    session.commit()
    return shop


def _order_data(
    shop: _Shop, quantities: list[str], *, discount_percent: str | None = None
) -> SalesOrderCreate:
    """Describe an order of the shop's product at 100 a piece, one line each."""
    return SalesOrderCreate(
        customer_id=shop.customer.id,
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        order_date=ON,
        lines=[
            SalesOrderLineWrite(
                line_number=number,
                product_id=shop.product.id,
                quantity=Decimal(quantity),
                unit_price=Decimal("100"),
                discount_percent=(
                    None if discount_percent is None else Decimal(discount_percent)
                ),
            )
            for number, quantity in enumerate(quantities, start=1)
        ],
    )


def _preview(
    shop: _Shop, quantities: list[str], *, discount_percent: str | None = None
) -> SalesOrderPreview:
    """Preview an order of the shop's product."""
    return SalesOrderService(shop.session).preview_order(
        _order_data(shop, quantities, discount_percent=discount_percent),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )


def _by_code(candidates: list[OfferCandidate]) -> dict[str, OfferCandidate]:
    """Index a line's candidates by code."""
    return {item.code: item for item in candidates}


def test_step_1_nine_pieces_take_tea_5_and_list_the_rest() -> None:
    """9 pieces: TEA-5 45.00 applied; CITY 36.00 and 2% 18.00 passed over."""
    shop = _shop("OC01")

    preview = _preview(shop, ["9"])
    line = preview.order.lines[0]
    found = _by_code(preview.lines[0].candidates)

    assert line.discount_amount == Decimal("45.0000")
    assert line.gross_amount - line.discount_amount == Decimal("855.0000")
    assert line.free_quantity == Decimal("0")
    assert [item.code for item in preview.lines[0].candidates] == [
        "TEA-5",
        "TEA-11",
        "CITY",
        "CUSTOMER",
    ]

    tea5 = found["TEA-5"]
    assert (tea5.source, tea5.applied, tea5.available, tea5.reason) == (
        "promotion",
        True,
        True,
        None,
    )
    assert tea5.worth == Decimal("45.0000")
    assert tea5.gives.kind == "LINE_DISCOUNT_PERCENT"
    assert tea5.gives.sentence == "5% off"
    assert tea5.combines is True and tea5.chosen is False

    tea11 = found["TEA-11"]
    assert tea11.applied is False and tea11.available is True
    assert tea11.worth == Decimal("0")
    assert tea11.reason == "Nothing earned on this line yet."
    assert tea11.gives.sentence == "11 + 1 free"
    # The hint is step 4 (test_offer_hints.py); the part share step 7.
    assert (tea11.needs_more, tea11.then_gives) == (Decimal("2"), "1 free")
    assert tea11.part_share is None

    city = found["CITY"]
    assert (city.source, city.applied, city.worth) == (
        "price_list",
        False,
        Decimal("36.0000"),
    )
    assert city.reason == "An offer gives this line its discount."
    assert city.gives.sentence == "4% off"
    standing = found["CUSTOMER"]
    assert (standing.key, standing.source, standing.worth) == (
        "CUSTOMER",
        "customer",
        Decimal("18.0000"),
    )
    assert standing.applied is False
    assert all(item.chosen is False for item in preview.lines[0].candidates)
    assert preview.bill_candidates == []


def test_the_keys_are_the_offer_s_identity_and_the_list_s_id() -> None:
    """An offer by its version group, a price list by its id (section 3.2)."""
    shop = _shop("OC02")
    session = shop.session

    found = _by_code(_preview(shop, ["9"]).lines[0].candidates)

    from app.promotions.models import Promotion

    tea5 = session.scalar(select(Promotion).where(Promotion.code == "TEA-5"))
    city = session.scalar(select(PriceList).where(PriceList.code == "CITY"))
    assert tea5 is not None and city is not None
    assert found["TEA-5"].key == str(tea5.version_group_id)
    assert found["CITY"].key == str(city.id)


def test_step_2_eleven_pieces_take_both_offers_when_they_combine() -> None:
    """11 pieces: TEA-5 55.00 and TEA-11 one free, both applied."""
    shop = _shop("OC03")

    preview = _preview(shop, ["11"])
    line = preview.order.lines[0]
    found = _by_code(preview.lines[0].candidates)

    assert line.discount_amount == Decimal("55.0000")
    assert line.gross_amount - line.discount_amount == Decimal("1045.0000")
    assert line.free_quantity == Decimal("1.0000")
    assert found["TEA-5"].applied and found["TEA-5"].worth == Decimal("55.0000")
    assert found["TEA-11"].applied and found["TEA-11"].reason is None
    # One free piece at the line's own rate of 100.
    assert found["TEA-11"].worth == Decimal("100.0000")
    assert found["CITY"].worth == Decimal("44.0000")
    assert not found["CITY"].applied


def test_step_2_under_best_one_only_takes_the_free_piece_and_the_list() -> None:
    """Best one only: TEA-11 (100.00) beats TEA-5 (55.00); CITY's 4% applies."""
    shop = _shop("OC04")
    _best_offer_only(shop.session, shop.firm.id)

    preview = _preview(shop, ["11"])
    line = preview.order.lines[0]
    found = _by_code(preview.lines[0].candidates)

    assert line.free_quantity == Decimal("1.0000")
    assert line.discount_amount == Decimal("44.0000")
    assert line.gross_amount - line.discount_amount == Decimal("1056.0000")
    assert found["TEA-11"].applied is True
    tea5 = found["TEA-5"]
    assert tea5.applied is False and tea5.available is True
    assert tea5.worth == Decimal("55.0000")
    assert tea5.reason is not None and "TEA-11 was worth more" in tea5.reason
    city = found["CITY"]
    assert city.applied is True and city.reason is None
    assert city.worth == Decimal("44.0000")
    assert found["CUSTOMER"].reason == "The price list gives this line its discount."


def test_a_typed_discount_makes_every_arrangement_unavailable() -> None:
    """3% typed: no offer reaches the line, and each says why."""
    shop = _shop("OC05")

    preview = _preview(shop, ["11"], discount_percent="3")
    line = preview.order.lines[0]

    assert line.discount_amount == Decimal("33.0000")
    assert line.free_quantity == Decimal("0")
    for item in preview.lines[0].candidates:
        assert item.applied is False, item.code
        assert item.available is False, item.code
        assert item.reason == "A discount is typed on this line.", item.code
    # Still worth what it would be: the reason, not the worth, says no.
    assert _by_code(preview.lines[0].candidates)["TEA-5"].worth == Decimal("55.0000")


def test_an_offer_needing_a_coupon_is_listed_as_needing_one() -> None:
    """A coupon offer the line meets is listed, unavailable, with the reason."""
    shop = _shop("OC06")
    coupon_only = _promotion(
        shop.session,
        firm_id=shop.firm.id,
        code="WELCOME",
        priority=5,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
    )
    coupon_only.requires_coupon = True
    shop.session.commit()

    found = _by_code(_preview(shop, ["9"]).lines[0].candidates)

    welcome = found["WELCOME"]
    assert welcome.available is False and welcome.applied is False
    assert welcome.reason == (
        "This offer is claimed with a coupon, and none was presented."
    )
    assert welcome.worth == Decimal("90.0000")
    assert found["TEA-5"].applied is True


def test_an_offer_after_one_that_does_not_combine_says_so() -> None:
    """TEA-5 stops evaluation: TEA-11 is listed as not combining with it."""
    shop = _shop("OC07")
    from app.promotions.models import Promotion

    tea5 = shop.session.scalar(select(Promotion).where(Promotion.code == "TEA-5"))
    assert tea5 is not None
    tea5.allow_stacking = False
    shop.session.commit()

    preview = _preview(shop, ["11"])
    found = _by_code(preview.lines[0].candidates)

    assert preview.order.lines[0].free_quantity == Decimal("0")
    assert found["TEA-5"].combines is False
    tea11 = found["TEA-11"]
    assert (tea11.applied, tea11.available) == (False, False)
    assert tea11.reason == "Does not combine with TEA-5."


def test_a_bill_offer_is_listed_under_the_bill() -> None:
    """A bill discount offer lands in ``bill_candidates``, not on the line."""
    shop = _shop("OC08")
    _promotion(
        shop.session,
        firm_id=shop.firm.id,
        code="BILL-2",
        priority=30,
        actions=[(PromotionActionType.BILL_DISCOUNT_PERCENT, {"percent": "2"})],
    )

    preview = _preview(shop, ["9"])

    assert "BILL-2" not in _by_code(preview.lines[0].candidates)
    (bill,) = preview.bill_candidates
    assert (bill.code, bill.applied, bill.available) == ("BILL-2", True, True)
    assert bill.gives.sentence == "2% off the bill"
    # Valued alone, on the bill before any line discount: 2% of 900.
    assert bill.worth == Decimal("18.0000")


def _redemption_reads(statements: list[str]) -> int:
    """Count the statements that count offers' claims.

    The document's own pending claims are read once more, to be staged
    again; that read counts nothing and is not a limit.
    """
    return sum(
        1
        for text in statements
        if text.lstrip().upper().startswith("SELECT")
        and "promotion_redemptions" in text
        and "count(" in text.lower()
    )


def _promotion_reads(statements: list[str]) -> int:
    """Count the statements that read the offers themselves."""
    return sum(
        1
        for text in statements
        if text.lstrip().upper().startswith("SELECT")
        and any(
            f"FROM {table}" in text
            for table in ("promotions", "promotion_actions", "promotion_conditions")
        )
    )


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    """Collect every statement the session's engine executes."""
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401
        """Keep the statement text."""
        seen.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _statements(shop: _Shop, lines: int) -> list[str]:
    """Return every statement one preview of ``lines`` lines executes."""
    with _counting(shop.session) as seen:
        _preview(shop, ["11"] * lines)
    return list(seen)


def test_the_list_costs_no_statement_per_line_and_limits_cost_one() -> None:
    """Three lines more cost the same with five candidates a line as with none.

    Every offer's claims and budget come from one statement for the whole
    document, however many offers and lines there are, and the offers with
    their conditions and actions are read the same number of times for one
    line as for six. Against a firm with no offer, no list and no standing
    rate, three lines more add exactly the same statements: listing the
    candidates asks nothing per line.
    """
    shop = _shop("OC09")
    _promotion(
        shop.session,
        firm_id=shop.firm.id,
        code="CAPPED",
        priority=40,
        actions=[(PromotionActionType.LINE_DISCOUNT_AMOUNT, {"amount": "1"})],
    ).max_redemptions = 50
    shop.session.commit()
    bare = _Shop(_session_factory()(), code="OC09B")

    # Each firm's document setup is made by its first preview; warm both.
    _statements(bare, 1)
    counts = {lines: _statements(shop, lines) for lines in (1, 3, 6)}
    plain = {lines: _statements(bare, lines) for lines in (3, 6)}

    preview = _preview(shop, ["11"] * 6)
    assert all(len(line.candidates) == 5 for line in preview.lines)
    for seen in counts.values():
        assert _redemption_reads(seen) == 1, "every offer's limits in one read"
    assert (
        _promotion_reads(counts[1])
        == _promotion_reads(counts[3])
        == _promotion_reads(counts[6])
    )
    assert len(counts[6]) - len(counts[3]) == len(plain[6]) - len(plain[3])


def _count(session: Session, model: type[Any]) -> int:
    """Count every row of one table."""
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_a_preview_leaves_nothing_behind() -> None:
    """No order, no row naming an offer, no claim and no trace survive it."""
    shop = _shop("OC10")
    session = shop.session
    models = (
        SalesOrder,
        SalesOrderOffer,
        PromotionRedemption,
        PromotionExecutionLog,
    )
    before = {model: _count(session, model) for model in models}

    preview = _preview(shop, ["11", "9"])

    assert len(preview.lines[0].candidates) == 4
    assert {model: _count(session, model) for model in models} == before


def test_the_quotation_preview_lists_the_same_candidates() -> None:
    """Step 2 on a quotation: the same list, the same price, nothing saved."""
    shop = _shop("OC11")
    session = shop.session

    preview = QuotationService(session).preview_quotation(
        QuotationCreate(
            customer_id=shop.customer.id,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            quotation_date=ON,
            valid_until=date(2026, 9, 3),
            lines=[
                QuotationLineWrite(
                    line_number=1,
                    product_id=shop.product.id,
                    quantity=Decimal("11"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )
    found = _by_code(preview.lines[0].candidates)

    assert preview.quotation.lines[0].discount_amount == Decimal("55.0000")
    assert found["TEA-5"].applied and found["TEA-11"].applied
    assert found["CITY"].worth == Decimal("44.0000") and not found["CITY"].applied
    assert found["CUSTOMER"].worth == Decimal("22.0000")
    assert _count(session, SalesQuotation) == 0


def test_a_counter_bill_preview_lists_what_its_order_priced() -> None:
    """A bill typed straight in is priced by the order behind it, list too."""
    session = _chain_session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    _promotion(
        session,
        firm_id=setup.firm.id,
        code="TEA-5",
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "5"})],
    )

    preview = SalesInvoiceService(session).preview_invoice(
        setup.bare_bill(Decimal("9")), firm_id=setup.firm.id, actor_id=uuid4()
    )

    (tea5,) = preview.lines[0].candidates
    assert (tea5.code, tea5.applied, tea5.worth) == ("TEA-5", True, Decimal("45.0000"))
    assert preview.invoice.lines[0].discount_amount == Decimal("45.0000")
    assert preview.bill_candidates == []
    assert _count(session, SalesInvoice) == 0
    assert _count(session, SalesOrder) == 0
