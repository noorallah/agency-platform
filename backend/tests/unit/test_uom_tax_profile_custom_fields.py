"""Custom fields reach units of measure and tax profiles, on the API.

The last two entity types. A unit is shared by every firm in the store, so
its values are the calling firm's own and a read names the firm -- one
firm's values must never be handed to another. A tax profile is per firm
like the rest. Neither desktop form carries the section yet; the API is
what makes the value table reachable at all.
"""

# ruff: noqa: D101,D102,D103

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeEntityType,
)
from app.business.schemas import AttributeValueInput
from app.core.database.base import Base
from app.firms.models import Firm
from app.sales.models import GeoCountry
from app.tax.api.router import _profile_response
from app.tax.schemas import TaxProfileWrite, TaxSystemWrite
from app.tax.services import TaxFrameworkService
from app.uom.api.router import _uom_response
from app.uom.schemas import UomCreate, UomUpdate
from app.uom.services import UomService

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str = "ACME") -> Firm:
    firm = Firm(
        name=code,
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _definition(
    session: Session, code: str, entity_type: AttributeEntityType
) -> AttributeDefinition:
    row = AttributeDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        entity_type=entity_type.value,
        data_type=AttributeDataType.TEXT.value,
    )
    session.add(row)
    session.commit()
    return row


def test_a_units_custom_fields_are_the_calling_firms_own() -> None:
    session = _session()
    ours = _firm(session, "ACME")
    theirs = _firm(session, "OTHER")
    pack = _definition(session, "PACK_NOTE", AttributeEntityType.UOM)
    service = UomService(session)

    unit = service.create_uom(
        UomCreate(
            code="CRATE",
            name="Crate",
            attributes=[
                AttributeValueInput(attribute_definition_id=pack.id, value="12 x 1L")
            ],
        ),
        actor_id=_ACTOR,
        firm_id=ours.id,
    )

    assert _uom_response(service, unit, ours.id).attributes[0].value_text == "12 x 1L"
    # The same shared unit, read by another firm: nothing.
    assert _uom_response(service, unit, theirs.id).attributes == []

    # An update that says nothing about them keeps them; a list replaces.
    service.update_uom(
        unit.id, UomUpdate(name="Crate (12)"), actor_id=_ACTOR, firm_id=ours.id
    )
    assert len(_uom_response(service, unit, ours.id).attributes) == 1
    service.update_uom(
        unit.id, UomUpdate(attributes=[]), actor_id=_ACTOR, firm_id=ours.id
    )
    assert _uom_response(service, unit, ours.id).attributes == []


def test_a_tax_profile_carries_a_custom_field() -> None:
    session = _session()
    firm = _firm(session)
    country = GeoCountry(code="IN", name="India", iso2="IN", iso3="IND")
    session.add(country)
    session.commit()
    hsn_note = _definition(session, "FILING_NOTE", AttributeEntityType.TAX_PROFILE)
    service = TaxFrameworkService(session)
    system = service.create_system(
        TaxSystemWrite(country_id=country.id, code="GST", name="GST"),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    profile = service.create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            code="GST_18",
            name="GST 18%",
            attributes=[
                AttributeValueInput(
                    attribute_definition_id=hsn_note.id, value="Schedule III"
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    assert _profile_response(profile, session).attributes[0].value_text == (
        "Schedule III"
    )

    # A replace that omits them (None) keeps them.
    service.update_profile(
        profile.id,
        TaxProfileWrite(tax_system_id=system.id, code="GST_18", name="GST 18% (r)"),
        firm_scope=firm.id,
        actor_id=_ACTOR,
    )
    assert len(_profile_response(profile, session).attributes) == 1
