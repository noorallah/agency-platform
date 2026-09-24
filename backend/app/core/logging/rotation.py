"""Log files named by day, rolled at midnight and at a size cap within a day.

An installed server writes under one folder, ``AGENCY_LOG_DIRECTORY`` --
``ProgramData/Agency Platform/logs`` on a customer machine -- in a
``server`` subfolder::

    server-2026-09-24.log        today's log, being written
    server-2026-09-24.1.log      today's first 50 MB, rolled over within the day
    errors-2026-09-24.log        WARNING and above only
    server-2026-09-22.log.gz     a finished day, compressed by the cleanup

The date in a name is the day its lines were written, so an operator asked
"what happened on Tuesday" opens one file rather than working out which of
``application.log.3`` and ``application.log.4`` covers it -- the question the
old size-only rotation could not answer. Compression, retention and the total
size cap live in ``retention.py``; this module only writes.

The day is the server's **local** day, deliberately and alone in this codebase:
a log's timestamps are the operator's wall clock (``asctime`` is local), and a
file whose name disagreed with its own lines would be worse than either. It is
read as ``utc_now().astimezone()`` -- an aware local time -- rather than from a
naive local clock, which ``test_time_conventions.py`` forbids.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.core.utils.dates import utc_now

#: ``server-2026-09-24.log``, ``server-2026-09-24.3.log``, and either one
#: gzipped. Anything else in the folder is somebody else's file.
_LOG_NAME = re.compile(
    r"^(?P<prefix>[a-z]+)-(?P<day>\d{4}-\d{2}-\d{2})"
    r"(?:\.(?P<index>\d+))?\.log(?P<gz>\.gz)?$"
)


def local_now() -> datetime:
    """Return the current time on the server's wall clock, timezone-aware."""
    return utc_now().astimezone()


def day_file_name(prefix: str, day: date) -> str:
    """Return the name of the file a day's lines are written to."""
    return f"{prefix}-{day.isoformat()}.log"


def rolled_file_name(prefix: str, day: date, index: int) -> str:
    """Return the name a day's file takes when it is rolled over within the day."""
    return f"{prefix}-{day.isoformat()}.{index}.log"


@dataclass(frozen=True, slots=True)
class LogFileName:
    """What a log file's name says about it."""

    prefix: str
    day: date
    index: int | None
    compressed: bool


def parse_log_file_name(name: str) -> LogFileName | None:
    """Read a log file's name, or return None for a file that is not ours."""
    match = _LOG_NAME.fullmatch(name)
    if match is None:
        return None
    try:
        day = date.fromisoformat(match["day"])
    except ValueError:
        return None
    index = match["index"]
    return LogFileName(
        prefix=match["prefix"],
        day=day,
        index=int(index) if index is not None else None,
        compressed=match["gz"] is not None,
    )


class DailyRotatingFileHandler(logging.FileHandler):
    """Write to ``<prefix>-<day>.log``; roll at midnight and at ``max_bytes``.

    At midnight the handler simply opens the next day's file -- nothing is
    renamed, so a file's name never changes while somebody has it open. When a
    day's file would pass ``max_bytes`` it is renamed to the next free
    ``<prefix>-<day>.<n>.log`` and a fresh one is started, so the lowest number
    is the earliest part of the day and the unnumbered file the latest.
    """

    def __init__(
        self,
        directory: str | Path,
        prefix: str,
        max_bytes: int,
        encoding: str = "utf-8",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Open (lazily) the file for the current day.

        Args:
            directory: The folder the files are written to; created if missing.
            prefix: ``server`` or ``errors``; the start of every file name.
            max_bytes: The size at which a day's file is rolled over.
            encoding: The text encoding of the file.
            clock: The time source, for tests; the server's wall clock otherwise.

        """
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._prefix = prefix
        self._max_bytes = max_bytes
        self._clock = clock or local_now
        self._day = self._clock().date()
        super().__init__(
            self._directory / day_file_name(prefix, self._day),
            encoding=encoding,
            delay=True,
        )

    @property
    def current_path(self) -> Path:
        """Return the file being written to now."""
        return Path(self.baseFilename)

    def emit(self, record: logging.LogRecord) -> None:
        """Roll over if the day changed or the file is full, then write."""
        try:
            self._roll_if_due(record)
        except Exception:  # noqa: BLE001 - logging must never raise into callers
            self.handleError(record)
            return
        super().emit(record)

    def _roll_if_due(self, record: logging.LogRecord) -> None:
        """Switch to the next day's file, or roll this one over by size."""
        today = self._clock().date()
        if today != self._day:
            self._switch_to(today)
            return
        path = self.current_path
        if not path.exists():
            return
        incoming = len(self.format(record).encode(self.encoding or "utf-8")) + 2
        if path.stat().st_size + incoming <= self._max_bytes:
            return
        self._close_stream()
        path.rename(self._directory / self._next_rolled_name(today))

    def _switch_to(self, day: date) -> None:
        """Start writing the given day's file."""
        self._close_stream()
        self._day = day
        self.baseFilename = str(
            (self._directory / day_file_name(self._prefix, day)).resolve()
        )

    def _next_rolled_name(self, day: date) -> str:
        """Return the first ``<prefix>-<day>.<n>.log`` not already taken."""
        taken = {
            parsed.index
            for parsed in (
                parse_log_file_name(entry.name) for entry in self._directory.iterdir()
            )
            if parsed is not None
            and parsed.prefix == self._prefix
            and parsed.day == day
            and parsed.index is not None
        }
        index = 1
        while index in taken:
            index += 1
        return rolled_file_name(self._prefix, day, index)

    def _close_stream(self) -> None:
        """Close the open file, if any; the next write reopens by name."""
        if self.stream is not None:
            self.stream.flush()
            self.stream.close()
            self.stream = None
