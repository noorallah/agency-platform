"""Tenant storage lifecycle services for schema/database provisioning."""

import re
from collections.abc import Callable, Mapping

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
from app.core.tenancy.migrations import upgrade_store
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
    # Job templates are identity: `IdentityService` reads them on the platform
    # session only. Absent from this list, every firm store kept a copy of
    # the seeded eleven that nothing read (D-IDN-10).
    "user_template_roles",
    "user_templates",
    # Crash and server-error reports are deliberately platform-only: support
    # reads one trail, and a report is written before any firm is resolved.
    # Listed here so a firm store never keeps a stray copy, and so the platform
    # store keeps it -- reset_tenancy_layout drops everything absent from this
    # list from the platform schema.
    "error_reports",
)


#: Schemas that belong to somebody other than a dedicated firm: the platform
#: store, the store every SHARED firm lives in, and PostgreSQL's own. A
#: dedicated firm routed to one of these would be migrated and **pruned** there
#: -- `DROP TABLE ... CASCADE` of `users`, `roles`, `firms` and the rest -- which
#: on `platform` is the identity store and the registry (D-IDN-4). Anything
#: starting `pg_` is PostgreSQL's too. Compared case-insensitively: a quoted
#: `"Platform"` is a different schema, but nobody means it as one.
RESERVED_SCHEMA_NAMES = frozenset(
    {"platform", "firm_shared", "public", "information_schema"}
)

#: Schemas `prune_platform_objects` refuses outright. Not `firm_shared`: it is a
#: firm store, and `scripts/reset_tenancy_layout.py` and CI prune it on purpose.
_NEVER_PRUNED = frozenset({"platform", "public", "information_schema"})

#: Databases a DATABASE-mode firm may not name: the server's own, before the
#: platform's database is added by whoever knows it.
RESERVED_DATABASE_NAMES = frozenset(
    {
        "postgres",
        "template0",
        "template1",
        "mysql",
        "sys",
        "information_schema",
        "performance_schema",
    }
)


def is_reserved_schema(name: str, *, also: frozenset[str] = frozenset()) -> bool:
    """Return whether a schema name belongs to the platform or the server.

    Args:
        name: The schema a firm would be routed to.
        also: Further names reserved by this installation's configuration --
            the platform schema and the shared schema as configured.

    Returns:
        True when no dedicated firm may be given the schema.

    """
    folded = name.strip().lower()
    reserved = RESERVED_SCHEMA_NAMES | {item.strip().lower() for item in also}
    return folded in reserved or folded.startswith("pg_")


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

    **Refuses the platform schema, `public`, `information_schema` and any
    `pg_*` schema**, as defence in depth behind the create-time refusal
    (D-IDN-4): pruning `platform` drops the identity store and the firm
    registry. `firm_shared` is allowed -- it is a firm store, pruned on
    purpose by the reset script and by CI.

    Raises:
        BusinessRuleError: If the schema is one that must never be pruned.

    """
    folded = schema_name.strip().lower()
    if folded in _NEVER_PRUNED or folded.startswith("pg_"):
        raise BusinessRuleError(
            f"Refusing to prune platform tables from the reserved schema "
            f"{schema_name!r}."
        )
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
        """Bind platform database configuration and connection profiles."""
        self._platform_database = platform_database
        self._connection_profiles = connection_profiles or {}
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
        self._assert_not_reserved(mode, schema_name, database_name)
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

    def _assert_not_reserved(
        self, mode: DeploymentMode, schema_name: str, database_name: str
    ) -> None:
        """Refuse to build a dedicated store on top of somebody else's.

        The create-time refusal in `FirmService` stops a new firm naming a
        reserved store; this stops provisioning one that was recorded before
        that refusal existed, since provisioning migrates the schema and then
        prunes it (D-IDN-4). Nothing is touched when it fires.

        Raises:
            BusinessRuleError: If the schema or database is reserved.

        """
        platform = self._platform_database.config
        also = frozenset({platform.default_schema} if platform.default_schema else ())
        if is_reserved_schema(schema_name, also=also):
            raise BusinessRuleError(
                f"The schema {schema_name!r} is reserved and cannot hold a "
                "dedicated firm."
            )
        if mode is DeploymentMode.DATABASE:
            platform_database = make_url(platform.url).database or ""
            reserved = RESERVED_DATABASE_NAMES | {platform_database.lower()}
            if database_name.strip().lower() in reserved:
                raise BusinessRuleError(
                    f"The database {database_name!r} is reserved and cannot "
                    "hold a dedicated firm."
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
        """Upgrade the store this firm was just given, to head.

        This used to run Alembic in-process with ``AGENCY_DATABASE_URL`` and
        ``AGENCY_DATABASE_SCHEMA`` set through ``os.environ``. Those are
        process-wide: two concurrent provisions raced on them, and any other
        request that read settings while one was running could resolve the
        wrong database. The answer then was a subprocess, which gets its own
        environment and cannot reach into this one.

        It runs in this process again as of 2026-09-17, without giving that
        back -- ``upgrade_store`` passes the target on Alembic's ``Config``
        rather than through the environment, and holds a lock while it runs.
        The reason for the change is that ``sys.executable -m alembic`` cannot
        work in a compiled build: the executable is the application, and there
        is no ``alembic`` module to hand it. Creating a firm would have failed
        on a packaged installation, which is the one flow a customer performs
        on their own.
        """
        try:
            upgrade_store(database_url=database_url, schema_name=schema_name)
        except Exception as error:  # noqa: BLE001 - the message is the point
            detail = str(error).strip()
            raise BusinessRuleError(
                f"Migrating tenant storage for schema '{schema_name}' failed: "
                f"{detail[-600:]}"
            ) from error

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
