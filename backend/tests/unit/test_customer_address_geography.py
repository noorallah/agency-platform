"""A customer address can name a place from the shared masters.

``customer_addresses`` held city, area, district, state, country and postal
code as plain strings with no link to the geography masters, so "Parrys" and
"Parry's Corner" never grouped and a pin-code search was a string match. It is
also why there is nowhere to hang a coordinate: a latitude on a free-text
address gives a map full of points nobody can group by locality.

The text stays -- it is NOT NULL and every report reads it. What changes is
where it comes from: wherever a key is sent the service derives the text from
that master row, so the two cannot drift apart. An address that sends no keys
keeps the text it was given, which is what every client written before these
columns existed does.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.schemas import (
    CustomerAddressInput,
    CustomerCreate,
    CustomerUpdate,
)
from app.customers.services import CustomerService
from app.firms.models import Firm
from app.sales.models.territory import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoPostalCode,
    GeoState,
)


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
        name="Address Firm",
        code="ADR01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


class _Places:
    """One full ladder, plus a second state to test parentage against."""

    def __init__(self, session: Session, actor: UUID) -> None:
        """Seed a country down to a locality."""
        self.country = GeoCountry(
            code="IND", name="India", iso2="IN", created_by=actor, updated_by=actor
        )
        session.add(self.country)
        session.flush()
        self.state = GeoState(
            country_id=self.country.id,
            code="TN",
            name="Tamil Nadu",
            created_by=actor,
            updated_by=actor,
        )
        self.other_state = GeoState(
            country_id=self.country.id,
            code="KL",
            name="Kerala",
            created_by=actor,
            updated_by=actor,
        )
        session.add_all([self.state, self.other_state])
        session.flush()
        self.district = GeoDistrict(
            state_id=self.state.id,
            code="CHN",
            name="Chennai",
            created_by=actor,
            updated_by=actor,
        )
        session.add(self.district)
        session.flush()
        self.city = GeoCity(
            district_id=self.district.id,
            code="CHN",
            name="Chennai",
            created_by=actor,
            updated_by=actor,
        )
        session.add(self.city)
        session.flush()
        self.postal = GeoPostalCode(
            city_id=self.city.id,
            postal_code="600001",
            created_by=actor,
            updated_by=actor,
        )
        session.add(self.postal)
        session.flush()
        self.locality = GeoLocality(
            postal_code_id=self.postal.id,
            name="Parrys",
            created_by=actor,
            updated_by=actor,
        )
        session.add(self.locality)
        session.commit()


def _address(**overrides: object) -> CustomerAddressInput:
    values: dict[str, object] = {
        "address_type": "BILLING",
        "address_line1": "1 Big Street",
        "city": "typed city",
        "state": "typed state",
        "country": "XX",
        "postal_code": "000000",
    }
    values.update(overrides)
    return CustomerAddressInput.model_validate(values)


def _customer(
    service: CustomerService,
    firm_id: UUID,
    actor: UUID,
    address: CustomerAddressInput,
    code: str = "C001",
) -> UUID:
    customer = service.create(
        CustomerCreate(
            code=code,
            name="Shop One",
            customer_type="BUSINESS",
            currency_code="INR",
            addresses=[address],
        ),
        firm_id=firm_id,
        actor_id=actor,
    )
    return customer.id


def test_the_keys_are_stored_and_the_text_is_derived_from_them() -> None:
    """The point of the change: one truth, and the text follows it."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    places = _Places(session, actor)
    service = CustomerService(session)

    customer_id = _customer(
        service,
        firm.id,
        actor,
        _address(
            country_id=places.country.id,
            state_id=places.state.id,
            district_id=places.district.id,
            city_id=places.city.id,
            postal_code_id=places.postal.id,
            locality_id=places.locality.id,
        ),
    )

    address = service.get(customer_id, firm_scope=firm.id).addresses[0]
    assert address.city_id == places.city.id
    assert address.locality_id == places.locality.id
    # The typed values are replaced by what the masters say, not kept beside
    # them where a report would have to choose.
    assert address.city == "Chennai"
    assert address.state == "Tamil Nadu"
    assert address.country == "IN"
    assert address.postal_code == "600001"
    assert address.area == "Parrys"


def test_an_address_with_no_keys_keeps_the_text_it_was_given() -> None:
    """Every client written before these columns existed sends no keys."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    _Places(session, actor)
    service = CustomerService(session)

    customer_id = _customer(
        service, firm.id, actor, _address(city="Madurai", state="TN", country="IN")
    )

    address = service.get(customer_id, firm_scope=firm.id).addresses[0]
    assert address.city == "Madurai"
    assert address.city_id is None


def test_a_partial_ladder_only_fills_what_it_names() -> None:
    """A firm may have countries and states and nothing below them."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    places = _Places(session, actor)
    service = CustomerService(session)

    customer_id = _customer(
        service,
        firm.id,
        actor,
        _address(
            country_id=places.country.id,
            state_id=places.state.id,
            city="Hosur",
        ),
    )

    address = service.get(customer_id, firm_scope=firm.id).addresses[0]
    assert address.country == "IN"
    assert address.state == "Tamil Nadu"
    # Untouched: no city was named, so the typed one stands.
    assert address.city == "Hosur"
    assert address.city_id is None


def test_places_that_do_not_belong_together_are_refused() -> None:
    """A district under one state cannot be claimed by another."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    places = _Places(session, actor)
    service = CustomerService(session)

    with pytest.raises(ValidationError):
        _customer(
            service,
            firm.id,
            actor,
            _address(
                country_id=places.country.id,
                state_id=places.other_state.id,
                district_id=places.district.id,
            ),
        )


def test_an_unknown_place_is_refused_by_name() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    _Places(session, actor)
    service = CustomerService(session)

    with pytest.raises(ValidationError):
        _customer(service, firm.id, actor, _address(city_id=uuid4()))


def test_a_retired_place_is_refused() -> None:
    """Soft delete is how a place is retired, and a FK never sees it."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    places = _Places(session, actor)
    places.city.is_deleted = True
    session.commit()
    service = CustomerService(session)

    with pytest.raises(ValidationError):
        _customer(service, firm.id, actor, _address(city_id=places.city.id))


def test_an_edit_can_move_an_address_to_another_place() -> None:
    """The reconcile path applies the keys too, not only create."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    places = _Places(session, actor)
    service = CustomerService(session)
    customer_id = _customer(service, firm.id, actor, _address())

    existing = service.get(customer_id, firm_scope=firm.id).addresses[0]
    updated = service.update(
        customer_id,
        CustomerUpdate(
            code="C001",
            name="Shop One",
            customer_type="BUSINESS",
            currency_code="INR",
            addresses=[
                _address(
                    id=existing.id,
                    country_id=places.country.id,
                    state_id=places.state.id,
                )
            ],
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    address = next(row for row in updated.addresses if not row.is_deleted)
    assert address.id == existing.id
    assert address.state_id == places.state.id
    assert address.state == "Tamil Nadu"
