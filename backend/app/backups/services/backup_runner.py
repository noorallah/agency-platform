"""Run a manual backup in the background, and say how it went.

A dump of a firm with two years of trading takes long enough that holding an
HTTP request open for it would time the desktop out, so ``start`` returns at
once and the screen polls ``GET /api/v1/backups``. The work itself is
:func:`app.core.tenancy.backup.back_up_every_store`, the same function
``agency-server backup`` runs, so the button and the command cannot differ.

The state is this process's memory. The server is one process, and a backup
interrupted by a restart leaves a folder with no ``.complete`` marker, which
the screen already shows as unfinished and the next run clears away.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.core.config.settings import Settings
from app.core.tenancy.backup import (
    BackupError,
    BackupResult,
    StoreDump,
    back_up_every_store,
)
from app.core.utils.dates import utc_now

RunStatus = Literal["idle", "running", "succeeded", "failed"]


@dataclass(slots=True)
class BackupRunState:
    """The manual backup this process is taking, or last took."""

    status: RunStatus = "idle"
    requested_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    folder: str | None = None
    message: str | None = None
    stores: list[StoreDump] = field(default_factory=list)


BackupFunction = Callable[..., BackupResult]


class BackupRunner:
    """Start at most one background backup and remember how it ended."""

    def __init__(self, backup: BackupFunction = back_up_every_store) -> None:
        """Hold the function that takes the backup; tests pass a fake."""
        self._backup = backup
        self._lock = threading.Lock()
        self._state = BackupRunState()
        self._thread: threading.Thread | None = None

    def state(self) -> BackupRunState:
        """Return a copy of the current state."""
        with self._lock:
            return BackupRunState(
                status=self._state.status,
                requested_by=self._state.requested_by,
                started_at=self._state.started_at,
                finished_at=self._state.finished_at,
                folder=self._state.folder,
                message=self._state.message,
                stores=list(self._state.stores),
            )

    def start(
        self, settings: Settings, *, requested_by: str, wait: bool = False
    ) -> BackupRunState:
        """Start a backup; raise :class:`BackupError` if one is running.

        ``wait`` runs it on the caller's thread, which is what a test wants.
        """
        with self._lock:
            if self._state.status == "running":
                raise BackupError("A backup is already running. Wait for it to finish.")
            self._state = BackupRunState(
                status="running", requested_by=requested_by, started_at=utc_now()
            )
        if wait:
            self._run(settings, requested_by)
        else:
            self._thread = threading.Thread(
                target=self._run,
                args=(settings, requested_by),
                name="manual-backup",
                daemon=True,
            )
            self._thread.start()
        return self.state()

    def _run(self, settings: Settings, requested_by: str) -> None:
        """Take the backup and record the outcome, whatever it is."""
        try:
            result = self._backup(settings, requested_by=requested_by)
        except BackupError as error:
            self._finish("failed", str(error), folder=None, stores=[])
            return
        except Exception as error:  # noqa: BLE001 - the screen must hear of it
            self._finish(
                "failed",
                f"The backup stopped: {type(error).__name__}: {error}",
                folder=None,
                stores=[],
            )
            return
        failed = result.failed
        if failed:
            names = ", ".join(store.label for store in failed)
            self._finish(
                "failed",
                f"{len(failed)} store(s) could not be backed up: {names}. "
                "The folder is kept but is not a complete backup.",
                folder=str(result.folder),
                stores=result.stores,
            )
            return
        taken = sum(1 for store in result.stores if store.outcome == "ok")
        self._finish(
            "succeeded",
            f"{taken} store(s) backed up to {result.folder}.",
            folder=str(result.folder),
            stores=result.stores,
        )

    def _finish(
        self,
        status: RunStatus,
        message: str,
        *,
        folder: str | None,
        stores: list[StoreDump],
    ) -> None:
        """Record how the run ended."""
        with self._lock:
            self._state.status = status
            self._state.finished_at = utc_now()
            self._state.message = message
            self._state.folder = folder
            self._state.stores = list(stores)


#: The one runner the server has.
backup_runner = BackupRunner()
