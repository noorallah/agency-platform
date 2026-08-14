"""Destructively rebuild the final platform + shared-tenant schema layout."""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url

from alembic import command
from app.api.dependencies.settings import get_settings
from app.core.database.engine import DatabaseManager
from app.core.tenancy.lifecycle import (
    _PLATFORM_TABLES,
    _safe_identifier,
    prune_platform_objects,
)

_ALEMBIC_INI = (Path(__file__).resolve().parents[1] / "alembic.ini").as_posix()
_LEGACY_SCHEMAS = ("PF_SHARED", "platform_shared", "platform", "firm_shared", "public")


def main() -> int:
    """Rebuild the platform and firm_shared schemas from scratch."""
    parser = argparse.ArgumentParser(
        description=(
            "Drop the current Agency Platform schemas/tables and rebuild the final "
            "platform and firm_shared schemas."
        )
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the safety prompt and execute the destructive reset immediately.",
    )
    args = parser.parse_args()

    if not args.yes:
        print("Refusing to run without --yes because this deletes existing app data.")
        return 1

    settings = get_settings()
    platform = DatabaseManager.from_settings(settings)
    shared_database_name = settings.tenancy.shared_database_name
    platform_schema = settings.database_schema or "platform"
    shared_schema = settings.tenancy.shared_schema_name
    platform_url = make_url(platform.config.url)
    current_database_name = platform_url.database or settings.database_name

    engine = create_engine(
        platform_url.render_as_string(hide_password=False), pool_pre_ping=True
    )
    try:
        app_tables = _collect_app_tables(engine)
        dedicated_databases = _collect_dedicated_databases(
            engine,
            current_database_name=current_database_name,
            shared_database_name=shared_database_name,
        )
        for database_name in sorted(dedicated_databases):
            _drop_postgresql_database(platform_url, database_name)

        for schema_name in sorted(
            {
                schema
                for schema in _collect_drop_schemas(engine)
                if schema.lower() != "public"
            }
        ):
            _drop_schema(engine, schema_name)

        if _schema_exists(engine, "public") and "alembic_version" in _list_tables(
            engine, "public"
        ):
            _drop_public_tables(engine, app_tables or _list_tables(engine, "public"))

        _create_schema(engine, platform_schema)
        _create_schema(engine, shared_schema)
    finally:
        engine.dispose()

    _run_migrations(platform_url, platform_schema)
    _run_migrations(platform_url, shared_schema)
    _prune_platform_tables(platform_url, shared_schema)
    _prune_non_platform_tables(platform_url, platform_schema)
    print(
        "Rebuilt tenancy layout: "
        f"database={current_database_name} platform_schema={platform_schema} "
        f"shared_schema={shared_schema}"
    )
    return 0


def _collect_app_tables(engine: Engine) -> set[str]:
    app_tables: set[str] = set()
    for schema_name in _LEGACY_SCHEMAS:
        if not _schema_exists(engine, schema_name):
            continue
        tables = _list_tables(engine, schema_name)
        if "alembic_version" not in tables:
            continue
        app_tables.update(tables)
    return app_tables


def _collect_drop_schemas(engine: Engine) -> set[str]:
    schemas = {
        schema_name
        for schema_name in _LEGACY_SCHEMAS
        if schema_name != "public" and _schema_exists(engine, schema_name)
    }
    for schema_name in _mapping_source_schemas(engine):
        schemas.update(
            discovered_schema
            for discovered_schema in _read_schema_mappings(engine, schema_name)
            if discovered_schema and discovered_schema.lower() != "public"
        )
    return schemas


def _collect_dedicated_databases(
    engine: Engine, *, current_database_name: str, shared_database_name: str
) -> set[str]:
    databases: set[str] = set()
    protected = {
        current_database_name.lower(),
        shared_database_name.lower(),
        "postgres",
    }
    for schema_name in _mapping_source_schemas(engine):
        for database_name in _read_database_mappings(engine, schema_name):
            if database_name and database_name.lower() not in protected:
                databases.add(database_name)
    return databases


def _mapping_source_schemas(engine: Engine) -> list[str]:
    result: list[str] = []
    for schema_name in _LEGACY_SCHEMAS:
        if not _schema_exists(engine, schema_name):
            continue
        if "firm_storage_mappings" in _list_tables(engine, schema_name):
            result.append(schema_name)
    return result


def _read_schema_mappings(engine: Engine, schema_name: str) -> set[str]:
    schema = _safe_identifier(schema_name, "schema name")
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                f'SELECT schema_name FROM "{schema}"."firm_storage_mappings" '
                "WHERE is_deleted IS FALSE"
            )
        )
        return {row[0] for row in rows if row[0] is not None and str(row[0]).strip()}


def _read_database_mappings(engine: Engine, schema_name: str) -> set[str]:
    schema = _safe_identifier(schema_name, "schema name")
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                f'SELECT database_name FROM "{schema}"."firm_storage_mappings" '
                "WHERE is_deleted IS FALSE"
            )
        )
        return {row[0] for row in rows if row[0] is not None and str(row[0]).strip()}


def _schema_exists(engine: Engine, schema_name: str) -> bool:
    with engine.connect() as connection:
        return (
            connection.scalar(
                text(
                    "SELECT 1 FROM information_schema.schemata "
                    "WHERE schema_name = :schema_name"
                ),
                {"schema_name": schema_name},
            )
            is not None
        )


def _list_tables(engine: Engine, schema_name: str) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema_name AND table_type = 'BASE TABLE'"
            ),
            {"schema_name": schema_name},
        )
        return {row[0] for row in rows}


def _drop_schema(engine: Engine, schema_name: str) -> None:
    schema = _safe_identifier(schema_name, "schema name")
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _drop_public_tables(engine: Engine, table_names: set[str]) -> None:
    with engine.begin() as connection:
        for table_name in sorted(table_names):
            if not table_name or not table_name.strip():
                continue
            table = _safe_identifier(table_name, "table name")
            connection.execute(text(f'DROP TABLE IF EXISTS "public"."{table}" CASCADE'))
        connection.execute(
            text('DROP FUNCTION IF EXISTS "public".reject_audit_log_mutation() CASCADE')
        )


def _create_schema(engine: Engine, schema_name: str) -> None:
    schema = _safe_identifier(schema_name, "schema name")
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))


def _drop_postgresql_database(platform_url: URL, database_name: str) -> None:
    database = _safe_identifier(database_name, "database name")
    admin_url = platform_url.set(database="postgres")
    engine = create_engine(
        admin_url.render_as_string(hide_password=False),
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
    finally:
        engine.dispose()


def _run_migrations(platform_url: URL, schema_name: str) -> None:
    with _temporary_environment(
        {
            "AGENCY_DATABASE_URL": platform_url.render_as_string(hide_password=False),
            "AGENCY_DATABASE_SCHEMA": schema_name,
        }
    ):
        alembic_config = Config(_ALEMBIC_INI)
        command.upgrade(alembic_config, "head")


def _prune_platform_tables(platform_url: URL, schema_name: str) -> None:
    prune_platform_objects(
        database_url=platform_url.render_as_string(hide_password=False),
        schema_name=schema_name,
    )


def _prune_non_platform_tables(platform_url: URL, schema_name: str) -> None:
    schema = _safe_identifier(schema_name, "schema name")
    keep_tables = {"alembic_version", "audit_logs", *_PLATFORM_TABLES}
    engine = create_engine(
        platform_url.render_as_string(hide_password=False), pool_pre_ping=True
    )
    try:
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema_name AND table_type = 'BASE TABLE'"
                ),
                {"schema_name": schema},
            )
            drop_tables = sorted(
                table_name for (table_name,) in rows if table_name not in keep_tables
            )
            for table_name in drop_tables:
                table = _safe_identifier(table_name, "table name")
                connection.execute(
                    text(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE')
                )
    finally:
        engine.dispose()


@contextmanager
def _temporary_environment(overrides: dict[str, str]) -> Iterator[None]:
    original = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
