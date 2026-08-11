"""Build tenant database connections from the platform baseline and profiles.

Both the request path (`FirmConnectionResolver`) and the provisioning path
(`TenantStorageLifecycleService`) have to answer the same question -- *which
server, which credentials, which database* -- and they have to answer it
identically. When they disagree, provisioning builds the tables on one host and
every request looks for them on another, which is a failure that only shows up
after a firm has been created. One function, used by both.
"""

from collections.abc import Mapping

from app.core.config.settings import ConnectionProfileSettings
from app.core.database.config import (
    DatabaseConfig,
    DatabaseDialect,
    MySQLConfig,
    PostgreSQLConfig,
)
from app.core.exceptions import BusinessRuleError

_DEFAULT_PORTS = {
    DatabaseDialect.POSTGRESQL: 5432,
    DatabaseDialect.MYSQL: 3306,
}


def resolve_connection_profile(
    profiles: Mapping[str, ConnectionProfileSettings] | None,
    name: str | None,
) -> ConnectionProfileSettings | None:
    """Return the named connection profile, or None for the platform server.

    An unknown name is refused rather than silently falling back: falling back
    would put a firm's data on the platform server when an administrator asked
    for a different one, and nothing afterwards would report the difference.
    """
    if name is None or not name.strip():
        return None
    key = name.strip().upper()
    profile = (profiles or {}).get(key)
    if profile is None:
        raise BusinessRuleError(
            f"Connection profile '{key}' is not configured. "
            "Add it to AGENCY_TENANCY_CONNECTION_PROFILES."
        )
    return profile


def build_tenant_database_config(
    base: DatabaseConfig,
    *,
    database_name: str,
    schema_name: str,
    database_type: str,
    profile: ConnectionProfileSettings | None,
) -> DatabaseConfig:
    """Build one tenant's connection, overriding the baseline with its profile.

    Without a profile the tenant is a different database on the platform server,
    which is the behaviour every firm had before profiles were honoured.
    """
    dialect = DatabaseDialect(database_type.lower())
    if dialect is not base.dialect:
        raise BusinessRuleError(
            "Firm database_type must match platform database dialect "
            f"({base.dialect.value})."
        )
    config_class = (
        PostgreSQLConfig if dialect is DatabaseDialect.POSTGRESQL else MySQLConfig
    )
    host = base.host
    port = base.port or _DEFAULT_PORTS[dialect]
    username = base.username
    password = base.password
    if profile is not None:
        host = profile.database_host or host
        port = profile.database_port or port
        username = profile.username
        password = profile.password
    return config_class(
        dialect=dialect,
        host=host,
        port=port,
        database=database_name,
        username=username,
        password=password,
        pool_size=base.pool_size,
        max_overflow=base.max_overflow,
        pool_recycle_seconds=base.pool_recycle_seconds,
        default_schema=schema_name,
        # AGENCY_DATABASE_URL names the platform database specifically. Letting
        # it through here would point every tenant connection back at it.
        url_override=None,
    )
