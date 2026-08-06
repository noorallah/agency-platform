"""Core tenancy contracts and normalized runtime tenant context."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class DeploymentMode(StrEnum):
    """Supported deployment modes for tenant business data."""

    SHARED = "SHARED"
    SCHEMA = "SCHEMA"
    DATABASE = "DATABASE"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Resolved tenant storage details for one request."""

    firm_id: UUID
    deployment_mode: DeploymentMode
    database_name: str
    schema_name: str
    database_type: str
