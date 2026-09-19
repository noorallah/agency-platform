"""A product import writes every row or none.

D-MST-9: all three formats end in ``import_products_json``, which looped over
``create_product`` -- and that commits. A two-record import whose second row
reused an existing code answered 409 with the first row written, and the
corrected file was then refused as a duplicate of what the failed one left.
"""

from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import BusinessProfile
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.firms.models import Firm
from app.products.models import Product
from app.products.schemas import ProductCreate
from app.products.services import ProductService


def _factory() -> sessionmaker[Session]:
    """Build one in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    """Add a firm and the default profile a product needs."""
    firm = Firm(
        name="Import Firm",
        code="IMPORT",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all(
        [
            firm,
            BusinessProfile(
                code="GENERIC",
                name="Generic",
                industry_type="GENERIC",
                status="ACTIVE",
                is_default=True,
                default_settings={},
            ),
        ]
    )
    session.commit()
    return firm


def _record(code: str) -> ProductCreate:
    """Build the smallest importable product."""
    return ProductCreate.model_validate(
        {"code": code, "name": code, "product_type": "STOCK_ITEM"}
    )


def _codes(factory: sessionmaker[Session]) -> list[str]:
    """Read what is durably stored, from a session of its own."""
    with factory() as fresh:
        return sorted(fresh.scalars(select(Product.code)).all())


def test_a_clash_on_the_second_row_writes_nothing_and_names_the_row() -> None:
    """The failed file leaves nothing, so the corrected file imports."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    service = ProductService(session)
    actor = uuid4()
    service.create_product(_record("TAKEN"), firm_id=firm.id, actor_id=actor)

    with pytest.raises(ConflictError) as refused:
        service.import_products_json(
            [_record("FIRST"), _record("TAKEN"), _record("THIRD")],
            firm_scope=firm.id,
            actor_id=actor,
        )

    assert "Row 2 (TAKEN)" in str(refused.value)
    assert "Nothing was imported" in str(refused.value)
    assert _codes(factory) == ["TAKEN"]
    with factory() as fresh:
        created = fresh.scalars(
            select(AuditLog).where(AuditLog.action == "product.created")
        ).all()
        assert len(created) == 1

    # The corrected file is not refused as a duplicate of the failed one.
    imported = service.import_products_json(
        [_record("FIRST"), _record("THIRD")], firm_scope=firm.id, actor_id=actor
    )
    assert [row.code for row in imported] == ["FIRST", "THIRD"]
    assert _codes(factory) == ["FIRST", "TAKEN", "THIRD"]


def test_two_rows_of_one_file_sharing_a_code_write_nothing() -> None:
    """A clash inside the file is a clash: the first of the pair is staged."""
    factory = _factory()
    session = factory()
    firm = _firm(session)

    with pytest.raises(ConflictError, match="Row 2 \\(TWICE\\)"):
        ProductService(session).import_products_json(
            [_record("TWICE"), _record("TWICE")], firm_scope=firm.id, actor_id=uuid4()
        )

    assert _codes(factory) == []


def test_a_csv_with_a_bad_number_names_the_row_and_writes_nothing() -> None:
    """The reader refused nothing by name; a bad price was a server error."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    content = (
        "Code,Name,Type,Brand,HSN,SellingPrice,Status\n"
        "CSV-1,One,STOCK_ITEM,Acme,1234,10.50,ACTIVE\n"
        "CSV-2,Two,STOCK_ITEM,Acme,1234,ten,ACTIVE\n"
    )

    with pytest.raises(ValidationError) as refused:
        ProductService(session).import_products_csv(
            content, firm_scope=firm.id, actor_id=uuid4()
        )

    assert "Row 3 (CSV-2): SellingPrice" in str(refused.value)
    assert _codes(factory) == []


def test_a_csv_with_an_unknown_status_names_the_row() -> None:
    """The schema's refusal reaches the caller with the row it belongs to."""
    session = _factory()()
    firm = _firm(session)
    content = "Code,Name,Status\nCSV-1,One,RETIRED\n"

    with pytest.raises(ValidationError, match="Row 2 \\(CSV-1\\): status"):
        ProductService(session).import_products_csv(
            content, firm_scope=firm.id, actor_id=uuid4()
        )


def test_a_good_csv_and_a_good_workbook_import_whole() -> None:
    """Both readers still fill the seven columns they always did."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    service = ProductService(session)
    csv_rows = service.import_products_csv(
        "Code,Name,Type,Brand,HSN,SellingPrice,Status\n"
        "csv-1,One,stock_item,Acme,ab12,10.50,active\n"
        ",Skipped for having no code,,,,,\n",
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    assert [(row.code, row.brand, row.hsn_sac) for row in csv_rows] == [
        ("CSV-1", "Acme", "AB12")
    ]
    assert str(csv_rows[0].selling_price) == "10.50"

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Code", "Name", "SellingPrice"])
    sheet.append(["XL-1", "Sheet one", 25])
    buffer = BytesIO()
    workbook.save(buffer)
    xlsx_rows = service.import_products_xlsx(
        buffer.getvalue(), firm_scope=firm.id, actor_id=uuid4()
    )
    # A sheet with no Status or Type column takes the defaults, rather than
    # reading the last column in their place.
    assert [(row.code, row.status, row.product_type) for row in xlsx_rows] == [
        ("XL-1", "ACTIVE", "STOCK_ITEM")
    ]
    assert _codes(factory) == ["CSV-1", "XL-1"]
