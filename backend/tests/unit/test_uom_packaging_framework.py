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
from app.business.models import BusinessProfile, FirmBusinessProfile
from app.business.models import framework as _business_models  # noqa: F401
from app.business.system_seed import seed_business_profiles
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
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
    BusinessProfileUomDefaultUpsert,
    ConversionRequest,
    ConversionRuleCreate,
    ConversionRuleUpdate,
    PackagingLevelCreate,
    PackagingTypeCreate,
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


def _new_profile(session: Session, code: str = "GARMENTS") -> BusinessProfile:
    """Create a profile the way the API does: with no defaults of any kind."""
    row = BusinessProfile(
        code=code,
        name=code.title(),
        industry_type=code,
        status="ACTIVE",
        is_default=False,
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
            version_number=1,
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


def test_packaging_levels_carry_their_own_barcode() -> None:
    """A product's packaging hierarchy is per firm and per level."""
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session)
    product = _product(session, firm.id)

    box = service.create_uom(UomCreate(code="carton", name="Carton"), actor_id=actor_id)
    packaging = service.create_packaging_type(
        PackagingTypeCreate(code="BOX", name="Box", status="ACTIVE"),
        actor_id=actor_id,
    )

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


def test_a_unit_a_product_uses_cannot_be_deleted() -> None:
    """The delete guard reads the columns a product actually stores.

    It checked ``product_uom_configs``, a duplicate of these seven columns
    that nothing ever wrote, so the guard passed however many products used
    the unit and deleting it left them pointing at a unit the catalogue no
    longer offered.
    """
    session = _session_factory()()
    service = UomService(session)
    actor_id = uuid4()
    firm = _firm(session, "UOMN")
    strip = service.create_uom(UomCreate(code="strip", name="Strip"), actor_id=actor_id)
    product = _product(session, firm.id, "SKU-UOM-GUARD")
    product.base_uom_id = strip.id
    session.commit()

    with pytest.raises(ValidationError, match="in use and cannot be deleted"):
        service.delete_uom(strip.id, actor_id=actor_id)

    # A unit nothing points at is still deletable.
    spare = service.create_uom(UomCreate(code="spare", name="Spare"), actor_id=actor_id)
    service.delete_uom(spare.id, actor_id=actor_id)
    assert spare.is_deleted is True


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
            version_number=1,
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
            version_number=1,
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
            version_number=1,
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
            version_number=1,
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
                version_number=1,
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
            version_number=1,
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


def test_a_firm_without_an_override_reads_the_profile_wide_default() -> None:
    """The seeded ``firm_id IS NULL`` row is what an industry default means.

    ``get_profile_default`` used to filter on the caller's firm alone, so every
    seeded industry default was unreachable: the endpoint answered ``null`` for
    a profile whose row was sitting in the same store.
    """
    session = _session_factory()()
    seed_business_profiles(session)
    seed_uom_reference_data(session)
    session.commit()
    firm = _firm(session, "UOMD")
    profile_id = session.scalar(
        select(BusinessProfileUomDefault.business_profile_id).where(
            BusinessProfileUomDefault.firm_id.is_(None),
            BusinessProfileUomDefault.is_deleted.is_(False),
        )
    )
    assert profile_id is not None

    row = UomService(session).get_profile_default(
        firm_scope=firm.id, profile_id=profile_id
    )
    assert row is not None
    # firm_id None tells the caller this is inherited, not the firm's own.
    assert row.firm_id is None


def test_a_firms_own_override_outranks_the_profile_wide_default() -> None:
    """A firm's row wins, and the rank must not depend on NULL sort order."""
    session = _session_factory()()
    seed_business_profiles(session)
    seed_uom_reference_data(session)
    session.commit()
    firm = _firm(session, "UOME")
    other = _firm(session, "UOMG")
    profile_id = session.scalar(
        select(BusinessProfileUomDefault.business_profile_id).where(
            BusinessProfileUomDefault.firm_id.is_(None),
            BusinessProfileUomDefault.is_deleted.is_(False),
        )
    )
    assert profile_id is not None
    unit = session.scalar(select(Uom).where(Uom.code == "UNIT"))
    assert unit is not None
    service = UomService(session)
    service.upsert_profile_default(
        firm_scope=firm.id,
        profile_id=profile_id,
        data=BusinessProfileUomDefaultUpsert(base_uom_id=unit.id, allow_fraction=True),
        actor_id=uuid4(),
    )

    mine = service.get_profile_default(firm_scope=firm.id, profile_id=profile_id)
    assert mine is not None
    assert mine.firm_id == firm.id
    assert mine.allow_fraction is True
    # Another firm in the same store still sees the profile-wide row, not mine.
    theirs = service.get_profile_default(firm_scope=other.id, profile_id=profile_id)
    assert theirs is not None
    assert theirs.firm_id is None


def test_a_firm_resolves_its_own_profile_defaults_without_a_profile_id() -> None:
    """A firm client cannot learn its profile id, so it must not need one.

    Every route that reveals a profile id is platform-admin only, which left
    the defaults meant for a firm unreachable by that firm.
    """
    session = _session_factory()()
    seed_business_profiles(session)
    seed_uom_reference_data(session)
    session.commit()
    firm = _firm(session, "UOMH")
    profile = session.scalar(
        select(BusinessProfile).where(BusinessProfile.code == "PHARMACY")
    )
    assert profile is not None
    session.add(
        FirmBusinessProfile(
            firm_id=firm.id,
            business_profile_id=profile.id,
            is_active=True,
            effective_from=date(2026, 4, 1),
        )
    )
    session.commit()

    row = UomService(session).resolve_firm_profile_default(firm_scope=firm.id)
    assert row is not None
    assert row.business_profile_id == profile.id
    # Inherited, because the firm has not overridden it.
    assert row.firm_id is None


def test_a_profile_wide_write_reaches_every_firm_on_the_profile() -> None:
    """``firm_scope=None`` writes the row all firms on a profile inherit.

    Until this existed only the seed could write one, so a profile created
    through the API could never carry defaults for the firms put on it.
    """
    session = _session_factory()()
    seed_business_profiles(session)
    seed_uom_reference_data(session)
    session.commit()
    first = _firm(session, "UOMI")
    second = _firm(session, "UOMJ")
    profile = _new_profile(session)
    for firm in (first, second):
        session.add(
            FirmBusinessProfile(
                firm_id=firm.id,
                business_profile_id=profile.id,
                is_active=True,
                effective_from=date(2026, 4, 1),
            )
        )
    session.commit()
    service = UomService(session)
    # GARMENTS is seeded without defaults, which is the state a newly created
    # profile is in.
    assert service.resolve_firm_profile_default(firm_scope=first.id) is None

    piece = session.scalar(select(Uom).where(Uom.code == "UNIT"))
    assert piece is not None
    service.upsert_profile_default(
        firm_scope=None,
        profile_id=profile.id,
        data=BusinessProfileUomDefaultUpsert(base_uom_id=piece.id),
        actor_id=uuid4(),
        audit_firm_id=first.id,
    )

    for firm in (first, second):
        inherited = service.resolve_firm_profile_default(firm_scope=firm.id)
        assert inherited is not None
        assert inherited.firm_id is None
        assert inherited.base_uom_id == piece.id


def test_a_firm_override_still_wins_over_a_profile_wide_write() -> None:
    """The two levels must not collapse into whichever was written last."""
    session = _session_factory()()
    seed_business_profiles(session)
    seed_uom_reference_data(session)
    session.commit()
    firm = _firm(session, "UOMK")
    other = _firm(session, "UOML")
    profile = _new_profile(session)
    for row in (firm, other):
        session.add(
            FirmBusinessProfile(
                firm_id=row.id,
                business_profile_id=profile.id,
                is_active=True,
                effective_from=date(2026, 4, 1),
            )
        )
    session.commit()
    service = UomService(session)
    units = {
        code: session.scalar(select(Uom).where(Uom.code == code))
        for code in ("UNIT", "BOX")
    }
    actor_id = uuid4()
    service.upsert_profile_default(
        firm_scope=firm.id,
        profile_id=profile.id,
        data=BusinessProfileUomDefaultUpsert(base_uom_id=units["BOX"].id),
        actor_id=actor_id,
    )
    # Written second, and must not displace the override above.
    service.upsert_profile_default(
        firm_scope=None,
        profile_id=profile.id,
        data=BusinessProfileUomDefaultUpsert(base_uom_id=units["UNIT"].id),
        actor_id=actor_id,
        audit_firm_id=firm.id,
    )

    mine = service.resolve_firm_profile_default(firm_scope=firm.id)
    assert mine is not None
    assert mine.base_uom_id == units["BOX"].id
    theirs = service.resolve_firm_profile_default(firm_scope=other.id)
    assert theirs is not None
    assert theirs.base_uom_id == units["UNIT"].id


def test_writing_profile_defaults_leaves_an_audit_entry() -> None:
    """A change reaching every firm on a profile must be attributable."""
    session = _session_factory()()
    seed_business_profiles(session)
    seed_uom_reference_data(session)
    session.commit()
    firm = _firm(session, "UOMM")
    profile = _new_profile(session)
    actor_id = uuid4()

    row = UomService(session).upsert_profile_default(
        firm_scope=None,
        profile_id=profile.id,
        data=BusinessProfileUomDefaultUpsert(),
        actor_id=actor_id,
        audit_firm_id=firm.id,
    )

    audit = session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == row.id,
            AuditLog.action == "uom.profile_default.created",
        )
    )
    assert audit is not None
    # The row has no firm, so the trail would otherwise lose the store it
    # happened in.
    assert audit.firm_id == firm.id


def test_a_stale_write_is_refused_and_a_current_one_is_not() -> None:
    """`If-Match` reaches uom now, which needed a name for it first.

    A conversion rule publishes a revision of its own, and the schema exposed
    that as ``version`` -- the one name the concurrency counter has to have. So
    the module could not be given a precondition at all: the field was taken.
    The revision is spelled ``version_number`` now, the way the column is and
    the way ``app/tax`` has always spelled it.
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
            version_number=1,
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    read_at = rule.version

    service.update_conversion_rule(
        rule.id,
        ConversionRuleUpdate(reason="first edit"),
        firm_scope=firm.id,
        actor_id=actor_id,
        expected_version=read_at,
    )

    # Somebody else has moved it since; the second writer is refused rather
    # than overwriting what they never saw.
    with pytest.raises(ConflictError):
        service.update_conversion_rule(
            rule.id,
            ConversionRuleUpdate(reason="second edit"),
            firm_scope=firm.id,
            actor_id=actor_id,
            expected_version=read_at,
        )

    # And sending nothing is still accepted: the precondition is opt-in, so an
    # older client keeps working.
    service.update_conversion_rule(
        rule.id,
        ConversionRuleUpdate(reason="no precondition"),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    # The service upper-cases the strings it stores on a rule; what matters
    # here is that the write was accepted without a precondition at all.
    assert rule.reason == "NO PRECONDITION"


def test_the_counter_and_the_published_revision_are_different_numbers() -> None:
    """Editing a rule moves one and leaves the other, which is the whole point.

    They were both called ``version`` in the schema, and a line that records
    "the rule revision I converted with" then meant two different numbers
    depending on which code path filled it in.
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
            version_number=1,
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    counter = rule.version

    service.update_conversion_rule(
        rule.id,
        ConversionRuleUpdate(reason="a note"),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    session.expire_all()
    stored = session.get(ConversionRule, rule.id)

    assert stored.version_number == 1
    assert stored.version > counter

    # The conversion answers with the published revision, not the counter --
    # it is what the seven transactional modules store on a line.
    result = service.convert_quantity(
        ConversionRequest(
            quantity=Decimal("2"),
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_date=date(2026, 6, 1),
        ),
        firm_scope=firm.id,
    )
    assert result.version_number == 1
