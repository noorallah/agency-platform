"""A supplier's catalogue (BUY-4, decision A101).

The supplier quotes widgets as BR-W1 at 90 from April and 95 from August.
An order dated in August takes 95 and the code BR-W1 on a blank line; a
price list's fixed rate still outranks the catalogue; the history keeps both
rows; the same date twice is refused; and a file brings rows in all or
nothing, refusing a product already listed unless asked to update.
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
from app.pricing.models import PriceList, PriceListItem
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.vendors.schemas.supplier_product import SupplierProductWrite
from app.vendors.services.supplier_catalogue import (
    SupplierCatalogueFileImporter,
    SupplierCatalogueService,
)
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm on a fresh in-memory store."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="CATLG")


def _quote(firm: _Firm, price: str, on: date) -> None:
    SupplierCatalogueService(firm.session).add(
        firm.vendor.id,
        SupplierProductWrite(
            product_id=firm.product.id,
            supplier_product_code="BR-W1",
            unit_price=D(price),
            pack_size=D("12"),
            effective_from=on,
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _line(firm: _Firm) -> PurchaseOrderLine:
    order = PurchaseService(firm.session).create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": "2026-08-10",
                "lines": [{"product_id": firm.product.id, "ordered_quantity": "10"}],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    line = firm.session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert line is not None
    return line


def test_the_dated_row_fills_a_blank_line(firm: _Firm) -> None:
    _quote(firm, "90", date(2026, 4, 1))
    _quote(firm, "95", date(2026, 8, 1))
    line = _line(firm)
    assert line.unit_price == D("95")
    assert line.vendor_product_code == "BR-W1"

    service = SupplierCatalogueService(firm.session)
    history = service.list_rows(firm.vendor.id, firm_id=firm.firm.id, history=True)
    assert [row.unit_price for row in history] == [D("90"), D("95")]
    with pytest.raises(ConflictError, match="already has a row"):
        _quote(firm, "99", date(2026, 8, 1))


def test_a_price_list_rate_outranks_the_catalogue(firm: _Firm) -> None:
    _quote(firm, "95", date(2026, 4, 1))
    price_list = PriceList(
        firm_id=firm.firm.id,
        code="SUP-LIST",
        name="Supplier list",
        vendor_id=firm.vendor.id,
        effective_from=date(2026, 4, 1),
    )
    firm.session.add(price_list)
    firm.session.flush()
    firm.session.add(
        PriceListItem(
            price_list_id=price_list.id,
            firm_id=firm.firm.id,
            product_id=firm.product.id,
            rate=D("80"),
        )
    )
    firm.session.commit()
    assert _line(firm).unit_price == D("80")


def test_a_file_imports_all_or_nothing(firm: _Firm) -> None:
    code = firm.product.code
    good = f"Code,SupplierCode,Price,EffectiveFrom\n{code},BR-W1,90,01-04-2026\n"
    importer = SupplierCatalogueFileImporter(firm.session, firm.vendor.id)
    report = importer.run(
        good.encode(),
        file_format="csv",
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
        apply=True,
    )
    assert report.imported and report.to_create == 1

    again = f"Code,Price,EffectiveFrom\n{code},95,01-08-2026\nNOPE,1,01-08-2026\n"
    report = SupplierCatalogueFileImporter(firm.session, firm.vendor.id).run(
        again.encode(),
        file_format="csv",
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
        existing="update",
        apply=True,
    )
    assert not report.imported
    assert [issue.code for issue in report.issues] == ["NOPE"]

    refused = SupplierCatalogueFileImporter(firm.session, firm.vendor.id).run(
        f"Code,Price\n{code},95\n".encode(),
        file_format="csv",
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
        apply=False,
    )
    assert "already a catalogue product" in refused.issues[0].message
    rows = SupplierCatalogueService(firm.session).list_rows(
        firm.vendor.id, firm_id=firm.firm.id, history=True
    )
    assert [row.unit_price for row in rows] == [D("90")]
