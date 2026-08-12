"""Server-side business-profile gating tests."""

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.gating import (
    SAFE_METHODS,
    require_feature,
    require_module,
    resolve_capabilities,
)
from app.business.models import (
    BusinessFeature,
    BusinessModule,
    BusinessProfile,
    FirmBusinessProfile,
    ProfileFeature,
    ProfileModule,
)
from app.core.database.base import Base
from app.core.exceptions import AuthorizationError
from app.firms.models import Firm


class _Request:
    """Minimal stand-in for the parts of Request the gate reads."""

    def __init__(self, method: str) -> None:
        self.method = method


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str) -> Firm:
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _profile(
    session: Session,
    code: str,
    *,
    features: tuple[str, ...] = (),
    modules: tuple[str, ...] = (),
    is_default: bool = False,
) -> BusinessProfile:
    profile = BusinessProfile(
        code=code,
        name=code.title(),
        industry_type=code,
        status="ACTIVE",
        is_default=is_default,
    )
    session.add(profile)
    session.flush()
    for feature_code in features:
        feature = session.query(BusinessFeature).filter_by(code=feature_code).first()
        if feature is None:
            feature = BusinessFeature(code=feature_code, name=feature_code)
            session.add(feature)
            session.flush()
        session.add(
            ProfileFeature(
                business_profile_id=profile.id,
                feature_id=feature.id,
                is_enabled=True,
            )
        )
    for module_code in modules:
        module = session.query(BusinessModule).filter_by(code=module_code).first()
        if module is None:
            module = BusinessModule(code=module_code, name=module_code)
            session.add(module)
            session.flush()
        session.add(
            ProfileModule(
                business_profile_id=profile.id,
                module_id=module.id,
                is_enabled=True,
            )
        )
    session.commit()
    return profile


def _assign(session: Session, firm: Firm, profile: BusinessProfile) -> None:
    session.add(
        FirmBusinessProfile(
            firm_id=firm.id,
            business_profile_id=profile.id,
            is_active=True,
            effective_from=date(2026, 4, 1),
        )
    )
    session.commit()


def _call(dependency: object, request: _Request, capabilities: object) -> object:
    """Invoke the callable FastAPI would have wrapped."""
    return dependency.dependency(request, capabilities)  # type: ignore[attr-defined]


def test_pharmacy_profile_resolves_its_own_capabilities() -> None:
    """A firm's assigned profile drives its features and modules."""
    session = _session()
    firm = _firm(session, "MEDI")
    pharmacy = _profile(
        session,
        "PHARMACY",
        features=("BATCH_TRACKING", "EXPIRY_TRACKING"),
        modules=("SALES", "INVENTORY"),
    )
    _assign(session, firm, pharmacy)

    capabilities = resolve_capabilities(session, firm.id)
    assert capabilities.profile_code == "PHARMACY"
    assert capabilities.has_feature("BATCH_TRACKING")
    assert capabilities.has_feature("EXPIRY_TRACKING")
    assert not capabilities.has_feature("RECIPE_MANAGEMENT")
    assert capabilities.has_module("INVENTORY")


def test_profiles_are_isolated_between_firms() -> None:
    """A food firm does not inherit a pharmacy firm's capabilities."""
    session = _session()
    pharma_firm = _firm(session, "MEDI")
    food_firm = _firm(session, "FOOD")
    _assign(
        session,
        pharma_firm,
        _profile(session, "PHARMACY", features=("DRUG_LICENSE", "BATCH_TRACKING")),
    )
    _assign(session, food_firm, _profile(session, "FOOD", features=("SHELF_LIFE",)))

    pharma = resolve_capabilities(session, pharma_firm.id)
    food = resolve_capabilities(session, food_firm.id)
    assert pharma.has_feature("DRUG_LICENSE")
    assert not food.has_feature("DRUG_LICENSE")
    assert food.has_feature("SHELF_LIFE")
    assert not pharma.has_feature("SHELF_LIFE")


def test_unassigned_firm_falls_back_to_the_default_profile() -> None:
    """A firm with no profile resolves to the platform default."""
    session = _session()
    firm = _firm(session, "ELEC")
    _profile(session, "GENERIC", features=("BARCODE",), is_default=True)

    capabilities = resolve_capabilities(session, firm.id)
    assert capabilities.profile_code == "GENERIC"
    assert capabilities.has_feature("BARCODE")


def test_missing_configuration_enforces_nothing() -> None:
    """With no profile and no default, the gate must not lock the firm out."""
    session = _session()
    firm = _firm(session, "NEW")
    capabilities = resolve_capabilities(session, firm.id)
    assert capabilities.profile_code is None
    assert capabilities.features == frozenset()


def test_disabled_feature_blocks_writes_but_not_reads() -> None:
    """Gating applies to mutations only, so existing data stays readable."""
    session = _session()
    firm = _firm(session, "FOOD")
    _assign(session, firm, _profile(session, "FOOD", features=("SHELF_LIFE",)))
    capabilities = resolve_capabilities(session, firm.id)

    gate = require_feature("BATCH_TRACKING")
    for method in sorted(SAFE_METHODS):
        assert _call(gate, _Request(method), capabilities) is capabilities

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        with pytest.raises(AuthorizationError, match="does not enable: BATCH_TRACKING"):
            _call(gate, _Request(method), capabilities)


def test_enabled_feature_permits_writes() -> None:
    """An enabled feature lets mutations through untouched."""
    session = _session()
    firm = _firm(session, "MEDI")
    _assign(session, firm, _profile(session, "PHARMACY", features=("BATCH_TRACKING",)))
    capabilities = resolve_capabilities(session, firm.id)
    gate = require_feature("BATCH_TRACKING")
    assert _call(gate, _Request("POST"), capabilities) is capabilities


def test_multiple_required_features_report_every_missing_code() -> None:
    """The error names all missing capabilities, not just the first."""
    session = _session()
    firm = _firm(session, "FOOD")
    _assign(session, firm, _profile(session, "FOOD", features=("BARCODE",)))
    capabilities = resolve_capabilities(session, firm.id)

    gate = require_feature("IMEI", "WARRANTY")
    with pytest.raises(AuthorizationError) as error:
        _call(gate, _Request("POST"), capabilities)
    assert "IMEI" in str(error.value)
    assert "WARRANTY" in str(error.value)


def test_module_gate_blocks_writes_for_a_disabled_module() -> None:
    """A module the profile does not operate rejects mutations."""
    session = _session()
    firm = _firm(session, "FOOD")
    _assign(session, firm, _profile(session, "FOOD", modules=("SALES",)))
    capabilities = resolve_capabilities(session, firm.id)

    sales_gate = require_module("SALES")
    assert _call(sales_gate, _Request("POST"), capabilities) is capabilities
    with pytest.raises(AuthorizationError, match="KITCHEN module is not enabled"):
        _call(require_module("KITCHEN"), _Request("POST"), capabilities)
    # Reads still pass so the screen can render existing records.
    assert (
        _call(require_module("KITCHEN"), _Request("GET"), capabilities) is capabilities
    )


def test_require_feature_rejects_an_empty_code_list() -> None:
    """A gate with no codes would silently permit everything."""
    with pytest.raises(ValueError, match="At least one feature code"):
        require_feature()


def test_capabilities_are_typed_frozen_sets() -> None:
    """Guard the immutability the dependency relies on."""
    session = _session()
    firm = _firm(session, "MEDI")
    _assign(session, firm, _profile(session, "PHARMACY", features=("BATCH_TRACKING",)))
    capabilities = resolve_capabilities(session, firm.id)
    assert isinstance(capabilities.features, frozenset)
    assert isinstance(capabilities.modules, frozenset)
    assert isinstance(firm.id, UUID)


def test_a_missing_mapping_row_inherits_the_catalogue_default() -> None:
    """A profile with no row for a feature falls back to ``default_enabled``.

    ``/active-features`` has always applied this fallback, so an inner join
    here made the gate disagree with the screen: RESTAURANT and SERVICE were
    advertised BARCODE, rendered the field, and were refused on save.
    """
    session = _session()
    firm = _firm(session, "REST")
    profile = _profile(session, "RESTAURANT", features=("EXPIRY_TRACKING",))
    session.add(BusinessFeature(code="BARCODE", name="Barcode", default_enabled=True))
    session.add(BusinessFeature(code="IMEI", name="IMEI", default_enabled=False))
    session.commit()
    _assign(session, firm, profile)

    capabilities = resolve_capabilities(session, firm.id)
    assert capabilities.has_feature("BARCODE")
    assert capabilities.has_feature("EXPIRY_TRACKING")
    assert not capabilities.has_feature("IMEI")
    # The gate must now agree with what the screen was told.
    assert _call(require_feature("BARCODE"), _Request("POST"), capabilities) is (
        capabilities
    )


def test_an_explicit_mapping_row_beats_the_catalogue_default() -> None:
    """Turning a feature off for one profile survives a permissive default."""
    session = _session()
    firm = _firm(session, "SERV")
    profile = _profile(session, "SERVICE")
    feature = BusinessFeature(code="BARCODE", name="Barcode", default_enabled=True)
    session.add(feature)
    session.flush()
    session.add(
        ProfileFeature(
            business_profile_id=profile.id,
            feature_id=feature.id,
            is_enabled=False,
        )
    )
    session.commit()
    _assign(session, firm, profile)

    capabilities = resolve_capabilities(session, firm.id)
    assert not capabilities.has_feature("BARCODE")
    with pytest.raises(AuthorizationError, match="does not enable: BARCODE"):
        _call(require_feature("BARCODE"), _Request("POST"), capabilities)


def test_a_deactivated_feature_is_withdrawn_despite_a_permissive_default() -> None:
    """``is_active`` still wins: the fallback must not resurrect it."""
    session = _session()
    firm = _firm(session, "CUST")
    profile = _profile(session, "CUSTOM")
    session.add(
        BusinessFeature(
            code="BARCODE", name="Barcode", default_enabled=True, is_active=False
        )
    )
    session.commit()
    _assign(session, firm, profile)

    assert not resolve_capabilities(session, firm.id).has_feature("BARCODE")


def test_module_visibility_does_not_decide_whether_a_write_is_refused() -> None:
    """Hiding a workspace from the menu must not revoke the right to use it."""
    session = _session()
    firm = _firm(session, "WHOL")
    profile = _profile(session, "WHOLESALE")
    module = BusinessModule(code="SALES", name="Sales", default_enabled=False)
    session.add(module)
    session.flush()
    session.add(
        ProfileModule(
            business_profile_id=profile.id,
            module_id=module.id,
            is_enabled=True,
            is_visible=False,
        )
    )
    session.commit()
    _assign(session, firm, profile)

    capabilities = resolve_capabilities(session, firm.id)
    assert capabilities.has_module("SALES")
    assert _call(require_module("SALES"), _Request("POST"), capabilities) is (
        capabilities
    )
