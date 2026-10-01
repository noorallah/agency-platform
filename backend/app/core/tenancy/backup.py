"""Back up every store, and list the backups on this machine.

Setup's nightly task (``packaging/server_setup.ps1 -Action DailyBackup``)
writes ``<backup root>/daily/<stamp>/``; an upgrade writes
``<backup root>/pre-upgrade-<version>-<stamp>/``. This module adds the third
kind, ``manual/<stamp>/``, taken when an administrator presses **Back up now**
or runs ``agency-server backup`` -- and it is what lists all three, so the
screen shows whether last night's backup actually happened.

The stores come from :func:`migration_targets`, the enumeration ``migrate-all``
upgrades, so a firm added tomorrow is backed up tomorrow. Soft-deleted firms
are included -- their data is still there -- and a store that was never built
is reported as skipped rather than failed. Each store is one custom-format
``pg_dump -n <schema>``, the same shape as the nightly one, so the restore steps
in ``docs/INSTALL_GUIDE.md`` section 6 apply to every kind.

A backup is only proved by reading it back. After each dump ``pg_restore
--list`` reads the archive's table of contents, and the number of tables whose
data it holds goes into ``manifest.json`` beside the dumps; an archive that
cannot be listed fails the backup. ``tests/integration/test_backup_restore_drill.py``
goes the whole way: it restores a backup into a fresh database and compares
every table's row count.

The password reaches ``pg_dump`` through ``PGPASSWORD`` in the child's own
environment, never on its command line, where any user on the machine could
read it from the process list.
"""

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.engine import make_url

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.paths import application_root
from app.core.tenancy.migrations import (
    MigrationTarget,
    count_firms,
    current_revision,
    migration_targets,
    store_is_built,
)
from app.core.utils.dates import utc_now

#: The marker a finished backup carries. A folder without it is a run that
#: stopped part-way, and is never offered as a backup.
COMPLETE_MARKER = ".complete"
MANIFEST_NAME = "manifest.json"
MANUAL_FOLDER = "manual"
DAILY_FOLDER = "daily"
PRE_UPGRADE_PREFIX = "pre-upgrade-"

# One dump at a time, whoever asked: two concurrent backups double the load on
# the database for no second copy worth having.
_RUN_LOCK = threading.Lock()


class BackupError(Exception):
    """A backup could not be taken; the message says why, in plain words."""


@dataclass(frozen=True, slots=True)
class StoreDump:
    """What happened to one store in one backup."""

    label: str
    database: str
    schema: str
    file_name: str | None
    size_bytes: int
    tables: int
    revision: str
    outcome: str  # "ok" | "skipped" | "failed"
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class BackupResult:
    """One finished run of :func:`back_up_every_store`."""

    run_id: UUID
    folder: Path
    started_at: datetime
    finished_at: datetime
    stores: list[StoreDump]

    @property
    def failed(self) -> list[StoreDump]:
        """Return the stores that could not be backed up."""
        return [store for store in self.stores if store.outcome == "failed"]


@dataclass(frozen=True, slots=True)
class BackupFolder:
    """One backup found on disk, of any kind."""

    kind: str  # "manual" | "daily" | "pre-upgrade"
    name: str
    path: Path
    created_at: datetime | None
    complete: bool | None  # None: the server may not read the folder
    size_bytes: int | None
    files: int | None
    application_version: str | None = None
    requested_by: str | None = None
    stores: list[dict[str, object]] = field(default_factory=list)


def find_pg_tool(name: str, settings: Settings) -> Path:
    """Return the path to ``pg_dump`` or ``pg_restore``, or say where it looked.

    In order: ``AGENCY_BACKUP_PG_BIN``; the private PostgreSQL an installed copy
    carries beside itself (``<install>/pgsql/bin``, the server being
    ``<install>/backend``); PATH; and the newest PostgreSQL under Program
    Files, which is where an install from before the private database kept
    its server.
    """
    executable = f"{name}.exe" if os.name == "nt" else name
    candidates: list[Path] = []
    if settings.backup_pg_bin is not None:
        candidates.append(Path(settings.backup_pg_bin) / executable)
    candidates.append(application_root().parent / "pgsql" / "bin" / executable)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    on_path = shutil.which(name)
    if on_path:
        return Path(on_path)
    program_files = os.environ.get("PROGRAMFILES")
    if program_files:
        found = sorted(
            Path(program_files).glob(f"PostgreSQL/*/bin/{executable}"), reverse=True
        )
        if found:
            return found[0]
    raise BackupError(
        f"{name} was not found, so no backup can be taken. Install the "
        "PostgreSQL client tools or set AGENCY_BACKUP_PG_BIN to their folder."
    )


def _connection_arguments(database_url: str) -> tuple[list[str], dict[str, str]]:
    """Split a SQLAlchemy URL into libpq arguments and the password env."""
    url = make_url(database_url)
    arguments = ["-h", url.host or "localhost", "-p", str(url.port or 5432)]
    if url.username:
        arguments += ["-U", url.username]
    environment = dict(os.environ)
    environment.pop("PGPASSWORD", None)
    if url.password is not None:
        environment["PGPASSWORD"] = str(url.password)
    return arguments, environment


def _run(arguments: list[str], environment: dict[str, str]) -> str:
    """Run one client tool; return its stdout or raise with its stderr."""
    completed = subprocess.run(  # noqa: S603 - fixed tool, no shell
        arguments,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        # Windows: no console window flashing up from a service.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-600:]
        raise BackupError(detail or f"exit code {completed.returncode}")
    return completed.stdout


def _exact_name(name: str) -> str:
    """Quote a schema name so ``pg_dump -n`` matches it exactly.

    ``-n`` takes a pattern, and an unquoted pattern is folded to lower case:
    ``-n SNTEST01`` matches no schema at all, and pg_dump writes an empty
    file. Firm schemas are named from firm codes, which are upper case.
    """
    return '"' + name.replace('"', '""') + '"'


def _count_table_data(listing: str) -> int:
    """Count the tables whose rows an archive holds, from ``pg_restore --list``."""
    return sum(1 for line in listing.splitlines() if " TABLE DATA " in line)


def _dump_one(
    target: MigrationTarget,
    folder: Path,
    *,
    pg_dump: Path,
    pg_restore: Path,
) -> StoreDump:
    """Dump one store into ``folder`` and read the archive back."""
    url = make_url(target.database_url)
    database = url.database or ""
    if not store_is_built(
        database_url=target.database_url, schema_name=target.schema_name
    ):
        return StoreDump(
            label=target.label,
            database=database,
            schema=target.schema_name,
            file_name=None,
            size_bytes=0,
            tables=0,
            revision="none",
            outcome="skipped",
            detail="never built, so there is nothing in it to back up",
        )
    revision = current_revision(target)
    file_name = f"{database}--{target.schema_name}.dump"
    path = folder / file_name
    connection, environment = _connection_arguments(target.database_url)
    try:
        _run(
            [
                str(pg_dump),
                *connection,
                "-d",
                database,
                "-n",
                _exact_name(target.schema_name),
                "-Fc",
                "--no-password",
                "-f",
                str(path),
            ],
            environment,
        )
        if not path.is_file() or path.stat().st_size == 0:
            raise BackupError("pg_dump wrote nothing")
        tables = _count_table_data(
            _run([str(pg_restore), "--list", str(path)], environment)
        )
    except BackupError as error:
        return StoreDump(
            label=target.label,
            database=database,
            schema=target.schema_name,
            file_name=file_name if path.is_file() else None,
            size_bytes=path.stat().st_size if path.is_file() else 0,
            tables=0,
            revision=revision,
            outcome="failed",
            detail=str(error),
        )
    return StoreDump(
        label=target.label,
        database=database,
        schema=target.schema_name,
        file_name=file_name,
        size_bytes=path.stat().st_size,
        tables=tables,
        revision=revision,
        outcome="ok",
    )


def backup_targets(settings: Settings) -> list[MigrationTarget]:
    """Return every store a backup takes, deleted firms' stores included."""
    platform = DatabaseManager.from_settings(settings)
    try:
        fresh = not count_firms(platform)
        return migration_targets(
            platform, settings, platform_only=fresh, include_deleted=True
        )
    finally:
        platform.dispose()


def _stamp(moment: datetime) -> str:
    """Name a backup folder by when it was taken, sortable as text.

    In the machine's own time, as the nightly task and Setup name theirs, so
    the three kinds sort together in the folder an administrator opens.
    """
    return moment.astimezone().strftime("%Y%m%d-%H%M%S")


def back_up_every_store(
    settings: Settings,
    *,
    requested_by: str,
    report: Callable[[str], None] | None = None,
    targets: list[MigrationTarget] | None = None,
) -> BackupResult:
    """Take a manual backup of every store. Raises :class:`BackupError`.

    A store that fails is reported and the rest are still taken, but the
    folder is then not marked complete: a backup missing a store is not a
    backup of the installation, and is never offered as one. Only one run
    at a time; a second caller is refused rather than queued.
    """
    say = report if report is not None else (lambda _line: None)
    if not _RUN_LOCK.acquire(blocking=False):
        raise BackupError("A backup is already running. Wait for it to finish.")
    try:
        pg_dump = find_pg_tool("pg_dump", settings)
        pg_restore = find_pg_tool("pg_restore", settings)
        stores = targets if targets is not None else backup_targets(settings)
        root = Path(settings.backup_directory) / MANUAL_FOLDER
        _clear_unfinished(root)
        started = utc_now()
        run_id = uuid4()
        folder = root / _stamp(started)
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise BackupError(
                f"Could not create the backup folder {folder}: {error.strerror}"
            ) from error
        say(f"{len(stores)} store(s) to back up into {folder}")
        results: list[StoreDump] = []
        for target in stores:
            result = _dump_one(target, folder, pg_dump=pg_dump, pg_restore=pg_restore)
            results.append(result)
            say(f"  {target.label}: {result.outcome}" + _suffix(result))
        finished = utc_now()
        backup = BackupResult(
            run_id=run_id,
            folder=folder,
            started_at=started,
            finished_at=finished,
            stores=results,
        )
        _write_manifest(backup, settings, requested_by=requested_by)
        if not backup.failed:
            (folder / COMPLETE_MARKER).write_text(_stamp(started) + "\n")
            removed = _apply_retention(root, settings.backup_keep_manual)
            for name in removed:
                say(f"  removed the old backup {name}")
        return backup
    finally:
        _RUN_LOCK.release()


def is_running() -> bool:
    """Return whether a backup is being taken in this process right now."""
    return _RUN_LOCK.locked()


def _suffix(result: StoreDump) -> str:
    """Return the detail printed after a store's outcome."""
    if result.outcome == "ok":
        return f" ({result.tables} tables, {result.size_bytes:,} bytes)"
    return f" -- {result.detail}" if result.detail else ""


def _write_manifest(
    backup: BackupResult, settings: Settings, *, requested_by: str
) -> None:
    """Record what the folder holds, for the screen and for whoever restores."""
    manifest = {
        "run_id": str(backup.run_id),
        "kind": MANUAL_FOLDER,
        "application_version": settings.app_version,
        "requested_by": requested_by,
        "started_at": backup.started_at.isoformat(),
        "finished_at": backup.finished_at.isoformat(),
        "stores": [
            {
                "label": store.label,
                "database": store.database,
                "schema": store.schema,
                "file": store.file_name,
                "size_bytes": store.size_bytes,
                "tables": store.tables,
                "revision": store.revision,
                "outcome": store.outcome,
                "detail": store.detail,
            }
            for store in backup.stores
        ],
    }
    (backup.folder / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _clear_unfinished(root: Path) -> None:
    """Delete manual folders a stopped run left behind without the marker."""
    if not root.is_dir():
        return
    for child in root.iterdir():
        if child.is_dir() and not (child / COMPLETE_MARKER).exists():
            shutil.rmtree(child, ignore_errors=True)


def _apply_retention(root: Path, keep: int) -> list[str]:
    """Keep the newest ``keep`` complete manual backups; return what went."""
    complete = sorted(
        (
            child
            for child in root.iterdir()
            if child.is_dir() and (child / COMPLETE_MARKER).exists()
        ),
        key=lambda child: child.name,
        reverse=True,
    )
    removed: list[str] = []
    for old in complete[keep:]:
        shutil.rmtree(old, ignore_errors=True)
        removed.append(old.name)
    return removed


def _parse_stamp(text_value: str) -> datetime | None:
    """Read a ``yyyyMMdd-HHmmss`` folder stamp as UTC, or None if it is not one.

    Every kind names its folder in the machine's local time (see ``_stamp``).
    """
    try:
        local = datetime.strptime(text_value[-15:], "%Y%m%d-%H%M%S")  # noqa: DTZ007
    except ValueError:
        return None
    return local.astimezone(UTC)


def _describe(kind: str, path: Path) -> BackupFolder:
    """Read one backup folder, tolerating one the server may not open."""
    created = _parse_stamp(path.name)
    try:
        files = [child for child in path.iterdir() if child.is_file()]
    except OSError:
        # The nightly folders are written as SYSTEM; one written before the
        # server was granted read on them cannot be looked inside.
        return BackupFolder(
            kind=kind,
            name=path.name,
            path=path,
            created_at=created,
            complete=None,
            size_bytes=None,
            files=None,
        )
    dumps = [child for child in files if child.suffix == ".dump"]
    complete = any(child.name == COMPLETE_MARKER for child in files)
    if kind == "pre-upgrade":
        # Setup writes no marker before an upgrade; it stops the upgrade
        # instead when a dump fails, so a folder with dumps in it is whole.
        complete = bool(dumps)
    folder = BackupFolder(
        kind=kind,
        name=path.name,
        path=path,
        created_at=created,
        complete=complete,
        size_bytes=sum(child.stat().st_size for child in dumps),
        files=len(dumps),
    )
    manifest_path = path / MANIFEST_NAME
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return folder
        return BackupFolder(
            kind=folder.kind,
            name=folder.name,
            path=folder.path,
            created_at=_manifest_time(manifest) or folder.created_at,
            complete=folder.complete,
            size_bytes=folder.size_bytes,
            files=folder.files,
            application_version=manifest.get("application_version"),
            requested_by=manifest.get("requested_by"),
            stores=list(manifest.get("stores") or []),
        )
    return folder


def _manifest_time(manifest: dict[str, object]) -> datetime | None:
    """Return when a manifest says its backup started, or None."""
    value = manifest.get("started_at")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def list_backups(settings: Settings) -> list[BackupFolder]:
    """Return every backup under the backup root, newest first, of all three kinds."""
    root = Path(settings.backup_directory)
    found: list[BackupFolder] = []
    for kind, folder in ((MANUAL_FOLDER, MANUAL_FOLDER), (DAILY_FOLDER, DAILY_FOLDER)):
        directory = root / folder
        try:
            children = [child for child in directory.iterdir() if child.is_dir()]
        except OSError:
            continue
        found.extend(_describe(kind, child) for child in children)
    try:
        upgrades = [
            child
            for child in root.iterdir()
            if child.is_dir() and child.name.startswith(PRE_UPGRADE_PREFIX)
        ]
    except OSError:
        upgrades = []
    found.extend(_describe("pre-upgrade", child) for child in upgrades)
    return sorted(
        found,
        key=lambda backup: backup.created_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
