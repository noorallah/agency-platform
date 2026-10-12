"""A picker can say where a customer or a supplier is (S3)."""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.party_places import customer_places, place_text, vendor_places
from app.core.database.base import Base
from app.customers.models import Customer, CustomerAddress
from app.firms.models import Firm
from app.sales.models import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoPostalCode,
    GeoState,
)
from app.settlements.api.router import _parties
from app.settlements.services import PaymentService, ReceiptService
from app.vendors.models import Vendor, VendorAddress


def _session() -> Session:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session) -> UUID:
    """Create the owning firm."""
    firm = Firm(
        name="Places Firm",
        code="PLACES",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm.id


def _customer(session: Session, firm_id: UUID, code: str) -> Customer:
    """Create a customer named like every other."""
    actor = uuid4()
    row = Customer(
        firm_id=firm_id,
        code=code,
        customer_type="BUSINESS",
        name="Sri Balaji Medicals",
        display_name="Sri Balaji Medicals",
        currency_code="INR",
        status="ACTIVE",
        created_by=actor,
        updated_by=actor,
    )
    session.add(row)
    session.flush()
    return row


def _address(
    customer: Customer,
    *,
    area: str | None,
    city: str,
    billing: bool = False,
    deleted: bool = False,
) -> CustomerAddress:
    """Build one customer address at the given place."""
    return CustomerAddress(
        customer_id=customer.id,
        address_type="BILLING",
        address_line1="12 Main Road",
        area=area,
        city=city,
        state="Telangana",
        country="IN",
        postal_code="500001",
        is_default_billing=billing,
        is_deleted=deleted,
    )


def _geo(session: Session) -> tuple[UUID, UUID]:
    """Seed one city with one area and return (city id, locality id)."""
    country = GeoCountry(code="IN", name="India")
    session.add(country)
    session.flush()
    state = GeoState(country_id=country.id, code="TS", name="Telangana")
    session.add(state)
    session.flush()
    district = GeoDistrict(state_id=state.id, code="HYD", name="Hyderabad")
    session.add(district)
    session.flush()
    city = GeoCity(district_id=district.id, code="SEC", name="Secunderabad")
    session.add(city)
    session.flush()
    postal = GeoPostalCode(city_id=city.id, postal_code="500003")
    session.add(postal)
    session.flush()
    locality = GeoLocality(postal_code_id=postal.id, name="Kavadiguda")
    session.add(locality)
    session.commit()
    return city.id, locality.id


def _vendor(session: Session, firm_id: UUID, code: str) -> Vendor:
    """Create a supplier named like every other."""
    actor = uuid4()
    row = Vendor(
        firm_id=firm_id,
        code=code,
        name="Sri Balaji Agencies",
        display_name="Sri Balaji Agencies",
        created_by=actor,
        updated_by=actor,
    )
    session.add(row)
    session.flush()
    return row


def test_the_place_is_the_area_and_the_city() -> None:
    """Blank halves are left out and a place is not said twice."""
    assert place_text("Abids", "Hyderabad") == "Abids, Hyderabad"
    assert place_text(None, "Hyderabad") == "Hyderabad"
    assert place_text("  ", " Hyderabad ") == "Hyderabad"
    assert place_text("Guntur", "Guntur") == "Guntur"
    assert place_text(None, None) == ""


def test_a_customer_is_placed_by_the_billing_address() -> None:
    """The default billing address speaks; a removed one never does."""
    session = _session()
    firm_id = _firm(session)
    first = _customer(session, firm_id, "C1")
    second = _customer(session, firm_id, "C2")
    bare = _customer(session, firm_id, "C3")
    session.add_all(
        [
            _address(first, area="Koti", city="Hyderabad"),
            _address(first, area="Abids", city="Hyderabad", billing=True),
            _address(second, area="Old Town", city="Guntur", deleted=True),
            _address(second, area=None, city="Vijayawada"),
        ]
    )
    session.commit()

    places = customer_places(session, [first.id, second.id, bare.id])

    assert places == {first.id: "Abids, Hyderabad", second.id: "Vijayawada"}


def test_a_supplier_is_placed_by_the_primary_address() -> None:
    """The names come from the geography masters behind the ids."""
    session = _session()
    firm_id = _firm(session)
    city_id, locality_id = _geo(session)
    placed = _vendor(session, firm_id, "V1")
    unplaced = _vendor(session, firm_id, "V2")
    session.add_all(
        [
            VendorAddress(
                vendor_id=placed.id, address_type="BILLING", address_line1="x"
            ),
            VendorAddress(
                vendor_id=placed.id,
                address_type="BILLING",
                address_line1="y",
                city_id=city_id,
                locality_id=locality_id,
                is_primary=True,
            ),
            VendorAddress(
                vendor_id=unplaced.id, address_type="BILLING", address_line1="z"
            ),
        ]
    )
    session.commit()

    assert vendor_places(session, [placed.id, unplaced.id]) == {
        placed.id: "Kavadiguda, Secunderabad"
    }


def test_the_money_pickers_carry_the_place() -> None:
    """Receipts name the customer's place and payments the supplier's."""
    session = _session()
    firm_id = _firm(session)
    city_id, locality_id = _geo(session)
    one = _customer(session, firm_id, "C1")
    two = _customer(session, firm_id, "C2")
    vendor = _vendor(session, firm_id, "V1")
    session.add_all(
        [
            _address(one, area="Abids", city="Hyderabad", billing=True),
            VendorAddress(
                vendor_id=vendor.id,
                address_type="BILLING",
                address_line1="y",
                city_id=city_id,
                locality_id=locality_id,
                is_primary=True,
            ),
        ]
    )
    session.commit()

    receipts = _parties(
        ReceiptService(session), firm_id=firm_id, search="", page=1, page_size=50
    ).data
    payments = _parties(
        PaymentService(session), firm_id=firm_id, search="", page=1, page_size=50
    ).data

    assert [(row.code, row.place) for row in receipts] == [
        ("C1", "Abids, Hyderabad"),
        ("C2", None),
    ]
    assert two.name == receipts[0].name == receipts[1].name
    assert [(row.code, row.place) for row in payments] == [
        ("V1", "Kavadiguda, Secunderabad")
    ]
