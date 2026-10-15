"""The "buy N more" hint beside a previewed line (L7 step 4).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md``, sections 1, 3.6 and step 4
of section 6. An offer whose other conditions hold and whose quantity, or
next round, the line is short of says how many more earn what; so does the
next break of the customer's price list. Shown only where the shortfall is no
more than the quantity typed, two a line at most, nearest kept. Worked out
from what the document already read: no statement per line, no price moves.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pricing.models import PriceList, PriceListItem
from app.promotions.schemas import (
    PromotionActionType,
    PromotionConditionOperator,
    PromotionField,
)
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService
from tests.unit.test_offer_candidates import (
    _by_code,
    _counting,
    _preview,
    _promotion_reads,
    _redemption_reads,
    _shop,
)
from tests.unit.test_promotions import _promotion, _session_factory, _Shop

ON = date(2026, 8, 4)


def _break(
    session: Session, firm_id: UUID, product_id: UUID, *, at: str, percent: str
) -> None:
    """Add a break to the firm's CITY list, which the worked example made."""
    city = session.scalar(select(PriceList).where(PriceList.code == "CITY"))
    assert city is not None
    session.add(
        PriceListItem(
            price_list_id=city.id,
            firm_id=firm_id,
            product_id=product_id,
            min_quantity=Decimal(at),
            discount_percent=Decimal(percent),
        )
    )
    session.commit()


def _minimum_offer(shop: _Shop, code: str, *, at_least: str, percent: str) -> None:
    """Add an offer of ``percent`` off a line of ``at_least`` pieces or more."""
    _promotion(
        shop.session,
        firm_id=shop.firm.id,
        code=code,
        priority=30,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": percent})],
        conditions=[
            (
                PromotionField.LINE_QUANTITY,
                PromotionConditionOperator.GREATER_OR_EQUAL,
                {"value_number": Decimal(at_least)},
            )
        ],
    )


def test_step_1_nine_pieces_are_two_short_of_one_free() -> None:
    """9 pieces: TEA-11 says 2 more give 1 free; nothing else hints."""
    shop = _shop("OH01")

    preview = _preview(shop, ["9"])
    found = _by_code(preview.lines[0].candidates)

    tea11 = found["TEA-11"]
    assert (tea11.needs_more, tea11.then_gives) == (Decimal("2"), "1 free")
    # Listed as before: conditions met, nothing earned yet, still choosable.
    assert (tea11.applied, tea11.available, tea11.worth) == (
        False,
        True,
        Decimal("0"),
    )
    for code in ("TEA-5", "CITY", "CUSTOMER"):
        assert found[code].needs_more is None, code
        assert found[code].then_gives is None, code
    # Nothing moves a price.
    assert preview.order.lines[0].discount_amount == Decimal("45.0000")
    assert preview.order.lines[0].free_quantity == Decimal("0")


def test_three_pieces_are_two_short_of_tea_5() -> None:
    """3 pieces: TEA-5 is listed for its hint alone, and cannot be chosen."""
    shop = _shop("OH02")

    preview = _preview(shop, ["3"])
    found = _by_code(preview.lines[0].candidates)

    tea5 = found["TEA-5"]
    assert (tea5.needs_more, tea5.then_gives) == (Decimal("2"), "5% off")
    assert (tea5.applied, tea5.available, tea5.worth) == (False, False, Decimal("0"))
    assert tea5.reason == "2 more to earn it."
    assert tea5.gives.sentence == "5% off"
    # 8 more for TEA-11 is past the window of the 3 typed.
    assert found["TEA-11"].needs_more is None
    # The price list gives the line its discount, as before the hint.
    assert found["CITY"].applied is True
    assert preview.order.lines[0].discount_amount == Decimal("12.0000")


def test_no_hint_past_the_window() -> None:
    """2 pieces: TEA-5 is 3 short, more than the 2 typed, so is not listed."""
    shop = _shop("OH03")

    preview = _preview(shop, ["2"])

    assert [item.code for item in preview.lines[0].candidates] == [
        "TEA-11",
        "CITY",
        "CUSTOMER",
    ]
    assert all(item.needs_more is None for item in preview.lines[0].candidates)


def test_an_earned_offer_says_what_its_next_round_gives() -> None:
    """15 pieces: TEA-11 gave 1 free and is 7 short of 1 more."""
    shop = _shop("OH04")

    preview = _preview(shop, ["15"])
    tea11 = _by_code(preview.lines[0].candidates)["TEA-11"]

    assert tea11.applied is True and tea11.reason is None
    assert (tea11.needs_more, tea11.then_gives) == (Decimal("7"), "1 more free")
    assert preview.order.lines[0].free_quantity == Decimal("1.0000")


def test_the_price_list_s_next_break() -> None:
    """CITY gives 6% from 20: at 11 pieces it is 9 short; at 9, 11 is too far."""
    shop = _shop("OH05")
    _break(shop.session, shop.firm.id, shop.product.id, at="20", percent="6")

    city = _by_code(_preview(shop, ["11"]).lines[0].candidates)["CITY"]
    assert (city.needs_more, city.then_gives) == (Decimal("9"), "6% off")
    # The list is listed at the rate the line takes; the hint names the next.
    assert city.gives.sentence == "4% off" and city.available is True

    city = _by_code(_preview(shop, ["9"]).lines[0].candidates)["CITY"]
    assert city.needs_more is None


def test_a_line_below_the_first_break_lists_the_list_for_its_hint() -> None:
    """A list starting at 10 pieces: 6 pieces are 4 short of its 4%."""
    shop = _Shop(_session_factory()(), code="OH06")
    session = shop.session
    city = PriceList(
        firm_id=shop.firm.id,
        code="CITY",
        name="City rates",
        effective_from=date(2026, 1, 1),
        status="ACTIVE",
    )
    session.add(city)
    session.flush()
    session.add(
        PriceListItem(
            price_list_id=city.id,
            firm_id=shop.firm.id,
            product_id=shop.product.id,
            min_quantity=Decimal("10"),
            discount_percent=Decimal("4"),
        )
    )
    session.commit()

    preview = _preview(shop, ["6"])
    (only,) = preview.lines[0].candidates

    assert (only.code, only.source, only.key) == ("CITY", "price_list", str(city.id))
    assert (only.needs_more, only.then_gives) == (Decimal("4"), "4% off")
    assert (only.applied, only.available, only.worth) == (False, False, Decimal("0"))
    assert only.reason == "4 more to earn it."
    assert preview.order.lines[0].discount_amount == Decimal("0.0000")


def test_two_hints_a_line_the_nearest_kept() -> None:
    """Four hints at 9 pieces: the two nearest stay, the rest are cleared.

    TEA-10 is 1 short, TEA-11 2, CITY's break at 12 is 3 and TEA-13 4. CITY
    is still listed -- it is choosable -- with its hint cleared; TEA-13 was
    listed for its hint alone, so it goes.
    """
    shop = _shop("OH07")
    _minimum_offer(shop, "TEA-10", at_least="10", percent="3")
    _minimum_offer(shop, "TEA-13", at_least="13", percent="7")
    _break(shop.session, shop.firm.id, shop.product.id, at="12", percent="6")

    candidates = _preview(shop, ["9"]).lines[0].candidates
    found = _by_code(candidates)

    hinted = sorted(
        (item.needs_more, item.code) for item in candidates if item.needs_more
    )
    assert hinted == [(Decimal("1"), "TEA-10"), (Decimal("2"), "TEA-11")]
    assert found["TEA-10"].then_gives == "3% off"
    assert found["CITY"].needs_more is None and found["CITY"].then_gives is None
    assert "TEA-13" not in found


def test_a_typed_discount_gives_no_hint() -> None:
    """A line priced by hand takes no offer, so none is hinted on it."""
    shop = _shop("OH08")
    _break(shop.session, shop.firm.id, shop.product.id, at="12", percent="6")

    candidates = _preview(shop, ["9"], discount_percent="3").lines[0].candidates

    assert all(item.needs_more is None for item in candidates)
    assert "TEA-5" in _by_code(candidates)


def test_the_quotation_preview_carries_the_hint() -> None:
    """The quotation is priced by the same rule, hint included."""
    shop = _shop("OH09")

    preview = QuotationService(shop.session).preview_quotation(
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
                    quantity=Decimal("9"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )
    tea11 = _by_code(preview.lines[0].candidates)["TEA-11"]

    assert (tea11.needs_more, tea11.then_gives) == (Decimal("2"), "1 free")


def _statements(shop: _Shop, lines: int) -> list[str]:
    """Return every statement one preview of ``lines`` lines of 9 executes."""
    with _counting(shop.session) as seen:
        _preview(shop, ["9"] * lines)
    return list(seen)


def test_the_hint_costs_no_statement_per_line() -> None:
    """Three lines more cost the same with hints as with no offer at all."""
    shop = _shop("OH10")
    _minimum_offer(shop, "TEA-10", at_least="10", percent="3")
    _break(shop.session, shop.firm.id, shop.product.id, at="12", percent="6")
    bare = _Shop(_session_factory()(), code="OH10B")

    _statements(bare, 1)
    counts = {lines: _statements(shop, lines) for lines in (1, 3, 6)}
    plain = {lines: _statements(bare, lines) for lines in (3, 6)}

    preview = _preview(shop, ["9"] * 6)
    for line in preview.lines:
        hinted = [item.code for item in line.candidates if item.needs_more]
        assert hinted == ["TEA-11", "TEA-10"]
    for seen in counts.values():
        assert _redemption_reads(seen) == 1
    assert (
        _promotion_reads(counts[1])
        == _promotion_reads(counts[3])
        == _promotion_reads(counts[6])
    )
    assert len(counts[6]) - len(counts[3]) == len(plain[6]) - len(plain[3])
