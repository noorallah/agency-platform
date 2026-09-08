"""FastAPI routes for protected platform firm administration."""

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.settings import get_request_settings
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.config.settings import Settings
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import firm_store_session, get_db
from app.core.exceptions import BusinessRuleError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import Principal, require_platform_admin
from app.core.tenancy import DeploymentMode
from app.firms.models import Firm
from app.firms.schemas import (
    FirmCreate,
    FirmProvisionResponse,
    FirmReadinessResponse,
    FirmReadinessStep,
    FirmResponse,
    FirmUpdate,
    OpenBooksRequest,
    OpenBooksResponse,
    TaxTemplateRequest,
    TaxTemplateResponse,
)
from app.firms.services import FirmReadinessService, FirmService
from app.firms.services.readiness import FirmReadiness, storage_is_ready

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


@contextmanager
def _store_if_built(request: Request, firm: Firm) -> Iterator[Session | None]:
    """Open the firm's store, or yield None when it has not been built.

    `firm_store_session` refuses an unprovisioned dedicated firm by name, which
    is right for a request that needs the store and wrong for one asking
    whether it exists: readiness has to answer for exactly that firm.
    """
    context = (
        firm_store_session(request, firm.id)
        if storage_is_ready(firm)
        else nullcontext(None)
    )
    with context as store:
        yield store


def _readiness_response(readiness: FirmReadiness) -> FirmReadinessResponse:
    return FirmReadinessResponse(
        firm_id=readiness.firm_id,
        code=readiness.code,
        name=readiness.name,
        deployment_mode=readiness.deployment_mode,
        storage_provisioned=readiness.storage_provisioned,
        can_post=readiness.can_post,
        ready=readiness.ready,
        steps=[
            FirmReadinessStep(
                key=step.key,
                label=step.label,
                status=step.status.value,
                detail=step.detail,
                required=step.required,
            )
            for step in readiness.steps
        ],
    )


@router.get("/{firm_id}/readiness", response_model=ApiResponse[FirmReadinessResponse])
def firm_readiness(
    firm_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
) -> ApiResponse[FirmReadinessResponse]:
    """Report whether the firm can trade yet, and what it still needs.

    Storage, business profile, books, tax, geography, branches and people,
    each read from wherever it lives -- the firm's own store for most of them.
    The same list `scripts/check_firm_readiness.py` prints, so the screen and
    the shell agree about what finished means.
    """
    firm = FirmService(db).get(firm_id)
    with _store_if_built(request, firm) as store:
        readiness = FirmReadinessService(db).readiness(firm, store)
    return ApiResponse(data=_readiness_response(readiness))


@router.post("/{firm_id}/open-books", response_model=ApiResponse[OpenBooksResponse])
def open_firm_books(
    firm_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
    data: OpenBooksRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[OpenBooksResponse]:
    """Give the firm a chart of accounts, a financial year and its mappings.

    The one setup step that had no screen: until it is done the firm accepts
    masters and drafts and refuses every posting. Idempotent -- a second call
    creates nothing and says the books were already open.
    """
    firm = FirmService(db).get(firm_id)
    if not storage_is_ready(firm):
        raise BusinessRuleError(
            "Provision the firm's storage before opening its books."
        )
    with firm_store_session(request, firm.id) as store:
        created, starts_on = FirmReadinessService(db).open_books(
            firm,
            store,
            _actor_id(principal),
            year_starts_on=data.year_starts_on if data else None,
        )
    already = not any(created.values())
    return ApiResponse(
        data=OpenBooksResponse(
            firm_id=firm.id,
            year_starts_on=starts_on,
            already_open=already,
            **created,
        ),
        message=(
            "The books were already open; nothing was created."
            if already
            else f"Books opened for the year starting {starts_on.isoformat()}."
        ),
    )


@router.post(
    "/{firm_id}/apply-tax-template", response_model=ApiResponse[TaxTemplateResponse]
)
def apply_firm_tax_template(
    firm_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
    data: TaxTemplateRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[TaxTemplateResponse]:
    """Give the firm a whole tax setup from a template -- Indian GST today.

    Every tax table is per firm, so a new firm prices every line with no tax
    until it has a system, components, profiles and rules; by hand that is
    five screens. Idempotent: a firm that already holds a tax system gets
    nothing and is told so.
    """
    firm = FirmService(db).get(firm_id)
    if not storage_is_ready(firm):
        raise BusinessRuleError(
            "Provision the firm's storage before applying a tax template."
        )
    template = data.template if data else "IN_GST"
    with firm_store_session(request, firm.id) as store:
        created = FirmReadinessService(db).apply_tax_template(
            firm, store, _actor_id(principal), template=template
        )
    already = not any(created.values())
    return ApiResponse(
        data=TaxTemplateResponse(
            firm_id=firm.id, template=template, already_configured=already, **created
        ),
        message=(
            "The firm already has a tax system; nothing was created."
            if already
            else f"GST set up: {created['profiles']} tax profiles and "
            f"{created['rules']} rules."
        ),
    )


@router.delete("/{firm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_firm(
    firm_id: UUID, principal: PlatformPrincipal, db: Session = Depends(get_db)
) -> Response:
    """Soft delete an unassigned firm."""
    FirmService(db).delete(firm_id, _actor_id(principal))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
