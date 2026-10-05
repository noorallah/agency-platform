"""Batch-wise PTR / PTS (PG-14, backlog 86 #22, 55 G5).

A pharma or FMCG distributor keeps two trade rates on every batch beside its
MRP: the price to retailer and the price to stockist. They are captured on the
goods receipt and kept on the batch, and a sale from that batch starts at the
rate for the buyer's trade class -- below an agreed price list, above the
customer's price level and the product's own price, and never above anything
typed. Gated on the BATCH_PTR_PTS business feature, and never above the MRP.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import BatchRecord
from app.business.models import (
    BusinessFeature,
    BusinessProfile,
    FirmBusinessProfile,
    ProfileFeature,
)
from app.common.audit.models.audit_log import AuditLog
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.utils.pricing import batch_trade_rate, resolve_unit_price
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services import GoodsReceiptService
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_counter_bill_batches import _Counter
from tests.unit.test_goods_receipt import _Fixture, _session_factory

pytestmark = pytest.mark.typed_document_numbers

_PHARMA_FEATURES = ("BATCH_TRACKING", "EXPIRY_TRACKING", "BATCH_PTR_PTS")


def _give_profile(
    session: Session, firm_id: UUID, code: str, features: tuple[str, ...]
) -> None:
    """Assign the firm a fresh profile enabling exactly ``features``."""
    profile = BusinessProfile(
        code=code, name=code.title(), industry_type=code, status="ACTIVE"
    )
    session.add(profile)
    session.flush()
    for feature_code in features:
        feature = session.scalar(
            select(BusinessFeature).where(BusinessFeature.code == feature_code)
        )
        if feature is None:
            feature = BusinessFeature(code=feature_code, name=feature_code)
            session.add(feature)
            session.flush()
        session.add(
            ProfileFeature(
                business_profile_id=profile.id,
                feature_id=feature.id,
                is_enabled=True,
            )
        )
    session.add(
        FirmBusinessProfile(
            firm_id=firm_id,
            business_profile_id=profile.id,
            is_active=True,
            effective_from=date(2026, 4, 1),
        )
    )
    session.commit()


# -- Receipt -----------------------------------------------------------------


def _receipt(fixture: _Fixture, quantity: str = "2", **line: object) -> object:
    """Create a receipt of the order line with these line fields."""
    payload = fixture.receipt_payload(quantity)
    data = payload.model_dump()
    data["lines"][0].update(line)
    return GoodsReceiptService(fixture.session).create_receipt(
        GoodsReceiptCreate.model_validate(data),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _pharma_receiver(code: str) -> _Fixture:
    """Build a receiving firm whose profile has BATCH_PTR_PTS."""
    fixture = _Fixture(_session_factory()(), code)
    _give_profile(fixture.session, fixture.firm.id, f"PH-{code}", _PHARMA_FEATURES)
    return fixture


def _complete(fixture: _Fixture, receipt: object) -> None:
    """Complete a receipt, which hands its rates to the batch."""
    GoodsReceiptService(fixture.session).complete_receipt(
        receipt.id,  # type: ignore[attr-defined]
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _batch(fixture: _Fixture, number: str) -> BatchRecord:
    """Return the firm's batch by number."""
    row = fixture.session.scalar(
        select(BatchRecord).where(
            BatchRecord.firm_id == fixture.firm.id,
            BatchRecord.batch_number == number,
        )
    )
    assert row is not None
    return row


def test_the_receipt_writes_ptr_and_pts_to_a_new_batch() -> None:
    """Stored on the line, handed to the batch the receipt creates."""
    fixture = _pharma_receiver("PTR1")
    receipt = _receipt(
        fixture,
        batch_number="B-1",
        mrp=Decimal("120"),
        ptr=Decimal("90"),
        pts=Decimal("80"),
    )
    [line] = GoodsReceiptService(fixture.session).receipt_response(receipt).lines
    assert (line.ptr, line.pts) == (Decimal("90.00"), Decimal("80.00"))

    _complete(fixture, receipt)

    batch = _batch(fixture, "B-1")
    assert (batch.mrp, batch.ptr, batch.pts) == (
        Decimal("120.00"),
        Decimal("90.00"),
        Decimal("80.00"),
    )


def test_a_later_receipt_with_different_rates_updates_the_batch_audited() -> None:
    """Same batch, new PTR: the receipt's stands and the trail says so."""
    fixture = _pharma_receiver("PTR2")
    _complete(
        fixture, _receipt(fixture, batch_number="B-2", ptr=Decimal("90"), pts=None)
    )
    batch = _batch(fixture, "B-2")
    assert batch.ptr == Decimal("90.00")

    # Blank keeps the batch's own and writes nothing.
    _complete(fixture, _receipt(fixture, batch_number="B-2"))
    fixture.session.refresh(batch)
    assert batch.ptr == Decimal("90.00")
    assert not fixture.session.scalars(
        select(AuditLog).where(AuditLog.action == "batch.rates_updated")
    ).all()

    _complete(
        fixture,
        _receipt(fixture, batch_number="B-2", ptr=Decimal("95"), pts=Decimal("85")),
    )
    fixture.session.refresh(batch)
    assert (batch.ptr, batch.pts) == (Decimal("95.00"), Decimal("85.00"))
    [audit] = fixture.session.scalars(
        select(AuditLog).where(
            AuditLog.action == "batch.rates_updated",
            AuditLog.entity_id == batch.id,
        )
    ).all()
    assert audit.before_data == {"ptr": "90.00", "pts": None}
    assert audit.after_data is not None
    assert audit.after_data["ptr"] == "95.00"


def test_the_feature_off_refuses_the_fields_and_nothing_else() -> None:
    """GENERIC has no BATCH_PTR_PTS: sending a rate is refused, omitting is not."""
    fixture = _Fixture(_session_factory()(), "PTR3")

    with pytest.raises(AuthorizationError, match="BATCH_PTR_PTS"):
        _receipt(fixture, batch_number="B-3", ptr=Decimal("90"))

    _receipt(fixture, batch_number="B-3")


def test_a_ptr_above_the_mrp_is_refused_at_receipt() -> None:
    """On the line's own MRP, and on the batch's when the line states none."""
    fixture = _pharma_receiver("PTR4")
    with pytest.raises(ValidationError, match="PTR 130.00 cannot exceed the MRP"):
        _receipt(fixture, batch_number="B-4", mrp=Decimal("120"), ptr=Decimal("130"))

    _complete(fixture, _receipt(fixture, batch_number="B-4", mrp=Decimal("120")))
    later = _receipt(fixture, batch_number="B-4", pts=Decimal("121"))
    with pytest.raises(ValidationError, match="PTS 121.00 cannot exceed the MRP"):
        _complete(fixture, later)


def test_a_rate_without_a_batch_number_is_refused() -> None:
    """The rates live on the batch; a line naming none has nowhere to put them."""
    fixture = _pharma_receiver("PTR5")
    with pytest.raises(ValidationError, match="needs a batch number"):
        _receipt(fixture, ptr=Decimal("90"))


# -- Sale --------------------------------------------------------------------


def _shop(trade_class: str | None) -> _Counter:
    """Build a counter firm with PTR / PTS on LATE and a buyer of this class."""
    shop = _Counter()
    _give_profile(shop.session, shop.firm.id, "PHARMA-SALE", _PHARMA_FEATURES)
    shop.drug.selling_price = Decimal("100")
    shop.batches["LATE"].mrp = Decimal("120")
    shop.batches["LATE"].ptr = Decimal("90")
    shop.batches["LATE"].pts = Decimal("80")
    shop.customer.trade_class = trade_class
    shop.session.commit()
    return shop


def _bill_price(shop: _Counter, *, unit_price: Decimal | None = None) -> Decimal:
    """Raise a counter bill of LATE with this price and return its line rate."""
    data = shop.bill([shop.pick("LATE")])
    data.lines[0].unit_price = unit_price
    draft = shop.bills.create_invoice(data, firm_id=shop.firm.id, actor_id=shop.actor)
    [line] = shop.bills.invoice_response(draft).lines
    return Decimal(line.unit_price)


def _order_price(
    shop: _Counter, *, batch: str | None = "LATE", unit_price: Decimal | None = None
) -> Decimal:
    """Raise an order pinning ``batch`` and return its line rate."""
    order = SalesOrderService(shop.session).create_order(
        SalesOrderCreate(
            customer_id=shop.customer.id,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            order_date=date(2026, 8, 4),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=shop.drug.id,
                    quantity=Decimal("4"),
                    unit_price=unit_price,
                    pinned_batch_id=shop.batches[batch].id if batch else None,
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    [line] = SalesOrderService(shop.session).order_response(order).lines
    return Decimal(line.unit_price)


def test_a_retailer_is_billed_ptr_and_a_stockist_pts() -> None:
    """On a counter bill naming the batch, and on an order pinning it."""
    retailer = _shop("RETAILER")
    assert _bill_price(retailer) == Decimal("90")
    assert _order_price(retailer) == Decimal("90")

    stockist = _shop("STOCKIST")
    assert _bill_price(stockist) == Decimal("80")
    assert _order_price(stockist) == Decimal("80")


def test_other_and_unclassed_buyers_fall_back_to_the_product_price() -> None:
    """OTHER, or no class at all, takes neither trade rate."""
    assert _bill_price(_shop("OTHER")) == Decimal("100")
    assert _order_price(_shop(None)) == Decimal("100")


def test_a_batch_without_the_rate_falls_back() -> None:
    """A stockist from a batch carrying only PTR, or a line naming no batch."""
    shop = _shop("STOCKIST")
    shop.batches["LATE"].pts = None
    shop.session.commit()
    assert _bill_price(shop) == Decimal("100")
    assert _order_price(_shop("RETAILER"), batch=None) == Decimal("100")


def test_an_explicit_price_still_wins() -> None:
    """A typed rate beats the batch's, on the bill and on the order."""
    shop = _shop("RETAILER")
    assert _bill_price(shop, unit_price=Decimal("95")) == Decimal("95")
    assert _order_price(shop, unit_price=Decimal("97")) == Decimal("97")


def test_the_feature_off_ignores_the_batch_rates_when_selling() -> None:
    """A profile without BATCH_PTR_PTS sells at the product's price."""
    shop = _Counter()
    _give_profile(
        shop.session, shop.firm.id, "NO-PTR", ("BATCH_TRACKING", "EXPIRY_TRACKING")
    )
    shop.drug.selling_price = Decimal("100")
    shop.batches["LATE"].ptr = Decimal("90")
    shop.customer.trade_class = "RETAILER"
    shop.session.commit()
    assert _order_price(shop) == Decimal("100")


def test_the_ranking_puts_the_list_above_the_batch_and_the_batch_above_the_level() -> (
    None
):
    """Price list, then batch rate, then price level, then the product."""
    rate = batch_trade_rate(trade_class="RETAILER", ptr=Decimal("90"), pts=None)
    assert rate is not None and rate.source == "BATCH_PTR"
    assert batch_trade_rate(trade_class="OTHER", ptr=Decimal("90"), pts=None) is None

    listed = resolve_unit_price(
        product_price=Decimal("100"),
        level_rate=Decimal("95"),
        list_rate=Decimal("85"),
        batch_rate=rate,
    )
    assert (listed.price, listed.source) == (Decimal("85"), "PRICE_LIST")
    batched = resolve_unit_price(
        product_price=Decimal("100"), level_rate=Decimal("95"), batch_rate=rate
    )
    assert (batched.price, batched.source) == (Decimal("90"), "BATCH_PTR")
