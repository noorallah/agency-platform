"""Backlog 138: ``20261013_0373`` files what was saved before the rule.

A product always has a brand and a brand a company, and the services refuse a
blank. The rows written before are settled by the migration, which a store
runs once and nobody watches: these drive its ``upgrade`` against a schema
built from the models, so the typed-brand path, the *Unbranded* path and a
second run are each seen to do what the revision says.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.products.models import Product
from app.products.models.brand import Brand, Principal

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20261013_0373_product_brand_and_company_always.py"
)


def _revision() -> ModuleType:
    """Load the revision as a module."""
    spec = importlib.util.spec_from_file_location("brand_always_0373", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine() -> Engine:
    """Return an in-memory store holding the whole schema."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _upgrade(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the revision's upgrade on this store and commit it."""
    module = _revision()
    with engine.begin() as connection:
        monkeypatch.setattr(module.op, "get_bind", lambda: connection)
        module.upgrade()


def _product(firm_id: UUID, code: str, **fields: object) -> Product:
    """Build a product row as an older build left it."""
    return Product(
        firm_id=firm_id,
        code=code,
        name=code,
        product_type="STOCK_ITEM",
        status="ACTIVE",
        **fields,
    )


def test_rows_without_a_parent_are_filed_and_the_rest_left_alone(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typed brands become rows, blanks go under Unbranded, brands get a company."""
    firm_id, other = uuid4(), uuid4()
    with Session(engine) as session:
        company = Principal(firm_id=firm_id, code="ACME", name="Acme Ltd")
        session.add(company)
        session.flush()
        kept = Brand(firm_id=firm_id, name="Acme", principal_id=company.id)
        loose = Brand(firm_id=firm_id, name="Loose")
        session.add_all([kept, loose])
        session.flush()
        session.add_all(
            [
                _product(firm_id, "FILED", brand="Acme", brand_id=kept.id),
                _product(firm_id, "TYPED-KEPT", brand=" acme "),
                _product(firm_id, "TYPED-NEW-1", brand="Nova"),
                _product(firm_id, "TYPED-NEW-2", brand="NOVA"),
                _product(firm_id, "BLANK"),
                _product(firm_id, "SPACES", brand="   "),
                _product(firm_id, "GONE", is_deleted=True),
                _product(other, "ELSEWHERE"),
            ]
        )
        session.commit()
        kept_id, loose_id, company_id = kept.id, loose.id, company.id

    _upgrade(engine, monkeypatch)

    with Session(engine) as session:
        general = session.scalars(
            select(Principal)
            .where(Principal.firm_id == firm_id)
            .order_by(Principal.code)
        ).all()
        assert [(row.code, row.name) for row in general] == [
            ("ACME", "Acme Ltd"),
            ("GENERAL", "General"),
        ]
        general_id = general[1].id
        brands = {
            row.name: row
            for row in session.scalars(select(Brand).where(Brand.firm_id == firm_id))
        }
        # One brand for the two spellings, spelt as either product had it.
        (nova,) = set(brands) - {"Acme", "Loose", "Unbranded"}
        assert nova in {"Nova", "NOVA"}
        assert len(brands) == 4
        assert brands["Acme"].principal_id == company_id
        assert brands["Loose"].id == loose_id
        assert brands["Loose"].principal_id == general_id
        assert brands[nova].principal_id == general_id
        assert brands["Unbranded"].principal_id == general_id
        products = {
            row.code: row
            for row in session.scalars(
                select(Product).where(Product.firm_id == firm_id)
            )
        }
        assert products["FILED"].brand_id == kept_id
        assert (products["TYPED-KEPT"].brand_id, products["TYPED-KEPT"].brand) == (
            kept_id,
            "Acme",
        )
        for code in ("TYPED-NEW-1", "TYPED-NEW-2"):
            assert products[code].brand_id == brands[nova].id
            assert products[code].brand == nova
        for code in ("BLANK", "SPACES", "GONE"):
            assert products[code].brand_id == brands["Unbranded"].id
            assert products[code].brand == "Unbranded"
        # The other firm gets its own General and Unbranded, never this one's.
        elsewhere = session.scalars(
            select(Product).where(Product.firm_id == other)
        ).one()
        theirs = session.get(Brand, elsewhere.brand_id)
        assert theirs is not None and theirs.firm_id == other
        assert theirs.id != brands["Unbranded"].id


def test_a_second_run_and_a_settled_store_write_nothing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is made where nothing needs it, and a re-run makes nothing more."""
    firm_id, settled = uuid4(), uuid4()
    with Session(engine) as session:
        company = Principal(firm_id=settled, code="ACME", name="Acme Ltd")
        session.add(company)
        session.flush()
        brand = Brand(firm_id=settled, name="Acme", principal_id=company.id)
        session.add(brand)
        session.flush()
        session.add(_product(settled, "FILED", brand="Acme", brand_id=brand.id))
        session.add(_product(firm_id, "BLANK"))
        session.commit()

    _upgrade(engine, monkeypatch)
    _upgrade(engine, monkeypatch)

    with Session(engine) as session:
        assert [
            row.code
            for row in session.scalars(
                select(Principal).where(Principal.firm_id == settled)
            )
        ] == ["ACME"]
        assert (
            len(session.scalars(select(Brand).where(Brand.firm_id == settled)).all())
            == 1
        )
        assert [
            row.name
            for row in session.scalars(select(Brand).where(Brand.firm_id == firm_id))
        ] == ["Unbranded"]
        assert (
            len(
                session.scalars(
                    select(Principal).where(Principal.firm_id == firm_id)
                ).all()
            )
            == 1
        )
