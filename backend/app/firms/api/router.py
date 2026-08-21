"""FastAPI routes for protected platform firm administration."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.settings import get_request_settings
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.config.settings import Settings
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import Principal, require_platform_admin
from app.core.tenancy import DeploymentMode
from app.firms.schemas import (
    FirmCreate,
    FirmProvisionResponse,
    FirmResponse,
    FirmUpdate,
)
from app.firms.services import FirmService

router = APIRouter(
    prefix="/api/v1/firms", tags=["Firms"], responses=STANDARD_ERROR_RESPONSES
)
PlatformPrincipal = Annotated[Principal, Depends(require_platform_admin())]


def _actor_id(principal: Principal) -> UUID:
    """Return the UUID user performing an administrative action."""
    if not isinstance(principal.subject, UUID):
        raise RuntimeError("Firm administration requires a user principal.")
    return principal.subject


@router.get("", response_model=PaginatedResponse[FirmResponse])
def list_firms(
    principal: PlatformPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
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
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[FirmResponse]:
    """Create a platform firm."""
    lifecycle = request.app.state.tenant_storage_lifecycle
    firm = FirmService(
        db, storage_lifecycle=lifecycle, tenancy_settings=settings.tenancy
    ).create(data, _actor_id(principal))
    return ApiResponse(data=FirmResponse.model_validate(firm))


@router.get("/{firm_id}", response_model=ApiResponse[FirmResponse])
def get_firm(
    firm_id: UUID,
    principal: PlatformPrincipal,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[FirmResponse]:
    """Retrieve a visible firm."""
    firm = FirmService(db).get(firm_id)
    set_etag(response, firm)
    return ApiResponse(data=FirmResponse.model_validate(firm))


@router.put("/{firm_id}", response_model=ApiResponse[FirmResponse])
def update_firm(
    firm_id: UUID,
    data: FirmUpdate,
    principal: PlatformPrincipal,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[FirmResponse]:
    """Replace one firm."""
    firm = FirmService(db, tenancy_settings=settings.tenancy).update(
        firm_id, data, _actor_id(principal), expected_version
    )
    set_etag(response, firm)
    return ApiResponse(data=FirmResponse.model_validate(firm))


@router.post("/{firm_id}/provision", response_model=ApiResponse[FirmProvisionResponse])
def provision_firm_storage(
    firm_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[FirmProvisionResponse]:
    """Create the firm's database and schema and build its tables.

    Safe to call again: every step is create-if-missing and the migration stops
    at head, so this is also how a firm is repaired after its target server was
    unreachable.
    """
    firm, already = FirmService(
        db,
        storage_lifecycle=request.app.state.tenant_storage_lifecycle,
        tenancy_settings=settings.tenancy,
    ).provision(firm_id, _actor_id(principal))
    return ApiResponse(
        data=FirmProvisionResponse(
            firm_id=firm.id,
            deployment_mode=DeploymentMode(firm.deployment_mode),
            database_name=firm.database_name,
            schema_name=firm.schema_name,
            connection_profile=firm.connection_profile,
            provisioned_at=firm.provisioned_at,
            already_provisioned=already,
        ),
        message=(
            "Firm storage was already provisioned."
            if already
            else "Firm storage provisioned."
        ),
    )


@router.delete("/{firm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_firm(
    firm_id: UUID, principal: PlatformPrincipal, db: Session = Depends(get_db)
) -> Response:
    """Soft delete an unassigned firm."""
    FirmService(db).delete(firm_id, _actor_id(principal))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
