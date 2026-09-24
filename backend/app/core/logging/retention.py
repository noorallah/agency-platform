"""Compress, expire and cap the log folder.

Three rules, applied in this order by ``clean_log_directory``:

1. **Compress.** A server or error log from before yesterday is gzipped. Today's
   files are being written and yesterday's may still be read, so both are left
   as text.
2. **Expire.** A server log older than ``server_days`` and an error log older
   than ``error_days`` is deleted. Errors are kept longer because they are
   what support asks for, and they are small.
3. **Cap.** If the whole log folder -- every file under it, whoever wrote it --
   still exceeds ``max_total_bytes``, the oldest files are deleted until it
   fits. The files being written today are never deleted, so a folder can sit
   above the cap for the rest of a day in which one file alone passes it.

Nothing here reads a clock: the caller passes ``today``, which is what lets the
tests fix it. The serving process runs this at startup and hourly
(``LogMaintenance``), and ``agency-server purge-retention --yes`` runs it too.
"""

import gzip
import logging
import shutil
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.core.config.settings import Settings
from app.core.logging.rotation import day_file_name, local_now, parse_log_file_name

logger = logging.getLogger(__name__)

#: The subfolder of ``AGENCY_LOG_DIRECTORY`` the server writes to.
SERVER_LOG_FOLDER = "server"
SERVER_LOG_PREFIX = "server"
ERROR_LOG_PREFIX = "errors"

_HOUR_SECONDS = 3600.0


@dataclass(frozen=True, slots=True)
class LogRetentionPolicy:
    """How long each kind of log is kept, and how large the folder may grow."""

    server_days: int = 30
    error_days: int = 90
    max_total_bytes: int = 1024 * 1024 * 1024

    @classmethod
    def from_settings(cls, settings: Settings) -> "LogRetentionPolicy":
        """Read the policy from ``AGENCY_LOG_*`` settings."""
        return cls(
            server_days=settings.log_retention_days,
            error_days=settings.log_error_retention_days,
            max_total_bytes=settings.log_max_total_mb * 1024 * 1024,
        )


@dataclass(slots=True)
class LogCleanupReport:
    """What one cleanup did, by file."""

    compressed: list[Path] = field(default_factory=list)
    expired: list[Path] = field(default_factory=list)
    capped: list[Path] = field(default_factory=list)


def _gzip(path: Path) -> Path:
    """Compress a file beside itself and remove the original."""
    target = path.with_name(path.name + ".gz")
    with path.open("rb") as source, gzip.open(target, "wb") as sink:
        shutil.copyfileobj(source, sink)
    path.unlink()
    return target


def _keep_days(prefix: str, policy: LogRetentionPolicy) -> int | None:
    """Return how many days a file with this prefix is kept; None if not ours."""
    if prefix == SERVER_LOG_PREFIX:
        return policy.server_days
    if prefix == ERROR_LOG_PREFIX:
        return policy.error_days
    return None


def clean_log_directory(
    root: Path, policy: LogRetentionPolicy, *, today: date
) -> LogCleanupReport:
    """Apply compression, retention and the size cap to one log folder.

    Args:
        root: ``AGENCY_LOG_DIRECTORY``; the server's files are in its
            ``server`` subfolder, and the cap covers everything under it.
        policy: The retention periods and the size cap.
        today: The server's local date, passed in so tests can fix it.

    Returns:
        The files compressed, expired and deleted to meet the cap.

    """
    report = LogCleanupReport()
    if not root.is_dir():
        return report

    server_folder = root / SERVER_LOG_FOLDER
    if server_folder.is_dir():
        for path in sorted(server_folder.iterdir()):
            parsed = parse_log_file_name(path.name)
            if parsed is None or not path.is_file():
                continue
            keep = _keep_days(parsed.prefix, policy)
            if keep is None:
                continue
            age = (today - parsed.day).days
            try:
                if age > keep:
                    path.unlink()
                    report.expired.append(path)
                elif age > 1 and not parsed.compressed:
                    report.compressed.append(_gzip(path))
            except OSError as error:
                # A file somebody has open cannot be moved on Windows. The
                # next pass, an hour later, will try again.
                logger.warning("Log cleanup skipped %s: %s", path, error)

    active = {
        (server_folder / day_file_name(prefix, today)).resolve()
        for prefix in (SERVER_LOG_PREFIX, ERROR_LOG_PREFIX)
    }
    files = [
        (path, path.stat())
        for path in root.rglob("*")
        if path.is_file() and path.resolve() not in active
    ]
    total = sum(stat.st_size for _, stat in files) + sum(
        path.stat().st_size for path in active if path.exists()
    )
    for path, stat in sorted(files, key=lambda item: (item[1].st_mtime, item[0])):
        if total <= policy.max_total_bytes:
            break
        try:
            path.unlink()
        except OSError as error:
            logger.warning("Log cleanup could not delete %s: %s", path, error)
            continue
        total -= stat.st_size
        report.capped.append(path)
    return report


def purge_log_files(settings: Settings) -> LogCleanupReport:
    """Clean the configured log folder now, by the configured policy."""
    return clean_log_directory(
        settings.log_directory,
        LogRetentionPolicy.from_settings(settings),
        today=local_now().date(),
    )


class LogMaintenance:
    """Clean the log folder at startup and then hourly, on a daemon thread.

    One small thread rather than a scheduler: the work is a directory listing
    and the odd gzip, once an hour, and the serving process is the only thing
    on an installed machine that is always running.
    """

    def __init__(
        self, settings: Settings, interval_seconds: float = _HOUR_SECONDS
    ) -> None:
        """Bind the settings; nothing runs until ``start``."""
        self._settings = settings
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Run one cleanup now, then one every interval until ``stop``."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="log-maintenance", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Ask the thread to finish and wait briefly for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        """Clean, then wait; a failed pass is logged and the next one runs."""
        while not self._stop.is_set():
            try:
                purge_log_files(self._settings)
            except Exception:  # noqa: BLE001 - a housekeeping thread must not die
                logger.exception("Log cleanup failed")
            self._stop.wait(self._interval)
