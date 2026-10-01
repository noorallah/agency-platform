"""Take a backup now, and see every backup the server holds (BACKLOG section 35).

``/api/v1/backups`` is a platform path (``app/core/database/dependencies.py``):
a backup is of the whole installation, every firm's store and the platform's,
so it belongs to no one firm and needs no ``X-Firm-ID``. Both routes are gated
on ``SYSTEM_BACKUP``, which only the platform tier holds -- a dump of the
platform store carries every user's password hash.

Restoring is deliberately not here. Putting a store back means stopping the
server that would be doing it, so it stays the documented procedure in
``docs/INSTALL_GUIDE.md`` section 6, and ``SYSTEM_RESTORE`` still guards
nothing.
"""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backups.schemas import (
    BackupFolderResponse,
    BackupOverviewResponse,
    BackupRunResponse,
    BackupStoreResponse,
)
from app.backups.services import BackupRunState, backup_runner
from app.common.audit.services import record_audit
from app.core.config.settings import Settings
from app.core.database.dependencies import get_db
from app.core.exceptions import ConflictError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.core.security.authorization import Principal, require_permission
from app.core.tenancy.backup import (
    BackupError,
    BackupFolder,
    StoreDump,
    is_running,
    list_backups,
)
from app.identity.models import User

router = APIRouter(
    prefix="/api/v1/backups",
    tags=["Backups"],
    responses=STANDARD_ERROR_RESPONSES,
)

BackupPrincipal = Annotated[Principal, Depends(require_permission("SYSTEM_BACKUP"))]


def _settings(request: Request) -> Settings:
    """Return the settings the application was built with."""
    settings: Settings = request.app.state.settings
    return settings


def _store(store: StoreDump) -> BackupStoreResponse:
    """Describe one store of a run."""
    return BackupStoreResponse(
        label=store.label,
        database=store.database,
        schema_name=store.schema,
        file=store.file_name,
        size_bytes=store.size_bytes,
        tables=store.tables,
        revision=store.revision,
        outcome=store.outcome,
        detail=store.detail,
    )


def _manifest_store(entry: dict[str, object]) -> BackupStoreResponse:
    """Describe one store as a manifest recorded it."""
    return BackupStoreResponse.model_validate(
        {**entry, "schema_name": entry.get("schema", "")}
    )


def _folder(backup: BackupFolder) -> BackupFolderResponse:
    """Describe one backup on disk."""
    return BackupFolderResponse(
        kind=backup.kind,
        name=backup.name,
        path=str(backup.path),
        created_at=backup.created_at,
        complete=backup.complete,
        size_bytes=backup.size_bytes,
        files=backup.files,
        application_version=backup.application_version,
        requested_by=backup.requested_by,
        stores=[_manifest_store(entry) for entry in backup.stores],
    )


def _run(state: BackupRunState) -> BackupRunResponse:
    """Describe the manual backup this server is taking, or last took."""
    return BackupRunResponse(
        status=state.status,
        requested_by=state.requested_by,
        started_at=state.started_at,
        finished_at=state.finished_at,
        folder=state.folder,
        message=state.message,
        stores=[_store(store) for store in state.stores],
    )


def _overview(settings: Settings) -> BackupOverviewResponse:
    """Build everything the screen shows."""
    return BackupOverviewResponse(
        backup_directory=str(settings.backup_directory.resolve()),
        keep_manual=settings.backup_keep_manual,
        run=_run(backup_runner.state()),
        backups=[_folder(backup) for backup in list_backups(settings)],
    )


@router.get("", response_model=ApiResponse[BackupOverviewResponse])
def list_all_backups(
    request: Request, principal: BackupPrincipal
) -> ApiResponse[BackupOverviewResponse]:
    """List every backup on the server -- by hand, nightly and pre-upgrade.

    Also says whether a backup is running now and how the last one ended, so
    the screen can poll this one route while it waits.
    """
    return ApiResponse(data=_overview(_settings(request)))


@router.post(
    "",
    response_model=ApiResponse[BackupOverviewResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def start_backup(
    request: Request,
    principal: BackupPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[BackupOverviewResponse]:
    """Back up every store now, in the background; poll ``GET`` for the result.

    Refused with 409 while a backup is running, whether this button or
    ``agency-server backup`` started it.
    """
    settings = _settings(request)
    if is_running() or backup_runner.state().status == "running":
        raise ConflictError("A backup is already running. Wait for it to finish.")
    actor_id = principal.subject if isinstance(principal.subject, UUID) else None
    requested_by = str(principal.subject)
    if actor_id is not None:
        email = db.scalar(select(User.email).where(User.id == actor_id))
        if email:
            requested_by = email
    try:
        backup_runner.start(settings, requested_by=requested_by)
    except BackupError as error:
        raise ConflictError(str(error)) from error
    record_audit(
        db,
        action="system.backup_started",
        entity_type="backup",
        entity_id=uuid4(),
        actor_id=actor_id,
        after_data={"requested_by": requested_by},
    )
    db.commit()
    return ApiResponse(
        data=_overview(settings),
        message="The backup has started. This page shows when it is done.",
    )
