"""Carry a business profile written at runtime to every store (backlog 17).

The profile catalogue is duplicated in every firm store on purpose: a firm on
its own server must render its own forms when the platform database is down.
The seeded profiles agree across stores only because their migrations insert
the same hardcoded ids. A profile created through the API used to land in
whichever store the caller happened to be in, with a random id -- so the
Profile Assignment dropdown offered it and assigning it to a firm in another
store was refused as not found.

This writes the profile to every other store the way a migration would: the
same row, **the same id**, one store at a time, each committed on its own.
Every store is reported -- written, unchanged, refused, unreachable -- and
none is skipped silently: a store that could not be written is exactly what
the administrator has to know about, because until it is fixed the profile
is usable only where it exists.

Stores are found from the registry, as ``app/core/tenancy/migrations.py``
finds its targets: every active firm resolved to its store, and firms that
share a store (every SHARED firm, in ``firm_shared``) counted once.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.business.models import BusinessProfile
from app.business.schemas import ProfileStoreOutcome
from app.business.services.framework_service import BusinessProfileFrameworkService
from app.core.exceptions import ApplicationError
from app.core.tenancy import FirmRegistryTenantResolver, MultiTenantDatabaseProvider
from app.core.tenancy.models import TenantContext
from app.firms.models import Firm

SessionOpener = Callable[[], AbstractContextManager[Session]]


@dataclass(frozen=True)
class ProfileStore:
    """One store a profile must reach, or the reason it cannot be reached."""

    label: str
    opener: SessionOpener | None = None
    unreachable: str | None = None


def replicate_profile(
    source: BusinessProfile, stores: list[ProfileStore], actor_id: UUID
) -> list[ProfileStoreOutcome]:
    """Write ``source`` into each store and say what happened in each."""
    return replicate(
        stores,
        lambda service: service.mirror_profile(source, actor_id),
    )


def replicate(
    stores: list[ProfileStore],
    action: Callable[[BusinessProfileFrameworkService], str],
) -> list[ProfileStoreOutcome]:
    """Run one catalogue write in each store and say what happened in each.

    Each store commits on its own: a store that refuses must not undo the
    stores that took the write, and the report names the one that refused.
    ``action`` runs the same service method a request would, on that store's
    session, and returns what it did.
    """
    outcomes: list[ProfileStoreOutcome] = []
    for store in stores:
        if store.opener is None:
            outcomes.append(
                ProfileStoreOutcome(
                    store=store.label,
                    status="FAILED",
                    detail=store.unreachable or "This store could not be reached.",
                )
            )
            continue
        try:
            with store.opener() as session:
                done = action(BusinessProfileFrameworkService(session))
        except (ApplicationError, SQLAlchemyError) as error:
            outcomes.append(
                ProfileStoreOutcome(
                    store=store.label, status="FAILED", detail=_reason(error)
                )
            )
            continue
        outcomes.append(
            ProfileStoreOutcome(store=store.label, status="WRITTEN", detail=done)
        )
    return outcomes


def summary(outcomes: list[ProfileStoreOutcome]) -> str:
    """Say in one line how far the profile reached."""
    if not outcomes:
        return "Saved. There is no other store to copy it to."
    failed = [item for item in outcomes if item.status == "FAILED"]
    if not failed:
        return f"Saved, and copied to all {len(outcomes)} other store(s)."
    names = "; ".join(f"{item.store}: {item.detail}" for item in failed)
    return (
        f"Saved here, but {len(failed)} of {len(outcomes)} other store(s) did "
        f"not take it, so firms there cannot use it yet -- {names}"
    )


def other_profile_stores(request: Request, platform_db: Session) -> list[ProfileStore]:
    """Return every store but the caller's, from the firm registry.

    Firms sharing a store are named together and the store is written once.
    A firm whose store cannot be resolved is returned with the reason, and an
    inactive firm -- whose store the registry will not route to -- is named
    too, so nothing is left out without saying so.
    """
    provider = cast(MultiTenantDatabaseProvider, request.app.state.database_provider)
    resolver = cast(FirmRegistryTenantResolver, request.app.state.tenant_resolver)
    caller = resolver.resolve(request)
    caller_key = None if caller is None else _store_key(provider, caller)
    firms = platform_db.scalars(
        select(Firm).where(Firm.is_deleted.is_(False)).order_by(Firm.code.asc())
    ).all()
    grouped: dict[tuple[str, int, str, str], list[str]] = {}
    tenants: dict[tuple[str, int, str, str], TenantContext] = {}
    problems: list[ProfileStore] = []
    for firm in firms:
        if not firm.is_active:
            problems.append(
                ProfileStore(
                    label=firm.code,
                    unreachable="The firm is inactive, so its store is not "
                    "routed to; reactivate it and save the profile again.",
                )
            )
            continue
        try:
            tenant = resolver.resolve_firm(firm.id)
            key = _store_key(provider, tenant)
        except (ApplicationError, SQLAlchemyError) as error:
            problems.append(ProfileStore(label=firm.code, unreachable=_reason(error)))
            continue
        if key == caller_key:
            continue
        grouped.setdefault(key, []).append(firm.code)
        tenants.setdefault(key, tenant)
    stores = [
        ProfileStore(
            label=f"{key[2]}/{key[3]} ({', '.join(codes)})",
            opener=_opener(provider, tenants[key]),
        )
        for key, codes in grouped.items()
    ]
    return stores + problems


def _store_key(
    provider: MultiTenantDatabaseProvider, tenant: TenantContext
) -> tuple[str, int, str, str]:
    """Name a store by server, database and schema -- what makes it distinct."""
    config = provider.manager_for(tenant).config
    return (config.host, config.port, config.database, provider.schema_for(tenant))


def _opener(
    provider: MultiTenantDatabaseProvider, tenant: TenantContext
) -> SessionOpener:
    """Return a callable that opens a session on that tenant's store."""

    @contextmanager
    def open_store() -> Iterator[Session]:
        """Open one session on the store, closed when the write is done."""
        manager = provider.manager_for(tenant)
        with manager.sessions(schema=provider.schema_for(tenant)).session() as db:
            yield db

    return open_store


def _reason(error: Exception) -> str:
    """Return the message an error carries, without a driver's traceback."""
    message = getattr(error, "message", None)
    if isinstance(message, str) and message:
        return message
    return str(error).splitlines()[0] if str(error) else type(error).__name__
