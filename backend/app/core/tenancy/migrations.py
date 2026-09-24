"""Upgrade one store, or every store the firm registry knows about.

``alembic/env.py`` migrates exactly **one** schema per run. So a bare ``alembic
upgrade head`` advances only the platform schema and silently leaves every firm
store behind, and the drift is invisible until a query hits a missing column --
which is how every product read in three firm schemas broke on 2026-08-09.

Two callers need this and used to have their own copy:

* provisioning a firm (``lifecycle.py``), which migrates the one store it just
  created;
* the operator command, which migrates all of them.

Both ran ``sys.executable -m alembic`` in a subprocess. That cannot work in a
compiled build -- the executable is the application, and there is no ``alembic``
module to hand it -- so creating a firm would have failed on a packaged
installation, which is the one flow a customer performs unaided.

The target now travels on Alembic's ``Config.attributes``, which ``env.py``
reads in preference to ``Settings()``. That is the part worth keeping: the
subprocess existed because the in-process version set ``os.environ`` and two
concurrent provisions raced. Nothing process-wide is touched now, so the race
is not reintroduced by returning to this process.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass

from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.paths import alembic_ini_path, alembic_script_location
from app.core.tenancy.connections import (
    build_tenant_database_config,
    resolve_connection_profile,
)
from app.core.tenancy.models import DeploymentMode
from app.firms.models import Firm, FirmStorageMapping

# Alembic keeps a module-level context for the duration of one run, so two
# upgrades in this process would tread on each other however cleanly their
# targets are passed. Migrating is rare, administrative and slow, so
# serialising it costs nothing worth having.
_MIGRATION_LOCK = threading.Lock()


def _print_line(text_line: str) -> None:
    """Write one report line to stdout."""
    print(text_line)


@dataclass(frozen=True, slots=True)
class MigrationTarget:
    """One database and schema pair that carries its own ``alembic_version``."""

    label: str
    database_url: str
    schema_name: str


def upgrade_store(*, database_url: str, schema_name: str) -> None:
    """Run ``upgrade head`` against one store, in this process.

    Raises whatever Alembic raises. Callers that owe a domain error -- firm
    provisioning does -- translate it; the operator command reports it.
    """
    config = Config(alembic_ini_path().as_posix())
    config.set_main_option("script_location", alembic_script_location().as_posix())
    # On the Config, never in os.environ: env.py reads these in preference to
    # Settings(), so two callers share no mutable state.
    config.attributes["database_url"] = database_url
    config.attributes["schema_name"] = schema_name
    with _MIGRATION_LOCK:
        command.upgrade(config, "head")


def store_is_built(*, database_url: str, schema_name: str) -> bool:
    """Whether a store exists and has been migrated at least once.

    "Built" means its schema carries an ``alembic_version`` table. A database
    that does not exist yet, or cannot be reached, answers False; the build
    that follows is what reports why.
    """
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            if connection.dialect.name != "postgresql":
                # Only PostgreSQL stores are built on demand; elsewhere nothing
                # changes from before the shared store was.
                return True
            found = connection.scalar(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = :schema AND table_name = 'alembic_version'"
                ),
                {"schema": schema_name},
            )
            return found is not None
    except Exception:  # noqa: BLE001 - absent or unreachable both mean "not yet"
        return False
    finally:
        engine.dispose()


def current_revision(target: MigrationTarget) -> str:
    """Return the revision a store is at, or why it could not be read."""
    engine = create_engine(target.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text(f'SET search_path TO "{target.schema_name}"'))
            return (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                or "none"
            )
    except Exception as error:  # noqa: BLE001 - reporting, not control flow
        return f"unreadable ({type(error).__name__})"
    finally:
        engine.dispose()


def count_firms(platform: DatabaseManager) -> int | None:
    """Return how many live firms the registry holds, or None if it has none yet.

    None means the platform store has not been migrated -- no ``firms`` table
    -- which is the state a fresh install is in before ``migrate-all``. Any
    other failure (the server unreachable, a wrong password) is raised: an
    installer asking "is this a fresh database" must not read "I could not
    tell" as "yes".
    """
    platform_schema = platform.config.default_schema or "platform"
    with platform.engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            present = connection.scalar(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = :schema AND table_name = 'firms'"
                ),
                {"schema": platform_schema},
            )
            if present is None:
                return None
    with platform.sessions(schema=platform_schema).session() as session:
        return int(
            session.scalar(
                select(func.count()).select_from(Firm).where(Firm.is_deleted.is_(False))
            )
            or 0
        )


def migration_targets(
    platform: DatabaseManager, settings: Settings, *, platform_only: bool = False
) -> list[MigrationTarget]:
    """Return every distinct store: platform, then shared, then dedicated.

    Enumerated from the registry rather than from a list someone maintains by
    hand, and each dedicated firm is reached through its own connection
    profile, so a firm on another server is upgraded on that server.

    ``platform_only`` is a fresh installation, one with no firm: the platform
    store is the only thing to migrate. The shared store is added all the same
    when it has already been built, so a database that once held firms keeps
    every store it has at head.
    """
    base = platform.config
    platform_schema = base.default_schema or "platform"
    targets: dict[tuple[str, str], MigrationTarget] = {}

    def add(label: str, database_url: str, schema_name: str) -> None:
        url = make_url(database_url)
        key = (f"{url.host}:{url.port}/{url.database}", schema_name)
        targets.setdefault(
            key,
            MigrationTarget(
                label=label, database_url=database_url, schema_name=schema_name
            ),
        )

    add(f"platform ({base.database}/{platform_schema})", base.url, platform_schema)
    shared_database = settings.tenancy.shared_database_name or base.database
    shared_url = make_url(base.url).set(database=shared_database)
    shared_rendered = shared_url.render_as_string(hide_password=False)
    if not platform_only or store_is_built(
        database_url=shared_rendered,
        schema_name=settings.tenancy.shared_schema_name,
    ):
        add(
            f"shared ({shared_database}/{settings.tenancy.shared_schema_name})",
            shared_rendered,
            settings.tenancy.shared_schema_name,
        )
    if platform_only:
        return list(targets.values())

    with platform.sessions(schema=platform_schema).session() as session:
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
            if DeploymentMode(mapping.deployment_mode) is DeploymentMode.SHARED:
                # Every shared firm resolves to the one schema added above.
                continue
            if mapping.database_name is None or mapping.schema_name is None:
                continue
            config = build_tenant_database_config(
                base,
                database_name=mapping.database_name,
                schema_name=mapping.schema_name,
                database_type=mapping.database_type,
                profile=resolve_connection_profile(
                    settings.tenancy.connection_profiles, mapping.connection_profile
                ),
            )
            where = mapping.connection_profile or "platform server"
            add(
                f"{firm.code} ({mapping.database_name}/{mapping.schema_name} "
                f"on {where})",
                config.url,
                mapping.schema_name,
            )
    return list(targets.values())


def _prune_fresh_platform(target: MigrationTarget, say: Callable[[str], None]) -> int:
    """Drop the firm-owned tables from a platform store that has no firm.

    Returns the number of failures, 0 or 1, in the shape the caller counts.
    Only ever called when the registry holds no firm, so an installation with
    firms keeps exactly the layout it had.
    """
    # Imported here: lifecycle imports this module for `upgrade_store`.
    from app.core.tenancy.lifecycle import prune_firm_objects

    try:
        dropped = prune_firm_objects(
            database_url=target.database_url, schema_name=target.schema_name
        )
    except Exception as error:  # noqa: BLE001 - reporting, not control flow
        say(f"  {target.label}: pruning firm tables FAILED\n    {error}")
        return 1
    if dropped:
        say(f"  {target.label}: {len(dropped)} firm-owned table(s) pruned")
    return 0


def upgrade_every_store(
    *, dry_run: bool, report: Callable[[str], None] | None = None
) -> int:
    """Report or apply ``upgrade head`` across every store. Returns an exit code.

    Reports every store rather than stopping at the first failure: knowing that
    four of five upgraded is the difference between a retry and an
    investigation.
    """
    say = report if report is not None else _print_line

    settings = Settings()
    platform = DatabaseManager.from_settings(settings)
    try:
        # A fresh installation -- no registry yet, or one holding no firm --
        # migrates the platform store only. The shared store is built by the
        # first SHARED firm, through provisioning, not here.
        fresh = not count_firms(platform)
        targets = migration_targets(platform, settings, platform_only=fresh)
    finally:
        platform.dispose()

    say(f"{len(targets)} store(s) to migrate.")
    if fresh:
        say("No firm is registered: the platform store is migrated on its own.")
    if dry_run:
        for target in targets:
            say(f"  {target.label}: at {current_revision(target)}")
        say("\nDry run only. Re-run with --yes to upgrade these stores.")
        return 0

    failures = 0
    for target in targets:
        try:
            upgrade_store(
                database_url=target.database_url, schema_name=target.schema_name
            )
        except Exception as error:  # noqa: BLE001 - reporting, not control flow
            failures += 1
            detail = str(error).strip()[-600:]
            say(f"  {target.label}: FAILED\n    {detail}")
            continue
        say(f"  {target.label}: upgraded to head")

    if fresh and failures == 0:
        failures += _prune_fresh_platform(targets[0], say)

    if failures:
        say(f"\n{failures} of {len(targets)} store(s) failed.")
        return 1
    say("\nEvery store is at head.")
    return 0
