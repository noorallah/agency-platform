"""Report whether a firm can trade yet, and name what is missing if not.

Creating a firm records the intent; it does not open its books. A firm needs a
chart of accounts, a financial year, open accounting periods and a mapped
control account for every posting purpose before ``DocumentPostingService``
will post anything -- it refuses rather than guesses, so an unfinished firm
accepts masters and drafts and then declines to approve an invoice.

That is easy to mistake for a bug, so this answers the question directly.
It is **read-only**: it opens each store, counts, and writes nothing. The
steps come from ``FirmReadinessService`` -- the same list
``GET /api/v1/firms/{id}/readiness`` answers with and the desktop's Firm setup
panel shows -- so this script and the screen cannot disagree about what
finished means. Opening the books is ``POST /api/v1/firms/{id}/open-books``,
or the setup panel's button.

Run from ``backend`` with a firm code, or with none for every firm::

    ./.venv/Scripts/python.exe scripts/check_firm_readiness.py WHOLE01
    ./.venv/Scripts/python.exe scripts/check_firm_readiness.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.core.database.all_models  # noqa: F401,E402
from app.core.config.settings import Settings  # noqa: E402
from app.core.database.engine import DatabaseManager, EngineFactory  # noqa: E402
from app.core.tenancy import (  # noqa: E402
    DeploymentMode,
    FirmConnectionResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantContext,
)
from app.firms.models import Firm, FirmStorageMapping  # noqa: E402
from app.firms.services.readiness import (  # noqa: E402
    FirmReadinessService,
    ReadinessStatus,
    storage_is_ready,
)


def _print_steps(platform: Session, store: Session | None, firm: Firm) -> bool:
    """Print every step for one firm and return whether it can post."""
    readiness = FirmReadinessService(platform).readiness(firm, store)
    for step in readiness.steps:
        marker = {
            ReadinessStatus.DONE: "ok ",
            ReadinessStatus.MISSING: "-- ",
            ReadinessStatus.BLOCKED: "?? ",
        }[step.status]
        need = "required" if step.required else "recommended"
        print(f"  {marker}{step.label:<24}: {step.detail}  [{need}]")
    return readiness.can_post


def _tenant_context(
    settings: Settings, firm: Firm, mapping: FirmStorageMapping
) -> TenantContext:
    """Build the routing for one firm's store."""
    mode = DeploymentMode(mapping.deployment_mode)
    # A SHARED firm carries no names of its own: its rows live in the
    # configured shared store, and reading the NULLs off the mapping resolves
    # to no schema at all.
    if mode is DeploymentMode.SHARED:
        database_name = settings.tenancy.shared_database_name
        schema_name = settings.tenancy.shared_schema_name
    else:
        database_name = mapping.database_name
        schema_name = mapping.schema_name
    return TenantContext(
        firm_id=firm.id,
        deployment_mode=mode,
        database_name=database_name,
        schema_name=schema_name,
        database_type=mapping.database_type,
    )


def main() -> int:
    """Report readiness for one firm or for every firm."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code", nargs="?", help="Firm code. Default is every firm.")
    args = parser.parse_args()

    settings = Settings()
    platform = DatabaseManager(EngineFactory.database_config_from_settings(settings))
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    not_ready = 0
    # `firms` lives only in the platform schema, so this session has to say
    # so -- and it stays open across the loop, because the firm's routing is
    # read off a relationship that a detached row cannot load.
    try:
        with platform.sessions(schema="platform").session() as psession:
            statement = select(Firm, FirmStorageMapping).join(
                FirmStorageMapping, FirmStorageMapping.firm_id == Firm.id
            )
            statement = statement.where(
                Firm.is_deleted.is_(False), FirmStorageMapping.is_deleted.is_(False)
            )
            if args.code:
                statement = statement.where(Firm.code == args.code.upper())
            rows = psession.execute(statement).all()
            if not rows:
                suffix = f" with code {args.code}" if args.code else ""
                print(f"No firm found{suffix}.")
                return 1
            for firm, mapping in rows:
                print(f"\n{firm.code}  {firm.name}")
                print(f"  active                : {firm.is_active}")
                print(f"  deployment mode       : {mapping.deployment_mode}")
                print(f"  storage provisioned   : {firm.provisioned_at or 'NO'}")
                # A dedicated store that was never built holds no tables at
                # all, so reading it would raise rather than report.
                if not storage_is_ready(firm):
                    _print_steps(psession, None, firm)
                    print("\n  VERDICT: not provisioned -- run Provision storage first")
                    not_ready += 1
                    continue
                context = _tenant_context(settings, firm, mapping)
                manager = provider.manager_for(context)
                schema = provider.schema_for(context)
                with manager.sessions(schema=schema).session() as store:
                    ready = _print_steps(psession, store, firm)
                print(
                    "\n  VERDICT: "
                    + (
                        "can post documents"
                        if ready
                        else "CANNOT post -- books not open"
                    )
                )
                if not ready:
                    not_ready += 1
    finally:
        provider.dispose()
        platform.dispose()
    return 1 if not_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
