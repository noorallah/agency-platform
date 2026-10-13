"""Principal and brand masters (MST-1, decision A118).

A principal owns a brand; a product given the brand carries its name as
text too, and renaming the brand renames the text. A brand a product
carries cannot be deleted, nor a principal that owns a brand. Sales
analysis groups and filters by brand and by principal.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.products.models import Product
from app.products.models.brand import Principal
from app.products.schemas import ProductCreate, ProductUpdate
from app.products.services import ProductService
from app.products.services.brands import BrandService, BrandWrite, PrincipalWrite
from app.sales_invoice.services.sales_analysis import (
    AnalysisFilters,
    SalesAnalysisService,
)
from tests.unit.test_credit_note import _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

FROM, TO = date(2026, 4, 1), date(2027, 3, 31)


def test_brands_belong_to_principals_and_reach_the_analysis() -> None:
    books = _Books(_session_factory()())
    session = books.session
    actor = books.firm.id
    brands = BrandService(session)
    principal = brands.save_principal(
        PrincipalWrite(code="hul", name="Hindustan Unilever"),
        firm_id=books.firm.id,
        actor_id=actor,
    )
    assert principal.code == "HUL"
    brand = brands.save_brand(
        BrandWrite(name="Surf", principal_id=principal.id),
        firm_id=books.firm.id,
        actor_id=actor,
    )
    product = session.scalar(select(Product).where(Product.firm_id == books.firm.id))
    assert product is not None
    product.brand_id = brand.id
    product.brand = "Surf"
    session.commit()

    brands.save_brand(
        BrandWrite(name="Surf Excel", principal_id=principal.id),
        firm_id=books.firm.id,
        actor_id=actor,
        brand_id=brand.id,
    )
    session.refresh(product)
    assert product.brand == "Surf Excel"

    analysis = SalesAnalysisService(session)
    by_brand = analysis.analyse(
        books.firm.id, rows="brand", columns=None, from_date=FROM, to_date=TO
    )
    assert [row.label for row in by_brand.rows] == ["Surf Excel"]
    by_principal = analysis.analyse(
        books.firm.id, rows="principal", columns=None, from_date=FROM, to_date=TO
    )
    assert [row.label for row in by_principal.rows] == ["Hindustan Unilever"]
    filtered = analysis.analyse(
        books.firm.id,
        rows="product",
        columns=None,
        from_date=FROM,
        to_date=TO,
        filters=AnalysisFilters(principal_id=principal.id),
    )
    assert len(filtered.rows) == 1

    with pytest.raises(ValidationError, match="still the brand of"):
        brands.delete_brand(brand.id, firm_id=books.firm.id, actor_id=actor)
    with pytest.raises(ValidationError, match="still owns brand"):
        brands.delete_principal(principal.id, firm_id=books.firm.id, actor_id=actor)


def _company(books: _Books) -> UUID:
    return (
        BrandService(books.session)
        .save_principal(
            PrincipalWrite(code="ACME", name="Acme Ltd"),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
        .id
    )


def _new(code: str, **fields: object) -> ProductCreate:
    return ProductCreate.model_validate(
        {"code": code, "name": code, "product_type": "STOCK_ITEM", **fields}
    )


def _create(books: _Books, code: str, **fields: object) -> Product:
    return ProductService(books.session).create_product(
        _new(code, **fields), firm_id=books.firm.id, actor_id=books.actor_id
    )


def _update(books: _Books, product: Product, **fields: object) -> Product:
    return ProductService(books.session).update_product(
        product.id,
        ProductUpdate.model_validate(
            {
                "code": product.code,
                "name": product.name,
                "product_type": "STOCK_ITEM",
                **fields,
            }
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )


def _books_with_brand() -> tuple[_Books, UUID]:
    books = _Books(_session_factory()())
    brand = BrandService(books.session).save_brand(
        BrandWrite(name="Acme", principal_id=_company(books)),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    return books, brand.id


def test_a_product_with_no_brand_is_refused_on_create() -> None:
    books, _ = _books_with_brand()

    with pytest.raises(ValidationError, match="A product needs a brand: choose one."):
        _create(books, "NO-BRAND")


def test_a_brand_text_is_resolved_to_the_firms_brand_in_any_case() -> None:
    books, brand_id = _books_with_brand()

    product = _create(books, "BY-NAME", brand="acme")

    assert product.brand_id == brand_id
    assert product.brand == "Acme"


def test_a_brand_the_firm_does_not_keep_is_refused_by_name() -> None:
    books, _ = _books_with_brand()

    with pytest.raises(ValidationError, match="'Zenith' is not one of the firm's"):
        _create(books, "UNKNOWN", brand="Zenith")


def test_an_update_naming_no_brand_row_is_refused_and_a_silent_one_keeps_it() -> None:
    books, brand_id = _books_with_brand()
    product = _create(books, "KEPT", brand_id=str(brand_id))

    with pytest.raises(ValidationError, match="needs a brand"):
        _update(books, product, brand_id=None)
    books.session.rollback()

    renamed = _update(books, product, name="Renamed")
    assert (renamed.brand_id, renamed.brand) == (brand_id, "Acme")

    blank = _update(books, product, name="Blank text", brand="")
    assert (blank.brand_id, blank.brand) == (brand_id, "Acme")


def test_a_product_row_with_no_brand_is_refused_on_any_update() -> None:
    books, brand_id = _books_with_brand()
    legacy = books.session.scalar(
        select(Product).where(Product.firm_id == books.firm.id)
    )
    assert legacy is not None
    legacy.brand_id = None
    legacy.brand = None
    books.session.commit()

    with pytest.raises(ValidationError, match="needs a brand"):
        _update(books, legacy, name="Renamed")
    books.session.rollback()

    named = _update(books, legacy, brand_id=str(brand_id))
    assert named.brand_id == brand_id


def test_a_brand_belongs_to_a_company() -> None:
    books = _Books(_session_factory()())
    brands = BrandService(books.session)

    with pytest.raises(ValidationError, match="A brand belongs to a company"):
        brands.save_brand(
            BrandWrite(name="Orphan", principal_id=None),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )

    saved = brands.save_brand(
        BrandWrite(name="Kept", principal_id=_company(books)),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    assert saved.name == "Kept"


def test_ensure_brand_returns_the_same_row_and_makes_the_company_once() -> None:
    books = _Books(_session_factory()())
    brands = BrandService(books.session)

    first = brands.ensure_brand("Plain", firm_id=books.firm.id, actor_id=books.actor_id)
    again = brands.ensure_brand("plain", firm_id=books.firm.id, actor_id=books.actor_id)
    other = brands.ensure_brand("Other", firm_id=books.firm.id, actor_id=books.actor_id)

    assert again.id == first.id
    assert other.id != first.id
    generals = books.session.scalars(
        select(Principal).where(
            Principal.firm_id == books.firm.id, Principal.code == "GENERAL"
        )
    ).all()
    assert [row.name for row in generals] == ["General"]
    assert first.principal_id == other.principal_id == generals[0].id


def test_a_duplicate_of_a_branded_product_carries_the_brand() -> None:
    books, brand_id = _books_with_brand()
    product = _create(books, "ORIGINAL", brand_id=str(brand_id))

    copy = ProductService(books.session).duplicate_product(
        product.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )

    assert copy.id != product.id
    assert (copy.brand_id, copy.brand) == (brand_id, "Acme")
