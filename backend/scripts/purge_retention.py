"""Apply every retention rule across every store, in one command.

The two retention services exist and nothing ran them. Worse, running the tax
one *correctly* meant knowing the tenancy layout: its log is firm-owned, so it
lives in ``firm_shared``, in each dedicated schema, and inside each dedicated
database. An operator scheduling ``purge_tax_execution_logs.py`` on its own
would have pruned the default schema and silently missed every other firm --
the same trap ``alembic upgrade head`` carries, and for the same reason.

This enumerates the stores from the firm registry rather than from a list
someone has to maintain, using the resolvers the application itself uses, then
applies:

* identity retention (refresh tokens, login history, password history) once,
  against the platform store, which is the only place those tables exist;
* tax execution log retention against every distinct firm store.

Run it with ``--dry-run`` first; it reports per store and changes nothing.

    uv run python scripts/purge_retention.py --dry-run
    uv run python scripts/purge_retention.py --yes
"""

import argparse
import sys
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.tenancy import (
    DeploymentMode,
    FirmConnectionResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantContext,
)
from app.firms.models import Firm, FirmStorageMapping
from app.identity.services import IdentityRetentionService
from app.tax.services import TaxRetentionService


@dataclass(frozen=True, slots=True)
class _Store:
    """One distinct place firm-owned rows live."""

    label: str
    context: TenantContext


def _firm_stores(platform: DatabaseManager, settings: Settings) -> list[_Store]:
    """Return one store per distinct database/schema pair in the registry.

    Firms in SHARED mode all resolve to the same schema, so they collapse to a
    single entry: pruning it once prunes every one of them.
    """
    stores: dict[tuple[str | None, str | None], _Store] = {}
    with platform.sessions(schema=platform.config.default_schema).session() as session:
        rows = session.execute(
            select(Firm, FirmStorageMapping)
            .join(FirmStorageMapping, FirmStorageMapping.firm_id == Firm.id)
            .where(
                Firm.is_deleted.is_(False),
                FirmStorageMapping.is_deleted.is_(False),
                FirmStorageMapping.is_active.is_(True),
            )
        ).all()
        for firm, mapping in rows:
            mode = DeploymentMode(mapping.deployment_mode)
            if mode is DeploymentMode.SHARED:
                database_name = settings.tenancy.shared_database_name
                schema_name = settings.tenancy.shared_schema_name
            else:
                database_name = mapping.database_name
                schema_name = mapping.schema_name
            key = (database_name, schema_name)
            if key in stores:
                continue
            stores[key] = _Store(
                label=f"{database_name}/{schema_name}",
                context=TenantContext(
                    firm_id=firm.id,
                    deployment_mode=mode,
                    database_name=database_name,
                    schema_name=schema_name,
                    database_type=mapping.database_type,
                ),
            )
    return sorted(stores.values(), key=lambda store: store.label)


def main() -> int:
    """Report or apply every retention rule across every store."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-token-grace-days", type=int, default=7)
    parser.add_argument("--login-history-days", type=int, default=365)
    parser.add_argument("--password-history-keep", type=int, default=10)
    parser.add_argument("--execution-log-days", type=int, default=365)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="Report counts without deleting."
    )
    group.add_argument("--yes", action="store_true", help="Apply the deletions.")
    args = parser.parse_args()

    settings = Settings()
    platform = DatabaseManager.from_settings(settings)
    verb = "would remove" if args.dry_run else "removed"
    removed = 0

    with platform.sessions(schema=settings.database_schema).session() as session:
        identity = IdentityRetentionService(session).purge(
            refresh_token_grace_days=args.refresh_token_grace_days,
            login_history_days=args.login_history_days,
            password_history_keep=args.password_history_keep,
            dry_run=args.dry_run,
        )
    removed += identity.total
    print(f"platform/{settings.database_schema}")
    print(f"  refresh_tokens:   {verb} {identity.refresh_tokens}")
    print(f"  login_history:    {verb} {identity.login_history}")
    print(f"  password_history: {verb} {identity.password_history}")

    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    try:
        for store in _firm_stores(platform, settings):
            manager = provider.manager_for(store.context)
            schema = provider.schema_for(store.context)
            with manager.sessions(schema=schema).session() as session:
                tax = TaxRetentionService(session).purge(
                    execution_log_days=args.execution_log_days,
                    dry_run=args.dry_run,
                )
            removed += tax.execution_logs
            print(store.label)
            print(f"  tax_rule_execution_logs: {verb} {tax.execution_logs}")
    finally:
        provider.dispose()

    print(f"total: {verb} {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
