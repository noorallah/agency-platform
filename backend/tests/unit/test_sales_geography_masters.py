"""Editing and retiring the shared geography masters.

Countries, states, districts, cities, postal codes and localities are the
reference data every firm's addresses and routes hang off. They could be
listed and created and nothing else -- no update, no delete, and no audit row
even on create, which for reference data every firm reads is the one change
people most need to trace afterwards.

The delete guard is the part with teeth. Every foreign key into these tables is
``ondelete="RESTRICT"``, which reads like the guard is already in place; it is
not, because these rows are soft-deleted and a soft delete never reaches the
database's referential check. A "deleted" city stays wired to every branch that
names it and simply disappears from the list.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.firms.models import Firm
from app.sales.schemas.territory import (
    GeoCityWrite,
    GeoCountryWrite,
    GeoDistrictWrite,
    GeoLocalityWrite,
    GeoPostalCodeWrite,
    GeoStateWrite,
)
from app.sales.services import SalesTerritoryService


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Geo Firm",
        code="GEO01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _chain(service: SalesTerritoryService, actor: UUID) -> dict[str, UUID]:
    """Build one country > state > district > city > postal code > locality."""
    country = service.create_country(
        GeoCountryWrite(code="IN", name="India"), actor_id=actor
    )
    state = service.create_state(
        GeoStateWrite(code="TN", name="Tamil Nadu", country_id=country.id),
        actor_id=actor,
    )
    district = service.create_district(
        GeoDistrictWrite(code="CHN", name="Chennai", state_id=state.id),
        actor_id=actor,
    )
    city = service.create_city(
        GeoCityWrite(code="CHE", name="Chennai City", district_id=district.id),
        actor_id=actor,
    )
    postal = service.create_postal_code(
        GeoPostalCodeWrite(city_id=city.id, postal_code="600001"), actor_id=actor
    )
    locality = service.create_locality(
        GeoLocalityWrite(postal_code_id=postal.id, name="Parrys"), actor_id=actor
    )
    return {
        "country": country.id,
        "state": state.id,
        "district": district.id,
        "city": city.id,
        "postal": postal.id,
        "locality": locality.id,
    }


def test_every_level_can_be_renamed() -> None:
    session = _session_factory()()
    actor = uuid4()
    service = SalesTerritoryService(session)
    ids = _chain(service, actor)

    assert (
        service.update_country(
            ids["country"],
            GeoCountryWrite(code="IN", name="Bharat"),
            actor_id=actor,
        ).name
        == "Bharat"
    )
    assert (
        service.update_state(
            ids["state"],
            GeoStateWrite(code="TN", name="Tamilnadu", country_id=ids["country"]),
            actor_id=actor,
        ).name
        == "Tamilnadu"
    )
    assert (
        service.update_district(
            ids["district"],
            GeoDistrictWrite(code="CHN", name="Chennai North", state_id=ids["state"]),
            actor_id=actor,
        ).name
        == "Chennai North"
    )
    assert (
        service.update_city(
            ids["city"],
            GeoCityWrite(code="CHE", name="Chennai", district_id=ids["district"]),
            actor_id=actor,
        ).name
        == "Chennai"
    )
    assert (
        service.update_postal_code(
            ids["postal"],
            GeoPostalCodeWrite(city_id=ids["city"], postal_code="600002"),
            actor_id=actor,
        ).postal_code
        == "600002"
    )
    assert (
        service.update_locality(
            ids["locality"],
            GeoLocalityWrite(postal_code_id=ids["postal"], name="Parrys Corner"),
            actor_id=actor,
        ).name
        == "Parrys Corner"
    )


def test_a_level_with_children_cannot_be_retired() -> None:
    """The guard the RESTRICT foreign keys look like they provide and do not."""
    session = _session_factory()()
    actor = uuid4()
    service = SalesTerritoryService(session)
    ids = _chain(service, actor)

    for delete, label in (
        (service.delete_country, "country"),
        (service.delete_state, "state"),
        (service.delete_district, "district"),
        (service.delete_city, "city"),
        (service.delete_postal_code, "postal code"),
    ):
        with pytest.raises(ConflictError, match="still use this"):
            delete(ids[_key_for(label)], actor_id=actor)


def _key_for(label: str) -> str:
    return {
        "country": "country",
        "state": "state",
        "district": "district",
        "city": "city",
        "postal code": "postal",
    }[label]


def test_a_leaf_with_nothing_under_it_retires_and_leaves_the_list() -> None:
    session = _session_factory()()
    actor = uuid4()
    service = SalesTerritoryService(session)
    ids = _chain(service, actor)

    service.delete_locality(ids["locality"], actor_id=actor)

    assert service.list_localities(postal_code_id=ids["postal"]) == []
    # The postal code above it becomes deletable once its only child is gone.
    service.delete_postal_code(ids["postal"], actor_id=actor)
    assert service.list_postal_codes(city_id=ids["city"]) == []


def test_a_city_a_branch_still_names_cannot_be_retired() -> None:
    """A reference from outside geography counts too, not only a child level."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = SalesTerritoryService(session)
    ids = _chain(service, actor)
    service.delete_locality(ids["locality"], actor_id=actor)
    service.delete_postal_code(ids["postal"], actor_id=actor)
    session.add(
        Branch(
            firm_id=firm.id,
            code="BR-001",
            name="Branch",
            display_name="Branch",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
            city_id=ids["city"],
        )
    )
    session.commit()

    with pytest.raises(ConflictError, match="still use this city"):
        service.delete_city(ids["city"], actor_id=actor)


def test_a_code_stays_unique_among_live_rows() -> None:
    session = _session_factory()()
    actor = uuid4()
    service = SalesTerritoryService(session)
    first = service.create_country(
        GeoCountryWrite(code="IN", name="India"), actor_id=actor
    )
    second = service.create_country(
        GeoCountryWrite(code="LK", name="Sri Lanka"), actor_id=actor
    )

    with pytest.raises(ConflictError, match="already uses the code"):
        service.update_country(
            second.id, GeoCountryWrite(code="IN", name="Sri Lanka"), actor_id=actor
        )

    # Retiring the first releases its code.
    service.delete_country(first.id, actor_id=actor)
    renamed = service.update_country(
        second.id, GeoCountryWrite(code="IN", name="Sri Lanka"), actor_id=actor
    )
    assert renamed.code == "IN"


def test_a_missing_row_is_not_found_rather_than_a_crash() -> None:
    session = _session_factory()()
    actor = uuid4()
    service = SalesTerritoryService(session)

    with pytest.raises(ResourceNotFoundError, match="Country not found."):
        service.update_country(
            uuid4(), GeoCountryWrite(code="XX", name="Nowhere"), actor_id=actor
        )


def test_changing_geography_leaves_an_audit_trail() -> None:
    """Reference data every firm reads: a change to it has to be traceable."""
    session = _session_factory()()
    actor = uuid4()
    service = SalesTerritoryService(session)
    country = service.create_country(
        GeoCountryWrite(code="IN", name="India"), actor_id=actor
    )
    service.update_country(
        country.id, GeoCountryWrite(code="IN", name="Bharat"), actor_id=actor
    )
    service.delete_country(country.id, actor_id=actor)

    actions = [
        row.action
        for row in session.scalars(
            select(AuditLog).where(AuditLog.entity_id == country.id)
        )
    ]
    assert "sales_territory.geo.country.updated" in actions
    assert "sales_territory.geo.country.deleted" in actions
