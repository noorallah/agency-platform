"""UOM and packaging framework service tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.batch_serial.models.batch_serial  # noqa: F401
import app.identity.models.identity  # noqa: F401
import app.inventory.models.inventory  # noqa: F401
import app.uom.models.uom  # noqa: F401
from app.branches.models import branch_warehouse as _branch_models  # noqa: F401
from app.business.models import framework as _business_models  # noqa: F401
from app.business.system_seed import seed_business_profiles
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import customer as _customer_models  # noqa: F401
from app.firms.models import Firm
from app.products.models import Product
from app.sales.models import territory as _sales_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import (
    BusinessProfileUomDefault,
    ConversionRule,
    IndustryTemplate,
    PackagingType,
    Uom,
    UomGroup,
)
from app.uom.schemas import (
    ConversionRequest,
    ConversionRuleCreate,
    ConversionRuleUpdate,
    PackagingLevelCreate,
    PackagingTypeCreate,
    ProductUomConfigUpsert,
    UomCreate,
)
from app.uom.services import UomService
from app.uom.system_seed import seed_uom_reference_data
from app.vendors.models import vendor as _vendor_models  # noqa: F401


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str = "UOMF") -> Firm:
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


def _product(session: Session, firm_id: UUID, code: str = "SKU-UOM-001") -> Product:
    actor_id = uuid4()
    row = Product(
        firm_id=firm_id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(row)
    session.commit()
    return row


def test_uom_crud_and_conversion() -> None:
    """Units are normalised on create and a rule converts a quantity."""
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session)

    piece = service.create_uom(
        UomCreate(code="piece", name="Piece", symbol="pc"), actor_id=actor_id
    )
    box = service.create_uom(UomCreate(code="box", name="Box"), actor_id=actor_id)
    assert piece.code == "PIECE"
    assert box.code == "BOX"

    rule = service.create_conversion_rule(
        ConversionRuleCreate(
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=Decimal("12"),
            effective_from=date(2026, 1, 1),
            version=1,
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    assert rule.version_number == 1

    converted = service.convert_quantity(
        ConversionRequest(
            quantity=Decimal("2"),
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_date=date(2026, 8, 2),
        ),
        firm_scope=firm.id,
    )
    assert converted.converted_quantity == Decimal("24.0000")


def test_product_config_and_packaging_levels() -> None:
    """A product carries a unit configuration and a packaging hierarchy."""
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session)
    product = _product(session, firm.id)

    piece = service.create_uom(UomCreate(code="each", name="Each"), actor_id=actor_id)
    box = service.create_uom(UomCreate(code="carton", name="Carton"), actor_id=actor_id)
    packaging = service.create_packaging_type(
        PackagingTypeCreate(code="BOX", name="Box", status="ACTIVE"),
        actor_id=actor_id,
    )

    config = service.upsert_product_config(
        firm_scope=firm.id,
        product_id=product.id,
        data=ProductUomConfigUpsert(
            base_uom_id=piece.id,
            inventory_uom_id=piece.id,
            purchase_uom_id=box.id,
            sales_uom_id=piece.id,
            allow_fraction=False,
            allow_decimal=True,
            weight=Decimal("0.010"),
        ),
        actor_id=actor_id,
    )
    assert config.base_uom_id == piece.id
    assert config.purchase_uom_id == box.id

    level = service.create_packaging_level(
        firm_scope=firm.id,
        product_id=product.id,
        data=PackagingLevelCreate(
            packaging_type_id=packaging.id,
            uom_id=box.id,
            level_name="Box",
            conversion_to_base_factor=Decimal("10"),
            barcode="123456",
            display_order=1,
        ),
        actor_id=actor_id,
    )
    assert level.conversion_to_base_factor == Decimal("10")
    assert level.barcode == "123456"


def test_conversion_rule_is_firm_scoped() -> None:
    """One firm's conversion rule is invisible to another firm."""
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm_a = _firm(session, "UOMA")
    firm_b = _firm(session, "UOMB")

    piece = service.create_uom(UomCreate(code="piece", name="Piece"), actor_id=actor_id)
    box = service.create_uom(UomCreate(code="box", name="Box"), actor_id=actor_id)
    service.create_conversion_rule(
        ConversionRuleCreate(
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=Decimal("12"),
            effective_from=date(2026, 1, 1),
            version=1,
        ),
        firm_scope=firm_a.id,
        actor_id=actor_id,
    )

    with pytest.raises(ValidationError, match="No active conversion rule"):
        service.convert_quantity(
            ConversionRequest(
                quantity=Decimal("1"),
                from_uom_id=box.id,
                to_uom_id=piece.id,
                conversion_date=date(2026, 8, 2),
            ),
            firm_scope=firm_b.id,
        )


def test_delete_conversion_rule_records_audit_entry() -> None:
    """Retiring a rule leaves an audit entry against the firm."""
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session, "UOMC")

    piece = service.create_uom(UomCreate(code="piece", name="Piece"), actor_id=actor_id)
    box = service.create_uom(UomCreate(code="box", name="Box"), actor_id=actor_id)
    rule = service.create_conversion_rule(
        ConversionRuleCreate(
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=Decimal("8"),
            effective_from=date(2026, 1, 1),
            version=1,
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    service.delete_conversion_rule(rule.id, firm_scope=firm.id, actor_id=actor_id)

    audit = session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == rule.id, AuditLog.action == "uom.conversion.deleted"
        )
    )
    assert audit is not None
    assert audit.firm_id == firm.id


def test_seed_uom_reference_data_prefills_catalogs_and_profile_defaults() -> None:
    """The baseline seed fills the catalogues every profile expects."""
    session = _session_factory()()

    seed_business_profiles(session)
    seed_uom_reference_data(session)
    seed_uom_reference_data(session)
    session.commit()

    uom_codes = {
        row.code
        for row in session.scalars(select(Uom).where(Uom.is_deleted.is_(False))).all()
    }
    group_codes = {
        row.code
        for row in session.scalars(
            select(UomGroup).where(UomGroup.is_deleted.is_(False))
        ).all()
    }
    packaging_codes = {
        row.code
        for row in session.scalars(
            select(PackagingType).where(PackagingType.is_deleted.is_(False))
        ).all()
    }
    template_codes = {
        row.code
        for row in session.scalars(
            select(IndustryTemplate).where(IndustryTemplate.is_deleted.is_(False))
        ).all()
    }
    defaults = session.scalars(
        select(BusinessProfileUomDefault).where(
            BusinessProfileUomDefault.firm_id.is_(None),
            BusinessProfileUomDefault.is_deleted.is_(False),
        )
    ).all()

    assert {"UNIT", "STRIP", "BOX", "CARTON", "KG", "L"}.issubset(uom_codes)
    assert {"DIST_COUNT", "PHARMA_PACK", "FOOD_PACK"}.issubset(group_codes)
    assert {"UNIT", "BOX", "CARTON", "PALLET"}.issubset(packaging_codes)
    assert {
        "AGENCY_DISTRIBUTION",
        "PHARMA_DISTRIBUTION",
        "FOOD_DISTRIBUTION",
        "WHOLESALE_DISTRIBUTION",
    }.issubset(template_codes)
    assert len(defaults) >= 5


def _rule_setup(
    session: Session, service: UomService, actor_id: UUID, firm: Firm
) -> tuple[Uom, Uom]:
    """Create the unit pair a conversion test needs."""
    box = service.create_uom(UomCreate(code="box", name="Box"), actor_id=actor_id)
    piece = service.create_uom(UomCreate(code="piece", name="Piece"), actor_id=actor_id)
    return box, piece


def test_editing_a_rule_does_not_move_its_published_version() -> None:
    """The rule's version is what documents record to identify the factor used.

    The business column was named ``version``, which is the name BaseEntity
    gives the mapper's optimistic-concurrency counter, so the two were one
    column: editing a rule's reason moved it from version 1 to version 2 and
    left every document that recorded version 1 pointing at nothing.
    """
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session)
    box, piece = _rule_setup(session, service, actor_id, firm)
    rule = service.create_conversion_rule(
        ConversionRuleCreate(
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=Decimal("12"),
            effective_from=date(2026, 1, 1),
            version=1,
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    counter_before = rule.version

    service.update_conversion_rule(
        rule.id,
        ConversionRuleUpdate(reason="corrected the note"),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    session.expire_all()
    stored = session.get(ConversionRule, rule.id)

    assert stored.version_number == 1
    # The counter still moves; that is what protects a concurrent write.
    assert stored.version > counter_before


def test_conversion_applies_the_configured_rounding_mode() -> None:
    """The rule stores a rounding mode and the conversion always rounded up."""
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session)
    box, piece = _rule_setup(session, service, actor_id, firm)
    service.create_conversion_rule(
        ConversionRuleCreate(
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=Decimal("1"),
            rounding_mode="DOWN",
            precision_scale=0,
            effective_from=date(2026, 1, 1),
            version=1,
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    converted = service.convert_quantity(
        ConversionRequest(
            quantity=Decimal("2.5"),
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_date=date(2026, 8, 2),
        ),
        firm_scope=firm.id,
    )
    assert converted.converted_quantity == Decimal("2")


def test_an_unusable_rounding_mode_is_refused() -> None:
    """A mode the conversion cannot apply must not be storable."""
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session)
    box, piece = _rule_setup(session, service, actor_id, firm)

    with pytest.raises(ValidationError):
        service.create_conversion_rule(
            ConversionRuleCreate(
                from_uom_id=box.id,
                to_uom_id=piece.id,
                conversion_factor=Decimal("1"),
                rounding_mode="NEAREST_ISH",
                effective_from=date(2026, 1, 1),
                version=1,
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
        )


def test_a_unit_in_use_cannot_be_deleted() -> None:
    """The catalogue has no firm_id, so a delete reaches every firm in the store.

    Nothing checked whether anything still pointed at the unit, so one firm
    could take a unit out from under another firm's conversion rules.
    """
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session)
    box, piece = _rule_setup(session, service, actor_id, firm)
    spare = service.create_uom(
        UomCreate(code="pallet", name="Pallet"), actor_id=actor_id
    )
    service.create_conversion_rule(
        ConversionRuleCreate(
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=Decimal("12"),
            effective_from=date(2026, 1, 1),
            version=1,
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    with pytest.raises(ValidationError):
        service.delete_uom(box.id, actor_id=actor_id)
    with pytest.raises(ValidationError):
        service.delete_uom(piece.id, actor_id=actor_id)

    # A unit nothing references is still removable.
    service.delete_uom(spare.id, actor_id=actor_id)
    assert session.get(Uom, spare.id).is_deleted is True


def test_a_packaging_type_in_use_cannot_be_deleted() -> None:
    """A packaging level names its type; removing the type orphans the level."""
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session)
    product = _product(session, firm.id)
    piece = service.create_uom(UomCreate(code="each", name="Each"), actor_id=actor_id)
    packaging = service.create_packaging_type(
        PackagingTypeCreate(code="BOX", name="Box", status="ACTIVE"),
        actor_id=actor_id,
    )
    service.create_packaging_level(
        firm_scope=firm.id,
        product_id=product.id,
        data=PackagingLevelCreate(
            level_name="Box of 10",
            packaging_type_id=packaging.id,
            uom_id=piece.id,
            conversion_to_base_factor=Decimal("10"),
        ),
        actor_id=actor_id,
    )

    with pytest.raises(ValidationError):
        service.delete_packaging_type(packaging.id, actor_id=actor_id)
