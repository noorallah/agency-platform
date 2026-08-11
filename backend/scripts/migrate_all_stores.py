"""Upgrade every database and schema the firm registry knows about.

``alembic/env.py`` migrates exactly one schema per run, chosen by
``AGENCY_DATABASE_SCHEMA``. So a bare ``alembic upgrade head`` advances only the
platform schema and silently leaves every firm store behind, and the drift is
invisible until a query hits a missing column -- which is how every product read
in three firm schemas broke on 2026-08-09. The documented workaround was a
hand-written loop of environment variables, which misses any store the person
writing it forgot about.

This enumerates the targets from the registry instead of from a list someone has
to maintain: the platform schema, the shared firm schema, and every distinct
dedicated database/schema pair, each reached through its own connection profile
so a firm on another server is upgraded on that server.

    uv run python scripts/migrate_all_stores.py --dry-run
    uv run python scripts/migrate_all_stores.py --yes

``--dry-run`` reports each target with the revision it is currently at and
changes nothing. Run it first: it is also the quickest way to see whether any
store has drifted.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.tenancy import DeploymentMode
from app.core.tenancy.connections import (
    build_tenant_database_config,
    resolve_connection_profile,
)
from app.firms.models import Firm, FirmStorageMapping

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_INI = (_PROJECT_ROOT / "alembic.ini").as_posix()


@dataclass(frozen=True, slots=True)
class _Target:
    """One database and schema pair that carries its own alembic_version."""

    label: str
    database_url: str
    schema_name: str


def _targets(platform: DatabaseManager, settings: Settings) -> list[_Target]:
    """Return every distinct store, platform first, then shared, then dedicated."""
    base = platform.config
    platform_schema = base.default_schema or "platform"
    targets: dict[tuple[str, str], _Target] = {}

    def add(label: str, database_url: str, schema_name: str) -> None:
        url = make_url(database_url)
        key = (
            f"{url.host}:{url.port}/{url.database}",
            schema_name,
        )
        targets.setdefault(
            key,
            _Target(label=label, database_url=database_url, schema_name=schema_name),
        )

    add(f"platform ({base.database}/{platform_schema})", base.url, platform_schema)
    shared_database = settings.tenancy.shared_database_name or base.database
    shared_url = make_url(base.url).set(database=shared_database)
    add(
        f"shared ({shared_database}/{settings.tenancy.shared_schema_name})",
        shared_url.render_as_string(hide_password=False),
        settings.tenancy.shared_schema_name,
    )

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


def _current_revision(target: _Target) -> str:
    """Return the revision a target is at, without importing Alembic here."""
    engine = create_engine(target.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text(f'SET search_path TO "{target.schema_name}"')  # noqa: S608
                )
            return (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                or "none"
            )
    except Exception as error:  # noqa: BLE001 - reporting, not control flow
        return f"unreadable ({type(error).__name__})"
    finally:
        engine.dispose()


def _upgrade(target: _Target) -> tuple[bool, str]:
    """Run `alembic upgrade head` against one target in its own environment."""
    environment = dict(os.environ)
    environment["AGENCY_DATABASE_URL"] = target.database_url
    environment["AGENCY_DATABASE_SCHEMA"] = target.schema_name
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", _ALEMBIC_INI, "upgrade", "head"],
        cwd=_PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True, ""
    return False, (completed.stderr or completed.stdout or "").strip()[-600:]


def main() -> int:
    """Report or apply `upgrade head` against every store in the registry."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="List every target and its current revision, and change nothing.",
    )
    group.add_argument("--yes", action="store_true", help="Apply the upgrades.")
    args = parser.parse_args()

    settings = Settings()
    platform = DatabaseManager.from_settings(settings)
    try:
        targets = _targets(platform, settings)
    finally:
        platform.dispose()

    print(f"{len(targets)} store(s) to migrate.")
    if args.dry_run:
        for target in targets:
            print(f"  {target.label}: at {_current_revision(target)}")
        print("\nDry run only. Re-run with --yes to upgrade these stores.")
        return 0

    failures = 0
    for target in targets:
        ok, detail = _upgrade(target)
        if ok:
            print(f"  {target.label}: upgraded to head")
            continue
        failures += 1
        print(f"  {target.label}: FAILED\n    {detail}")
    if failures:
        # Report every store rather than stopping at the first failure: knowing
        # that four of five upgraded is the difference between a retry and an
        # investigation.
        print(f"\n{failures} of {len(targets)} store(s) failed.")
        return 1
    print("\nEvery store is at head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
