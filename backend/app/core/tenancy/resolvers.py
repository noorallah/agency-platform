"""Default tenancy resolvers backed by the platform firm registry."""

from uuid import UUID

from fastapi import Request
from sqlalchemy import select

from app.core.database.config import (
    DatabaseConfig,
    DatabaseDialect,
    MySQLConfig,
    PostgreSQLConfig,
)
from app.core.database.engine import DatabaseManager
from app.core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ResourceNotFoundError,
)
from app.core.tenancy.contracts import (
    ConnectionResolver,
    SchemaResolver,
    TenantResolver,
)
from app.core.tenancy.models import DeploymentMode, TenantContext
from app.firms.models import Firm, FirmStorageMapping


class FirmRegistryTenantResolver(TenantResolver):
    """Resolve tenant context from `X-Firm-ID` and firm registry metadata."""

    def __init__(
        self,
        platform_database: DatabaseManager,
        *,
        shared_database_name: str,
        shared_schema_name: str,
    ) -> None:
        """Bind platform database access used for firm-registry lookups."""
        self._platform_database = platform_database
        self._shared_database_name = shared_database_name
        self._shared_schema_name = shared_schema_name

    def resolve(self, request: Request) -> TenantContext | None:
        """Resolve a tenant from request headers, or return None for platform scope."""
        value = request.headers.get("X-Firm-ID")
        if value is None:
            return None
        try:
            firm_id = UUID(value)
        except ValueError as error:
            raise AuthorizationError(
                "X-Firm-ID must be a valid firm identifier."
            ) from error
        with self._platform_database.sessions(
            schema=self._platform_database.config.default_schema
        ).session() as session:
            firm = session.scalar(
                select(Firm).where(
                    Firm.id == firm_id,
                    Firm.is_active.is_(True),
                    Firm.is_deleted.is_(False),
                )
            )
            if firm is None:
                raise ResourceNotFoundError("Firm not found.")
            mapping = session.scalar(
                select(FirmStorageMapping).where(
                    FirmStorageMapping.firm_id == firm.id,
                    FirmStorageMapping.is_active.is_(True),
                    FirmStorageMapping.is_deleted.is_(False),
                )
            )
        mode = (
            DeploymentMode.SHARED
            if mapping is None
            else DeploymentMode(mapping.deployment_mode)
        )
        database_type = "postgresql" if mapping is None else mapping.database_type
        if mode is DeploymentMode.SHARED:
            database_name = self._shared_database_name
            schema_name = self._shared_schema_name
        else:
            if (
                mapping is None
                or mapping.database_name is None
                or mapping.schema_name is None
            ):
                raise BusinessRuleError(
                    "Dedicated firms must define database_name and schema_name."
                )
            database_name = mapping.database_name
            schema_name = mapping.schema_name
        return TenantContext(
            firm_id=firm.id,
            deployment_mode=mode,
            database_name=database_name,
            schema_name=schema_name,
            database_type=database_type,
        )


class FirmConnectionResolver(ConnectionResolver):
    """Resolve tenant connection settings from the firm registry."""

    def __init__(
        self, platform_database: DatabaseManager, connection_profiles: object
    ) -> None:
        """Bind platform database configuration as the connection baseline."""
        self._platform_database = platform_database
        _ = connection_profiles

    def resolve(self, tenant: TenantContext) -> DatabaseConfig:
        """Build a tenant-specific database config from the resolved context."""
        base = self._platform_database.config
        dialect = DatabaseDialect(tenant.database_type.lower())
        if dialect is not base.dialect:
            raise BusinessRuleError(
                "Firm database_type must match platform database dialect "
                f"({base.dialect.value})."
            )
        config_class = (
            PostgreSQLConfig
            if dialect is DatabaseDialect.POSTGRESQL
            else MySQLConfig
        )
        default_port = 5432 if dialect is DatabaseDialect.POSTGRESQL else 3306
        return config_class(
            host=base.host,
            port=base.port or default_port,
            database=tenant.database_name,
            username=base.username,
            password=base.password,
            pool_size=base.pool_size,
            max_overflow=base.max_overflow,
            pool_recycle_seconds=base.pool_recycle_seconds,
            default_schema=tenant.schema_name,
            url_override=None,
        )


class FirmSchemaResolver(SchemaResolver):
    """Resolve the tenant schema from resolved tenant context."""

    def resolve(self, tenant: TenantContext) -> str:
        """Return the schema selected in the firm registry."""
        return tenant.schema_name
