"""Database provider that reuses the platform manager and caches tenant managers."""

from threading import Lock

from app.core.database.engine import DatabaseManager
from app.core.tenancy.contracts import (
    ConnectionResolver,
    DatabaseProvider,
    SchemaResolver,
)
from app.core.tenancy.models import DeploymentMode, TenantContext


class MultiTenantDatabaseProvider(DatabaseProvider):
    """Provide database managers for platform and tenant data requests."""

    def __init__(
        self,
        platform_database: DatabaseManager,
        connection_resolver: ConnectionResolver,
        schema_resolver: SchemaResolver,
    ) -> None:
        """Initialize provider with platform manager and tenant resolvers."""
        self._platform_database = platform_database
        self._connection_resolver = connection_resolver
        self._schema_resolver = schema_resolver
        self._lock = Lock()
        self._managers: dict[str, DatabaseManager] = {}

    def manager_for(self, tenant: TenantContext) -> DatabaseManager:
        """Return the appropriate shared or dedicated database manager."""
        if tenant.deployment_mode in {DeploymentMode.SHARED, DeploymentMode.SCHEMA}:
            return self._platform_database
        key = f"{tenant.database_type}:{tenant.database_name}:{tenant.schema_name}"
        with self._lock:
            existing = self._managers.get(key)
            if existing is not None:
                return existing
            manager = DatabaseManager(self._connection_resolver.resolve(tenant))
            self._managers[key] = manager
            return manager

    def schema_for(self, tenant: TenantContext) -> str:
        """Return the schema to apply on sessions opened for this tenant."""
        return self._schema_resolver.resolve(tenant)

    def dispose(self) -> None:
        """Dispose all dedicated-tenant managers owned by this provider."""
        with self._lock:
            managers = list(self._managers.values())
            self._managers.clear()
        for manager in managers:
            manager.dispose()
