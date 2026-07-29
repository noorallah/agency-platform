"""FastAPI routes for protected platform firm administration."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.settings import get_request_settings
from app.core.config.settings import Settings
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import Principal, require_platform_admin
from app.firms.schemas import FirmCreate, FirmResponse, FirmUpdate
from app.firms.services import FirmService

router = APIRouter(
    prefix="/api/v1/firms", tags=["Firms"], responses=STANDARD_ERROR_RESPONSES
)
AdminPrincipal = Annotated[Principal, Depends(require_platform_admin())]


def _actor_id(principal: Principal) -> UUID:
    """Return the UUID user performing an administrative action."""
    if not isinstance(principal.subject, UUID):
        raise RuntimeError("Firm administration requires a user principal.")
    return principal.subject


@router.get("", response_model=PaginatedResponse[FirmResponse])
def list_firms(
    principal: AdminPrincipal,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal["name", "code", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[FirmResponse]:
    """List firms using the standardized paging and approved sorting contract."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = FirmService(db).list(
        params.page, params.page_size, search, sort_by, sort_direction == "desc"
    )
    return PaginatedResponse(
        data=[FirmResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "", response_model=ApiResponse[FirmResponse], status_code=status.HTTP_201_CREATED
)
def create_firm(
    data: FirmCreate,
    principal: AdminPrincipal,
    db: Session = Depends(get_db),
    _: Settings = Depends(get_request_settings),
) -> ApiResponse[FirmResponse]:
    """Create a platform firm."""
    firm = FirmService(db).create(data, _actor_id(principal))
    return ApiResponse(data=FirmResponse.model_validate(firm))


@router.get("/{firm_id}", response_model=ApiResponse[FirmResponse])
def get_firm(
    firm_id: UUID, principal: AdminPrincipal, db: Session = Depends(get_db)
) -> ApiResponse[FirmResponse]:
    """Retrieve a visible firm."""
    return ApiResponse(data=FirmResponse.model_validate(FirmService(db).get(firm_id)))


@router.put("/{firm_id}", response_model=ApiResponse[FirmResponse])
def update_firm(
    firm_id: UUID,
    data: FirmUpdate,
    principal: AdminPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[FirmResponse]:
    """Replace one firm."""
    firm = FirmService(db).update(firm_id, data, _actor_id(principal))
    return ApiResponse(data=FirmResponse.model_validate(firm))


@router.delete("/{firm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_firm(
    firm_id: UUID, principal: AdminPrincipal, db: Session = Depends(get_db)
) -> Response:
    """Soft delete an unassigned firm."""
    FirmService(db).delete(firm_id, _actor_id(principal))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
