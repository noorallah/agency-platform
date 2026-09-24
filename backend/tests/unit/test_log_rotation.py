"""Server logs: one folder, a file per day, compressed, expired and capped.

An installed server writes to ``<AGENCY_LOG_DIRECTORY>/server``. These pin the
names an operator (and the support notes) rely on, the midnight and size
rollovers, and the three cleanup rules -- all against ``tmp_path`` with a fixed
clock, so nothing here depends on when it runs.
"""

import gzip
import logging
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.core.config.settings import Settings
from app.core.logging.configuration import _build_logging_config
from app.core.logging.retention import (
    LogRetentionPolicy,
    clean_log_directory,
)
from app.core.logging.rotation import (
    DailyRotatingFileHandler,
    LogFileName,
    day_file_name,
    parse_log_file_name,
    rolled_file_name,
)

_TODAY = date(2026, 9, 24)


class _Clock:
    """A clock the test moves by hand."""

    def __init__(self, moment: datetime) -> None:
        """Start at the given moment."""
        self.moment = moment

    def __call__(self) -> datetime:
        """Return the current moment."""
        return self.moment


def _record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    """Build a log record carrying one message."""
    return logging.LogRecord("t", level, __file__, 1, message, None, None)


def _handler(folder: Path, clock: _Clock, max_bytes: int) -> DailyRotatingFileHandler:
    """Build a server-log handler with a plain message format."""
    handler = DailyRotatingFileHandler(folder, "server", max_bytes, clock=clock)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def _write(path: Path, size: int, day: date) -> Path:
    """Create a file of ``size`` bytes whose mtime is noon on ``day``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    stamp = datetime(day.year, day.month, day.day, 12, tzinfo=UTC).timestamp()
    os.utime(path, (stamp, stamp))
    return path


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------


def test_the_names_carry_the_day_and_the_part() -> None:
    """``server-<day>.log`` for the day, ``.<n>.log`` for a part rolled by size."""
    assert day_file_name("server", _TODAY) == "server-2026-09-24.log"
    assert day_file_name("errors", _TODAY) == "errors-2026-09-24.log"
    assert rolled_file_name("server", _TODAY, 2) == "server-2026-09-24.2.log"


def test_a_name_reads_back_as_what_it_says() -> None:
    """Every shape the handler and the cleanup produce parses; others do not."""
    assert parse_log_file_name("server-2026-09-24.log") == LogFileName(
        "server", _TODAY, None, False
    )
    assert parse_log_file_name("errors-2026-09-24.3.log.gz") == LogFileName(
        "errors", _TODAY, 3, True
    )
    for foreign in ("application.log", "server-2026-13-40.log", "notes.txt"):
        assert parse_log_file_name(foreign) is None


# --------------------------------------------------------------------------
# The handler
# --------------------------------------------------------------------------


def test_midnight_starts_the_next_days_file(tmp_path: Path) -> None:
    """Nothing is renamed at midnight; the next line opens the next day's file."""
    clock = _Clock(datetime(2026, 9, 24, 23, 59, tzinfo=UTC))
    handler = _handler(tmp_path, clock, max_bytes=10_000)
    try:
        handler.emit(_record("before midnight"))
        clock.moment += timedelta(minutes=2)
        handler.emit(_record("after midnight"))
    finally:
        handler.close()

    assert (tmp_path / "server-2026-09-24.log").read_text().strip() == (
        "before midnight"
    )
    assert (tmp_path / "server-2026-09-25.log").read_text().strip() == (
        "after midnight"
    )


def test_a_full_file_rolls_to_the_next_free_part(tmp_path: Path) -> None:
    """Past ``max_bytes`` the day's file becomes ``.1``, then ``.2``, and so on."""
    clock = _Clock(datetime(2026, 9, 24, 10, tzinfo=UTC))
    handler = _handler(tmp_path, clock, max_bytes=32)
    try:
        for index in range(6):
            handler.emit(_record(f"line number {index:02d}"))
    finally:
        handler.close()

    names = sorted(entry.name for entry in tmp_path.iterdir())
    assert names == [
        "server-2026-09-24.1.log",
        "server-2026-09-24.2.log",
        "server-2026-09-24.log",
    ]
    # The lowest part is the earliest; the unnumbered file the latest.
    assert "line number 00" in (tmp_path / "server-2026-09-24.1.log").read_text()
    assert "line number 05" in (tmp_path / "server-2026-09-24.log").read_text()
    for entry in tmp_path.iterdir():
        assert entry.stat().st_size <= 32


def test_the_configuration_writes_two_files_under_server(tmp_path: Path) -> None:
    """Everything goes to ``server-*``; WARNING and above also to ``errors-*``."""
    settings = Settings(log_directory=tmp_path, log_file_enabled=True)
    config = _build_logging_config(settings)
    handlers = config["handlers"]

    assert handlers["file"]["prefix"] == "server"
    assert handlers["errors"]["prefix"] == "errors"
    assert handlers["errors"]["level"] == "WARNING"
    assert handlers["file"]["directory"] == str(tmp_path / "server")
    assert config["root"]["handlers"] == ["console", "file", "errors"]


def test_file_logging_off_leaves_the_console_alone(tmp_path: Path) -> None:
    """``AGENCY_LOG_FILE_ENABLED=false`` builds no file handler at all."""
    settings = Settings(log_directory=tmp_path, log_file_enabled=False)
    config = _build_logging_config(settings)

    assert set(config["handlers"]) == {"console"}
    assert config["root"]["handlers"] == ["console"]


def test_the_retired_names_still_load() -> None:
    """An existing ``.env`` naming the old settings must not stop the server."""
    settings = Settings(log_file_name="application.log", log_backup_count=5)
    assert settings.log_retention_days == 30
    assert settings.log_error_retention_days == 90
    assert settings.log_max_total_mb == 1024


# --------------------------------------------------------------------------
# Cleanup
# --------------------------------------------------------------------------


def test_files_from_before_yesterday_are_compressed(tmp_path: Path) -> None:
    """Today and yesterday stay as text; older days are gzipped intact."""
    server = tmp_path / "server"
    for age in (0, 1, 2):
        day = _TODAY - timedelta(days=age)
        _write(server / day_file_name("server", day), 100, day)
    _write(
        server / rolled_file_name("errors", _TODAY - timedelta(days=5), 1), 10, _TODAY
    )

    report = clean_log_directory(tmp_path, LogRetentionPolicy(), today=_TODAY)

    names = sorted(entry.name for entry in server.iterdir())
    assert names == [
        "errors-2026-09-19.1.log.gz",
        "server-2026-09-22.log.gz",
        "server-2026-09-23.log",
        "server-2026-09-24.log",
    ]
    assert len(report.compressed) == 2
    with gzip.open(server / "server-2026-09-22.log.gz", "rb") as stream:
        assert stream.read() == b"x" * 100


def test_each_kind_is_kept_for_its_own_number_of_days(tmp_path: Path) -> None:
    """Server logs go after ``server_days``, error logs after ``error_days``."""
    server = tmp_path / "server"
    policy = LogRetentionPolicy(server_days=30, error_days=90)
    for prefix in ("server", "errors"):
        for age in (30, 31, 90, 91):
            day = _TODAY - timedelta(days=age)
            _write(server / (day_file_name(prefix, day) + ".gz"), 10, day)

    report = clean_log_directory(tmp_path, policy, today=_TODAY)

    remaining = sorted(entry.name for entry in server.iterdir())
    assert remaining == [
        "errors-2026-06-26.log.gz",  # 90 days: kept
        "errors-2026-08-24.log.gz",
        "errors-2026-08-25.log.gz",
        "server-2026-08-25.log.gz",  # 30 days: kept
    ]
    assert len(report.expired) == 4


def test_the_cap_deletes_the_oldest_files_first(tmp_path: Path) -> None:
    """Over the cap, whole files go oldest first until the folder fits.

    The cap covers the whole log folder, not only the server's files, and
    never deletes the two files being written today.
    """
    server = tmp_path / "server"
    today_file = _write(server / day_file_name("server", _TODAY), 400, _TODAY)
    today_errors = _write(server / day_file_name("errors", _TODAY), 50, _TODAY)
    yesterday = _TODAY - timedelta(days=1)
    kept = _write(server / day_file_name("server", yesterday), 300, yesterday)
    installer = _write(
        tmp_path / "installer" / "setup.log", 300, _TODAY - timedelta(days=3)
    )
    older = _write(
        server / (day_file_name("server", _TODAY - timedelta(days=2)) + ".gz"),
        300,
        _TODAY - timedelta(days=2),
    )

    report = clean_log_directory(
        tmp_path, LogRetentionPolicy(max_total_bytes=1000), today=_TODAY
    )

    assert report.capped == [installer, older]
    assert today_file.exists() and today_errors.exists() and kept.exists()


def test_todays_files_survive_even_when_they_alone_pass_the_cap(
    tmp_path: Path,
) -> None:
    """A folder may sit above the cap for the rest of the day rather than lose it."""
    server = tmp_path / "server"
    active = _write(server / day_file_name("server", _TODAY), 5000, _TODAY)

    report = clean_log_directory(
        tmp_path, LogRetentionPolicy(max_total_bytes=1000), today=_TODAY
    )

    assert report.capped == []
    assert active.exists()


def test_a_missing_folder_is_nothing_to_do(tmp_path: Path) -> None:
    """A server that has never logged has nothing to clean."""
    report = clean_log_directory(
        tmp_path / "absent", LogRetentionPolicy(), today=_TODAY
    )
    assert (report.compressed, report.expired, report.capped) == ([], [], [])


@pytest.mark.parametrize("days", [0, -1])
def test_retention_must_keep_at_least_a_day(days: int) -> None:
    """A retention of zero would delete the file being written."""
    with pytest.raises(ValueError):
        Settings(log_retention_days=days)
