"""Provision schema/database storage for one firm from the registry."""

from __future__ import annotations

import argparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.tenancy.lifecycle import TenantStorageLifecycleService
from app.firms.models import Firm


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision schema/database storage for a firm."
    )
    parser.add_argument("--firm-id", type=UUID, help="Firm UUID to provision.")
    parser.add_argument("--firm-code", help="Firm code to provision.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved target and exit without provisioning.",
    )
    return parser


def _resolve_firm(
    session: Session, *, firm_id: UUID | None, firm_code: str | None
) -> Firm:
    if firm_id is not None:
        firm = session.scalar(
            select(Firm).where(Firm.id == firm_id, Firm.is_deleted.is_(False))
        )
        if firm is not None:
            return firm
        raise SystemExit(f"Firm '{firm_id}' was not found.")
    if firm_code is not None and firm_code.strip():
        normalized = firm_code.strip().upper()
        firm = session.scalar(
            select(Firm).where(Firm.code == normalized, Firm.is_deleted.is_(False))
        )
        if firm is not None:
            return firm
        raise SystemExit(f"Firm '{normalized}' was not found.")
    raise SystemExit("Provide either --firm-id or --firm-code.")


def main() -> int:
    """Resolve one firm and provision its configured storage target."""
    args = _build_parser().parse_args()
    settings = Settings()
    database = DatabaseManager.from_settings(settings)
    lifecycle = TenantStorageLifecycleService(
        database,
        settings.tenancy.connection_profiles,
    )
    try:
        with database.sessions(
            schema=database.config.default_schema
        ).session() as session:
            firm = _resolve_firm(
                session,
                firm_id=args.firm_id,
                firm_code=args.firm_code,
            )
            if args.dry_run:
                print(
                    "Dry run:",
                    f"firm={firm.code}",
                    f"mode={firm.deployment_mode}",
                    f"database={firm.database_name}",
                    f"schema={firm.schema_name}",
                )
                return 0
            lifecycle.provision_new_firm(firm)
            print(
                "Provisioned:",
                f"firm={firm.code}",
                f"mode={firm.deployment_mode}",
                f"database={firm.database_name}",
                f"schema={firm.schema_name}",
            )
            return 0
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
