"""Mapping a file from other software onto an import's template (decision B3).

``/api/v1/imports/{kind}`` -- the kinds are the six imports that take a
mapping. Each route needs the import permission of its kind, the code its own
import endpoint is guarded by, so nobody maps a file they could not import.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi import Response as FastApiResponse
from sqlalchemy.orm import Session

from app.common.file_import import file_format_of
from app.common.scope import ResolvedFirmScope, firm_any_permission_scope
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.imports.schemas import ImportMappingResponse, ImportMappingWrite, ImportPreview
from app.imports.services import IMPORT_KINDS, ImportMappingService
from app.imports.services.import_mapping_service import kind_of

router = APIRouter(
    prefix="/api/v1/imports",
    tags=["Imports"],
    responses=STANDARD_ERROR_RESPONSES,
)

ImportScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope(
        *sorted({kind.permission for kind in IMPORT_KINDS.values()})
    ),
]


def _require_kind(scope: ResolvedFirmScope, kind: str) -> None:
    """Refuse a caller who may not run this kind's import."""
    needed = kind_of(kind).permission
    if not scope.principal.has_permission(needed):
        raise AuthorizationError(
            f"Mapping a {kind} file needs the right to import it ({needed})."
        )


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_import_mapping(
    mapping_id: UUID,
    scope: ImportScope,
    db: Session = Depends(get_db),
) -> FastApiResponse:
    """Delete a saved mapping."""
    service = ImportMappingService(db)
    row = service.get_mapping(scope.firm_id, mapping_id)
    _require_kind(scope, row.kind)
    service.delete_mapping(row, actor_id=scope.actor_id)
    return FastApiResponse(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{kind}/preview", response_model=ApiResponse[ImportPreview])
async def preview_import_file(
    kind: str,
    scope: ImportScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
) -> ApiResponse[ImportPreview]:
    """Read a file's headings and first rows, and suggest how to map them.

    Writes nothing. The suggestion is what the import would do with the file
    as it is; the screen lets the person change it before the check.
    """
    _require_kind(scope, kind)
    return ApiResponse(
        data=ImportMappingService(db).preview(
            kind, await file.read(), file_format_of(file.filename)
        )
    )


@router.get("/{kind}/mappings", response_model=ApiResponse[list[ImportMappingResponse]])
def list_import_mappings(
    kind: str,
    scope: ImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ImportMappingResponse]]:
    """List the firm's saved mappings for one import."""
    _require_kind(scope, kind)
    return ApiResponse(data=ImportMappingService(db).list_mappings(scope.firm_id, kind))


@router.post("/{kind}/mappings", response_model=ApiResponse[ImportMappingResponse])
def save_import_mapping(
    kind: str,
    data: ImportMappingWrite,
    scope: ImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ImportMappingResponse]:
    """Save a mapping under a name, replacing one already called that."""
    _require_kind(scope, kind)
    saved = ImportMappingService(db).save_mapping(
        scope.firm_id, kind, data, actor_id=scope.actor_id
    )
    return ApiResponse(data=saved, message=f"Mapping {saved.name} saved.")
