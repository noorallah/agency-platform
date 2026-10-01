"""Back up now, and the list of backups (BACKLOG section 35).

``pg_dump`` and ``pg_restore`` are faked here: what these pin is the folder a
backup leaves, the marker that says it is whole, retention, refusing a second
run, and the exact ``-n`` argument -- an unquoted upper-case schema matched no
schema at all and dumped an empty file. The real round trip, dump and restore
into a fresh database, is ``tests/integration/test_backup_restore_drill.py``.
"""

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.backups.api.router import list_all_backups, start_backup
from app.backups.services import BackupRunner
from app.common.audit.models import AuditLog
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.database.dependencies import _is_platform_path
from app.core.enums import TokenType
from app.core.exceptions import ConflictError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.core.tenancy import backup
from app.core.tenancy.backup import (
    COMPLETE_MARKER,
    BackupError,
    back_up_every_store,
    list_backups,
)
from app.core.tenancy.migrations import MigrationTarget
from app.identity.system_seed import PERMISSION_GROUPS


def _settings(tmp_path: Path, keep: int = 10) -> Settings:
    return Settings(backup_directory=tmp_path, backup_keep_manual=keep)


def _target(schema: str, database: str = "agency") -> MigrationTarget:
    return MigrationTarget(
        label=f"{schema} ({database}/{schema})",
        database_url=f"postgresql+psycopg://app:secret@db.local:5433/{database}",
        schema_name=schema,
    )


@pytest.fixture
def fake_tools(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Fake pg_dump/pg_restore; record every command line they were given."""
    calls: list[list[str]] = []

    def run(arguments: list[str], environment: dict[str, str]) -> str:
        calls.append(arguments)
        assert environment["PGPASSWORD"] == "secret"
        assert "secret" not in " ".join(arguments)
        if "--list" in arguments:
            return (
                "1; 2615 2200 TABLE DATA s users app\n2; 1 1 TABLE DATA s firms app\n"
            )
        target = Path(arguments[arguments.index("-f") + 1])
        if '"BROKEN"' in arguments:
            raise BackupError("pg_dump: error: connection refused")
        target.write_bytes(b"PGDMP fake archive")
        return ""

    monkeypatch.setattr(backup, "_run", run)
    monkeypatch.setattr(backup, "find_pg_tool", lambda name, _s: Path(name))
    monkeypatch.setattr(backup, "store_is_built", lambda **_kw: True)
    monkeypatch.setattr(backup, "current_revision", lambda _t: "20261001_0179")
    return calls


def test_a_backup_dumps_every_store_and_marks_the_folder_whole(
    tmp_path: Path, fake_tools: list[list[str]]
) -> None:
    """One dump per store, a manifest, and the marker that says it is whole."""
    result = back_up_every_store(
        _settings(tmp_path),
        requested_by="admin@firm.test",
        targets=[_target("platform"), _target("SNTEST01")],
    )

    assert not result.failed
    assert result.folder.parent == tmp_path / "manual"
    assert (result.folder / COMPLETE_MARKER).is_file()
    assert sorted(path.name for path in result.folder.glob("*.dump")) == [
        "agency--SNTEST01.dump",
        "agency--platform.dump",
    ]
    manifest = json.loads((result.folder / "manifest.json").read_text())
    assert manifest["requested_by"] == "admin@firm.test"
    assert [store["tables"] for store in manifest["stores"]] == [2, 2]
    assert {store["revision"] for store in manifest["stores"]} == {"20261001_0179"}


def test_the_schema_is_quoted_so_an_upper_case_name_matches(
    tmp_path: Path, fake_tools: list[list[str]]
) -> None:
    """``-n SNTEST01`` unquoted matched nothing; quoted it matches exactly."""
    back_up_every_store(
        _settings(tmp_path), requested_by="x", targets=[_target("SNTEST01")]
    )

    dump = next(call for call in fake_tools if "-Fc" in call)
    assert dump[dump.index("-n") + 1] == '"SNTEST01"'
    assert dump[dump.index("-h") + 1] == "db.local"
    assert dump[dump.index("-p") + 1] == "5433"
    assert dump[dump.index("-U") + 1] == "app"


def test_a_failed_store_leaves_the_folder_unmarked_and_the_rest_taken(
    tmp_path: Path, fake_tools: list[list[str]]
) -> None:
    """A backup missing a store is never offered as a whole one."""
    result = back_up_every_store(
        _settings(tmp_path),
        requested_by="x",
        targets=[_target("platform"), _target("BROKEN")],
    )

    assert [store.label for store in result.failed] == ["BROKEN (agency/BROKEN)"]
    assert "connection refused" in (result.failed[0].detail or "")
    assert (result.folder / "agency--platform.dump").is_file()
    assert not (result.folder / COMPLETE_MARKER).exists()
    listed = list_backups(_settings(tmp_path))
    assert [(item.kind, item.complete) for item in listed] == [("manual", False)]


def test_a_store_never_built_is_skipped_not_failed(
    tmp_path: Path, fake_tools: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dedicated firm never provisioned has nothing to back up."""
    monkeypatch.setattr(
        backup, "store_is_built", lambda **kw: kw["schema_name"] != "firm_new"
    )

    result = back_up_every_store(
        _settings(tmp_path),
        requested_by="x",
        targets=[_target("platform"), _target("firm_new")],
    )

    assert [store.outcome for store in result.stores] == ["ok", "skipped"]
    assert (result.folder / COMPLETE_MARKER).is_file()


def test_retention_keeps_the_newest_manual_backups(
    tmp_path: Path, fake_tools: list[list[str]]
) -> None:
    """Old complete backups go; an unfinished folder is cleared."""
    manual = tmp_path / "manual"
    for stamp in ("20260901-020000", "20260902-020000", "20260903-020000"):
        (manual / stamp).mkdir(parents=True)
        (manual / stamp / COMPLETE_MARKER).write_text(stamp)
    unfinished = manual / "20260904-020000"
    unfinished.mkdir()

    result = back_up_every_store(
        _settings(tmp_path, keep=2), requested_by="x", targets=[_target("platform")]
    )

    remaining = sorted(path.name for path in manual.iterdir())
    assert remaining == ["20260903-020000", result.folder.name]
    assert not unfinished.exists()


def test_a_second_backup_is_refused_while_one_runs(
    tmp_path: Path, fake_tools: list[list[str]]
) -> None:
    """Two dumps at once double the load for no second copy."""
    backup._RUN_LOCK.acquire()
    try:
        with pytest.raises(BackupError, match="already running"):
            back_up_every_store(
                _settings(tmp_path), requested_by="x", targets=[_target("platform")]
            )
    finally:
        backup._RUN_LOCK.release()


def test_no_pg_dump_says_where_to_point_the_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal names the setting that fixes it."""
    monkeypatch.setattr(backup.shutil, "which", lambda _name: None)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.setenv("AGENCY_APPLICATION_ROOT", str(tmp_path / "backend"))

    with pytest.raises(BackupError, match="AGENCY_BACKUP_PG_BIN"):
        backup.find_pg_tool("pg_dump", _settings(tmp_path))


def test_the_private_postgresql_beside_the_install_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An installed copy uses ``<install>/pgsql/bin`` with no setting."""
    monkeypatch.setenv("AGENCY_APPLICATION_ROOT", str(tmp_path / "backend"))
    name = "pg_dump.exe" if backup.os.name == "nt" else "pg_dump"
    bundled = tmp_path / "pgsql" / "bin" / name
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"")

    assert backup.find_pg_tool("pg_dump", _settings(tmp_path)) == bundled


def test_the_list_shows_all_three_kinds_newest_first(tmp_path: Path) -> None:
    """By hand, nightly and pre-upgrade backups are listed together."""
    manual = tmp_path / "manual" / "20260930-101500"
    manual.mkdir(parents=True)
    (manual / "agency--platform.dump").write_bytes(b"x" * 10)
    (manual / COMPLETE_MARKER).write_text("")
    (manual / "manifest.json").write_text(
        json.dumps(
            {
                "application_version": "1.1.0",
                "requested_by": "admin@firm.test",
                "started_at": "2026-09-30T04:45:00+00:00",
                "stores": [{"label": "platform", "schema": "platform"}],
            }
        )
    )
    daily = tmp_path / "daily" / "20261001-020000"
    daily.mkdir(parents=True)
    (daily / "agency--platform.dump").write_bytes(b"x" * 20)
    (daily / COMPLETE_MARKER).write_text("")
    upgrade = tmp_path / "pre-upgrade-1.0.2-20260915-090000"
    upgrade.mkdir()
    (upgrade / "agency.dump").write_bytes(b"x" * 30)
    (tmp_path / "not-a-backup").mkdir()

    listed = list_backups(_settings(tmp_path))

    assert [(item.kind, item.complete, item.size_bytes) for item in listed] == [
        ("daily", True, 20),
        ("manual", True, 10),
        ("pre-upgrade", True, 30),
    ]
    assert listed[1].requested_by == "admin@firm.test"
    assert listed[1].application_version == "1.1.0"


def test_an_empty_backup_root_lists_nothing(tmp_path: Path) -> None:
    """No backup folder yet is an empty list, not an error."""
    assert list_backups(_settings(tmp_path / "missing")) == []


# -- The API -----------------------------------------------------------------


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _principal() -> Principal:
    subject = uuid4()
    return Principal(
        subject=subject,
        roles=frozenset(),
        permissions=frozenset({"SYSTEM_BACKUP"}),
        claims=TokenClaims(
            sub=str(subject), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )


def _request(settings: Settings) -> Request:
    return cast(
        Request,
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))),
    )


def test_the_routes_are_platform_paths_gated_on_a_seeded_code() -> None:
    """A backup belongs to no firm, and its gate is a seeded code."""
    assert _is_platform_path("/api/v1/backups")
    assert "SYSTEM_BACKUP" in PERMISSION_GROUPS["platform"]


def test_back_up_now_starts_once_records_it_and_reports_the_outcome(
    tmp_path: Path, fake_tools: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The button starts one run, audits it, and the list reports it."""
    release = threading.Event()

    def slow_backup(settings: Settings, *, requested_by: str) -> backup.BackupResult:
        release.wait(5)
        return back_up_every_store(
            settings, requested_by=requested_by, targets=[_target("platform")]
        )

    runner = BackupRunner(backup=slow_backup)
    # `app.backups.api.router` names the APIRouter as well as the module.
    monkeypatch.setattr(sys.modules[start_backup.__module__], "backup_runner", runner)
    settings = _settings(tmp_path)
    session = _session()

    started = start_backup(_request(settings), _principal(), session)
    assert started.data is not None
    assert started.data.run.status == "running"
    with pytest.raises(ConflictError, match="already running"):
        start_backup(_request(settings), _principal(), session)

    release.set()
    assert runner._thread is not None
    runner._thread.join(5)

    overview = list_all_backups(_request(settings), _principal()).data
    assert overview is not None
    assert overview.run.status == "succeeded"
    assert overview.run.stores[0].tables == 2
    assert [(item.kind, item.complete) for item in overview.backups] == [
        ("manual", True)
    ]
    actions = session.scalars(select(AuditLog.action)).all()
    assert actions == ["system.backup_started"]


def test_a_failed_run_says_why(tmp_path: Path) -> None:
    """A run that cannot start reports the reason to the screen."""

    def failing(settings: Settings, *, requested_by: str) -> backup.BackupResult:
        raise BackupError("pg_dump was not found")

    runner = BackupRunner(backup=failing)
    state = runner.start(_settings(tmp_path), requested_by="x", wait=True)
    assert state.status == "failed"
    assert state.message == "pg_dump was not found"
