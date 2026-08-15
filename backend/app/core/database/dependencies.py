"""FastAPI dependencies that provide request-scoped database sessions."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import cast
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.database.engine import DatabaseManager
from app.core.tenancy import FirmRegistryTenantResolver, MultiTenantDatabaseProvider


def get_platform_db(request: Request) -> Generator[Session]:
    """Yield a platform-database session for identity/platform modules."""
    database = cast(DatabaseManager, request.app.state.database)
    with database.sessions(schema=database.config.default_schema).session() as session:
        yield session


def get_db(request: Request) -> Generator[Session]:
    """Yield a tenant-aware session while hiding deployment-model details."""
    if _is_platform_path(request.url.path):
        database = cast(DatabaseManager, request.app.state.database)
        sessions = database.sessions(schema=database.config.default_schema)
        with sessions.session() as session:
            yield session
        return
    provider = cast(MultiTenantDatabaseProvider, request.app.state.database_provider)
    resolver = cast(FirmRegistryTenantResolver, request.app.state.tenant_resolver)
    tenant = resolver.resolve(request)
    if tenant is None:
        database = cast(DatabaseManager, request.app.state.database)
        sessions = database.sessions(schema=database.config.default_schema)
        with sessions.session() as session:
            yield session
        return
    manager = provider.manager_for(tenant)
    schema = provider.schema_for(tenant)
    with manager.sessions(schema=schema).session() as session:
        yield session


@contextmanager
def firm_store_session(request: Request, firm_id: UUID) -> Generator[Session]:
    """Open a session against **one named firm's** store.

    `get_db` routes by the caller's `X-Firm-ID`, which is right for a
    firm-scoped request and wrong for a platform screen administering another
    firm: the session lands in the caller's store, so a read answers for the
    wrong firm and a write puts the row somewhere its owner will never see it.
    That is not hypothetical — the business-profile assignment endpoints did
    exactly this, reporting success while changing nothing for the firm named
    in the URL.

    Use it wherever a platform endpoint touches firm-owned data.

    Args:
        request: The live request, for the application's tenancy services.
        firm_id: The firm whose store is wanted.

    Yields:
        A session bound to that firm's database and schema.

    """
    provider = cast(MultiTenantDatabaseProvider, request.app.state.database_provider)
    resolver = cast(FirmRegistryTenantResolver, request.app.state.tenant_resolver)
    tenant = resolver.resolve_firm(firm_id)
    manager = provider.manager_for(tenant)
    schema = provider.schema_for(tenant)
    with manager.sessions(schema=schema).session() as session:
        yield session


def _is_platform_path(path: str) -> bool:
    prefixes = (
        "/health",
        "/api/v1/auth",
        "/api/v1/users",
        "/api/v1/roles",
        "/api/v1/permissions",
        "/api/v1/firms",
        "/api/v1/dashboard",
        "/api/v1/me",
        # Error reports are operational telemetry for whoever maintains the
        # product, so they live in one place rather than scattered across firm
        # stores. `firm_id` is recorded as data, not used as routing.
        "/api/v1/diagnostics",
    )
    return path.startswith(prefixes)
