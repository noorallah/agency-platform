"""Loading districts, towns, PIN codes and localities from India Post (B6).

Run against the real pack shipped with the server, on its two smallest
states: Lakshadweep (ten offices, one district) and Puducherry (95 offices,
four districts).
"""

# ruff: noqa: D103

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.sales.models import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoPostalCode,
    GeoState,
)
from app.sales.services.places_pack import (
    PlacesPackService,
    district_name,
    place_name,
)

ACTOR = uuid4()


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    india = GeoCountry(code="IN", name="India")
    session.add(india)
    session.flush()
    for code, name in (
        ("LD", "Lakshadweep"),
        ("PY", "Puducherry"),
        ("KA", "Karnataka"),
        ("TN", "Tamil Nadu"),
    ):
        session.add(GeoState(country_id=india.id, code=code, name=name))
    session.commit()
    return session


def _state(session: Session, code: str) -> UUID:
    return session.scalars(select(GeoState.id).where(GeoState.code == code)).one()


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_office_and_district_names_read_as_an_address() -> None:
    assert place_name("Kothimir B.O") == "Kothimir"
    assert place_name("Kavaratti H.O") == "Kavaratti"
    assert place_name("Androth S.O") == "Androth"
    assert district_name("KUMURAM BHEEM ASIFABAD") == "Kumuram Bheem Asifabad"


def test_the_pack_offers_every_state_with_the_south_ticked() -> None:
    session = _session()

    states = {item["code"]: item for item in PlacesPackService(session).summary()}

    assert len(states) == 36
    assert states["LD"]["available"] and states["LD"]["post_offices"] == 10
    assert states["TN"]["default"] and not states["MH"]["default"]
    # This store holds only three states; the rest cannot be loaded here.
    assert not states["MH"]["available"]


def test_a_state_loads_district_town_pin_and_locality() -> None:
    session = _session()

    outcome = PlacesPackService(session).load(["LD"], actor_id=ACTOR)
    session.commit()

    result = outcome.states[0]
    assert (result.districts, result.postal_codes, result.localities) == (1, 9, 10)
    district = session.scalars(select(GeoDistrict)).one()
    assert district.name == "Lakshadweep District"
    assert district.state_id == _state(session, "LD")
    # A PIN's town is its delivering office; a village branch under the same
    # PIN is a locality of it, not a town of its own.
    pin = session.scalars(
        select(GeoPostalCode).where(GeoPostalCode.postal_code == "682554")
    ).one()
    town = session.get(GeoCity, pin.city_id)
    assert town is not None and town.name == "Chetlat"
    localities = set(
        session.scalars(
            select(GeoLocality.name).where(GeoLocality.postal_code_id == pin.id)
        )
    )
    assert localities == {"Bithra", "Chetlat"}
    assert session.scalars(
        select(AuditLog.action).where(
            AuditLog.action == "sales_territory.geo.places_loaded"
        )
    ).one()


def test_loading_twice_adds_nothing_twice() -> None:
    session = _session()
    service = PlacesPackService(session)
    service.load(["PY"], actor_id=ACTOR)
    session.commit()
    before = [
        _count(session, model)
        for model in (GeoDistrict, GeoCity, GeoPostalCode, GeoLocality)
    ]

    again = service.load(["PY"], actor_id=ACTOR).states[0]
    session.commit()

    assert (again.districts, again.cities, again.postal_codes, again.localities) == (
        0,
        0,
        0,
        0,
    )
    assert again.skipped == before[2]
    assert [
        _count(session, model)
        for model in (GeoDistrict, GeoCity, GeoPostalCode, GeoLocality)
    ] == before


def test_a_district_the_firm_typed_is_kept_and_filled() -> None:
    session = _session()
    typed = GeoDistrict(
        state_id=_state(session, "LD"), code="LKD", name="Lakshadweep district"
    )
    session.add(typed)
    session.commit()

    PlacesPackService(session).load(["LD"], actor_id=ACTOR)
    session.commit()

    district = session.scalars(select(GeoDistrict)).one()
    assert (district.id, district.code, district.name) == (
        typed.id,
        "LKD",
        "Lakshadweep district",
    )
    assert session.scalars(select(func.count()).select_from(GeoCity)).one() == 9


def test_a_deleted_district_is_not_brought_back() -> None:
    session = _session()
    session.add(
        GeoDistrict(
            state_id=_state(session, "LD"),
            code="LKD",
            name="Lakshadweep District",
            is_deleted=True,
        )
    )
    session.commit()

    result = PlacesPackService(session).load(["LD"], actor_id=ACTOR).states[0]

    assert (result.districts, result.postal_codes) == (0, 0)
    assert result.skipped == 1
    assert _count(session, GeoPostalCode) == 0


def test_a_pin_already_held_is_left_where_it_is() -> None:
    session = _session()
    district = GeoDistrict(state_id=_state(session, "KA"), code="X", name="Elsewhere")
    session.add(district)
    session.flush()
    city = GeoCity(district_id=district.id, code="X", name="Typed town")
    session.add(city)
    session.flush()
    session.add(GeoPostalCode(city_id=city.id, postal_code="682555"))
    session.commit()

    result = PlacesPackService(session).load(["LD"], actor_id=ACTOR).states[0]

    assert result.postal_codes == 8
    assert (
        session.scalars(
            select(func.count()).where(GeoPostalCode.postal_code == "682555")
        ).one()
        == 1
    )


def test_an_unknown_or_missing_state_is_refused_or_reported() -> None:
    session = _session()
    service = PlacesPackService(session)

    with pytest.raises(ValidationError, match="Not in the places file: ZZ"):
        service.load(["ZZ"], actor_id=ACTOR)
    with pytest.raises(ValidationError, match="at least one state"):
        service.load([" "], actor_id=ACTOR)
    result = service.load(["MH"], actor_id=ACTOR).states[0]
    assert result.note is not None and result.localities == 0


def test_a_pin_across_a_border_keeps_both_sides_offices() -> None:
    """A PIN in two states gets the second state's offices as localities."""
    session = _session()

    outcome = PlacesPackService(session).load(["TN", "PY"], actor_id=ACTOR)

    puducherry = outcome.states[1]
    assert puducherry.skipped == 0
    assert puducherry.localities == 95
    assert puducherry.postal_codes < 33


def test_a_new_store_is_given_the_southern_states() -> None:
    """What migration 20261002_0231 runs on every firm store (owner, B6)."""
    from app.sales.services.places_pack import initialise_store

    session = _session()

    outcome = initialise_store(session)
    session.commit()

    assert outcome is not None
    # This store holds LD, PY, KA and TN of the seven; the rest are skipped.
    assert [item.code for item in outcome.states] == ["KA", "TN", "PY", "LD"]
    assert _count(session, GeoPostalCode) > 3000
    # The audit row names no actor: nobody pressed anything.
    assert (
        session.scalars(
            select(AuditLog.actor_id).where(
                AuditLog.action == "sales_territory.geo.places_loaded"
            )
        ).one()
        is None
    )
    again = initialise_store(session)
    assert again is not None
    assert sum(item.localities for item in again.states) == 0
