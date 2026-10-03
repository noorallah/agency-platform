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
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ConflictError
from app.pricing.services.unit_price import UnitPriceResolver
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


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with new widget rates from 1 November."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="PRREV")
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
