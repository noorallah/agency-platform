"""Default tenancy resolvers backed by the platform firm registry."""

from collections.abc import Mapping
from uuid import UUID

from fastapi import Request
from sqlalchemy import select

from app.core.config.settings import ConnectionProfileSettings
from app.core.database.config import DatabaseConfig
from app.core.database.engine import DatabaseManager
from app.core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ResourceNotFoundError,
)
from app.core.tenancy.connections import (
    build_tenant_database_config,
    resolve_connection_profile,
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
        return self.resolve_firm(firm_id)

    def resolve_firm(self, firm_id: UUID) -> TenantContext:
        """Resolve one firm's storage, whoever is asking and from where.

        Split out of :meth:`resolve` so a **platform** endpoint can reach a
        firm's own store rather than whichever store the caller's `X-Firm-ID`
        happens to name. Anything owned by a firm but administered from a
        platform screen needs this: a business profile assignment lives in the
        firm's store, so reading it on the caller's session answered for the
        wrong firm, and writing it put the row in the wrong store while
        reporting success.

        Args:
            firm_id: The firm whose storage is wanted.

        Returns:
            The tenant context for that firm.

        Raises:
            ResourceNotFoundError: If no active firm has that id.
            BusinessRuleError: If dedicated storage is unusable or unprovisioned.

        """
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
            # Dedicated storage is built by an explicit provisioning action, so
            # until that has succeeded the schema is either absent or empty.
            # Serving the request anyway produces "relation does not exist" from
            # somewhere deep in a query, which reads as a bug rather than as the
            # one remaining setup step.
            if mapping.provisioned_at is None:
                raise BusinessRuleError(
                    f"Firm storage for '{firm.code}' has not been provisioned yet. "
                    "Run the provisioning action for this firm before using it."
                )
            database_name = mapping.database_name
            schema_name = mapping.schema_name
        return TenantContext(
            firm_id=firm.id,
            deployment_mode=mode,
            database_name=database_name,
            schema_name=schema_name,
            database_type=database_type,
            connection_profile=None if mapping is None else mapping.connection_profile,
        )


class FirmConnectionResolver(ConnectionResolver):
    """Resolve tenant connection settings from the firm registry."""

    def __init__(
        self,
        platform_database: DatabaseManager,
        connection_profiles: Mapping[str, ConnectionProfileSettings] | None = None,
    ) -> None:
        """Bind the platform baseline and the configured connection profiles."""
        self._platform_database = platform_database
        self._connection_profiles = connection_profiles or {}

    def resolve(self, tenant: TenantContext) -> DatabaseConfig:
        """Build a tenant-specific database config from the resolved context."""
        return build_tenant_database_config(
            self._platform_database.config,
            database_name=tenant.database_name,
            schema_name=tenant.schema_name,
            database_type=tenant.database_type,
            profile=resolve_connection_profile(
                self._connection_profiles, tenant.connection_profile
            ),
        )


class FirmSchemaResolver(SchemaResolver):
    """Resolve the tenant schema from resolved tenant context."""

    def resolve(self, tenant: TenantContext) -> str:
        """Return the schema selected in the firm registry."""
        return tenant.schema_name
