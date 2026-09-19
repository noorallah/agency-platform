"""No dedicated firm is routed into a store that is not a firm's.

D-IDN-4. `_assert_storage_unclaimed` compared a new firm's routing only with
other firms' mappings. SHARED firms record no schema and `platform` is nobody's
mapping, so a SCHEMA or DATABASE firm could name `firm_shared`, `platform` or
`public` (live: `IDNPROBE1`, SCHEMA on `agency_platform/firm_shared`, accepted
201). **Provision** would then migrate that schema and run
`prune_platform_objects` on it -- `DROP TABLE ... CASCADE` of `users`, `roles`,
`user_firms`, `firms` and the rest: on `platform`, the identity store and the
registry.

Refused now in three places, each tested alone: by name at create, again at
provision (for a row recorded before the create-time check), and in the prune
itself. **Nothing here connects to a database**: the refusals fire before any
engine is used, which is the point of them.
"""

from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config.settings import Environment, Settings
from app.core.database.base import Base
from app.core.database.config import PostgreSQLConfig
from app.core.database.engine import DatabaseManager
from app.core.exceptions import BusinessRuleError
from app.core.tenancy import TenantStorageLifecycleService
from app.core.tenancy import lifecycle as tenancy_lifecycle
from app.core.tenancy.lifecycle import prune_platform_objects
from app.firms.models import Firm
from app.firms.schemas import FirmCreate
from app.firms.services import FirmService

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _service(session: Session) -> FirmService:
    """Build the firm service with this installation's tenancy settings."""
    settings = Settings(
        environment=Environment.TESTING,
        bootstrap_admin_password="test-bootstrap-password",
        database_name="agency_platform",
        database_schema="platform",
    )
    return FirmService(session, tenancy_settings=settings.tenancy)


def _create(**overrides: object) -> FirmCreate:
    """Build a valid firm creation body."""
    payload: dict[str, object] = {
        "name": "Probe Firm",
        "code": "PROBE",
        "country": "IN",
        "currency_code": "INR",
        "financial_year_start": date(2026, 4, 1),
    }
    payload.update(overrides)
    return FirmCreate(**payload)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# At create
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema",
    ["firm_shared", "platform", "public", "information_schema", "pg_catalog", "PUBLIC"],
)
@pytest.mark.parametrize("mode", ["SCHEMA", "DATABASE"])
def test_a_dedicated_firm_cannot_name_a_reserved_schema(schema: str, mode: str) -> None:
    """The live probe, and the schema whose prune takes the registry with it."""
    session = _session()

    with pytest.raises(BusinessRuleError, match="reserved"):
        _service(session).create(
            _create(deployment_mode=mode, schema_name=schema), _ACTOR
        )

    assert session.scalar(select(Firm.id)) is None


@pytest.mark.parametrize("database", ["agency_platform", "postgres", "template1"])
def test_a_database_firm_cannot_name_the_platform_or_server_database(
    database: str,
) -> None:
    """The platform's own database, and the server's, are nobody's firm store."""
    session = _session()

    with pytest.raises(BusinessRuleError, match="reserved"):
        _service(session).create(
            _create(
                deployment_mode="DATABASE",
                database_name=database,
                schema_name="firm_probe",
            ),
            _ACTOR,
        )


def test_the_configured_shared_schema_is_reserved_whatever_it_is_called() -> None:
    """An installation that renamed `firm_shared` is protected under its name."""
    session = _session()
    settings = Settings(
        environment=Environment.TESTING,
        bootstrap_admin_password="test-bootstrap-password",
        tenancy_shared_schema_name="tenants",
    )

    with pytest.raises(BusinessRuleError, match="reserved"):
        FirmService(session, tenancy_settings=settings.tenancy).create(
            _create(deployment_mode="SCHEMA", schema_name="tenants"), _ACTOR
        )


def test_an_ordinary_dedicated_schema_is_still_accepted() -> None:
    """The check refuses names, not the modes."""
    session = _session()

    firm = _service(session).create(
        _create(deployment_mode="SCHEMA", schema_name="wholesale_hub"), _ACTOR
    )

    assert firm.schema_name == "wholesale_hub"


def test_the_names_are_compared_the_way_people_mean_them() -> None:
    """Case and surrounding space do not make a reserved name somebody's."""
    assert tenancy_lifecycle.is_reserved_schema(" Platform ")
    assert tenancy_lifecycle.is_reserved_schema("pg_toast")
    assert not tenancy_lifecycle.is_reserved_schema("firm_platformer")


# --------------------------------------------------------------------------
# At provision, and in the prune
# --------------------------------------------------------------------------


def _lifecycle() -> TenantStorageLifecycleService:
    """Build the lifecycle over a platform database it never connects to."""
    return TenantStorageLifecycleService(
        DatabaseManager(
            PostgreSQLConfig(
                host="localhost",
                port=5432,
                database="agency_platform",
                username="postgres",
                password="postgres",
                pool_size=1,
                max_overflow=0,
                pool_recycle_seconds=1800,
                default_schema="platform",
            )
        )
    )


@pytest.mark.parametrize(
    ("mode", "database", "schema"),
    [
        ("SCHEMA", "agency_platform", "firm_shared"),
        ("SCHEMA", "agency_platform", "platform"),
        ("DATABASE", "erp_probe", "pg_catalog"),
        ("DATABASE", "agency_platform", "firm_probe"),
    ],
)
def test_provisioning_refuses_a_reserved_store_recorded_before_the_check(
    mode: str, database: str, schema: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence in depth: nothing is created, migrated or pruned."""
    lifecycle = _lifecycle()
    touched: list[str] = []
    for step in (
        "_create_schema_if_missing",
        "_create_database_if_missing",
        "_run_migrations",
        "_prune_platform_objects",
    ):
        monkeypatch.setattr(
            lifecycle, step, lambda *args, _step=step, **kwargs: touched.append(_step)
        )
    firm = SimpleNamespace(
        id=uuid4(),
        deployment_mode=mode,
        database_name=database,
        schema_name=schema,
        database_type="postgresql",
        connection_profile=None,
    )

    with pytest.raises(BusinessRuleError, match="reserved"):
        lifecycle.provision_new_firm(firm)  # type: ignore[arg-type]

    assert touched == []


@pytest.mark.parametrize("schema", ["platform", "public", "PG_CATALOG"])
def test_the_prune_refuses_the_platform_and_server_schemas(schema: str) -> None:
    """The last lock, before any engine is built."""
    with pytest.raises(BusinessRuleError, match="reserved"):
        prune_platform_objects(
            # SQLite: were the refusal missing, the prune would be a no-op and
            # this would fail on `raises` rather than try a real server.
            database_url="sqlite://",
            schema_name=schema,
        )


def test_the_prune_still_runs_on_the_shared_firm_store() -> None:
    """`firm_shared` is a firm store the reset script and CI prune on purpose."""
    prune_platform_objects(database_url="sqlite://", schema_name="firm_shared")
