"""The brands a supplier may sell (backlog 129, row M11).

A supplier with brands named is answered from its own list; one with none
takes the brands of the company bought from it, and a branch its main
office's; a supplier nothing answers for is not limited. A stockist is
named brands that belong to other companies. The product list narrows to
brand rows exactly. A brand a supplier names is not deleted, and a merge
carries the list across without a clash.
"""

# ruff: noqa: D103

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.party_merge import PartyMergeService, PartyMergeWrite
from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.products.models import Product
from app.products.schemas import ProductListFilters
from app.products.services import ProductService
from app.products.services.brands import BrandService, BrandWrite, PrincipalWrite
from app.vendors.models import Vendor, VendorBrand
from app.vendors.services.vendor_brands import VendorBrandService, VendorBrandsWrite
from tests.unit.test_purchase_chain_synthesis import _Firm


@pytest.fixture
def firm() -> _Firm:
    """Build a firm on a fresh in-memory store."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="BRAND")


def _brand(firm: _Firm, name: str, principal_id: UUID | None = None) -> UUID:
    return (
        BrandService(firm.session)
        .save_brand(
            BrandWrite(name=name, principal_id=principal_id),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
        .id
    )


def _company(firm: _Firm, code: str, vendor_id: UUID | None = None) -> UUID:
    return (
        BrandService(firm.session)
        .save_principal(
            PrincipalWrite(code=code, name=f"{code} Ltd", vendor_id=vendor_id),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
        .id
    )


def _supplier(firm: _Firm, code: str, parent_id: UUID | None = None) -> Vendor:
    vendor = Vendor(
        firm_id=firm.firm.id,
        code=code,
        name=f"{code} Traders",
        display_name=f"{code} Traders",
        status="ACTIVE",
        parent_vendor_id=parent_id,
    )
    firm.session.add(vendor)
    firm.session.commit()
    return vendor


def _product(firm: _Firm, code: str, brand_id: UUID | None) -> Product:
    product = Product(
        firm_id=firm.firm.id,
        code=code,
        name=code,
        product_type="STOCK_ITEM",
        status="ACTIVE",
        brand_id=brand_id,
    )
    firm.session.add(product)
    firm.session.commit()
    return product


def _name(firm: _Firm, vendor_id: UUID, *brand_ids: UUID) -> None:
    VendorBrandService(firm.session).set(
        vendor_id,
        VendorBrandsWrite(brand_ids=list(brand_ids)),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _names(firm: _Firm, vendor_id: UUID) -> tuple[str, list[str]]:
    answer = VendorBrandService(firm.session).brands_of(vendor_id, firm_id=firm.firm.id)
    return answer.source, [row.name for row in answer.brands]


def test_a_supplier_with_nothing_named_is_not_limited(firm: _Firm) -> None:
    _brand(firm, "Surf")
    assert _names(firm, firm.vendor.id) == ("NONE", [])


def test_the_brands_named_on_a_supplier_are_its_own_list(firm: _Firm) -> None:
    surf, lux = _brand(firm, "Surf"), _brand(firm, "Lux")
    _brand(firm, "Tide")
    _name(firm, firm.vendor.id, surf, lux, surf)
    answer = VendorBrandService(firm.session).brands_of(
        firm.vendor.id, firm_id=firm.firm.id
    )
    assert answer.source == "OWN"
    assert [row.name for row in answer.brands] == ["Lux", "Surf"]
    assert set(answer.named_brand_ids) == {surf, lux}

    # The list is replaced whole, and an empty one clears it.
    _name(firm, firm.vendor.id, lux)
    assert _names(firm, firm.vendor.id) == ("OWN", ["Lux"])
    _name(firm, firm.vendor.id)
    assert _names(firm, firm.vendor.id) == ("NONE", [])
    assert firm.session.scalars(select(VendorBrand)).all() == []


def test_a_company_bought_from_a_supplier_gives_it_its_brands(firm: _Firm) -> None:
    company = _company(firm, "HUL", vendor_id=firm.vendor.id)
    _brand(firm, "Surf", company)
    _brand(firm, "Lux", company)
    tide = _brand(firm, "Tide", _company(firm, "PG"))
    assert _names(firm, firm.vendor.id) == ("COMPANY", ["Lux", "Surf"])

    # A list of its own outranks the company's.
    _name(firm, firm.vendor.id, tide)
    assert _names(firm, firm.vendor.id) == ("OWN", ["Tide"])


def test_a_stockist_is_named_brands_of_other_companies(firm: _Firm) -> None:
    surf = _brand(firm, "Surf", _company(firm, "HUL"))
    tide = _brand(firm, "Tide", _company(firm, "PG"))
    stockist = _supplier(firm, "STOCK")
    _name(firm, stockist.id, surf, tide)
    answer = VendorBrandService(firm.session).brands_of(
        stockist.id, firm_id=firm.firm.id
    )
    assert [(row.name, row.principal_name) for row in answer.brands] == [
        ("Surf", "HUL Ltd"),
        ("Tide", "PG Ltd"),
    ]


def test_a_branch_takes_its_main_offices_brands_until_it_names_its_own(
    firm: _Firm,
) -> None:
    surf, lux = _brand(firm, "Surf"), _brand(firm, "Lux")
    branch = _supplier(firm, "BRANCH", parent_id=firm.vendor.id)
    assert _names(firm, branch.id) == ("NONE", [])

    _name(firm, firm.vendor.id, surf)
    answer = VendorBrandService(firm.session).brands_of(branch.id, firm_id=firm.firm.id)
    assert (answer.source, answer.source_vendor_name) == ("MAIN_OFFICE", "Vendor")
    assert [row.name for row in answer.brands] == ["Surf"]
    assert answer.named_brand_ids == []

    _name(firm, branch.id, lux)
    assert _names(firm, branch.id) == ("OWN", ["Lux"])
    assert _names(firm, firm.vendor.id) == ("OWN", ["Surf"])


def test_a_brand_of_another_firm_or_a_deleted_one_is_refused(firm: _Firm) -> None:
    surf = _brand(firm, "Surf")
    with pytest.raises(ValidationError, match="not one of the firm's brands"):
        _name(firm, firm.vendor.id, surf, uuid4())
    assert _names(firm, firm.vendor.id) == ("NONE", [])
    with pytest.raises(ResourceNotFoundError):
        _name(firm, uuid4(), surf)


def test_a_brand_a_supplier_names_is_not_deleted(firm: _Firm) -> None:
    surf = _brand(firm, "Surf")
    _name(firm, firm.vendor.id, surf)
    brands = BrandService(firm.session)
    with pytest.raises(ValidationError, match="brand of supplier Vendor"):
        brands.delete_brand(surf, firm_id=firm.firm.id, actor_id=firm.actor_id)
    _name(firm, firm.vendor.id)
    brands.delete_brand(surf, firm_id=firm.firm.id, actor_id=firm.actor_id)


def test_the_product_list_narrows_to_brand_rows_exactly(firm: _Firm) -> None:
    surf, lux = _brand(firm, "Surf"), _brand(firm, "Lux")
    _product(firm, "SURF-1KG", surf)
    _product(firm, "SURF-2KG", surf)
    _product(firm, "LUX-100G", lux)
    _product(firm, "LOOSE", None)

    def listed(*brand_ids: UUID) -> list[str]:
        rows, total = ProductService(firm.session).list_products(
            firm_scope=firm.firm.id,
            filters=ProductListFilters(brand_ids=list(brand_ids)),
            page=1,
            page_size=50,
            search=None,
            sort_by="code",
            descending=False,
        )
        assert total == len(rows)
        return [row.code for row in rows]

    assert listed(surf) == ["SURF-1KG", "SURF-2KG"]
    assert listed(surf, lux) == ["LUX-100G", "SURF-1KG", "SURF-2KG"]
    assert len(listed()) == 5


def test_a_merge_carries_the_brands_across_without_a_clash(firm: _Firm) -> None:
    surf, lux = _brand(firm, "Surf"), _brand(firm, "Lux")
    twin = _supplier(firm, "TWIN")
    _name(firm, firm.vendor.id, surf)
    _name(firm, twin.id, surf, lux)
    PartyMergeService(firm.session).merge(
        "VENDOR",
        firm.vendor.id,
        PartyMergeWrite(duplicate_id=twin.id, reason="Same supplier typed twice"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert _names(firm, firm.vendor.id) == ("OWN", ["Lux", "Surf"])
