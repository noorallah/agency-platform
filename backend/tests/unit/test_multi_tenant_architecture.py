"""Multi-tenant architecture unit tests for resolver/provider wiring."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config.settings import Environment, Settings
from app.core.database.base import Base
from app.core.database.config import PostgreSQLConfig
from app.core.database.engine import DatabaseManager
from app.core.exceptions import BusinessRuleError
from app.core.tenancy import (
    DeploymentMode,
    FirmConnectionResolver,
    FirmRegistryTenantResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantContext,
)
from app.firms.models import Firm, FirmStorageMapping
from app.firms.schemas import FirmCreate
from app.firms.services import FirmService


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _platform_database() -> DatabaseManager:
    return DatabaseManager(
        PostgreSQLConfig(
            host="localhost",
            port=5432,
            database="agency_platform",
            username="postgres",
            password="postgres",
            pool_size=5,
            max_overflow=10,
            pool_recycle_seconds=1800,
            default_schema="platform",
        )
    )


def _tenant_resolver(platform: DatabaseManager) -> FirmRegistryTenantResolver:
    return FirmRegistryTenantResolver(
        platform,
        shared_database_name="agency_platform",
        shared_schema_name="firm_shared",
    )


def _settings(profiles: str | None = None) -> Settings:
    return Settings(
        environment=Environment.TESTING,
        bootstrap_admin_password="test-bootstrap-password",
        tenancy_connection_profiles=profiles,
    )


def _request_with_firm(firm_id: str | None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/customers",
        "headers": [],
    }
    if firm_id is not None:
        scope["headers"] = [(b"x-firm-id", firm_id.encode("utf-8"))]
    return Request(scope)


def test_firm_service_applies_registry_defaults_for_shared_mode() -> None:
    """Ensure new firm registry fields are auto-populated in shared mode."""
    session = _session()
    firm = FirmService(session).create(
        FirmCreate(
            name="Acme",
            code="ACME",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        ),
        actor_id=uuid4(),
    )
    assert firm.deployment_mode == DeploymentMode.SHARED.value
    assert firm.database_name is None
    assert firm.schema_name is None
    assert firm.database_type == "postgresql"


def test_tenant_resolver_reads_firm_registry() -> None:
    """Resolve deployment/database/schema metadata from firm registry."""
    session = _session()
    firm = Firm(
        name="Schema Firm",
        code="SCHEMA_FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()
    session.add(
        FirmStorageMapping(
            firm_id=firm.id,
            deployment_mode=DeploymentMode.SCHEMA.value,
            schema_name="firm_schema_firm",
            database_name="agency_platform",
            database_type="postgresql",
            is_active=True,
        )
    )
    session.commit()

    platform = _platform_database()
    platform.session_factory = sessionmaker(bind=session.bind, expire_on_commit=False)
    tenant = _tenant_resolver(platform).resolve(_request_with_firm(str(firm.id)))
    assert tenant is not None
    assert tenant.deployment_mode is DeploymentMode.SCHEMA
    assert tenant.schema_name == "firm_schema_firm"
    platform.dispose()


def test_tenant_resolver_applies_shared_defaults() -> None:
    """Resolve shared firm storage from tenancy defaults, not firm columns."""
    session = _session()
    firm = Firm(
        name="Shared Firm",
        code="SHARED_FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()
    session.add(
        FirmStorageMapping(
            firm_id=firm.id,
            deployment_mode=DeploymentMode.SHARED.value,
            schema_name=None,
            database_name=None,
            database_type="postgresql",
            is_active=True,
        )
    )
    session.commit()

    platform = _platform_database()
    platform.session_factory = sessionmaker(bind=session.bind, expire_on_commit=False)
    tenant = _tenant_resolver(platform).resolve(_request_with_firm(str(firm.id)))

    assert tenant is not None
    assert tenant.deployment_mode is DeploymentMode.SHARED
    assert tenant.database_name == "agency_platform"
    assert tenant.schema_name == "firm_shared"
    platform.dispose()


def test_database_provider_uses_platform_for_non_database_modes() -> None:
    """Ensure shared and schema modes reuse the platform database manager."""
    platform = _platform_database()
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, _settings().tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    shared = provider.manager_for(
        TenantContext(
            firm_id=uuid4(),
            deployment_mode=DeploymentMode.SHARED,
            database_name="agency_platform",
            schema_name="firm_shared",
            database_type="postgresql",
        )
    )
    assert shared is platform
    provider.dispose()
    platform.dispose()


def test_connection_resolver_uses_platform_connection() -> None:
    """Resolve DATABASE mode connections from platform credentials."""
    platform = _platform_database()
    resolver = FirmConnectionResolver(
        platform, _settings().tenancy.connection_profiles
    )
    tenant = TenantContext(
        firm_id=uuid4(),
        deployment_mode=DeploymentMode.DATABASE,
        database_name="erp_firm_a",
        schema_name="public",
        database_type="postgresql",
    )

    config = resolver.resolve(tenant)

    assert config.username == "postgres"
    assert config.password.get_secret_value() == "postgres"
    assert config.host == "localhost"
    assert config.port == 5432
    platform.dispose()


def test_connection_resolver_rejects_mismatched_tenant_database_type() -> None:
    """Reject a tenant row database_type that differs from platform dialect."""
    platform = _platform_database()
    resolver = FirmConnectionResolver(
        platform, _settings().tenancy.connection_profiles
    )
    tenant = TenantContext(
        firm_id=uuid4(),
        deployment_mode=DeploymentMode.DATABASE,
        database_name="erp_firm_a",
        schema_name="public",
        database_type="mysql",
    )

    with pytest.raises(BusinessRuleError):
        resolver.resolve(tenant)
    platform.dispose()


def test_firm_service_uses_configured_schema_prefix_defaults() -> None:
    """Apply configured shared schema and dedicated schema prefix defaults."""
    session = _session()
    settings = _settings()
    tenancy = settings.tenancy.model_copy(
        update={
            "shared_schema_name": "firm_shared",
            "dedicated_schema_prefix": "org_",
        }
    )
    shared = FirmService(session, tenancy_settings=tenancy).create(
        FirmCreate(
            name="Shared Firm",
            code="S1",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
            deployment_mode=DeploymentMode.SHARED,
        ),
        actor_id=uuid4(),
    )
    dedicated = FirmService(session, tenancy_settings=tenancy).create(
        FirmCreate(
            name="Dedicated Firm",
            code="D1",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
            deployment_mode=DeploymentMode.SCHEMA,
        ),
        actor_id=uuid4(),
    )
    assert shared.schema_name is None
    assert dedicated.schema_name == "org_d1"


def test_firm_service_defaults_to_shared_mode_without_payload_mode() -> None:
    """Default omitted deployment mode to SHARED for new firms."""
    session = _session()
    firm = FirmService(session).create(
        FirmCreate(
            name="Shared Default Firm",
            code="SDF1",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        ),
        actor_id=uuid4(),
    )
    assert firm.deployment_mode == DeploymentMode.SHARED.value
    assert firm.schema_name is None


def test_settings_parses_database_slot_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse AGENCY_DATABASE<n>_* variables into connection profiles."""
    monkeypatch.setenv("AGENCY_DATABASE1_HOST", "10.0.0.25")
    monkeypatch.setenv("AGENCY_DATABASE1_PORT", "5432")
    monkeypatch.setenv("AGENCY_DATABASE1_TYPE", "postgresql")
    monkeypatch.setenv("AGENCY_DATABASE1_USERNAME", "tenant_user")
    monkeypatch.setenv("AGENCY_DATABASE1_PASSWORD", "tenant_password")

    settings = _settings()
    profile = settings.tenancy.connection_profiles["DATABASE1"]

    assert profile.database_host == "10.0.0.25"
    assert profile.database_port == 5432
    assert profile.database_type is not None
    assert profile.username == "tenant_user"


def test_firm_service_rejects_mismatched_database_type() -> None:
    """Reject a firm database_type that differs from the platform dialect."""
    session = _session()
    with pytest.raises(BusinessRuleError):
        FirmService(session).create(
            FirmCreate(
                name="MySQL Firm",
                code="MYSQL1",
                country="IN",
                currency_code="INR",
                financial_year_start=date(2026, 4, 1),
                database_type="mysql",
            ),
            actor_id=uuid4(),
        )


def test_settings_reject_mismatched_profile_database_type() -> None:
    """Reject profile database types that differ from platform dialect."""
    with pytest.raises(ValueError):
        _ = _settings(
            profiles=(
                '{"REMOTE_A":{"username":"tenant_user",'
                '"password":"tenant_password","database_type":"mysql"}}'
            )
        ).tenancy
