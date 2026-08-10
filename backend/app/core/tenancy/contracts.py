"""Pluggable tenancy interfaces for resolution and connection provisioning."""

from abc import ABC, abstractmethod

from fastapi import Request

from app.core.database.config import DatabaseConfig
from app.core.database.engine import DatabaseManager
from app.core.tenancy.models import TenantContext


class TenantResolver(ABC):
    """Resolve tenant context for an incoming request."""

    @abstractmethod
    def resolve(self, request: Request) -> TenantContext | None:
        """Return a tenant context, or None when request is platform-scoped."""


class ConnectionResolver(ABC):
    """Resolve a tenant-specific database connection configuration."""

    @abstractmethod
    def resolve(self, tenant: TenantContext) -> DatabaseConfig:
        """Return the target database configuration for the tenant."""


class SchemaResolver(ABC):
    """Resolve the SQL schema to use for the tenant session."""

    @abstractmethod
    def resolve(self, tenant: TenantContext) -> str:
        """Return a safe schema identifier for tenant business queries."""


class DatabaseProvider(ABC):
    """Provide configured database managers for tenant contexts."""

    @abstractmethod
    def manager_for(self, tenant: TenantContext) -> DatabaseManager:
        """Return a database manager suitable for the tenant context."""

    @abstractmethod
    def dispose(self) -> None:
        """Dispose any internally owned database managers."""
