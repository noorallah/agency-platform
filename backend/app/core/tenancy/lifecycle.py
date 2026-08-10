"""Tenant storage lifecycle services for schema/database provisioning."""

import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from alembic import command
from app.core.database.config import (
    DatabaseConfig,
    DatabaseDialect,
    MySQLConfig,
    PostgreSQLConfig,
)
from app.core.database.engine import DatabaseManager
from app.core.exceptions import BusinessRuleError
from app.core.tenancy.models import DeploymentMode, TenantContext
from app.firms.models import Firm

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_PLATFORM_TABLES = (
    "users",
    "platform_admins",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "password_history",
    "refresh_tokens",
    "login_history",
    "firms",
    "firm_storage_mappings",
    "user_firms",
    "user_preferences",
)


def _safe_identifier(value: str, label: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise BusinessRuleError(f"Invalid {label}: {value!r}.")
    return value


class TenantStorageLifecycleService:
    """Create dedicated tenant storage and bootstrap schema migrations."""

    def __init__(
        self,
        platform_database: DatabaseManager,
        connection_profiles: object | None = None,
    ) -> None:
        """Bind platform database configuration and Alembic entrypoint."""
        self._platform_database = platform_database
        _ = connection_profiles
        self._alembic_ini = (
            Path(__file__).resolve().parents[3] / "alembic.ini"
        ).as_posix()
        self._seed_handler: Callable[[TenantContext], None] | None = None

    def register_seed_handler(self, handler: Callable[[TenantContext], None]) -> None:
        """Register a pluggable seed handler for tenant default data."""
        self._seed_handler = handler

    def provision_new_firm(self, firm: Firm) -> None:
        """Provision storage resources for dedicated deployments."""
        mode = DeploymentMode(firm.deployment_mode)
        if mode is DeploymentMode.SHARED:
            return
        schema_name = firm.schema_name
        database_name = firm.database_name
        if schema_name is None or not schema_name.strip():
            raise BusinessRuleError("schema_name is required for dedicated firms.")
        if database_name is None or not database_name.strip():
            raise BusinessRuleError("database_name is required for dedicated firms.")
        target_config = self._build_database_config_for_firm(firm)
        target_url = make_url(target_config.url)
        schema = _safe_identifier(schema_name, "schema name")
        if mode is DeploymentMode.SCHEMA:
            self._create_schema_if_missing(target_config, schema, target_url)
            self._run_migrations(
                database_url=target_url.render_as_string(hide_password=False),
                schema_name=schema,
            )
            self._prune_platform_objects(
                database_url=target_url.render_as_string(hide_password=False),
                schema_name=schema,
            )
            self._seed_defaults(
                TenantContext(
                    firm_id=firm.id,
                    deployment_mode=mode,
                    database_name=database_name,
                    schema_name=schema,
                    database_type=target_config.dialect.value,
                )
            )
            return
        dedicated_database = _safe_identifier(database_name, "database name")
        self._create_database_if_missing(target_config, dedicated_database)
        target_url = make_url(target_config.url).set(database=dedicated_database)
        self._create_schema_if_missing(target_config, schema, target_url)
        self._run_migrations(
            database_url=target_url.render_as_string(hide_password=False),
            schema_name=schema,
        )
        self._prune_platform_objects(
            database_url=target_url.render_as_string(hide_password=False),
            schema_name=schema,
        )
        self._seed_defaults(
            TenantContext(
                firm_id=firm.id,
                deployment_mode=mode,
                database_name=database_name,
                schema_name=schema,
                database_type=target_config.dialect.value,
            )
        )

    def _create_schema_if_missing(
        self,
        config: DatabaseConfig,
        schema_name: str,
        target_url: URL | None = None,
    ) -> None:
        schema = _safe_identifier(schema_name, "schema name")
        url = (
            target_url.render_as_string(hide_password=False)
            if target_url is not None
            else config.url
        )
        engine = create_engine(url, pool_pre_ping=True)
        try:
            with engine.begin() as connection:
                if config.dialect is DatabaseDialect.POSTGRESQL:
                    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
                else:
                    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS `{schema}`"))
        finally:
            engine.dispose()

    def _create_database_if_missing(
        self, config: DatabaseConfig, database_name: str
    ) -> None:
        database = _safe_identifier(database_name, "database name")
        if config.dialect is DatabaseDialect.POSTGRESQL:
            admin_url = make_url(config.url).set(database="postgres")
            engine = create_engine(
                admin_url.render_as_string(hide_password=False),
                pool_pre_ping=True,
                isolation_level="AUTOCOMMIT",
            )
            try:
                with engine.connect() as connection:
                    exists = connection.scalar(
                        text("SELECT 1 FROM pg_database WHERE datname = :name"),
                        {"name": database},
                    )
                    if exists is None:
                        connection.execute(text(f'CREATE DATABASE "{database}"'))
            finally:
                engine.dispose()
            return
        if config.dialect is DatabaseDialect.MYSQL:
            admin_url = make_url(config.url).set(database="mysql")
            engine = create_engine(
                admin_url.render_as_string(hide_password=False), pool_pre_ping=True
            )
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text(f"CREATE DATABASE IF NOT EXISTS `{database}`")
                    )
            finally:
                engine.dispose()
            return
        raise BusinessRuleError("Unsupported database dialect for tenant provisioning.")

    def _run_migrations(self, *, database_url: str, schema_name: str) -> None:
        with _temporary_environment(
            {
                "AGENCY_DATABASE_URL": database_url,
                "AGENCY_DATABASE_SCHEMA": schema_name,
            }
        ):
            alembic_config = Config(self._alembic_ini)
            command.upgrade(alembic_config, "head")

    def _seed_defaults(self, tenant: TenantContext) -> None:
        """Seed tenant defaults. Data seeding stays intentionally minimal here."""
        if self._seed_handler is not None:
            self._seed_handler(tenant)

    def _build_database_config_for_firm(self, firm: Firm) -> DatabaseConfig:
        base = self._platform_database.config
        if firm.database_name is None or not firm.database_name.strip():
            raise BusinessRuleError("database_name is required for dedicated firms.")
        if firm.schema_name is None or not firm.schema_name.strip():
            raise BusinessRuleError("schema_name is required for dedicated firms.")
        firm_dialect = DatabaseDialect(firm.database_type.lower())
        if firm_dialect is not base.dialect:
            raise BusinessRuleError(
                "Firm database_type must match platform database dialect "
                f"({base.dialect.value})."
            )
        dialect = base.dialect
        config_class = (
            PostgreSQLConfig if dialect is DatabaseDialect.POSTGRESQL else MySQLConfig
        )
        default_port = 5432 if dialect is DatabaseDialect.POSTGRESQL else 3306
        return config_class(
            dialect=dialect,
            host=base.host,
            port=base.port or default_port,
            database=firm.database_name,
            username=base.username,
            password=base.password,
            pool_size=base.pool_size,
            max_overflow=base.max_overflow,
            pool_recycle_seconds=base.pool_recycle_seconds,
            default_schema=firm.schema_name,
            url_override=None,
        )

    def _prune_platform_objects(self, *, database_url: str, schema_name: str) -> None:
        """Remove platform tables from tenant-dedicated storage."""
        schema = _safe_identifier(schema_name, "schema name")
        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.begin() as connection:
                if connection.dialect.name != "postgresql":
                    return
                for table_name in _PLATFORM_TABLES:
                    quoted_table = _safe_identifier(table_name, "table name")
                    connection.execute(
                        text(
                            f'DROP TABLE IF EXISTS "{schema}"."{quoted_table}" CASCADE'
                        )
                    )
                connection.execute(
                    text(
                        f'DROP FUNCTION IF EXISTS "{schema}".'
                        "reject_audit_log_mutation() CASCADE"
                    )
                )
        finally:
            engine.dispose()


@contextmanager
def _temporary_environment(overrides: dict[str, str]) -> Iterator[None]:
    original = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
