"""Price revisions with an effective date (MST-2, decision A119).

Widgets sell at the product's own price until 1 November, when a revision
makes them 120; a purchase order dated in October still takes the old
purchase price and one dated in November the new. The same date twice is
refused, and a file of revisions comes in whole or not at all.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.pricing.services.unit_price import UnitPriceResolver
from app.products.api.router import _response, _responses
from app.products.services.price_revisions import (
    PriceRevisionFileImporter,
    PriceRevisionService,
    PriceRevisionWrite,
    price_in_force,
)
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal

#: The day these tests are run on. Pinned, because a revision may not start
#: before today (D-PRC-15) and the dates below are written out.
TODAY = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hold the firm's day at ``TODAY`` for the revision service."""
    monkeypatch.setattr(
        "app.products.services.price_revisions.firm_today",
        lambda session, firm_id: TODAY,
    )


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with new widget rates from 1 November.

    On a session that does not flush on a read, as a request's does not.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(
        sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)(),
        code="PRREV",
    )
    built.product.selling_price = D("100")
    built.session.commit()
    PriceRevisionService(built.session).add(
        built.product.id,
        PriceRevisionWrite(
            effective_from=date(2026, 11, 1),
            selling_price=D("120"),
            purchase_price=D("95"),
        ),
        firm_id=built.firm.id,
        actor_id=built.actor_id,
    )
    return built


def _sale_price(firm: _Firm, on: date) -> Decimal | None:
    resolver = UnitPriceResolver(
        firm.session, firm_id=firm.firm.id, customer_id=None, territory_id=None, on=on
    )
    return resolver.price(firm.product.id).price


def _order_price(firm: _Firm, on: str) -> Decimal:
    order = PurchaseService(firm.session).create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": on,
                "lines": [{"product_id": firm.product.id, "ordered_quantity": "1"}],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    line = firm.session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert line is not None
    return D(str(line.unit_price))


def test_the_rate_in_force_on_the_documents_date(firm: _Firm) -> None:
    assert _sale_price(firm, date(2026, 10, 31)) == D("100")
    assert _sale_price(firm, date(2026, 11, 1)) == D("120")
    assert (
        price_in_force(firm.session, firm.product.id, "mrp", on=date(2026, 12, 1))
        is None
    )
    assert _order_price(firm, "2026-10-15") == D("90")
    assert _order_price(firm, "2026-11-15") == D("95")


def test_the_same_date_twice_is_refused(firm: _Firm) -> None:
    with pytest.raises(ConflictError, match="already has new rates"):
        PriceRevisionService(firm.session).add(
            firm.product.id,
            PriceRevisionWrite(effective_from=date(2026, 11, 1), selling_price=D("1")),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_a_file_comes_in_whole(firm: _Firm) -> None:
    code = firm.product.code
    report = PriceRevisionFileImporter(firm.session).run(
        f"Code,EffectiveFrom,SellingPrice\n{code},01-12-2026,130\nNOPE,01-12-2026,1\n".encode(),
        file_format="csv",
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
        apply=True,
    )
    assert not report.imported
    report = PriceRevisionFileImporter(firm.session).run(
        f"Code,EffectiveFrom,SellingPrice\n{code},01-12-2026,130\n".encode(),
        file_format="csv",
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
        apply=True,
    )
    assert report.imported
    assert _sale_price(firm, date(2026, 12, 5)) == D("130")


def _revise(firm: _Firm, on: date, **prices: str) -> None:
    """Add one revision from ``on``."""
    PriceRevisionService(firm.session).add(
        firm.product.id,
        PriceRevisionWrite.model_validate({"effective_from": on, **prices}),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_new_rates_start_today_or_later(firm: _Firm) -> None:
    """D-PRC-15(b): a revision dated back was taken in silence.

    Driven on S9: 70.00 from three days ago was accepted with no word and
    became the price in force, so a quotation today took 70.00 against a
    product reading 84.00. Typed or from a file, it is refused.
    """
    with pytest.raises(ValidationError) as refusal:
        _revise(firm, date(2026, 9, 28), selling_price="70")
    assert str(refusal.value) == (
        "New rates start today (01-10-2026) or later, not from 28-09-2026. "
        "A price dated back would change today's price without saying so; "
        "date it today instead."
    )
    assert _sale_price(firm, TODAY) == D("100")

    report = PriceRevisionFileImporter(firm.session).run(
        f"Code,EffectiveFrom,SellingPrice\n{firm.product.code},28-09-2026,70\n".encode(),
        file_format="csv",
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
        apply=True,
    )
    assert not report.imported
    assert "New rates start today (01-10-2026) or later" in report.issues[0].message
    assert _sale_price(firm, TODAY) == D("100")

    _revise(firm, TODAY, selling_price="110")
    assert _sale_price(firm, TODAY) == D("110"), "today itself is not the past"


def test_a_revision_keeps_the_mrp_at_or_above_the_selling_price(firm: _Firm) -> None:
    """D-PRC-15(a): selling 50 with an MRP of 40 was taken.

    In the product form's own words when one revision names both, and
    against the price the revision leaves alone when it names one.
    """
    with pytest.raises(PydanticValidationError, match="MRP must be greater than"):
        PriceRevisionWrite(effective_from=TODAY, selling_price=D("50"), mrp=D("40"))

    # An MRP from December below the 120.00 that starts in November.
    with pytest.raises(ValidationError) as refusal:
        _revise(firm, date(2026, 12, 1), mrp="115")
    assert str(refusal.value) == (
        "MRP must be greater than or equal to selling price. From 01-12-2026 "
        f"{firm.product.code} would sell at 120 against an MRP of 115."
    )
    # A price from today above the product's own MRP.
    firm.product.mrp = D("105")
    firm.session.commit()
    with pytest.raises(
        ValidationError, match="would sell at 110 against an MRP of 105"
    ):
        _revise(firm, TODAY, selling_price="110")

    _revise(firm, TODAY, selling_price="105")
    assert _sale_price(firm, TODAY) == D("105")


def test_the_product_says_what_it_sells_at_today(firm: _Firm) -> None:
    """D-PRC-15(c): the product read 84.00 while documents took the revision.

    The card price stays as typed; the price in force today sits beside it,
    read once for a page.
    """
    before = _response(firm.product, can_view_cost=True, db=firm.session)
    assert (before.selling_price, before.selling_price_in_force) == (
        D("100"),
        D("100"),
    ), "the 120.00 starts on 1 November, which has not come"
    assert before.purchase_price_in_force == before.purchase_price == D("90")
    assert before.mrp_in_force is None

    _revise(firm, TODAY, selling_price="86", mrp="99")

    [listed] = _responses([firm.product], can_view_cost=True, db=firm.session)
    assert (listed.selling_price, listed.selling_price_in_force) == (D("100"), D("86"))
    assert (listed.mrp, listed.mrp_in_force) == (None, D("99"))
    assert listed.purchase_price_in_force == D("90"), "no revision names it yet"
    assert listed == _response(firm.product, can_view_cost=True, db=firm.session)
    hidden = _response(firm.product, can_view_cost=False, db=firm.session)
    assert hidden.purchase_price is None and hidden.purchase_price_in_force is None
