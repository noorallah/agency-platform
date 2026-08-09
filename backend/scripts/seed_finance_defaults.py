"""Give every firm the finance setup its documents need before they can post.

Each firm is seeded in its own store, resolved through the tenancy provider, so
this works across SHARED, SCHEMA and DATABASE deployments without being told
where anything lives.

    uv run python scripts/seed_finance_defaults.py --yes

Idempotent: re-running reports zeros.

There is deliberately no --dry-run. FinanceService commits inside each of its
fifteen mutating methods, so a caller cannot roll the work back — a preview flag
here would write the chart of accounts and then claim it had not. Removing those
commits is tracked separately; until then the only honest mode is to apply.
"""

import argparse
import sys
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.tenancy import (
    FirmConnectionResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
)
from app.core.tenancy.models import DeploymentMode, TenantContext
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm, FirmStorageMapping


def main() -> int:
    """Seed finance defaults for every active firm."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="apply the changes")
    args = parser.parse_args()
    if not args.yes:
        parser.error(
            "pass --yes to apply; this script cannot preview, because "
            "FinanceService commits internally"
        )

    settings = Settings()
    database = DatabaseManager.from_settings(settings)
    provider = MultiTenantDatabaseProvider(
        database,
        FirmConnectionResolver(database, settings.tenancy_connection_profiles),
        FirmSchemaResolver(),
    )
    actor_id = uuid4()

    with database.sessions(schema=database.config.default_schema).session() as platform:
        firms = platform.scalars(
            select(Firm).where(Firm.is_active.is_(True), Firm.is_deleted.is_(False))
        ).all()
        mappings = {
            row.firm_id: row
            for row in platform.scalars(
                select(FirmStorageMapping).where(
                    FirmStorageMapping.is_active.is_(True),
                    FirmStorageMapping.is_deleted.is_(False),
                )
            ).all()
        }
        targets = [
            (firm.id, firm.code, firm.financial_year_start, mappings.get(firm.id))
            for firm in firms
        ]

    for firm_id, code, year_start, mapping in targets:
        tenant = _tenant_for(firm_id, mapping, settings)
        manager = provider.manager_for(tenant)
        schema = provider.schema_for(tenant)
        with manager.sessions(schema=schema).session() as session:
            created = seed_finance_setup(
                session,
                firm_id=firm_id,
                year_starts_on=year_start,
                actor_id=actor_id,
            )
            session.commit()
            summary = ", ".join(f"{key}={value}" for key, value in created.items())
            print(f"{code:10} {schema:16} {summary}")

    print("applied")
    return 0


def _tenant_for(
    firm_id: UUID, mapping: FirmStorageMapping | None, settings: Settings
) -> TenantContext:
    """Build the tenant context for a firm's storage mapping."""
    if mapping is None:
        return TenantContext(
            firm_id=firm_id,
            deployment_mode=DeploymentMode.SHARED,
            database_name=settings.tenancy_shared_database_name,
            schema_name=settings.tenancy_shared_schema_name,
            database_type=settings.database_dialect,
        )
    return TenantContext(
        firm_id=firm_id,
        deployment_mode=DeploymentMode(mapping.deployment_mode),
        database_name=mapping.database_name or settings.tenancy_shared_database_name,
        schema_name=mapping.schema_name or settings.tenancy_shared_schema_name,
        database_type=settings.database_dialect,
    )


if __name__ == "__main__":
    sys.exit(main())
