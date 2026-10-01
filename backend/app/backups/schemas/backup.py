"""What the backups screen reads."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BackupStoreResponse(BaseModel):
    """One store inside one backup."""

    label: str
    database: str
    schema_name: str
    file: str | None
    size_bytes: int
    tables: int
    revision: str
    outcome: Literal["ok", "skipped", "failed"]
    detail: str | None = None


class BackupFolderResponse(BaseModel):
    """One backup on disk: taken by hand, nightly, or before an upgrade."""

    kind: Literal["manual", "daily", "pre-upgrade"]
    name: str
    path: str
    created_at: datetime | None
    #: None when the server may not look inside the folder.
    complete: bool | None
    size_bytes: int | None
    files: int | None
    application_version: str | None = None
    requested_by: str | None = None
    stores: list[BackupStoreResponse] = []


class BackupRunResponse(BaseModel):
    """The backup this server is taking, or last took, by hand."""

    status: Literal["idle", "running", "succeeded", "failed"]
    requested_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    folder: str | None = None
    message: str | None = None
    stores: list[BackupStoreResponse] = []


class BackupOverviewResponse(BaseModel):
    """Everything the backups screen shows."""

    backup_directory: str
    keep_manual: int
    run: BackupRunResponse
    backups: list[BackupFolderResponse]
