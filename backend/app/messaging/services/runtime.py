"""Wire the outbox worker to the firm registry and each firm's own store.

The server builds these from the tenancy services ``create_app`` already holds;
the CLI builds them from settings, the same way. Each firm is reached through
its own store -- a DATABASE-mode firm on another server included -- because
its outbox lives there.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import STORE_FIRM_SESSION_KEY
from app.core.database.engine import DatabaseManager
from app.core.tenancy import FirmRegistryTenantResolver, MultiTenantDatabaseProvider
from app.firms.models import Firm
from app.messaging.services.outbox_worker import StoreOpener


def live_firm_ids(platform: DatabaseManager) -> Callable[[], list[UUID]]:
    """Return a callable listing every live, active firm in the registry."""

    def read() -> list[UUID]:
        """Read the firm ids from the platform store."""
        with platform.sessions(
            schema=platform.config.default_schema
        ).session() as session:
            return list(
                session.scalars(
                    select(Firm.id).where(
                        Firm.is_deleted.is_(False), Firm.is_active.is_(True)
                    )
                ).all()
            )

    return read


def store_opener(
    resolver: FirmRegistryTenantResolver, provider: MultiTenantDatabaseProvider
) -> StoreOpener:
    """Return a context manager factory that opens one firm's store."""

    @contextmanager
    def open_store(firm_id: UUID) -> Generator[Session]:
        """Open a session on the firm's own database and schema."""
        tenant = resolver.resolve_firm(firm_id)
        manager = provider.manager_for(tenant)
        with manager.sessions(schema=provider.schema_for(tenant)).session() as session:
            session.info[STORE_FIRM_SESSION_KEY] = tenant.firm_id
            yield session

    return open_store
