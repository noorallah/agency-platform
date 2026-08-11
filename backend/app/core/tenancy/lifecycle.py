"""Tenant storage lifecycle services for schema/database provisioning."""

import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.core.config.settings import ConnectionProfileSettings
from app.core.database.config import DatabaseConfig, DatabaseDialect
from app.core.database.engine import DatabaseManager
from app.core.exceptions import BusinessRuleError
from app.core.tenancy.connections import (
    build_tenant_database_config,
    resolve_connection_profile,
)
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
    # Crash and server-error reports are deliberately platform-only: support
    # reads one trail, and a report is written before any firm is resolved.
    # Listed here so a firm store never keeps a stray copy, and so the platform
    # store keeps it -- reset_tenancy_layout drops everything absent from this
    # list from the platform schema.
    "error_reports",
)


def _safe_identifier(value: str, label: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise BusinessRuleError(f"Invalid {label}: {value!r}.")
    return value


def prune_platform_objects(*, database_url: str, schema_name: str) -> None:
    """Drop the platform-owned tables from a firm store.

    Alembic migrates one schema per run and every migration targets whichever
    schema it was pointed at, so a freshly migrated firm store also carries
    ``firms``, ``users``, ``roles`` and the rest. They are not the firm's to
    hold: the registry and identity live in the platform store alone, and a
    tenant session must not be able to resolve them. Every path that builds a
    firm store therefore migrates and then prunes -- dedicated provisioning
    below, ``scripts/reset_tenancy_layout.py`` for the shared schema, and CI.

    Safe to repeat, and a no-op on dialects other than PostgreSQL.
    """
    schema = _safe_identifier(schema_name, "schema name")
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            if connection.dialect.name != "postgresql":
                return
            for table_name in _PLATFORM_TABLES:
                quoted_table = _safe_identifier(table_name, "table name")
                connection.execute(
                    text(f'DROP TABLE IF EXISTS "{schema}"."{quoted_table}" CASCADE')
                )
            # `reject_audit_log_mutation()` is deliberately left alone. Every
            # schema owns its own copy of that function and of the
            # TR_audit_logs_append_only trigger that calls it (20260809_0043),
            # and the firm keeps its own audit_logs -- the trail is per store.
            # Dropping the function CASCADE took the firm's trigger with it, so
            # every dedicated store provisioned this way had a rewritable audit
            # trail while CLAUDE.md called it immutable.
    finally:
        engine.dispose()


class TenantStorageLifecycleService:
    """Create dedicated tenant storage and bootstrap schema migrations."""

    def __init__(
        self,
        platform_database: DatabaseManager,
        connection_profiles: Mapping[str, ConnectionProfileSettings] | None = None,
    ) -> None:
        """Bind platform database configuration and Alembic entrypoint."""
        self._platform_database = platform_database
        self._connection_profiles = connection_profiles or {}
        self._project_root = Path(__file__).resolve().parents[3]
        self._alembic_ini = (self._project_root / "alembic.ini").as_posix()
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
                    connection_profile=firm.connection_profile,
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
        """Upgrade one target to head in a subprocess.

        This used to run Alembic in-process with ``AGENCY_DATABASE_URL`` and
        ``AGENCY_DATABASE_SCHEMA`` set through ``os.environ``. Those are
        process-wide: two concurrent provisions raced on them, and any other
        request that read settings while one was running could resolve the
        wrong database. A subprocess gets its own environment and cannot reach
        into this one.
        """
        environment = dict(os.environ)
        environment["AGENCY_DATABASE_URL"] = database_url
        environment["AGENCY_DATABASE_SCHEMA"] = schema_name
        completed = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                self._alembic_ini,
                "upgrade",
                "head",
            ],
            cwd=self._project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise BusinessRuleError(
                f"Migrating tenant storage for schema '{schema_name}' failed: "
                f"{detail[-600:]}"
            )

    def _seed_defaults(self, tenant: TenantContext) -> None:
        """Seed tenant defaults. Data seeding stays intentionally minimal here."""
        if self._seed_handler is not None:
            self._seed_handler(tenant)

    def _build_database_config_for_firm(self, firm: Firm) -> DatabaseConfig:
        if firm.database_name is None or not firm.database_name.strip():
            raise BusinessRuleError("database_name is required for dedicated firms.")
        if firm.schema_name is None or not firm.schema_name.strip():
            raise BusinessRuleError("schema_name is required for dedicated firms.")
        return build_tenant_database_config(
            self._platform_database.config,
            database_name=firm.database_name,
            schema_name=firm.schema_name,
            database_type=firm.database_type,
            profile=resolve_connection_profile(
                self._connection_profiles, firm.connection_profile
            ),
        )

    def _prune_platform_objects(self, *, database_url: str, schema_name: str) -> None:
        """Remove platform tables from tenant-dedicated storage."""
        prune_platform_objects(database_url=database_url, schema_name=schema_name)
