"""Tenancy architecture exports."""

from app.core.tenancy.contracts import (
    ConnectionResolver,
    DatabaseProvider,
    SchemaResolver,
    TenantResolver,
)
from app.core.tenancy.lifecycle import TenantStorageLifecycleService
from app.core.tenancy.models import DeploymentMode, TenantContext
from app.core.tenancy.provider import MultiTenantDatabaseProvider
from app.core.tenancy.resolvers import (
    FirmConnectionResolver,
    FirmRegistryTenantResolver,
    FirmSchemaResolver,
)

__all__ = [
    "ConnectionResolver",
    "DatabaseProvider",
    "DeploymentMode",
    "FirmConnectionResolver",
    "FirmRegistryTenantResolver",
    "FirmSchemaResolver",
    "MultiTenantDatabaseProvider",
    "SchemaResolver",
    "TenantContext",
    "TenantResolver",
    "TenantStorageLifecycleService",
]
