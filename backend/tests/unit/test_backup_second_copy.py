"""A password-protected copy of each backup in a second folder (backlog 112).

Every folder here is under ``tmp_path``: nothing reads or writes the real
backup folder, and no ``pg_dump`` runs.
"""

import argparse
import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from app import cli
from app.backups.api.router import _overview
from app.backups.services.backup_runner import BackupRunner
from app.core.config.settings import Settings
from app.core.tenancy import backup, backup_copy
from app.core.tenancy.backup import (
    COMPLETE_MARKER,
    BackupError,
    back_up_every_store,
)
from app.core.tenancy.backup_copy import (
    copy_backups_to_second_folder,
    list_second_copies,
    open_copy,
    seal_folder,
    verify_copy,
)
from app.core.tenancy.migrations import MigrationTarget

PASSWORD = "Correct-Horse-9"


@pytest.fixture(autouse=True)
def quick_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Derive keys in a few rounds; the real count costs a second a file."""
    monkeypatch.setattr(backup_copy, "KEY_ROUNDS", 10)


def _settings(
    tmp_path: Path, *, password: str | None = PASSWORD, keep_days: int = 10
) -> Settings:
    return Settings(
        backup_directory=tmp_path / "backups",
        backup_second_directory=tmp_path / "second",
        backup_second_password=None if password is None else SecretStr(password),
        backup_second_keep_days=keep_days,
    )


def _backup(
    settings: Settings,
    kind: str,
    name: str,
    *,
    complete: bool = True,
    body: bytes = b"PGDMP rows of one store",
) -> Path:
    """Put one backup folder on disk as the three writers leave theirs."""
    root = Path(settings.backup_directory)
    folder = root / name if kind == "pre-upgrade" else root / kind / name
    folder.mkdir(parents=True)
    (folder / "agency--platform.dump").write_bytes(body)
    (folder / "manifest.json").write_text(json.dumps({"kind": kind}))
    if complete and kind != "pre-upgrade":
        (folder / COMPLETE_MARKER).write_text(name + "\n")
    return folder


def _names(folder: Path) -> list[str]:
    return sorted(child.name for child in folder.iterdir())


def test_a_backup_lands_in_both_places_and_opens_only_with_the_password(
    tmp_path: Path,
) -> None:
    """The copy holds every file of the backup and nothing readable without."""
    settings = _settings(tmp_path)
    body = b"PGDMP " + bytes(range(256)) * 9000  # more than two chunks
    source = _backup(settings, "daily", "20261013-020000", body=body)

    result = copy_backups_to_second_folder(settings)

    assert result is not None
    assert result.written == ["agency-backup-daily-20261013-020000.agbk"]
    assert source.is_dir(), "the backup itself stays where it was"
    copy = tmp_path / "second" / result.written[0]
    sealed = copy.read_bytes()
    assert b"PGDMP" not in sealed
    assert b"manifest.json" not in sealed, "not even the file names are readable"

    with pytest.raises(BackupError, match="does not open"):
        open_copy(copy, tmp_path / "wrong", password="Correct-Horse-8")
    assert not (tmp_path / "wrong").exists(), "a refusal writes nothing"

    names = open_copy(copy, tmp_path / "opened", password=PASSWORD)
    assert sorted(names) == _names(source)
    assert (tmp_path / "opened" / "agency--platform.dump").read_bytes() == body


def test_an_altered_or_cut_copy_does_not_open(tmp_path: Path) -> None:
    """One changed byte, or a file a sync client cut short, is refused."""
    settings = _settings(tmp_path)
    _backup(settings, "manual", "20261013-101500")
    copy_backups_to_second_folder(settings)
    copy = tmp_path / "second" / "agency-backup-manual-20261013-101500.agbk"
    whole = copy.read_bytes()

    changed = bytearray(whole)
    changed[len(changed) // 2] ^= 1
    copy.write_bytes(bytes(changed))
    with pytest.raises(BackupError, match="does not open"):
        verify_copy(copy, password=PASSWORD)

    copy.write_bytes(whole[:-10])
    with pytest.raises(BackupError, match="does not open"):
        open_copy(copy, tmp_path / "out", password=PASSWORD)

    copy.write_bytes(b"just a text file somebody dropped here, long enough" * 3)
    with pytest.raises(BackupError, match="not a protected backup copy"):
        verify_copy(copy, password=PASSWORD)


def test_the_eleventh_day_removes_the_oldest(tmp_path: Path) -> None:
    """Ten days of copies are kept; a backup on the eleventh takes the first."""
    settings = _settings(tmp_path)
    for day in range(1, 11):
        _backup(settings, "daily", f"202610{day:02d}-020000")
    first = copy_backups_to_second_folder(settings)
    assert first is not None
    assert len(first.written) == 10
    assert first.removed == []

    _backup(settings, "daily", "20261011-020000")
    second = copy_backups_to_second_folder(settings)

    assert second is not None
    assert second.written == ["agency-backup-daily-20261011-020000.agbk"]
    assert second.removed == ["agency-backup-daily-20261001-020000.agbk"]
    held = [copy.name for copy in list_second_copies(tmp_path / "second")]
    assert len(held) == 10
    assert held[0] == "agency-backup-daily-20261011-020000.agbk"
    assert held[-1] == "agency-backup-daily-20261002-020000.agbk"


def test_days_are_counted_not_files_and_a_removed_backup_keeps_its_copy(
    tmp_path: Path,
) -> None:
    """Two backups on one day are one day; the copy outlives the local folder."""
    settings = _settings(tmp_path, keep_days=2)
    old = _backup(settings, "daily", "20261001-020000")
    _backup(settings, "daily", "20261002-020000")
    _backup(settings, "manual", "20261002-153000")
    copy_backups_to_second_folder(settings)
    assert len(list_second_copies(tmp_path / "second")) == 3

    # The nightly task keeps fewer days here than the second folder does.
    for child in old.iterdir():
        child.unlink()
    old.rmdir()
    again = copy_backups_to_second_folder(settings)
    assert again is not None
    assert again.written == []
    assert again.removed == []
    assert len(list_second_copies(tmp_path / "second")) == 3

    _backup(settings, "daily", "20261003-020000")
    third = copy_backups_to_second_folder(settings)
    assert third is not None
    assert third.removed == ["agency-backup-daily-20261001-020000.agbk"]


def test_only_its_own_files_are_ever_removed(tmp_path: Path) -> None:
    """A cloud folder holds other things; none of them is touched."""
    settings = _settings(tmp_path, keep_days=1)
    second = tmp_path / "second"
    second.mkdir()
    (second / "holiday.jpg").write_bytes(b"jpeg")
    (second / "agency-backup-notes.txt").write_text("mine")
    (second / "agency-backup-daily-20200101-020000.agbk.old").write_text("mine")
    (second / "agency-backup-daily-not-a-stamp.agbk").write_text("mine")
    stale = second / "agency-backup-daily-20261001-020000.agbk.part"
    stale.write_bytes(b"a run that stopped")
    _backup(settings, "daily", "20261001-020000")
    _backup(settings, "daily", "20261002-020000")

    result = copy_backups_to_second_folder(settings)

    assert result is not None
    assert result.written == ["agency-backup-daily-20261002-020000.agbk"]
    assert _names(second) == [
        "agency-backup-daily-20200101-020000.agbk.old",
        "agency-backup-daily-20261002-020000.agbk",
        "agency-backup-daily-not-a-stamp.agbk",
        "agency-backup-notes.txt",
        "holiday.jpg",
    ]


def test_an_unfinished_backup_is_not_copied_and_a_pre_upgrade_one_is(
    tmp_path: Path,
) -> None:
    """Only a backup offered as one is copied; Setup's has its own name."""
    settings = _settings(tmp_path)
    _backup(settings, "daily", "20261012-020000", complete=False)
    _backup(settings, "pre-upgrade", "pre-upgrade-1.3.0-20261012-180000")

    result = copy_backups_to_second_folder(settings)

    assert result is not None
    assert result.written == ["agency-backup-pre-upgrade-1.3.0-20261012-180000.agbk"]


def test_a_missed_night_is_caught_up_by_the_next_run(tmp_path: Path) -> None:
    """The pass copies what is missing, not only the newest backup."""
    settings = _settings(tmp_path)
    _backup(settings, "daily", "20261010-020000")
    copy_backups_to_second_folder(settings)
    _backup(settings, "daily", "20261011-020000")  # the drive was unplugged
    _backup(settings, "daily", "20261012-020000")

    result = copy_backups_to_second_folder(settings)

    assert result is not None
    assert result.written == [
        "agency-backup-daily-20261011-020000.agbk",
        "agency-backup-daily-20261012-020000.agbk",
    ]


def test_no_copy_is_ever_written_without_a_password(tmp_path: Path) -> None:
    """A folder with no password, or a short one, is refused by name."""
    for password in (None, "", "short"):
        settings = _settings(tmp_path, password=password)
        if not (tmp_path / "backups" / "daily").exists():
            _backup(settings, "daily", "20261013-020000")
        with pytest.raises(BackupError, match="AGENCY_BACKUP_SECOND_PASSWORD"):
            copy_backups_to_second_folder(settings)
    assert not (tmp_path / "second").exists()


def test_no_second_folder_means_nothing_happens(tmp_path: Path) -> None:
    """Unset is off: no folder appears and nothing is refused."""
    settings = Settings(backup_directory=tmp_path / "backups")
    _backup(settings, "daily", "20261013-020000")
    assert copy_backups_to_second_folder(settings) is None
    assert _names(tmp_path) == ["backups"]


def test_a_folder_inside_the_backup_folder_is_no_second_place(
    tmp_path: Path,
) -> None:
    """The copy must not sit on the disk it is there to outlive."""
    settings = Settings(
        backup_directory=tmp_path / "backups",
        backup_second_directory=tmp_path / "backups" / "copies",
        backup_second_password=SecretStr(PASSWORD),
    )
    with pytest.raises(BackupError, match="inside the backup folder"):
        copy_backups_to_second_folder(settings)


def test_one_copy_that_fails_is_reported_and_the_rest_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full disk on one file does not lose the others, and leaves no part."""
    settings = _settings(tmp_path)
    _backup(settings, "daily", "20261011-020000")
    _backup(settings, "daily", "20261012-020000")
    real = backup_copy.seal_folder

    def seal(folder: Path, destination: Path, *, password: str) -> None:
        if "20261011" in folder.name:
            destination.write_bytes(b"half")
            raise OSError(28, "No space left on device")
        real(folder, destination, password=password)

    monkeypatch.setattr(backup_copy, "seal_folder", seal)

    result = copy_backups_to_second_folder(settings)

    assert result is not None
    assert result.written == ["agency-backup-daily-20261012-020000.agbk"]
    assert len(result.failed) == 1
    assert "No space left" in result.failed[0]
    assert "FAILED" in result.summary()
    assert _names(tmp_path / "second") == ["agency-backup-daily-20261012-020000.agbk"]


def _fake_pg(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(arguments: list[str], environment: dict[str, str]) -> str:
        if "--list" in arguments:
            return "1; 2615 2200 TABLE DATA s users app\n"
        Path(arguments[arguments.index("-f") + 1]).write_bytes(b"PGDMP fake")
        return ""

    monkeypatch.setattr(backup, "_run", run)
    monkeypatch.setattr(backup, "find_pg_tool", lambda name, _s: Path(name))
    monkeypatch.setattr(backup, "store_is_built", lambda **_kw: True)
    monkeypatch.setattr(backup, "current_revision", lambda _t: "20261013_0356")


def _target() -> MigrationTarget:
    return MigrationTarget(
        label="platform (agency/platform)",
        database_url="postgresql+psycopg://app:secret@db.local:5433/agency",
        schema_name="platform",
    )


def test_back_up_now_ends_with_the_second_copy_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The button's backup is in both places when it reports success."""
    _fake_pg(monkeypatch)
    settings = _settings(tmp_path)

    result = back_up_every_store(settings, requested_by="a test", targets=[_target()])

    assert result.second_copy is not None
    assert result.second_copy.startswith("Second copy: 1 copied to")
    copies = list_second_copies(tmp_path / "second")
    assert [copy.name for copy in copies] == [
        f"agency-backup-manual-{result.folder.name}.agbk"
    ]
    opened = open_copy(copies[0].path, tmp_path / "opened", password=PASSWORD)
    assert sorted(opened) == _names(result.folder)

    runner = BackupRunner(
        lambda s, requested_by: back_up_every_store(
            s, requested_by=requested_by, targets=[_target()]
        )
    )
    monkeypatch.setattr(backup, "_stamp", lambda _moment: "20991231-235959")
    state = runner.start(settings, requested_by="a test", wait=True)
    assert state.status == "succeeded"
    assert state.message is not None
    assert "Second copy: 1 copied to" in state.message


def test_a_second_folder_that_cannot_be_used_does_not_fail_the_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unplugged drive tonight leaves tonight's backup whole, and says so."""
    _fake_pg(monkeypatch)
    settings = _settings(tmp_path, password=None)

    result = back_up_every_store(settings, requested_by="a test", targets=[_target()])

    assert not result.failed
    assert (result.folder / COMPLETE_MARKER).is_file()
    assert result.second_copy is not None
    assert result.second_copy.startswith("Second copy NOT written")


def test_the_screen_is_told_the_second_folder_and_what_it_holds(
    tmp_path: Path,
) -> None:
    """The overview names the folder, the days kept and each copy."""
    settings = _settings(tmp_path)
    before = _overview(settings)
    assert before.second_directory == str(tmp_path / "second")
    assert before.second_keep_days == 10
    assert before.second_copies == []
    assert before.second_problem is not None

    _backup(settings, "daily", "20261013-020000")
    copy_backups_to_second_folder(settings)
    after = _overview(settings)
    assert after.second_problem is None
    assert [copy.name for copy in after.second_copies] == [
        "agency-backup-daily-20261013-020000.agbk"
    ]
    assert after.second_copies[0].size_bytes > 0

    off = _overview(Settings(backup_directory=tmp_path / "backups"))
    assert off.second_directory is None
    assert off.second_copies == []
    assert off.second_problem is None


def test_the_command_opens_a_copy_with_a_password_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``agency-server backup-open`` is the way back from a copy."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "agency--platform.dump").write_bytes(b"PGDMP rows")
    copy = tmp_path / "agency-backup-daily-20261013-020000.agbk"
    seal_folder(source, copy, password=PASSWORD)
    right = tmp_path / "right.txt"
    right.write_text(PASSWORD + "\n", encoding="utf-8")
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("Something-Else-1\n", encoding="utf-8")

    refused = cli._backup_open(
        argparse.Namespace(file=copy, into=tmp_path / "out", password_file=wrong)
    )
    assert refused == 1
    assert "does not open" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()

    opened = cli._backup_open(
        argparse.Namespace(file=copy, into=tmp_path / "out", password_file=right)
    )
    assert opened == 0
    assert (tmp_path / "out" / "agency--platform.dump").read_bytes() == b"PGDMP rows"
