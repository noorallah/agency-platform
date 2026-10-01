"""A business profile written at runtime reaches every store (backlog 17).

Each store keeps its own profile catalogue, and the seeded profiles agree only
because migrations insert the same ids. A profile created through the API used
to exist in the caller's store alone, so it was offered for a firm elsewhere
and then refused as not found. These build several stores as separate
in-memory databases and drive the real routes against a stub registry.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.api.router import create_profile, delete_profile, update_profile
from app.business.models import BusinessProfile, FirmBusinessProfile
from app.business.schemas import BusinessProfileCreate, BusinessProfileUpdate
from app.business.services import BusinessProfileFrameworkService
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import BusinessRuleError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.core.tenancy.models import DeploymentMode, TenantContext
from app.firms.models import Firm


def _store() -> sessionmaker[Session]:
    """Build one store: its own in-memory database holding every table."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Manager:
    """Stand in for a `DatabaseManager`: a config and a session source."""

    def __init__(self, name: str, factory: sessionmaker[Session]) -> None:
        """Name the store and hold its sessions."""
        self.config = SimpleNamespace(host="db", port=5432, database=name)
        self._factory = factory

    def sessions(self, schema: str | None = None) -> SimpleNamespace:
        """Return an object whose `session()` opens one session on the store."""

        @contextmanager
        def session() -> Iterator[Session]:
            """Open and close one session."""
            db = self._factory()
            try:
                yield db
            finally:
                db.close()

        return SimpleNamespace(session=session)


class _Registry:
    """A stub firm registry: which store each firm lives in."""

    def __init__(self, caller: UUID) -> None:
        """Start empty, with the caller's firm named."""
        self.caller = caller
        self.tenants: dict[UUID, TenantContext] = {}
        self.managers: dict[str, _Manager] = {}
        self.broken: set[UUID] = set()

    def resolve(self, request: object) -> TenantContext:
        """Resolve the caller's store, as the X-Firm-ID header would."""
        return self.tenants[self.caller]

    def resolve_firm(self, firm_id: UUID) -> TenantContext:
        """Resolve one firm's store, or refuse an unprovisioned one."""
        if firm_id in self.broken:
            raise BusinessRuleError("Dedicated storage is not provisioned.")
        return self.tenants[firm_id]

    def manager_for(self, tenant: TenantContext) -> _Manager:
        """Return the store's manager."""
        return self.managers[tenant.database_name]

    def schema_for(self, tenant: TenantContext) -> str:
        """Return the store's schema."""
        return tenant.schema_name


class _World:
    """A platform store, a firm registry and three firm stores."""

    def __init__(self) -> None:
        """Lay out WHOLE01 (caller) alone, FOOD01+FOOD02 shared, PHARM01 alone."""
        self.platform = _store()()
        self.stores = {name: _store() for name in ("whole", "shared", "pharm")}
        firms = {
            code: self._firm(code)
            for code in ("WHOLE01", "FOOD01", "FOOD02", "PHARM01", "NEW01")
        }
        self.firms = firms
        self.registry = _Registry(firms["WHOLE01"].id)
        for name, factory in self.stores.items():
            self.registry.managers[name] = _Manager(name, factory)
        for code, store in (
            ("WHOLE01", "whole"),
            ("FOOD01", "shared"),
            ("FOOD02", "shared"),
            ("PHARM01", "pharm"),
        ):
            self.registry.tenants[firms[code].id] = TenantContext(
                firm_id=firms[code].id,
                deployment_mode=DeploymentMode.SHARED,
                database_name=store,
                schema_name="firm",
                database_type="postgresql",
            )
        self.registry.broken.add(firms["NEW01"].id)
        self.request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    database_provider=self.registry, tenant_resolver=self.registry
                )
            )
        )
        self.caller_db = self.stores["whole"]()
        self.actor = uuid4()
        self.principal = Principal(
            subject=self.actor,
            roles=frozenset(),
            permissions=frozenset({"PLATFORM_VIEW"}),
            claims=TokenClaims(
                sub=str(self.actor),
                type=TokenType.ACCESS,
                iat=1,
                exp=4_102_444_800,
                roles=[],
            ),
        )

    def _firm(self, code: str) -> Firm:
        """Register one firm on the platform."""
        row = Firm(
            name=f"{code} Firm",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.platform.add(row)
        self.platform.commit()
        return row

    def profile_in(self, store: str, profile_id: UUID) -> BusinessProfile | None:
        """Read a profile straight out of one store."""
        with self.stores[store]() as db:
            return db.get(BusinessProfile, profile_id)


def _bakery(code: str = "BAKERY") -> BusinessProfileCreate:
    """Describe a profile nobody seeded."""
    return BusinessProfileCreate(code=code, name="Bakery", industry_type="FOOD")


def test_a_new_profile_reaches_every_store_under_one_id() -> None:
    """The caller's store, the shared store once, and a dedicated store."""
    world = _World()

    response = create_profile(
        _bakery(),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )

    profile_id = response.data.id
    for store in ("whole", "shared", "pharm"):
        copy = world.profile_in(store, profile_id)
        assert copy is not None and copy.code == "BAKERY", store
    outcomes = {item.store: item for item in response.data.stores}
    assert outcomes["shared/firm (FOOD01, FOOD02)"].status == "WRITTEN"
    assert outcomes["shared/firm (FOOD01, FOOD02)"].detail == "created"
    assert outcomes["pharm/firm (PHARM01)"].status == "WRITTEN"
    # The store that could not be resolved is named, never skipped.
    assert outcomes["NEW01"].status == "FAILED"
    assert "not provisioned" in outcomes["NEW01"].detail
    assert "1 of 3" in (response.message or "")
    # Each store records the write in its own trail.
    with world.stores["pharm"]() as db:
        assert db.scalar(
            select(AuditLog.action).where(AuditLog.entity_id == profile_id)
        ) == ("business_profile.created")


def test_a_profile_can_then_be_assigned_to_a_firm_in_another_store() -> None:
    """The defect itself: offered in one store, refused in the next."""
    world = _World()
    response = create_profile(
        _bakery(),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )

    with world.stores["shared"]() as db:
        assigned = BusinessProfileFrameworkService(db).get_profile(response.data.id)
    assert assigned.code == "BAKERY"


def test_a_change_and_a_delete_follow_the_profile() -> None:
    """An edit updates every copy; a delete removes every copy."""
    world = _World()
    created = create_profile(
        _bakery(),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    ).data

    updated = update_profile(
        created.id,
        BusinessProfileUpdate(
            code="BAKERY", name="Bakery & Cafe", industry_type="FOOD"
        ),
        world.principal,
        SimpleNamespace(headers={}),  # type: ignore[arg-type]
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )
    assert {
        item.detail for item in updated.data.stores if item.status == "WRITTEN"
    } == {"updated"}
    copy = world.profile_in("pharm", created.id)
    assert copy is not None and copy.name == "Bakery & Cafe"

    removed = delete_profile(
        created.id,
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )
    assert {item.detail for item in removed.data if item.status == "WRITTEN"} == {
        "deleted"
    }
    copy = world.profile_in("shared", created.id)
    assert copy is not None and copy.is_deleted


def test_a_store_holding_the_code_under_another_id_is_reported_not_overwritten() -> (
    None
):
    """Two ids for one code is the drift this exists to stop."""
    world = _World()
    with world.stores["pharm"]() as db:
        BusinessProfileFrameworkService(db).create_profile(_bakery(), uuid4())

    response = create_profile(
        _bakery(),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )

    outcome = next(
        item for item in response.data.stores if item.store.startswith("pharm")
    )
    assert outcome.status == "FAILED"
    assert "code already exists" in outcome.detail
    copy = world.profile_in("pharm", response.data.id)
    assert copy is None


def test_a_delete_refused_in_one_store_is_named() -> None:
    """A firm assigned the profile in its own store stops the delete there."""
    world = _World()
    created = create_profile(
        _bakery(),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    ).data
    with world.stores["pharm"]() as db:
        db.add(
            FirmBusinessProfile(
                firm_id=world.firms["PHARM01"].id,
                business_profile_id=created.id,
                is_active=True,
                effective_from=date(2026, 4, 1),
            )
        )
        db.commit()

    removed = delete_profile(
        created.id,
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )

    pharm = next(item for item in removed.data if item.store.startswith("pharm"))
    assert pharm.status == "FAILED"
    assert "Assigned" in pharm.detail
    copy = world.profile_in("pharm", created.id)
    assert copy is not None and not copy.is_deleted


def test_a_profiles_features_follow_it_and_a_missing_feature_is_named() -> None:
    """The feature set is written per store; a store lacking one says so."""
    from app.business.api.router import set_profile_features
    from app.business.models import BusinessFeature, ProfileFeature
    from app.business.schemas import IdentifierList

    world = _World()
    feature_id = uuid4()
    for store in ("whole", "shared"):
        with world.stores[store]() as db:
            db.add(
                BusinessFeature(
                    id=feature_id,
                    code="BATCH_TRACKING",
                    name="Batch tracking",
                    is_implemented=True,
                )
            )
            db.commit()
    created = create_profile(
        _bakery(),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    ).data

    result = set_profile_features(
        created.id,
        IdentifierList(ids=[feature_id]),
        world.principal,
        world.request,  # type: ignore[arg-type]
        world.caller_db,
        world.platform,
    )

    outcomes = {item.store: item for item in result.data}
    assert outcomes["shared/firm (FOOD01, FOOD02)"].status == "WRITTEN"
    # PHARM01's store never had the feature, and says so rather than dropping it.
    assert outcomes["pharm/firm (PHARM01)"].status == "FAILED"
    with world.stores["shared"]() as db:
        assert db.scalar(
            select(ProfileFeature.is_enabled).where(
                ProfileFeature.business_profile_id == created.id,
                ProfileFeature.feature_id == feature_id,
            )
        )
