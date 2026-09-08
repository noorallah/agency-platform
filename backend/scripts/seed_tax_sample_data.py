"""Seed the Indian GST template into one or more firms.

The template itself lives in ``app/tax/services/gst_template.py`` as of
2026-09-08, where ``POST /api/v1/firms/{id}/apply-tax-template`` and the
Firms setup panel reach it; this script applies the same one from a shell to
every firm at once, in each firm's own store. A firm that already holds a
tax system is skipped, as the endpoint would.

Run from ``backend``::

    ./.venv/Scripts/python.exe scripts/seed_tax_sample_data.py
    ./.venv/Scripts/python.exe scripts/seed_tax_sample_data.py --firm-code WHOLE01
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies.settings import get_settings
from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.exceptions import ResourceNotFoundError
from app.core.tenancy import (
    DeploymentMode,
    FirmConnectionResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantContext,
)
from app.firms.models import Firm
from app.identity.models import User
from app.tax.services.gst_template import apply_india_gst_template


def main() -> int:
    """Apply the GST template to the requested firms."""
    parser = argparse.ArgumentParser(description="Seed the Indian GST template.")
    parser.add_argument(
        "--firm-code",
        action="append",
        dest="firm_codes",
        help="Seed one specific firm code. Repeat for multiple firms. Defaults to all "
        "firms.",
    )
    args = parser.parse_args()

    settings = get_settings()
    platform = DatabaseManager.from_settings(settings)
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    try:
        with platform.sessions(
            schema=platform.config.default_schema
        ).session() as session:
            actor_id = _resolve_actor(session)
            firms = _resolve_firms(session, args.firm_codes)
            for firm in firms:
                tenant = _tenant_context_for_firm(settings, firm)
                database = provider.manager_for(tenant)
                schema = provider.schema_for(tenant)
                with database.sessions(schema=schema).session() as tenant_session:
                    created = apply_india_gst_template(
                        tenant_session, firm_id=firm.id, actor_id=actor_id
                    )
                    tenant_session.commit()
                    if not any(created.values()):
                        print(
                            f"Skipped: firm={firm.code} schema={schema} "
                            "reason=tax_system_exists"
                        )
                        continue
                    print(
                        f"Seeded: firm={firm.code} schema={schema} "
                        f"system=GST profiles={created['profiles']} "
                        f"rules={created['rules']}"
                    )
    finally:
        provider.dispose()
        platform.dispose()
    return 0


def _resolve_actor(session: Session) -> object:
    """Return who the seeded rows are attributed to."""
    actor = session.scalar(
        select(User).where(User.email == "platform-admin@agency.local")
    ) or session.scalar(select(User).order_by(User.email.asc()))
    if actor is None:
        raise ResourceNotFoundError("No user is available to own seeded tax records.")
    return actor.id


def _resolve_firms(session: Session, requested_codes: list[str] | None) -> list[Firm]:
    statement = select(Firm).options(selectinload(Firm.storage_mappings))
    if not requested_codes:
        return list(session.scalars(statement.order_by(Firm.code.asc())).all())
    normalized = [code.strip().upper() for code in requested_codes]
    firms = list(
        session.scalars(
            statement.where(Firm.code.in_(normalized)).order_by(Firm.code.asc())
        ).all()
    )
    found_codes = {firm.code for firm in firms}
    missing = [code for code in normalized if code not in found_codes]
    if missing:
        raise ResourceNotFoundError(f"Firm not found: {', '.join(missing)}")
    return firms


def _tenant_context_for_firm(settings: Settings, firm: Firm) -> TenantContext:
    mapping = next(
        (
            item
            for item in firm.storage_mappings
            if item.is_active and not item.is_deleted
        ),
        None,
    )
    mode = (
        DeploymentMode.SHARED
        if mapping is None
        else DeploymentMode(mapping.deployment_mode)
    )
    if mode is DeploymentMode.SHARED:
        return TenantContext(
            firm_id=firm.id,
            deployment_mode=DeploymentMode.SHARED,
            database_name=settings.tenancy.shared_database_name,
            schema_name=settings.tenancy.shared_schema_name,
            database_type=settings.tenancy.platform_database_type.value,
        )
    if mapping is None or mapping.database_name is None or mapping.schema_name is None:
        raise ResourceNotFoundError(
            f"Firm {firm.code} does not have a complete storage mapping."
        )
    return TenantContext(
        firm_id=firm.id,
        deployment_mode=mode,
        database_name=mapping.database_name,
        schema_name=mapping.schema_name,
        database_type=mapping.database_type,
    )


if __name__ == "__main__":
    raise SystemExit(main())
