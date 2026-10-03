"""Principal and brand masters (MST-1, decision A118).

A principal owns a brand; a product given the brand carries its name as
text too, and renaming the brand renames the text. A brand a product
carries cannot be deleted, nor a principal that owns a brand. Sales
analysis groups and filters by brand and by principal.
"""

# ruff: noqa: D103

from datetime import date

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.products.models import Product
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
