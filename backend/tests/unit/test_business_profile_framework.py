"""Business profile framework service and authorization tests."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.api.router import _resolve_firm_scope
from app.business.gating import assert_feature_fields
from app.business.models import (
    BusinessFeature,
    BusinessProfile,
    FirmBusinessProfile,
    ProfileFeature,
)
from app.business.schemas import (
    AttributeDefinitionCreate,
    BusinessFeatureCreate,
    BusinessFeatureUpdate,
    BusinessModuleCreate,
    BusinessProfileCreate,
    BusinessProfileUpdate,
    CategoryAttributeRuleCreate,
    FirmBusinessProfileAssign,
)
from app.business.services import BusinessProfileFrameworkService
from app.business.system_seed import seed_business_profiles
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from app.core.security.authorization import Principal, require_platform_admin
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm


def _session_factory() -> sessionmaker[Session]:
    """Create one in-memory database for service and API helper tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str) -> Firm:
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


def _principal(
    user_id: UUID,
    *,
    roles: set[str] | None = None,
    firm_id: UUID | None = None,
) -> Principal:
    role_values = roles or set()
    return Principal(
        subject=user_id,
        roles=frozenset(role_values),
        permissions=frozenset({"PLATFORM_VIEW"}),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            roles=sorted(role_values),
        ),
        firm_id=firm_id,
    )


def test_business_profile_crud_and_default_switching() -> None:
    """Support profile CRUD while preserving exactly one chosen default profile."""
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    actor = uuid4()

    first = service.create_profile(
        BusinessProfileCreate(
            code="GENERIC",
            name="Generic",
            industry_type="GENERIC",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )
    second = service.create_profile(
        BusinessProfileCreate(
            code="PHARMACY",
            name="Pharmacy",
            industry_type="PHARMACY",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )

    session.refresh(first)
    assert first.is_default is False
    assert second.is_default is True
    rows, total = service.list_profiles(1, 20, "PHAR", "code", False)
    assert total == 1
    assert rows[0].code == "PHARMACY"


def test_profile_feature_module_assignment_and_runtime_resolution() -> None:
    """Resolve active features/modules from profile defaults and explicit toggles."""
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    actor = uuid4()
    profile = service.create_profile(
        BusinessProfileCreate(
            code="SERVICE",
            name="Service",
            industry_type="SERVICE",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )
    feature = service.create_feature(
        BusinessFeatureCreate(
            code="PROJECT_MANAGEMENT",
            name="Project Management",
            default_enabled=False,
        ),
        actor,
    )
    module = service.create_module(
        BusinessModuleCreate(
            code="PROJECTS",
            name="Projects",
            ui_route="projects",
            default_enabled=False,
        ),
        actor,
    )
    service.set_profile_features(profile.id, [feature.id], actor)
    service.set_profile_modules(profile.id, [module.id], actor)

    active_features = service.active_features(None)
    active_modules = service.active_modules(None)
    assert any(item[0].code == "PROJECT_MANAGEMENT" for item in active_features)
    assert any(item[0].code == "PROJECTS" for item in active_modules)


def test_firm_assignment_and_scope_authorization() -> None:
    """Assign profile to firm and enforce selected-firm membership checks."""
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    actor = uuid4()
    profile = service.create_profile(
        BusinessProfileCreate(
            code="RETAIL",
            name="Retail",
            industry_type="RETAIL",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )
    firm = _firm(session, "RET")
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()

    assignment = service.assign_profile_to_firm(
        firm.id,
        FirmBusinessProfileAssign(business_profile_id=profile.id),
        actor,
    )
    assert assignment.business_profile_id == profile.id
    assert service.get_firm_assignment(firm.id) is not None

    principal = _principal(user_id, firm_id=firm.id)
    assert _resolve_firm_scope(principal, session, firm.id, None) == firm.id
    with pytest.raises(AuthorizationError):
        _resolve_firm_scope(principal, session, uuid4(), None)


def test_platform_admin_dependency_rejects_non_admin_claim() -> None:
    """Keep business profile management restricted to platform administrators."""
    user_id = uuid4()
    non_admin = _principal(user_id, roles={"FIRM_ADMIN"})
    with pytest.raises(AuthorizationError):
        require_platform_admin()(non_admin)


def test_seed_business_profiles_prefills_distribution_profiles() -> None:
    """Seed baseline distributor profiles with stable defaults and no duplicates."""
    session = _session_factory()()

    seed_business_profiles(session)
    seed_business_profiles(session)
    session.commit()

    profiles = {
        profile.code: profile
        for profile in session.scalars(select(BusinessProfile)).all()
    }
    assert profiles["GENERIC"].is_default is True
    assert profiles["AGENCY"].default_settings["business_model"] == "distributor"
    assert profiles["AGENCY"].default_settings["route_management"] is True
    assert profiles["PHARMACY"].default_settings["expiry_required"] is True
    assert profiles["FOOD"].default_settings["near_expiry_alert_days"] == 30
    assert profiles["WHOLESALE"].default_settings["bulk_pricing"] is True


def test_a_feature_a_profile_enables_cannot_be_deleted() -> None:
    """Deleting the master row revokes the capability for every firm at once.

    ``resolve_capabilities`` skips deleted features, so removing one does not
    tidy a catalogue -- it makes ``require_feature`` start rejecting writes that
    the firms on that profile were making the day before. ``delete_profile``
    already refuses while an assignment exists; this is the same rule one level
    down.
    """
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    actor = uuid4()
    profile = service.create_profile(
        BusinessProfileCreate(
            code="PHARMA_X",
            name="Pharma",
            industry_type="PHARMA",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )
    feature = service.create_feature(
        BusinessFeatureCreate(
            code="BATCH_TRACKING_X",
            name="Batch tracking",
            default_enabled=False,
        ),
        actor,
    )
    module = service.create_module(
        BusinessModuleCreate(
            code="BATCHES_X",
            name="Batches",
            ui_route="batches",
            default_enabled=False,
        ),
        actor,
    )
    service.set_profile_features(profile.id, [feature.id], actor)
    service.set_profile_modules(profile.id, [module.id], actor)

    with pytest.raises(ConflictError, match="still enable this feature"):
        service.delete_feature(feature.id, actor)
    with pytest.raises(ConflictError, match="still enable this module"):
        service.delete_module(module.id, actor)

    # Disabled everywhere, it can go.
    service.set_profile_features(profile.id, [], actor)
    service.delete_feature(feature.id, actor)


def test_a_roadmap_feature_is_listed_but_cannot_be_switched_on() -> None:
    """Seven catalogue entries name a subsystem nothing has built.

    They stay listed so the intent is visible, but enabling one would tell a
    firm it had a capability that can never do anything, so the write is
    refused rather than silently stored.
    """
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    actor = uuid4()
    profile = service.create_profile(
        BusinessProfileCreate(
            code="FOOD",
            name="Food",
            industry_type="FOOD",
            status="ACTIVE",
            is_default=True,
        ),
        actor,
    )
    built = service.create_feature(
        BusinessFeatureCreate(code="BARCODE", name="Barcode"), actor
    )
    roadmap = service.create_feature(
        BusinessFeatureCreate(code="RECIPE_MANAGEMENT", name="Recipes"), actor
    )
    roadmap.is_implemented = False
    session.commit()

    # Still in the catalogue: roadmap is not the same as removed.
    codes = {
        row.code
        for row in service.list_features(
            page=1,
            page_size=50,
            search=None,
            sort_by="code",
            descending=False,
        )[0]
    }
    assert "RECIPE_MANAGEMENT" in codes

    with pytest.raises(ValidationError) as error:
        service.set_profile_features(profile.id, [built.id, roadmap.id], actor)
    assert "RECIPE_MANAGEMENT" in str(error.value)

    # And nothing was stored, including the feature that was implemented.
    assert service.active_features(None) == []


def test_a_feature_is_presumed_implemented_when_it_is_created() -> None:
    """Whoever adds a feature is asserting it exists; the flag defaults true.

    Only the migration clears it, for the seven entries surveyed as unbacked.
    """
    session = _session_factory()()
    service = BusinessProfileFrameworkService(session)
    feature = service.create_feature(
        BusinessFeatureCreate(code="WARRANTY", name="Warranty"), uuid4()
    )

    assert feature.is_implemented is True


def _profile_with(session: Session, *codes: str) -> None:
    """Seed the default profile, enabling only the named features."""
    profile = BusinessProfile(
        code="GENERIC",
        name="Generic",
        industry_type="GENERIC",
        status="ACTIVE",
        is_default=True,
    )
    session.add(profile)
    session.flush()
    for code in ("EXPIRY_TRACKING", "BARCODE", "DRUG_LICENSE"):
        feature = BusinessFeature(code=code, name=code.title())
        session.add(feature)
        session.flush()
        session.add(
            ProfileFeature(
                business_profile_id=profile.id,
                feature_id=feature.id,
                is_enabled=code in codes,
            )
        )
    session.commit()


def test_a_disabled_feature_blocks_only_the_field_it_owns() -> None:
    """The capability is gated, not the record.

    ``require_feature`` gates a whole endpoint, which suits BATCH_TRACKING: a
    firm that does not track batches has no business posting one. Expiry dates
    are not like that. A firm without EXPIRY_TRACKING still records batches --
    it just cannot date them -- so gating the endpoint would have stopped it
    creating batches at all.
    """
    session = _session_factory()()
    _profile_with(session, "BARCODE")
    firm = uuid4()

    # The field belonging to the disabled feature is refused...
    with pytest.raises(AuthorizationError, match="EXPIRY_TRACKING"):
        assert_feature_fields(
            session,
            firm,
            feature="EXPIRY_TRACKING",
            values={"expiry_date": date(2027, 1, 1)},
        )

    # ...while the rest of the write is untouched.
    assert_feature_fields(
        session, firm, feature="BARCODE", values={"barcode": "890100001"}
    )


def test_leaving_a_gated_field_blank_is_always_allowed() -> None:
    """Turning a feature off must not freeze the records that predate it.

    A write that does not populate the field is not exercising the feature, so
    it passes whatever the profile says. Clearing the field is the same case.
    """
    session = _session_factory()()
    _profile_with(session)
    firm = uuid4()

    for value in (None, "", False):
        assert_feature_fields(
            session, firm, feature="EXPIRY_TRACKING", values={"expiry_date": value}
        )


def test_the_message_names_every_field_that_was_refused() -> None:
    """One error listing all of them, not one round trip per field."""
    session = _session_factory()()
    _profile_with(session)
    firm = uuid4()

    with pytest.raises(AuthorizationError) as error:
        assert_feature_fields(
            session,
            firm,
            feature="EXPIRY_TRACKING",
            values={
                "expiry_date": date(2027, 1, 1),
                "best_before_date": date(2026, 12, 1),
            },
        )

    message = str(error.value)
    assert "best_before_date" in message
    assert "expiry_date" in message


def test_a_firm_with_no_profile_at_all_is_not_locked_out() -> None:
    """A configuration gap is not a decision.

    resolve_capabilities already treats "no profile and no platform default"
    as a gap rather than a denial. Gating fields on it would lock every firm
    out of every optional field in a database where nobody has seeded the
    catalogue yet.
    """
    session = _session_factory()()
    assert_feature_fields(
        session,
        uuid4(),
        feature="EXPIRY_TRACKING",
        values={"expiry_date": date(2027, 1, 1)},
    )


def test_an_empty_collection_is_blank_and_never_refused() -> None:
    """A document with no attachments must not be refused for having the field.

    The first version of this check treated any value that was not None, ""
    or False as populated, so an empty ``attachments`` list counted as a use
    of the feature -- which would have refused every document raised by a firm
    without ATTACHMENTS, whether or not it attached anything.
    """
    session = _session_factory()()
    _profile_with(session)
    firm = uuid4()

    for blank in ([], {}, (), "", None, False):
        assert_feature_fields(
            session, firm, feature="EXPIRY_TRACKING", values={"attachments": blank}
        )

    with pytest.raises(AuthorizationError):
        assert_feature_fields(
            session,
            firm,
            feature="EXPIRY_TRACKING",
            values={"attachments": ["invoice.pdf"]},
        )


def test_zero_counts_as_a_value_somebody_typed() -> None:
    """Blank means absent, not falsy. A numeric zero is a deliberate entry."""
    session = _session_factory()()
    _profile_with(session)

    with pytest.raises(AuthorizationError):
        assert_feature_fields(
            session,
            uuid4(),
            feature="EXPIRY_TRACKING",
            values={"shelf_life_days": 0},
        )


def test_a_soft_deleted_assignment_does_not_reserve_the_firm() -> None:
    """A removed assignment must not lock its firm out of ever having another.

    `firm_business_profiles` carried a table-wide UNIQUE on `firm_id`. Every
    query in this module filters `is_deleted`, so a soft-deleted row is
    invisible to all of them while still holding the key — re-assigning that
    firm would fail on the constraint with nothing on screen to explain it.

    Nothing sets `is_deleted` here today, which is why this was a trap rather
    than a defect. The point of the test is the day somebody adds an
    "unassign" action: the index is now partial (`20260815_0089`), so this
    passes, and a table-wide constraint makes it fail.
    """
    session = _session_factory()()
    firm = _firm(session, "SOFTDEL")
    actor_id = uuid4()
    service = BusinessProfileFrameworkService(session)
    profile = service.create_profile(
        BusinessProfileCreate(code="FIRST", name="First", industry_type="GENERIC"),
        actor_id,
    )
    second = service.create_profile(
        BusinessProfileCreate(code="SECOND", name="Second", industry_type="GENERIC"),
        actor_id,
    )
    assigned = service.assign_profile_to_firm(
        firm.id,
        FirmBusinessProfileAssign(business_profile_id=profile.id),
        actor_id,
    )
    session.commit()

    # Stand in for the unassign action that does not exist yet.
    assigned.is_deleted = True
    session.commit()
    assert service.get_firm_assignment(firm.id) is None

    fresh = service.assign_profile_to_firm(
        firm.id,
        FirmBusinessProfileAssign(business_profile_id=second.id),
        actor_id,
    )
    session.commit()

    assert fresh.id != assigned.id, "a new row, not the resurrected old one"
    assert fresh.business_profile_id == second.id
    current = service.get_firm_assignment(firm.id)
    assert current is not None and current.business_profile_id == second.id


def test_a_firm_still_cannot_hold_two_live_assignments() -> None:
    """Scoping the key to live rows must not let a firm have two profiles.

    The service updates the firm's existing row in place, so this asserts the
    behaviour rather than the constraint — but it is the half that would be
    lost if somebody "fixed" the uniqueness by dropping it altogether.
    """
    session = _session_factory()()
    firm = _firm(session, "ONEONLY")
    actor_id = uuid4()
    service = BusinessProfileFrameworkService(session)
    first = service.create_profile(
        BusinessProfileCreate(code="AA", name="A", industry_type="GENERIC"),
        actor_id,
    )
    second = service.create_profile(
        BusinessProfileCreate(code="BB", name="B", industry_type="GENERIC"),
        actor_id,
    )
    original = service.assign_profile_to_firm(
        firm.id, FirmBusinessProfileAssign(business_profile_id=first.id), actor_id
    )
    session.commit()

    replaced = service.assign_profile_to_firm(
        firm.id, FirmBusinessProfileAssign(business_profile_id=second.id), actor_id
    )
    session.commit()

    # The same row, repointed — assigning does not accumulate.
    assert replaced.id == original.id
    assert replaced.business_profile_id == second.id
    live = session.scalars(
        select(FirmBusinessProfile).where(
            FirmBusinessProfile.firm_id == firm.id,
            FirmBusinessProfile.is_deleted.is_(False),
        )
    ).all()
    assert len(live) == 1


def test_an_update_that_omits_a_field_leaves_it_alone() -> None:
    """A write schema gives every optional field a default.

    ``model_dump()`` therefore returns a value for a field the caller never
    mentioned, and assigning all of them writes that default over live data.
    It has shipped twice -- a vendor lost its addresses, a branch its street
    lines -- and these eight update methods were the last with the shape.

    ``default_enabled`` is the one that bites hardest here: it is the fallback
    every profile without an explicit mapping row inherits, so flipping it by
    omission silently changes what firms on those profiles can do.
    """
    session = _session_factory()()
    actor = uuid4()
    service = BusinessProfileFrameworkService(session)
    feature = service.create_feature(
        BusinessFeatureCreate(
            code="BARCODE",
            name="Barcode",
            description="Scan a barcode.",
            category="OPERATIONS",
            default_enabled=True,
            is_active=True,
        ),
        actor,
    )

    # A rename, and nothing else.
    service.update_feature(
        feature.id,
        BusinessFeatureUpdate.model_construct(
            **BusinessFeatureUpdate(code="BARCODE", name="Barcode scanning").model_dump(
                include={"code", "name"}
            )
        ),
        actor,
    )

    assert feature.name == "Barcode scanning"
    assert feature.default_enabled is True, "omitted, so it must not flip"
    assert feature.is_active is True
    assert feature.description == "Scan a barcode."
    assert feature.category == "OPERATIONS"


def test_renaming_the_default_profile_does_not_demote_it() -> None:
    """Renaming the default profile must not quietly demote it.

    Reading it off the model instead makes an omission mean False: the profile
    that *is* the default demotes nobody and is then written back as not
    default, which leaves a store with no default at all -- and a store with no
    default enforces nothing.
    """
    session = _session_factory()()
    actor = uuid4()
    service = BusinessProfileFrameworkService(session)
    generic = service.create_profile(
        BusinessProfileCreate(
            code="GENERIC",
            name="Generic",
            industry_type="GENERIC",
            is_default=True,
        ),
        actor,
    )
    service.create_profile(
        BusinessProfileCreate(code="PHARMACY", name="Pharmacy", industry_type="PHARMA"),
        actor,
    )

    service.update_profile(
        generic.id,
        BusinessProfileUpdate.model_construct(
            code="GENERIC",
            name="Generic business",
            industry_type="GENERIC",
        ),
        actor,
    )

    assert generic.name == "Generic business"
    assert generic.is_default is True
    assert generic.status == "ACTIVE"


def _rule_fixture(
    service: BusinessProfileFrameworkService, actor: UUID, *, code: str
) -> tuple[UUID, UUID]:
    """Create one attribute and one profile, and return their ids."""
    attribute = service.create_attribute(
        AttributeDefinitionCreate(
            code=code,
            name=f"{code.title()} field",
            entity_type="PRODUCT",
            data_type="TEXT",
        ),
        actor,
    )
    profile = service.create_profile(
        BusinessProfileCreate(
            code=f"PROFILE_{code}",
            name=f"Profile {code}",
            industry_type="GENERIC",
            description="For the rule to be scoped to.",
        ),
        actor,
    )
    return attribute.id, profile.id


def test_the_rule_list_pages_and_searches() -> None:
    """It returned every rule in one unpaginated list until 2026-08-22.

    Which nothing noticed, because nothing called it: the table had no screen,
    so the one place a firm can say "a medicine must carry an expiry date" was
    unreachable from the application. `20260815_0087` had cleared the blanket
    `mandatory` flags on exactly that understanding.
    """
    session = _session_factory()()
    actor = uuid4()
    service = BusinessProfileFrameworkService(session)
    attribute_id, profile_id = _rule_fixture(service, actor, code="EXPIRY")

    for category in ("MEDICINE", "SYRUP", "TABLET"):
        service.create_category_rule(
            CategoryAttributeRuleCreate(
                business_profile_id=profile_id,
                category_code=category,
                attribute_definition_id=attribute_id,
            ),
            actor,
        )

    rows, total = service.list_category_rules(1, 2, None, "category_code", False)
    assert total == 3
    assert [row.category_code for row in rows] == ["MEDICINE", "SYRUP"]

    rows, total = service.list_category_rules(2, 2, None, "category_code", False)
    assert [row.category_code for row in rows] == ["TABLET"]

    rows, total = service.list_category_rules(1, 20, "med", "category_code", False)
    assert total == 1
    assert rows[0].category_code == "MEDICINE"


def test_a_rule_answers_with_the_names_behind_its_ids() -> None:
    """A grid of raw UUIDs tells the person reading it nothing.

    The alternative is the screen loading the whole attribute catalogue to
    render one column, so the ids are resolved here -- in two queries for the
    page, not one per row.
    """
    session = _session_factory()()
    actor = uuid4()
    service = BusinessProfileFrameworkService(session)
    attribute_id, profile_id = _rule_fixture(service, actor, code="BATCH")

    scoped = service.create_category_rule(
        CategoryAttributeRuleCreate(
            business_profile_id=profile_id,
            category_code="MEDICINE",
            attribute_definition_id=attribute_id,
        ),
        actor,
    )
    everywhere = service.create_category_rule(
        CategoryAttributeRuleCreate(
            category_code="SYRUP",
            attribute_definition_id=attribute_id,
        ),
        actor,
    )

    described = service.describe_category_rules([scoped, everywhere])
    assert described[scoped.id] == ("BATCH", "Batch field", "PROFILE_BATCH")
    assert described[everywhere.id] == ("BATCH", "Batch field", None), (
        "a rule with no profile holds for every industry, and says so by "
        "carrying no profile code rather than an empty one"
    )
