"""A supplier's address says its city and area by name (S3)."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.sales.models import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoPostalCode,
    GeoState,
)
from app.vendors.api.router import create_vendor, get_vendor, list_vendors
from app.vendors.schemas import VendorAddressInput, VendorCreate
from app.vendors.schemas.vendor import VendorListFilters
from app.vendors.services import VendorService

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _engine() -> Engine:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _scope(session: Session) -> ResolvedFirmScope:
    """Create a firm and a member who may read and create suppliers."""
    firm = Firm(
        name="Places Firm",
        code="PLACES",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()
    permissions = ["VENDOR_CREATE", "VENDOR_VIEW"]
    principal = Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=permissions,
        ),
    )
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm.id)
    )


def _places(session: Session) -> dict[str, dict[str, UUID]]:
    """Seed two cities, each with one area, and return an address for each."""
    country = GeoCountry(code="IN", name="India")
    session.add(country)
    session.flush()
    state = GeoState(country_id=country.id, code="TS", name="Telangana")
    session.add(state)
    session.flush()
    district = GeoDistrict(state_id=state.id, code="HYD", name="Hyderabad")
    session.add(district)
    session.flush()
    found: dict[str, dict[str, UUID]] = {}
    for code, city_name, pin, area in (
        ("HYD", "Hyderabad", "500001", "Abids"),
        ("SEC", "Secunderabad", "500003", "Kavadiguda"),
    ):
        city = GeoCity(district_id=district.id, code=code, name=city_name)
        session.add(city)
        session.flush()
        postal = GeoPostalCode(city_id=city.id, postal_code=pin)
        session.add(postal)
        session.flush()
        locality = GeoLocality(postal_code_id=postal.id, name=area)
        session.add(locality)
        session.flush()
        found[city_name] = {
            "country_id": country.id,
            "state_id": state.id,
            "district_id": district.id,
            "city_id": city.id,
            "postal_code_id": postal.id,
            "locality_id": locality.id,
        }
    session.commit()
    return found


def _vendor(code: str, address: dict[str, object]) -> VendorCreate:
    """Build a supplier named like every other, at the given address."""
    return VendorCreate.model_validate(
        {
            "code": code,
            "name": "Sri Balaji Agencies",
            "display_name": "Sri Balaji Agencies",
            "status": "ACTIVE",
            "addresses": [
                {
                    "address_type": "BILLING",
                    "address_line1": "Main Road",
                    "is_primary": True,
                    **address,
                }
            ],
        }
    )


def _list(scope: ResolvedFirmScope, session: Session) -> list[tuple[str, str, str]]:
    """Read the supplier list as (code, city, area) of each first address."""
    listed = list_vendors(
        scope=scope,
        page=1,
        page_size=50,
        search=None,
        sort_by="code",
        sort_direction="asc",
        status_value=None,
        category_id=None,
        type_id=None,
        business_profile_id=None,
        city_id=None,
        state_id=None,
        country_id=None,
        firm_id=None,
        created_from=None,
        created_to=None,
        include_deleted=False,
        db=session,
    )
    return [
        (row.code, row.addresses[0].city or "", row.addresses[0].area or "")
        for row in listed.data
    ]


def test_two_suppliers_of_one_name_are_told_apart_by_place() -> None:
    """The list and the single read both name the city and the area."""
    session = sessionmaker(bind=_engine(), expire_on_commit=False)()
    scope = _scope(session)
    places = _places(session)
    first = create_vendor(_vendor("SUP-1", places["Hyderabad"]), scope, session)
    create_vendor(_vendor("SUP-2", places["Secunderabad"]), scope, session)
    create_vendor(_vendor("SUP-3", {}), scope, session)

    assert first.data.addresses[0].city == "Hyderabad"
    assert first.data.addresses[0].area == "Abids"
    assert _list(scope, session) == [
        ("SUP-1", "Hyderabad", "Abids"),
        ("SUP-2", "Secunderabad", "Kavadiguda"),
        ("SUP-3", "", ""),
    ]
    one = get_vendor(first.data.id, scope, Response(), False, session)
    assert (one.data.addresses[0].city, one.data.addresses[0].area) == (
        "Hyderabad",
        "Abids",
    )


def test_the_names_cost_two_reads_however_long_the_page() -> None:
    """Naming the places does not grow with the number of suppliers."""
    engine = _engine()
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    scope = _scope(session)
    places = _places(session)
    for number in range(6):
        city = "Hyderabad" if number % 2 else "Secunderabad"
        create_vendor(_vendor(f"SUP-{number}", places[city]), scope, session)
    rows, _ = VendorService(session).list_vendors(
        firm_scope=scope.firm_id,
        filters=VendorListFilters(),
        page=1,
        page_size=50,
        search=None,
        sort_by="code",
        descending=False,
    )
    for row in rows:
        assert row.addresses

    statements: list[str] = []

    def record(*args: object) -> None:
        """Keep each statement the engine is asked to run."""
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", record)
    try:
        named = VendorService(session).address_places(list(rows))
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert len(statements) == 2
    assert len(named) == 6
    assert set(named.values()) == {
        ("Hyderabad", "Abids"),
        ("Secunderabad", "Kavadiguda"),
    }


def test_the_names_cannot_be_written() -> None:
    """An address is written by its ids; a name sent with it is refused."""
    with pytest.raises(ValueError, match="city"):
        VendorAddressInput.model_validate(
            {"address_type": "BILLING", "address_line1": "x", "city": "Hyderabad"}
        )
