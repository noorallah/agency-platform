"""A part share of "buy N get M free", chosen on the line (L7 step 7).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` section 3.7 and step 4 of
the worked example. An offer that allows it lists the split of what the
customer takes away -- 6 on "11 + 1" is 5.5 charged and 0.5 free -- and a
line that picks it is priced on the charged quantity, the offer giving free
goods in proportion. The test shop has no tax rule, so a line's taxable
value is what the example says and its tax is nothing.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.promotions.models import Promotion, PromotionRedemption
from app.promotions.schemas import (
    OfferChoice,
    PromotionActionType,
    PromotionActionWrite,
    PromotionStatus,
    PromotionWrite,
)
from app.promotions.services import PromotionCrudService
from app.promotions.services.promotion_service import (
    part_share_free,
    part_share_split,
)
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_offer_candidates import ON, _by_code, _shop
from tests.unit.test_offer_choice import _key, _line, _order, _rows, _save
from tests.unit.test_offer_choice_chain import (
    _bill,
    _billed,
    _counter_firm,
    _live_order_line,
)
from tests.unit.test_promotions import _Shop


def _part_share_shop(code: str) -> _Shop:
    """Build the worked example's firm with TEA-11 allowing a part share."""
    shop = _shop(code)
    offer = shop.session.scalar(select(Promotion).where(Promotion.code == "TEA-11"))
    assert offer is not None
    offer.allow_part_share = True
    shop.session.commit()
    return shop


def _part_share(shop: _Shop) -> OfferChoice:
    """Pick the part share of TEA-11."""
    return OfferChoice(part_share=_key(shop, "TEA-11"))


def test_the_split_always_adds_up_to_what_is_taken_away() -> None:
    """6 is 5.5 + 0.5; 4 is 3.6667 + 0.3333; 16.5 charged gives 1.5."""
    eleven, one = Decimal("11"), Decimal("1")
    assert part_share_split(Decimal("6"), buy=eleven, free=one) == (
        Decimal("5.5000"),
        Decimal("0.5000"),
    )
    assert part_share_split(Decimal("4"), buy=eleven, free=one) == (
        Decimal("3.6667"),
        Decimal("0.3333"),
    )
    assert part_share_free(Decimal("3.6667"), buy=eleven, free=one) == Decimal("0.3333")
    assert part_share_free(Decimal("16.5"), buy=eleven, free=one) == Decimal("1.5")
    assert part_share_free(Decimal("5.5"), buy=eleven, free=one) == Decimal("0.5")


def test_step_4_six_pieces_as_a_part_share_to_the_paisa() -> None:
    """6 typed, part share picked: 5.5 + 0.5 free, taxable 522.50."""
    shop = _part_share_shop("PS01")

    listed = SalesOrderService(shop.session).preview_order(
        _order(shop, _line(1, shop, "6")),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )
    offered = _by_code(listed.lines[0].candidates)["TEA-11"].part_share
    assert offered is not None
    assert (offered.charged_quantity, offered.free_quantity) == (
        Decimal("5.5000"),
        Decimal("0.5000"),
    )
    assert _by_code(listed.lines[0].candidates)["TEA-5"].part_share is None

    data = _order(shop, _line(1, shop, "5.5", _part_share(shop)))
    preview = SalesOrderService(shop.session).preview_order(
        data, firm_id=shop.firm.id, actor_id=uuid4(), may_choose=True
    )
    shown = preview.order.lines[0]
    assert preview.lines[0].choice_refused is None
    assert shown.free_quantity == Decimal("0.5000")
    assert shown.discount_amount == Decimal("27.5000")
    found = _by_code(preview.lines[0].candidates)
    assert (found["TEA-11"].applied, found["TEA-11"].chosen) == (True, True)
    assert found["TEA-11"].needs_more is None, "a part share needs no more"
    still = found["TEA-11"].part_share
    assert still is not None and still.charged_quantity == Decimal("5.5000")

    line = _save(shop, data)
    assert line.quantity == Decimal("5.5000")
    assert line.free_quantity == Decimal("0.5000")
    assert line.gross_amount == Decimal("550.0000")
    assert line.discount_amount == Decimal("27.5000")
    assert line.gross_amount - line.discount_amount == Decimal("522.5000")
    assert line.offer_choice_made is True
    rows = _rows(shop, line)
    assert rows["TEA-11"].part_share is True
    assert rows["TEA-11"].free_quantity == Decimal("0.5000")
    assert rows["TEA-11"].chosen is True
    assert rows["TEA-5"].part_share is False

    # The claim takes the fraction.
    claims = shop.session.scalars(
        select(PromotionRedemption).where(
            PromotionRedemption.document_id == line.sales_order_id
        )
    ).all()
    assert {claim.free_quantity for claim in claims} >= {Decimal("0.5000")}


def test_four_pieces_split_to_four_places_and_add_up() -> None:
    """4 taken away: 3.6667 charged, 0.3333 free, four whole pieces."""
    shop = _part_share_shop("PS02")
    shop.product.allow_decimal = False
    shop.session.commit()

    line = _save(shop, _order(shop, _line(1, shop, "3.6667", _part_share(shop))))

    assert line.free_quantity == Decimal("0.3333")
    assert line.quantity + line.free_quantity == Decimal("4.0000")


def test_charged_and_free_must_make_whole_pieces() -> None:
    """8.3 charged gives 0.7545 free: 9.0545 pieces is no number of pieces."""
    shop = _part_share_shop("PS03")
    shop.product.allow_decimal = False
    shop.session.commit()

    with pytest.raises(ValidationError) as refused:
        _save(shop, _order(shop, _line(1, shop, "8.3", _part_share(shop))))
    assert "whole numbers" in refused.value.message


def test_an_offer_that_does_not_allow_it_is_refused_by_name() -> None:
    """TEA-11 with the switch off: no split listed, a pick refused."""
    shop = _shop("PS04")

    listed = SalesOrderService(shop.session).preview_order(
        _order(shop, _line(1, shop, "6")),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )
    assert _by_code(listed.lines[0].candidates)["TEA-11"].part_share is None

    with pytest.raises(ValidationError) as refused:
        _save(shop, _order(shop, _line(1, shop, "5.5", _part_share(shop))))
    assert refused.value.message.startswith(
        "Line 1: offer TEA-11 cannot be billed as a part share on this line."
    )


def test_without_a_part_share_the_offer_gives_whole_rounds() -> None:
    """The switch on, nobody picks it: 5.5 earns nothing, 11 earns one."""
    shop = _part_share_shop("PS05")

    line = _save(shop, _order(shop, _line(1, shop, "5.5"), _line(2, shop, "11")))
    assert line.free_quantity == Decimal("0")
    second = shop.session.scalar(
        select(SalesOrderLine).where(
            SalesOrderLine.sales_order_id == line.sales_order_id,
            SalesOrderLine.line_number == 2,
        )
    )
    assert second is not None and second.free_quantity == Decimal("1.0000")


def test_a_free_quantity_typed_refuses_a_part_share() -> None:
    """The line's own free figure stands, so the offer gives none."""
    shop = _part_share_shop("PS06")
    typed = SalesOrderLineWrite.model_validate(
        {
            **_line(1, shop, "5.5", _part_share(shop)).model_dump(exclude_unset=True),
            "free_quantity": Decimal("0"),
        }
    )

    with pytest.raises(ValidationError) as refused:
        _save(shop, _order(shop, typed))
    assert "cannot be billed as a part share" in refused.value.message


def test_a_budget_counts_the_fraction() -> None:
    """A free-unit budget of 0.4 cannot hold half a piece; 0.5 can."""
    shop = _part_share_shop("PS07")
    offer = shop.session.scalar(select(Promotion).where(Promotion.code == "TEA-11"))
    assert offer is not None
    offer.max_free_quantity = Decimal("0.4")
    shop.session.commit()
    data = _order(shop, _line(1, shop, "5.5", _part_share(shop)))

    with pytest.raises(ValidationError) as refused:
        _save(shop, data)
    assert refused.value.message == (
        "Line 1: offer TEA-11 gives this line nothing as a part share (This "
        "offer has 0.4 left of its budget of 0.4 free units, and this "
        "document would take 0.5)."
    )
    shop.session.rollback()

    offer.max_free_quantity = Decimal("0.5")
    shop.session.commit()
    assert _save(shop, data).free_quantity == Decimal("0.5000")


def test_an_edit_keeps_the_part_share_and_null_clears_it() -> None:
    """Absent on an edit keeps the stored part share; null gives whole rounds."""
    shop = _part_share_shop("PS08")
    service = SalesOrderService(shop.session)
    row = service.create_order(
        _order(shop, _line(1, shop, "5.5", _part_share(shop))),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
        may_choose=True,
    )

    service.update_order(
        row.id,
        _order(shop, _line(1, shop, "5.5")),
        firm_scope=shop.firm.id,
        actor_id=uuid4(),
    )
    line = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == row.id)
    )
    assert line is not None
    assert line.free_quantity == Decimal("0.5000")
    assert _rows(shop, line)["TEA-11"].part_share is True

    cleared = SalesOrderLineWrite.model_validate(
        {
            **_line(1, shop, "5.5").model_dump(exclude_unset=True),
            "offer_choice": None,
        }
    )
    service.update_order(
        row.id, _order(shop, cleared), firm_scope=shop.firm.id, actor_id=uuid4()
    )
    shop.session.refresh(line)
    assert line.free_quantity == Decimal("0")


def _offer_write(code: str, **fields: object) -> PromotionWrite:
    """Describe "buy 11 get 1", with the fields given."""
    return PromotionWrite(
        code=code,
        name="Eleven and one",
        status=PromotionStatus.ACTIVE,
        actions=[
            PromotionActionWrite(
                sequence=1,
                action_type=PromotionActionType.FREE_QUANTITY,
                buy_quantity=Decimal("11"),
                free_quantity=Decimal("1"),
            )
        ],
        **fields,  # type: ignore[arg-type]
    )


def test_the_switch_is_on_the_offer_form_and_an_edit_keeps_it() -> None:
    """Set on create, kept by an edit that leaves it out, cleared by False."""
    shop = _shop("PS09")
    crud = PromotionCrudService(shop.session)
    created = crud.create_promotion(
        _offer_write(code="TEA-12", allow_part_share=True),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )
    assert created.allow_part_share is True
    assert crud.promotion_response(created).allow_part_share is True

    kept = crud.update_promotion(
        created.id,
        _offer_write(code="TEA-12"),
        firm_scope=shop.firm.id,
        actor_id=uuid4(),
    )
    assert kept.allow_part_share is True

    off = crud.update_promotion(
        kept.id,
        _offer_write(code="TEA-12", allow_part_share=False),
        firm_scope=shop.firm.id,
        actor_id=uuid4(),
    )
    assert off.allow_part_share is False


def test_a_part_share_is_only_for_free_goods_of_the_item() -> None:
    """A discount offer cannot carry the switch."""
    with pytest.raises(SchemaError) as refused:
        PromotionWrite(
            code="TEA-5",
            name="Five off",
            allow_part_share=True,
            actions=[
                PromotionActionWrite(
                    sequence=1,
                    action_type=PromotionActionType.LINE_DISCOUNT_PERCENT,
                    percent=Decimal("5"),
                )
            ],
        )
    assert "buy N get M free" in str(refused.value)


def test_the_quotation_takes_a_part_share_as_the_order_does() -> None:
    """5.5 quoted as a part share: 0.5 free, the row says so."""
    shop = _part_share_shop("PS10")

    row = QuotationService(shop.session).create_quotation(
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
                    quantity=Decimal("5.5"),
                    unit_price=Decimal("100"),
                    offer_choice=_part_share(shop),
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
        may_choose=True,
    )

    line = QuotationService(shop.session).quotation_response(row).lines[0]
    assert line.free_quantity == Decimal("0.5000")
    assert line.discount_amount == Decimal("27.5000")
    shared = {item.code: item.part_share for item in line.offers}
    assert shared == {"TEA-5": False, "TEA-11": True}


def test_a_counter_bill_bills_a_part_share_and_claims_the_half_at_approval() -> None:
    """6 pieces at the counter: 5.5 + 0.5 free; the claim at approval is 0.5."""
    setup = _counter_firm()
    setup.product.allow_decimal = False
    offer = setup.session.scalar(select(Promotion).where(Promotion.code == "TEA-11"))
    assert offer is not None
    offer.allow_part_share = True
    setup.session.commit()
    service = SalesInvoiceService(setup.session)

    invoice = service.create_invoice(
        _bill(setup, "5.5", OfferChoice(part_share=str(offer.version_group_id))),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
        may_choose=True,
    )
    line = _billed(setup, invoice.id)
    assert line.free_quantity == Decimal("0.5000")
    assert line.discount_amount == Decimal("27.5000")
    assert _live_order_line(setup).free_quantity == Decimal("0.5000")

    service.approve_invoice(invoice.id, firm_scope=setup.firm.id, actor_id=uuid4())
    claimed = setup.session.scalars(
        select(PromotionRedemption.free_quantity).where(
            PromotionRedemption.promotion_id == offer.id,
            PromotionRedemption.status == "CLAIMED",
        )
    ).all()
    assert list(claimed) == [Decimal("0.5000")]
