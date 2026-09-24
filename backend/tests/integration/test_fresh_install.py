"""A fresh install holds the platform only, and the first shared firm builds its store.

Runs what the installer runs -- ``create-database`` then ``migrate-all`` -- into
a throwaway database, then creates and provisions a SHARED firm the way the
Firms screen does. Only a real server can say which schemas and tables exist,
whether the platform seed survived the prune, and whether the audit trigger is
still there afterwards; SQLite has one schema holding everything.

The development database is never touched: every setting that names a database
-- the platform's *and* the shared store's -- is pointed at the throwaway one.
"""

from collections.abc import Iterator
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import URL, make_url

from app.business.models import BusinessProfile
from app.common.audit.models import AuditLog
from app.common.audit.services import record_audit
from app.core.config.settings import Settings
from app.core.database.bootstrap import ensure_role_and_database
from app.core.database.config import database_config_from_settings
from app.core.database.dependencies import firm_store_session
from app.core.tenancy.lifecycle import PLATFORM_STORE_TABLES
from app.core.tenancy.migrations import count_firms, upgrade_every_store
from app.firms.models import FirmStorageMapping
from app.firms.schemas import FirmCreate
from app.firms.services import FirmService
from app.identity.models import Permission, Role, User
from app.main import create_app


@pytest.fixture
def fresh_database(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Point every database setting at a database that does not exist yet.

    Yields its name, and drops it afterwards.
    """
    with engine.connect() as connection:
        is_superuser = connection.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    if not is_superuser:
        pytest.skip("creating a database needs a superuser account")
    admin_url: URL = make_url(database_config_from_settings(Settings()).url)
    database = f"zz_fresh_{uuid4().hex[:8]}"
    monkeypatch.delenv("AGENCY_DATABASE_URL", raising=False)
    monkeypatch.setenv("AGENCY_DATABASE_NAME", database)
    monkeypatch.setenv("AGENCY_DATABASE_SCHEMA", "platform")
    # The shared store's database too, or the first shared firm would build
    # `firm_shared` in the development database.
    monkeypatch.setenv("AGENCY_TENANCY_SHARED_DATABASE_NAME", database)
    monkeypatch.setenv("AGENCY_TENANCY_SHARED_SCHEMA_NAME", "firm_shared")
    monkeypatch.setenv("AGENCY_LOG_FILE_ENABLED", "false")
    try:
        yield database
    finally:
        cleanup = create_engine(
            admin_url.set(database="postgres").render_as_string(hide_password=False),
            isolation_level="AUTOCOMMIT",
        )
        with cleanup.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
            )
        cleanup.dispose()


def _tables(connection: object, schema: str) -> set[str]:
    """Return the base tables in one schema."""
    rows = connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_type = 'BASE TABLE'"
        ),
        {"schema": schema},
    )
    return {name for (name,) in rows}


def _schema_exists(connection: object, schema: str) -> bool:
    """Return whether a schema exists."""
    found = connection.execute(  # type: ignore[attr-defined]
        text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
        {"s": schema},
    ).scalar()
    return found is not None


def _firm(code: str) -> FirmCreate:
    """Build a SHARED firm creation body."""
    return FirmCreate(
        name=f"{code} Traders",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )  # type: ignore[call-arg]


def test_a_fresh_install_holds_the_platform_and_the_first_firm_builds_its_store(
    fresh_database: str,
) -> None:
    """create-database, migrate-all, then a SHARED firm created and provisioned."""
    ensure_role_and_database()
    lines: list[str] = []
    assert upgrade_every_store(dry_run=False, report=lines.append) == 0, lines

    settings = Settings()
    application = create_app(settings)
    platform = application.state.database
    try:
        # --- What the install left behind ---------------------------------
        with platform.engine.connect() as connection:
            assert _tables(connection, "platform") == set(PLATFORM_STORE_TABLES)
            assert not _schema_exists(connection, "firm_shared")
            trigger = connection.execute(
                text(
                    "SELECT 1 FROM information_schema.triggers "
                    "WHERE event_object_schema = 'platform' "
                    "AND event_object_table = 'audit_logs'"
                )
            ).scalar()
            assert trigger is not None, "the platform trail lost its trigger"
        assert count_firms(platform) == 0

        # The platform seed is migrations' work and lives in `platform`: the
        # system roles and permissions and the bootstrap administrator.
        with platform.sessions(schema="platform").session() as session:
            assert session.scalar(select(func.count()).select_from(Role)) > 0
            assert session.scalar(select(func.count()).select_from(Permission)) > 0
            admin = session.scalar(
                select(User).where(User.email == "platform-admin@agency.local")
            )
            assert admin is not None
            admin_id = admin.id

        # A second migrate-all on a still-empty install changes nothing.
        assert upgrade_every_store(dry_run=False, report=lines.append) == 0, lines

        # --- The first firm, the way an older client creates it: record,
        # then provision -----------------------------------------------------
        lifecycle = application.state.tenant_storage_lifecycle
        with platform.sessions(schema="platform").session() as session:
            first = FirmService(session, tenancy_settings=settings.tenancy).create(
                _firm("FIRST"), admin_id
            )
            first_id = first.id
            _, already = FirmService(
                session, storage_lifecycle=lifecycle, tenancy_settings=settings.tenancy
            ).provision(first_id, admin_id)
            assert already is False

        with platform.engine.connect() as connection:
            shared_tables = _tables(connection, "firm_shared")
            platform_tables = _tables(connection, "platform")
        # Firm-owned tables are in the shared store, the platform's are not,
        # and the platform store is as it was.
        assert "products" in shared_tables and "sales_invoices" in shared_tables
        assert not shared_tables & {"users", "firms", "roles", "user_firms"}
        assert "audit_logs" in shared_tables
        assert platform_tables == set(PLATFORM_STORE_TABLES)

        # --- A second shared firm, the way the Firms screen creates it -----
        with platform.sessions(schema="platform").session() as session:
            second = FirmService(
                session, storage_lifecycle=lifecycle, tenancy_settings=settings.tenancy
            ).create(_firm("SECOND"), admin_id)
            second_id = second.id
            mapping = session.scalar(
                select(FirmStorageMapping).where(
                    FirmStorageMapping.firm_id == second_id
                )
            )
            assert mapping is not None and mapping.provisioned_at is not None
        assert count_firms(platform) == 2

        # --- The firm works: its store opens as a request's would ----------
        request = SimpleNamespace(app=application)
        with firm_store_session(request, first_id) as session:  # type: ignore[arg-type]
            # Business profiles are firm-store seed: `20260801_0011` wrote
            # them into `firm_shared` when provisioning migrated it.
            assert session.scalar(select(func.count()).select_from(BusinessProfile))
            record_audit(
                session,
                action="fresh_install.probe",
                entity_type="firm",
                entity_id=first_id,
                actor_id=admin_id,
                firm_id=first_id,
            )
            session.commit()
            written = session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "fresh_install.probe")
            )
            assert written == 1

        # With firms registered, migrate-all is back to every store.
        lines.clear()
        assert upgrade_every_store(dry_run=True, report=lines.append) == 0
        assert lines[0] == "2 store(s) to migrate."
    finally:
        application.state.database_provider.dispose()
        platform.dispose()
