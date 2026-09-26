"""Configuration changes the audit trail can show (D-CFG-13).

A firm's trail is read by `firm_id`, and most configuration writes either
wrote no row, wrote one with `firm_id` null into the firm's own store, or wrote
one that named the record and not the change -- a conversion factor moved from
1 to 2 with both sides empty, the print template's bank account changed with
only the document type recorded, a customer's custom field overwritten in place
with the old value kept nowhere, and 521 empty preference rows from screens that
changed nothing. Each case below writes, then reads the trail as a person would:
which firm, and what moved.
"""

# ruff: noqa: D103

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from fastapi import Request
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import AttributeDefinition
from app.business.schemas import (
    AttributeDefinitionCreate,
    AttributeDefinitionUpdate,
    BusinessFeatureCreate,
    BusinessProfileCreate,
    FirmBusinessProfileAssign,
)
from app.business.services import (
    AttributeInput,
    AttributeService,
    BusinessProfileFrameworkService,
)
from app.common.audit.models import AuditLog
from app.core.config.settings import Environment, Settings
from app.core.context import STORE_FIRM_SESSION_KEY
from app.core.database.base import Base
from app.core.database.dependencies import get_db
from app.customers.models import Customer, CustomerAttributeValue
from app.document_framework.schemas import (
    DocumentNumberingRuleCreate,
    DocumentNumberingRuleUpdate,
    DocumentPrintTemplateWrite,
    DocumentTypeCreate,
)
from app.document_framework.services import DocumentFrameworkService
from app.document_framework.services.print_template_service import (
    DocumentPrintTemplateService,
)
from app.firms.models import Firm
from app.identity.models import User
from app.identity.schemas.api import UserPreferencesUpdate
from app.identity.services.identity_service import IdentityService
from app.sales.schemas.territory import GeoCountryWrite
from app.sales.services import SalesTerritoryService
from app.uom.schemas.uom import (
    ConversionRuleCreate,
    ConversionRuleUpdate,
    UomCreate,
    UomUpdate,
)
from app.uom.services.uom_service import UomService

ACTOR = uuid4()


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str = "CFG13") -> Firm:
    row = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _firm_store(session: Session, firm: Firm) -> Session:
    """Mark the session the way `get_db` marks a firm's store."""
    session.info[STORE_FIRM_SESSION_KEY] = firm.id
    return session


def _rows(session: Session, action: str) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.action == action)
            .order_by(AuditLog.created_at.asc())
        )
    )


def _data(payload: dict[str, object] | None) -> dict[str, object]:
    """Drop the request metadata `record_audit` adds, if any."""
    return {k: v for k, v in (payload or {}).items() if k != "_meta"}


# ---------------------------------------------------------------------------
# Which firm
# ---------------------------------------------------------------------------


def test_get_db_marks_the_session_with_the_firm_whose_store_it_opened() -> None:
    firm_id = uuid4()
    opened = _session()

    @contextmanager
    def sessions() -> Iterator[Session]:
        yield opened

    manager = SimpleNamespace(sessions=lambda schema: SimpleNamespace(session=sessions))
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/business-framework/attribute-definitions"),
        app=SimpleNamespace(
            state=SimpleNamespace(
                database_provider=SimpleNamespace(
                    manager_for=lambda tenant: manager,
                    schema_for=lambda tenant: "fx_cfg13",
                ),
                tenant_resolver=SimpleNamespace(
                    resolve=lambda req: SimpleNamespace(firm_id=firm_id)
                ),
            )
        ),
    )

    generator = get_db(cast(Request, request))
    session = next(generator)

    assert session.info[STORE_FIRM_SESSION_KEY] == firm_id


def test_a_catalogue_write_lands_on_the_trail_of_the_firm_that_made_it() -> None:
    """The business-framework catalogue has no firm column; its audit does."""
    session = _session()
    firm = _firm(session)
    service = BusinessProfileFrameworkService(_firm_store(session, firm))

    row = service.create_attribute(
        AttributeDefinitionCreate(
            code="COLD_ID", name="Cold chain id", data_type="TEXT"
        ),
        ACTOR,
    )
    service.update_attribute(
        row.id,
        AttributeDefinitionUpdate(
            code="COLD_ID", name="Cold chain number", data_type="TEXT"
        ),
        ACTOR,
    )

    created = _rows(session, "attribute_definition.created")[0]
    updated = _rows(session, "attribute_definition.updated")[0]
    assert created.firm_id == firm.id
    assert _data(created.after_data)["code"] == "COLD_ID"
    assert updated.firm_id == firm.id
    assert _data(updated.before_data) == {"name": "Cold chain id"}
    assert _data(updated.after_data) == {"name": "Cold chain number"}


def test_a_re_save_that_changes_nothing_writes_no_row() -> None:
    session = _session()
    service = BusinessProfileFrameworkService(session)
    row = service.create_attribute(
        AttributeDefinitionCreate(code="GRADE", name="Grade", data_type="TEXT"),
        ACTOR,
    )

    service.update_attribute(
        row.id,
        AttributeDefinitionUpdate(code="GRADE", name="Grade", data_type="TEXT"),
        ACTOR,
    )

    assert _rows(session, "attribute_definition.updated") == []


def test_switching_a_feature_names_the_feature() -> None:
    session = _session()
    service = BusinessProfileFrameworkService(session)
    profile = service.create_profile(
        BusinessProfileCreate(
            code="WHOLESALE", name="Wholesale", industry_type="WHOLESALE"
        ),
        ACTOR,
    )
    barcode = service.create_feature(
        BusinessFeatureCreate(code="BARCODE", name="Barcode"), ACTOR
    )
    batches = service.create_feature(
        BusinessFeatureCreate(code="BATCHES", name="Batches"), ACTOR
    )
    service.set_profile_features(profile.id, [barcode.id], ACTOR)
    service.set_profile_features(profile.id, [batches.id], ACTOR)
    # The same set again is not an event.
    service.set_profile_features(profile.id, [batches.id], ACTOR)

    rows = _rows(session, "business_profile.features.updated")
    assert len(rows) == 2
    assert _data(rows[1].before_data)["features"] == ["BARCODE"]
    assert _data(rows[1].after_data)["enabled"] == ["BATCHES"]
    assert _data(rows[1].after_data)["disabled"] == ["BARCODE"]


def test_a_profile_change_keeps_the_profile_it_replaced() -> None:
    """The row is updated in place; only the trail remembers the old one."""
    session = _session()
    firm = _firm(session)
    service = BusinessProfileFrameworkService(session)
    wholesale = service.create_profile(
        BusinessProfileCreate(
            code="WHOLESALE", name="Wholesale", industry_type="WHOLESALE"
        ),
        ACTOR,
    )
    retail = service.create_profile(
        BusinessProfileCreate(code="RETAIL", name="Retail", industry_type="RETAIL"),
        ACTOR,
    )
    first = service.assign_profile_to_firm(
        firm.id, FirmBusinessProfileAssign(business_profile_id=wholesale.id), ACTOR
    )
    since = first.effective_from
    service.assign_profile_to_firm(
        firm.id, FirmBusinessProfileAssign(business_profile_id=retail.id), ACTOR
    )

    row = _rows(session, "firm_business_profile.updated")[0]
    assert row.firm_id == firm.id
    assert _data(row.before_data)["business_profile_id"] == str(wholesale.id)
    assert _data(row.after_data)["business_profile_id"] == str(retail.id)
    # "On RETAIL since" is no longer the day it first became WHOLESALE.
    assert "effective_from" in _data(row.after_data)
    assert service.get_firm_assignment(firm.id).effective_from != since  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Geography and units
# ---------------------------------------------------------------------------


def test_creating_a_place_is_audited_on_the_firms_trail() -> None:
    session = _session()
    firm = _firm(session)
    service = SalesTerritoryService(_firm_store(session, firm))

    country = service.create_country(
        GeoCountryWrite(code="LK", name="Sri Lanka"), actor_id=ACTOR
    )
    service.update_country(
        country.id, GeoCountryWrite(code="LK", name="Lanka"), actor_id=ACTOR
    )

    created = _rows(session, "sales_territory.geo.country.created")[0]
    updated = _rows(session, "sales_territory.geo.country.updated")[0]
    assert created.firm_id == firm.id
    assert _data(created.after_data)["code"] == "LK"
    assert _data(updated.before_data) == {"name": "Sri Lanka"}
    assert _data(updated.after_data) == {"name": "Lanka"}


def test_a_unit_is_audited_from_creation_to_deletion() -> None:
    session = _session()
    firm = _firm(session)
    service = UomService(_firm_store(session, firm))

    unit = service.create_uom(UomCreate(code="BOX", name="Box"), actor_id=ACTOR)
    service.update_uom(unit.id, UomUpdate(is_decimal_allowed=False), actor_id=ACTOR)
    service.delete_uom(unit.id, actor_id=ACTOR)

    created = _rows(session, "uom.unit.created")[0]
    updated = _rows(session, "uom.unit.updated")[0]
    deleted = _rows(session, "uom.unit.deleted")[0]
    assert {created.firm_id, updated.firm_id, deleted.firm_id} == {firm.id}
    assert _data(updated.before_data) == {"is_decimal_allowed": True}
    assert _data(updated.after_data) == {"is_decimal_allowed": False}
    assert _data(deleted.before_data)["code"] == "BOX"


def test_a_conversion_factor_change_says_from_what_to_what() -> None:
    session = _session()
    firm = _firm(session)
    service = UomService(session)
    pack = service.create_uom(UomCreate(code="PACK", name="Pack"), actor_id=ACTOR)
    kilo = service.create_uom(UomCreate(code="KG", name="Kilogram"), actor_id=ACTOR)
    rule = service.create_conversion_rule(
        ConversionRuleCreate(
            from_uom_id=pack.id,
            to_uom_id=kilo.id,
            conversion_factor=Decimal("1"),
            effective_from=date(2026, 4, 1),
        ),
        firm_scope=firm.id,
        actor_id=ACTOR,
    )

    service.update_conversion_rule(
        rule.id,
        ConversionRuleUpdate(conversion_factor=Decimal("2")),
        firm_scope=firm.id,
        actor_id=ACTOR,
    )

    row = _rows(session, "uom.conversion.updated")[0]
    assert row.firm_id == firm.id
    assert Decimal(str(_data(row.before_data)["conversion_factor"])) == 1
    assert Decimal(str(_data(row.after_data)["conversion_factor"])) == 2


# ---------------------------------------------------------------------------
# Numbering, print settings, custom fields, preferences
# ---------------------------------------------------------------------------


def test_a_numbering_prefix_change_is_recorded_as_one() -> None:
    session = _session()
    firm = _firm(session)
    service = DocumentFrameworkService(session)
    document_type = service.create_type(
        firm.id, DocumentTypeCreate(code="RECEIPT", name="Receipt"), ACTOR
    )
    rule = service.create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=document_type.id,
            code="DEFAULT",
            name="Default",
            prefix="RC",
            include_financial_year=True,
        ),
        ACTOR,
    )

    service.update_numbering_rule(
        firm.id,
        rule.id,
        DocumentNumberingRuleUpdate(
            document_type_id=document_type.id,
            code="DEFAULT",
            name="Default",
            prefix="RX",
        ),
        ACTOR,
    )

    row = _rows(session, "document_numbering_rule.updated")[0]
    assert _data(row.before_data) == {"prefix": "RC"}
    assert _data(row.after_data) == {"prefix": "RX"}


def test_changing_the_bank_account_on_the_bill_is_recorded() -> None:
    """The account customers pay into is the change that must be traceable."""
    session = _session()
    firm = _firm(session)
    service = DocumentPrintTemplateService(session)

    service.set(
        "SALES_INVOICE",
        DocumentPrintTemplateWrite(bank_details="HDFC 111"),
        firm_scope=firm.id,
        actor_id=ACTOR,
    )
    service.set(
        "SALES_INVOICE",
        DocumentPrintTemplateWrite(bank_details="ICICI 222"),
        firm_scope=firm.id,
        actor_id=ACTOR,
    )

    row = _rows(session, "document_print_template.updated")[0]
    assert _data(row.before_data) == {"bank_details": "HDFC 111"}
    assert _data(row.after_data) == {"bank_details": "ICICI 222"}


def test_a_custom_field_change_keeps_the_value_it_replaced() -> None:
    session = _session()
    firm = _firm(session)
    definition = AttributeDefinition(
        code="ROUTE_NOTE",
        name="Route note",
        entity_type="CUSTOMER",
        data_type="TEXT",
    )
    customer = Customer(
        firm_id=firm.id,
        code="C1",
        customer_type="BUSINESS",
        name="Parrys Traders",
        display_name="Parrys Traders",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add_all([definition, customer])
    session.commit()
    service = AttributeService(session)

    for value in ("Alpha", "Beta", "Beta"):
        service.replace_values(
            CustomerAttributeValue,
            customer.id,
            [AttributeInput(attribute_definition_id=definition.id, value=value)],
            firm_id=firm.id,
            actor_id=ACTOR,
        )
        session.commit()

    rows = _rows(session, "customer.attributes.updated")
    # Two changes; the third save resent the same value.
    assert len(rows) == 2
    assert rows[1].entity_id == customer.id
    assert rows[1].firm_id == firm.id
    assert _data(rows[1].before_data) == {"ROUTE_NOTE": "Alpha"}
    assert _data(rows[1].after_data) == {"ROUTE_NOTE": "Beta"}


def test_a_preference_save_that_changes_nothing_writes_nothing() -> None:
    session = _session()
    user = User(email="prefs@cfg13.local", full_name="Prefs User", password_hash="*")
    session.add(user)
    session.commit()
    service = IdentityService(
        session,
        Settings(
            environment=Environment.TESTING,
            bootstrap_admin_password="Test-Bootstrap-Only1!",
        ),
    )
    service.get_user_preferences(user.id)

    service.update_user_preferences(user.id, UserPreferencesUpdate(language="en"))
    service.update_user_preferences(user.id, UserPreferencesUpdate(rows_per_page=50))

    rows = _rows(session, "user_preferences.updated")
    assert len(rows) == 1
    assert _data(rows[0].before_data) == {"rows_per_page": 20}
    assert _data(rows[0].after_data) == {"rows_per_page": 50}


def test_moving_between_screens_is_stored_but_not_audited() -> None:
    """The screen a user is on is remembered, not recorded.

    The desktop saves it with every move, so each click wrote an audit row:
    123,537 of them in one firm's trail by 2026-09-26. The next sign-in still
    opens where they were; a real preference change is still audited.
    """
    session = _session()
    user = User(email="moves@ui.local", full_name="Moves User", password_hash="*")
    session.add(user)
    session.commit()
    service = IdentityService(
        session,
        Settings(
            environment=Environment.TESTING,
            bootstrap_admin_password="Test-Bootstrap-Only1!",
        ),
    )
    for page in ("sales/sales-orders", "masters/customers", "inventory"):
        service.update_user_preferences(
            user.id, UserPreferencesUpdate(default_landing_page=page)
        )

    assert service.get_user_preferences(user.id).default_landing_page == "inventory"
    assert _rows(session, "user_preferences.updated") == []

    service.update_user_preferences(
        user.id,
        UserPreferencesUpdate(default_landing_page="home", rows_per_page=50),
    )
    rows = _rows(session, "user_preferences.updated")
    assert len(rows) == 1, "a real change, even beside a move, is audited"
