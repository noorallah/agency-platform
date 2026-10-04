"""REST access to the agency's branding.

The two reads are **public**: the sign-in screen shows the agency's name and
logo before anybody has signed in, and nothing in them is secret
(``docs/BRANDING_AND_NAMES.md`` section 4.1). The writes need
``PLATFORM_SETTINGS``, because the branding belongs to the installation rather
than to any one firm. ``/api/v1/branding`` is a platform path in
``app/core/database/dependencies.py``, so ``get_db`` opens the platform store
whatever ``X-Firm-ID`` a client sends.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.branding.schemas import AgencyBrandingResponse, AgencyBrandingWrite
from app.branding.services import MAX_LOGO_BYTES, AgencyBrandingService
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.database.dependencies import get_db
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.core.security.authorization import Principal, require_permission

router = APIRouter(
    prefix="/api/v1/branding",
    tags=["Branding"],
    responses=STANDARD_ERROR_RESPONSES,
)

BrandingSettingsPrincipal = Annotated[
    Principal, Depends(require_permission("PLATFORM_SETTINGS"))
]


def _actor(principal: Principal) -> UUID | None:
    """Return the acting user's id, when the token names one."""
    return principal.subject if isinstance(principal.subject, UUID) else None


def _answer(
    service: AgencyBrandingService, response: Response
) -> ApiResponse[AgencyBrandingResponse]:
    """Return the branding, publishing its version as the ETag."""
    row = service.current()
    if row is not None:
        set_etag(response, row)
    return ApiResponse(data=service.response())


@router.get("", response_model=ApiResponse[AgencyBrandingResponse])
def get_branding(
    response: Response, db: Session = Depends(get_db)
) -> ApiResponse[AgencyBrandingResponse]:
    """Return the agency's name, tagline and colour, with no sign-in needed."""
    return _answer(AgencyBrandingService(db), response)


@router.get(
    "/logo",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}},
)
def get_branding_logo(db: Session = Depends(get_db)) -> Response:
    """Return the agency's logo image, with no sign-in needed."""
    row = AgencyBrandingService(db).current()
    if row is None or row.logo is None or row.logo_content_type is None:
        raise ResourceNotFoundError("No logo has been given for the agency.")
    return Response(
        content=row.logo,
        media_type=row.logo_content_type,
        headers={"ETag": f'"{row.version}"', "Cache-Control": "no-cache"},
    )


@router.put("", response_model=ApiResponse[AgencyBrandingResponse])
def update_branding(
    data: AgencyBrandingWrite,
    principal: BrandingSettingsPrincipal,
    response: Response,
    expected_version: ExpectedVersion,
    db: Session = Depends(get_db),
) -> ApiResponse[AgencyBrandingResponse]:
    """Replace the agency's name, tagline and colour; the first save creates it."""
    service = AgencyBrandingService(db)
    service.update(data, actor_id=_actor(principal), expected_version=expected_version)
    return _answer(service, response)


@router.put("/logo", response_model=ApiResponse[AgencyBrandingResponse])
async def upload_branding_logo(
    file: Annotated[UploadFile, File()],
    principal: BrandingSettingsPrincipal,
    response: Response,
    expected_version: ExpectedVersion,
    db: Session = Depends(get_db),
) -> ApiResponse[AgencyBrandingResponse]:
    """Replace the logo with a PNG or JPG of at most 1 MB."""
    # Read one byte past the limit, so an oversized upload is refused by name
    # without holding the whole of it in memory.
    content = await file.read(MAX_LOGO_BYTES + 1)
    if len(content) > MAX_LOGO_BYTES:
        raise ValidationError("The logo is larger than 1024 KB, the most it may be.")
    service = AgencyBrandingService(db)
    service.set_logo(
        content, actor_id=_actor(principal), expected_version=expected_version
    )
    return _answer(service, response)


@router.delete("/logo", response_model=ApiResponse[AgencyBrandingResponse])
def delete_branding_logo(
    principal: BrandingSettingsPrincipal,
    response: Response,
    expected_version: ExpectedVersion,
    db: Session = Depends(get_db),
) -> ApiResponse[AgencyBrandingResponse]:
    """Remove the logo; the agency's initials are shown instead."""
    service = AgencyBrandingService(db)
    service.clear_logo(actor_id=_actor(principal), expected_version=expected_version)
    return _answer(service, response)
