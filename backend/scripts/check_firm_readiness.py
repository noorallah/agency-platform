"""Report whether a firm can trade yet, and name what is missing if not.

Creating a firm records the intent; it does not open its books. A firm needs a
chart of accounts, a financial year, open accounting periods and a mapped
control account for every posting purpose before ``DocumentPostingService``
will post anything -- it refuses rather than guesses, so an unfinished firm
accepts masters and drafts and then declines to approve an invoice.

That is easy to mistake for a bug, so this answers the question directly.
It is **read-only**: it opens each store, counts, and writes nothing.

Run from ``backend`` with a firm code, or with none for every firm::

    ./.venv/Scripts/python.exe scripts/check_firm_readiness.py WHOLE01
    ./.venv/Scripts/python.exe scripts/check_firm_readiness.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.core.database.all_models  # noqa: F401,E402
from app.business.models import BusinessProfile, FirmBusinessProfile  # noqa: E402
from app.core.config.settings import Settings  # noqa: E402
from app.core.database.engine import DatabaseManager, EngineFactory  # noqa: E402
from app.core.tenancy import (  # noqa: E402
    DeploymentMode,
    FirmConnectionResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantContext,
)
from app.finance.models import (  # noqa: E402
    AccountingPeriod,
    FinancialYear,
    LedgerAccount,
)
from app.finance.services.control_accounts import (  # noqa: E402
    ControlAccountPurpose,
    ControlAccountService,
)
from app.firms.models import Firm, FirmStorageMapping  # noqa: E402


def _count(session: Session, model: type, firm_id: UUID) -> int:
    """Count a firm's live rows in one of its own tables."""
    return (
        session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.firm_id == firm_id, model.is_deleted.is_(False))
        )
        or 0
    )


def _report_store(session: Session, firm_id: UUID) -> bool:
    """Print what the firm's own store holds, and whether it can post."""
    profile = session.scalar(
        select(BusinessProfile.code)
        .join(
            FirmBusinessProfile,
            FirmBusinessProfile.business_profile_id == BusinessProfile.id,
        )
        .where(
            FirmBusinessProfile.firm_id == firm_id,
            FirmBusinessProfile.is_deleted.is_(False),
        )
    )
    # A firm with no assignment is not misconfigured -- it resolves to the
    # platform default -- but a wholesaler running as GENERIC is rarely meant.
    print(f"  business profile      : {profile or 'none (runs as GENERIC)'}")

    accounts = _count(session, LedgerAccount, firm_id)
    years = _count(session, FinancialYear, firm_id)
    periods = _count(session, AccountingPeriod, firm_id)
    print(f"  ledger accounts       : {accounts}")
    print(f"  financial years       : {years}")
    print(f"  accounting periods    : {periods}")

    purposes = tuple(ControlAccountPurpose)
    missing = ControlAccountService(session).missing(firm_id, purposes)
    if missing:
        shown = ", ".join(sorted(p.value for p in missing)[:5])
        print(
            f"  control accounts      : {len(missing)} of {len(purposes)} "
            f"unmapped ({shown}...)"
        )
    else:
        print(f"  control accounts      : all {len(purposes)} mapped")

    return bool(accounts and years and periods and not missing)


def main() -> int:
    """Report readiness for one firm or for every firm."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code", nargs="?", help="Firm code. Default is every firm.")
    args = parser.parse_args()

    settings = Settings()
    platform = DatabaseManager(EngineFactory.database_config_from_settings(settings))
    # `firms` lives only in the platform schema, so this session has to say so.
    with platform.sessions(schema="platform").session() as psession:
        statement = select(Firm, FirmStorageMapping).join(
            FirmStorageMapping, FirmStorageMapping.firm_id == Firm.id
        )
        statement = statement.where(
            Firm.is_deleted.is_(False), FirmStorageMapping.is_deleted.is_(False)
        )
        if args.code:
            statement = statement.where(Firm.code == args.code.upper())
        rows = []
        for firm, mapping in psession.execute(statement).all():
            mode = DeploymentMode(mapping.deployment_mode)
            # A SHARED firm carries no names of its own: its rows live in the
            # configured shared store, and reading the NULLs off the mapping
            # resolves to no schema at all.
            if mode is DeploymentMode.SHARED:
                database_name = settings.tenancy.shared_database_name
                schema_name = settings.tenancy.shared_schema_name
            else:
                database_name = mapping.database_name
                schema_name = mapping.schema_name
            rows.append(
                (
                    firm.id,
                    firm.code,
                    firm.name,
                    firm.is_active,
                    firm.provisioned_at,
                    TenantContext(
                        firm_id=firm.id,
                        deployment_mode=mode,
                        database_name=database_name,
                        schema_name=schema_name,
                        database_type=mapping.database_type,
                    ),
                )
            )

    if not rows:
        print(f"No firm found{f' with code {args.code}' if args.code else ''}.")
        platform.dispose()
        return 1

    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    not_ready = 0
    try:
        for firm_id, code, name, active, provisioned, context in rows:
            print(f"\n{code}  {name}")
            print(f"  active                : {active}")
            print(f"  deployment mode       : {context.deployment_mode.value}")
            print(f"  storage provisioned   : {provisioned or 'NO'}")
            # A dedicated store that was never built holds no tables at all,
            # so reading it would raise rather than report.
            if (
                context.deployment_mode is not DeploymentMode.SHARED
                and provisioned is None
            ):
                print("\n  VERDICT: not provisioned -- run Provision storage first")
                not_ready += 1
                continue
            manager = provider.manager_for(context)
            with manager.sessions(schema=provider.schema_for(context)).session() as s:
                ready = _report_store(s, firm_id)
            print(
                "\n  VERDICT: "
                + ("can post documents" if ready else "CANNOT post -- books not open")
            )
            if not ready:
                not_ready += 1
    finally:
        provider.dispose()
        platform.dispose()
    return 1 if not_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
