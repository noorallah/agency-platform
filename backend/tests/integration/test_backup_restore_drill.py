"""The restore drill: a backup is only a backup once it has been put back.

``Back up now`` and ``agency-server backup`` write one ``pg_dump -Fc`` per
store (``app/core/tenancy/backup.py``). This takes one through the same code,
restores it with ``pg_restore`` into a database that did not exist a moment
before -- which is what a restore onto a replacement machine is -- and asks
that every table came back with every row.

The store's schema is named in upper case on purpose. Firm schemas are named
from firm codes, and ``pg_dump -n SNTEST01`` folds the pattern to lower case,
matches nothing and writes an empty file; that broke the nightly backup of any
such firm until 2026-10-01, and nothing short of a real ``pg_dump`` can see it.

Needs the PostgreSQL client tools as new as the server (CI installs them and
points ``AGENCY_BACKUP_PG_BIN`` at them). Skipped without them on a laptop;
**failed** without them in CI, so the drill cannot quietly stop running.
"""

import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.core.config.settings import Settings
from app.core.tenancy.backup import (
    BackupError,
    back_up_every_store,
    find_pg_tool,
)
from app.core.tenancy.migrations import MigrationTarget


def _major(version_text: str) -> int:
    """Read the major version out of ``pg_dump --version`` or ``SHOW``."""
    found = re.search(r"(\d+)(?:\.\d+)?", version_text)
    return int(found.group(1)) if found else 0


def _tools_or_skip(engine: Engine) -> tuple[Path, Path]:
    """Return pg_dump and pg_restore, or skip (fail in CI) without usable ones."""
    settings = Settings()
    try:
        pg_dump = find_pg_tool("pg_dump", settings)
        pg_restore = find_pg_tool("pg_restore", settings)
    except BackupError as error:
        if os.environ.get("CI"):
            pytest.fail(f"CI must run the restore drill: {error}")
        pytest.skip(str(error))
    client = _major(
        subprocess.run(  # noqa: S603 - fixed tool
            [str(pg_dump), "--version"], capture_output=True, text=True, check=True
        ).stdout
    )
    with engine.connect() as connection:
        server = _major(str(connection.scalar(text("SHOW server_version"))))
    if client < server:
        message = f"pg_dump {client} cannot dump a PostgreSQL {server} server"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    return pg_dump, pg_restore


@pytest.fixture
def source_store(engine: Engine) -> Iterator[str]:
    """Build a store with an upper-case name, four tables and a few rows."""
    schema = f"DRILL_{uuid4().hex[:8].upper()}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".firms '
                "(id uuid PRIMARY KEY, code text NOT NULL UNIQUE)"
            )
        )
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".invoices (id serial PRIMARY KEY, '
                f'firm_id uuid NOT NULL REFERENCES "{schema}".firms(id), '
                "total numeric(14, 2) NOT NULL)"
            )
        )
        connection.execute(text(f'CREATE TABLE "{schema}".empty_table (id int)'))
        # What makes it a built store rather than one provisioning never
        # reached, which a backup skips.
        connection.execute(
            text(f'CREATE TABLE "{schema}".alembic_version (version_num varchar(32))')
        )
        connection.execute(
            text(f"INSERT INTO \"{schema}\".alembic_version VALUES ('drill')")
        )
        firm = uuid4()
        connection.execute(
            text(f"INSERT INTO \"{schema}\".firms VALUES (:id, 'DRILL01')"),
            {"id": firm},
        )
        for total in ("100.00", "250.50", "999.99"):
            connection.execute(
                text(
                    f'INSERT INTO "{schema}".invoices (firm_id, total) '
                    "VALUES (:firm, :total)"
                ),
                {"firm": firm, "total": total},
            )
    try:
        yield schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _counts(engine: Engine, schema: str) -> dict[str, int]:
    """Return every table in a schema with its row count."""
    with engine.connect() as connection:
        tables = connection.scalars(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema ORDER BY table_name"
            ),
            {"schema": schema},
        ).all()
        return {
            table: int(
                connection.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"'))
                or 0
            )
            for table in tables
        }


def test_a_backup_restores_into_a_fresh_database_with_every_row(
    engine: Engine, source_store: str, tmp_path: Path
) -> None:
    """Dump through the product's own code, restore elsewhere, compare."""
    _, pg_restore = _tools_or_skip(engine)
    url = engine.url.render_as_string(hide_password=False)
    settings = Settings(backup_directory=tmp_path)

    result = back_up_every_store(
        settings,
        requested_by="restore drill",
        targets=[
            MigrationTarget(label="drill", database_url=url, schema_name=source_store)
        ],
    )

    assert not result.failed, result.failed
    (dump,) = result.stores
    assert dump.outcome == "ok"
    assert dump.revision == "drill"
    assert dump.tables == 4, "pg_restore --list should see every table's data"
    archive = result.folder / str(dump.file_name)

    fresh = f"drill_restore_{uuid4().hex[:8]}"
    admin = create_engine(engine.url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{fresh}"'))
    except Exception as error:  # noqa: BLE001 - a permission, not a defect
        admin.dispose()
        pytest.skip(f"cannot create a scratch database: {type(error).__name__}")
    restored_url = make_url(url).set(database=fresh)
    restored = create_engine(restored_url)
    try:
        parsed = make_url(url)
        environment = {**os.environ, "PGPASSWORD": str(parsed.password or "")}
        subprocess.run(  # noqa: S603 - fixed tool
            [
                str(pg_restore),
                "-h",
                parsed.host or "localhost",
                "-p",
                str(parsed.port or 5432),
                "-U",
                parsed.username or "",
                "-d",
                fresh,
                "--no-owner",
                "--exit-on-error",
                str(archive),
            ],
            env=environment,
            check=True,
            capture_output=True,
        )

        assert _counts(restored, source_store) == _counts(engine, source_store)
        assert _counts(restored, source_store) == {
            "alembic_version": 1,
            "empty_table": 0,
            "firms": 1,
            "invoices": 3,
        }
        with restored.connect() as connection:
            total = connection.scalar(
                text(f'SELECT sum(total) FROM "{source_store}".invoices')
            )
        assert str(total) == "1350.49"
    finally:
        restored.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{fresh}"'))
        admin.dispose()
