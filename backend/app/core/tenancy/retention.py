"""Apply every retention rule across every store.

The two retention services exist and nothing ran them. Worse, running the tax
one *correctly* meant knowing the tenancy layout: its log is firm-owned, so it
lives in ``firm_shared``, in each dedicated schema, and inside each dedicated
database. An operator pruning the default schema on its own would have silently
missed every other firm -- the same trap ``alembic upgrade head`` carries, and
for the same reason.

This enumerates the stores from the firm registry rather than from a list
someone has to maintain, using the resolvers the application itself uses, then
applies:

* identity retention (refresh tokens, login history, password history) once,
  against the platform store, which is the only place those tables exist;
* error-report retention, also platform-only: they are telemetry for whoever
  maintains the product, so unlike the audit trail they are not per firm;
* tax execution log retention against every distinct firm store.

It lives under ``app/`` rather than in ``scripts/`` because the shipped product
runs it -- a compiled build has no interpreter to hand a script to.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.tenancy.models import DeploymentMode, TenantContext
from app.core.tenancy.provider import MultiTenantDatabaseProvider
from app.core.tenancy.resolvers import FirmConnectionResolver, FirmSchemaResolver
from app.core.utils.dates import utc_now
from app.diagnostics.models import ErrorReport
from app.diagnostics.services import ErrorReportService
from app.firms.models import Firm, FirmStorageMapping
from app.identity.services import IdentityRetentionService
from app.tax.services import TaxRetentionService


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How long each kind of row is kept. The defaults are the documented ones."""

    refresh_token_grace_days: int = 7
    login_history_days: int = 365
    password_history_keep: int = 10
    execution_log_days: int = 365
    error_report_days: int = 90


@dataclass(frozen=True, slots=True)
class _Store:
    """One distinct place firm-owned rows live."""

    label: str
    context: TenantContext


def _print_line(text_line: str) -> None:
    """Write one report line to stdout."""
    print(text_line)


def firm_stores(platform: DatabaseManager, settings: Settings) -> list[_Store]:
    """Return one store per distinct database/schema pair in the registry.

    Firms in SHARED mode all resolve to the same schema, so they collapse to a
    single entry: pruning it once prunes every one of them.
    """
    stores: dict[tuple[str | None, str | None, str | None], _Store] = {}
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
            # Keyed on the server too: two firms on different hosts may use the
            # same database and schema names, and collapsing them would prune
            # one store and silently skip the other.
            key = (mapping.connection_profile, database_name, schema_name)
            if key in stores:
                continue
            stores[key] = _Store(
                label=(
                    f"{database_name}/{schema_name}"
                    + (
                        f" on {mapping.connection_profile}"
                        if mapping.connection_profile
                        else ""
                    )
                ),
                context=TenantContext(
                    firm_id=firm.id,
                    deployment_mode=mode,
                    database_name=database_name,
                    schema_name=schema_name,
                    database_type=mapping.database_type,
                    # A firm on another server is pruned on that server.
                    # Without this the connection resolver falls back to the
                    # platform host and prunes the wrong store, or nothing.
                    connection_profile=mapping.connection_profile,
                ),
            )
    return sorted(stores.values(), key=lambda store: store.label)


def purge_every_store(
    *,
    dry_run: bool,
    policy: RetentionPolicy | None = None,
    report: Callable[[str], None] | None = None,
) -> int:
    """Report or apply every retention rule across every store."""
    say = report if report is not None else _print_line
    rules = policy or RetentionPolicy()

    settings = Settings()
    platform = DatabaseManager.from_settings(settings)
    verb = "would remove" if dry_run else "removed"
    removed = 0

    with platform.sessions(schema=settings.database_schema).session() as session:
        identity = IdentityRetentionService(session).purge(
            refresh_token_grace_days=rules.refresh_token_grace_days,
            login_history_days=rules.login_history_days,
            password_history_keep=rules.password_history_keep,
            dry_run=dry_run,
        )
    removed += identity.total

    with platform.sessions(schema=settings.database_schema).session() as session:
        cutoff = utc_now() - timedelta(days=rules.error_report_days)
        error_reports = (
            session.scalar(
                select(func.count())
                .select_from(ErrorReport)
                .where(ErrorReport.received_at < cutoff)
            )
            or 0
            if dry_run
            else ErrorReportService(session).purge_before(cutoff)
        )
    removed += error_reports
    say(f"platform/{settings.database_schema}")
    say(f"  refresh_tokens:   {verb} {identity.refresh_tokens}")
    say(f"  login_history:    {verb} {identity.login_history}")
    say(f"  password_history: {verb} {identity.password_history}")
    say(f"  error_reports:    {verb} {error_reports}")

    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    try:
        for store in firm_stores(platform, settings):
            manager = provider.manager_for(store.context)
            schema = provider.schema_for(store.context)
            with manager.sessions(schema=schema).session() as session:
                tax = TaxRetentionService(session).purge(
                    execution_log_days=rules.execution_log_days,
                    dry_run=dry_run,
                )
            removed += tax.execution_logs
            say(store.label)
            say(f"  tax_rule_execution_logs: {verb} {tax.execution_logs}")
    finally:
        provider.dispose()

    say(f"total: {verb} {removed}")
    return 0
