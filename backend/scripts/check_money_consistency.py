"""Report where a firm's books disagree with themselves, month by month.

**Read-only**: it opens each store, reads, and writes nothing. The checks come
from ``check_money_consistency`` in ``app/finance/services/money_consistency.py``
-- the trial balance, receivables and payables against their parties and
bills, and every posting document against its journal -- and this only prints
what that returns. Exits non-zero when any firm has a difference.

Run from ``backend`` with a firm code, or with none for every firm::

    ./.venv/Scripts/python.exe scripts/check_money_consistency.py WHOLE01
    ./.venv/Scripts/python.exe scripts/check_money_consistency.py WHOLE01 \
        --from 2026-04 --to 2026-06
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

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
from app.finance.services.money_consistency import (  # noqa: E402
    check_money_consistency,
)
from app.firms.models import Firm, FirmStorageMapping  # noqa: E402
from app.firms.services.readiness import storage_is_ready  # noqa: E402


def _month(text: str) -> date:
    """Read ``YYYY-MM`` as the first day of that month."""
    year, month = text.split("-")
    return date(int(year), int(month), 1)


def _tenant_context(
    settings: Settings, firm: Firm, mapping: FirmStorageMapping
) -> TenantContext:
    """Build the routing for one firm's store."""
    mode = DeploymentMode(mapping.deployment_mode)
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
    """Check one firm or every firm and print each difference."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code", nargs="?", help="Firm code. Default is every firm.")
    parser.add_argument("--from", dest="from_month", type=_month, help="YYYY-MM")
    parser.add_argument("--to", dest="to_month", type=_month, help="YYYY-MM")
    args = parser.parse_args()

    settings = Settings()
    platform = DatabaseManager(EngineFactory.database_config_from_settings(settings))
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    out = 0
    try:
        with platform.sessions(schema="platform").session() as psession:
            statement = (
                select(Firm, FirmStorageMapping)
                .join(FirmStorageMapping, FirmStorageMapping.firm_id == Firm.id)
                .where(
                    Firm.is_deleted.is_(False),
                    FirmStorageMapping.is_deleted.is_(False),
                )
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
                if not storage_is_ready(firm):
                    print("  skipped: storage not provisioned")
                    continue
                context = _tenant_context(settings, firm, mapping)
                manager = provider.manager_for(context)
                schema = provider.schema_for(context)
                with manager.sessions(schema=schema).session() as store:
                    found = check_money_consistency(
                        store,
                        firm.id,
                        from_month=args.from_month,
                        to_month=args.to_month,
                    )
                    # Nothing was written; say so to the database as well.
                    store.rollback()
                for item in found:
                    print(
                        f"  {item.period}  {item.check:<32} {item.document_ref}: "
                        f"expected {item.expected}, found {item.actual}"
                        + (f" -- {item.note}" if item.note else "")
                    )
                print(
                    f"  VERDICT: {len(found)} difference(s)"
                    if found
                    else "  VERDICT: the books agree"
                )
                if found:
                    out = 1
    finally:
        provider.dispose()
        platform.dispose()
    return out


if __name__ == "__main__":
    raise SystemExit(main())
