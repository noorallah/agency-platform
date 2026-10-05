"""Fixed assets: classes, register, depreciation, disposal (PG-13, backlog 86 #7)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.fixed_assets.schemas import (
    AssetClassCreate,
    AssetClassResponse,
    AssetClassUpdate,
    DepreciationRunCancel,
    DepreciationRunCreate,
    DepreciationRunResponse,
    FixedAssetCreate,
    FixedAssetDispose,
    FixedAssetResponse,
    FixedAssetSchedule,
    FixedAssetUpdate,
    ItBlockSchedule,
)
from app.fixed_assets.services import FixedAssetService

router = APIRouter(
    prefix="/api/v1/fixed-assets",
    tags=["Fixed Assets"],
    responses=STANDARD_ERROR_RESPONSES,
)

ViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("FIXED_ASSET_VIEW")]
ManageScope = Annotated[ResolvedFirmScope, firm_permission_scope("FIXED_ASSET_MANAGE")]
#: A report opens to its module's readers and to ``REPORT_VIEW`` alike.
ReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("FIXED_ASSET_VIEW", "REPORT_VIEW")
]
#: What posts a journal -- a depreciation run, its cancellation, a disposal --
#: also needs the right to post journals.
_POSTING_CODE = "JOURNAL_POST"


def _may_post(scope: ResolvedFirmScope) -> None:
    """Refuse a person who may manage assets but not post journals."""
    if not scope.principal.has_permission(_POSTING_CODE):
        raise AuthorizationError(
            f"This posts a journal, which needs {_POSTING_CODE} as well."
        )


# == asset classes ============================================================
@router.get("/classes", response_model=PaginatedResponse[AssetClassResponse])
def list_asset_classes(
    scope: ViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[AssetClassResponse]:
    """Return one page of the firm's asset classes, by code."""
    params = PaginationParams(page=page, page_size=page_size)
    service = FixedAssetService(db)
    rows, total = service.class_page(
        scope.firm_id,
        search=search,
        active=is_active,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=service.class_responses(rows), pagination=params.metadata(total)
    )


@router.post(
    "/classes",
    response_model=ApiResponse[AssetClassResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_asset_class(
    data: AssetClassCreate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[AssetClassResponse]:
    """Add an asset class."""
    service = FixedAssetService(db)
    row = service.create_class(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.class_responses([row])[0])


@router.get("/classes/{class_id}", response_model=ApiResponse[AssetClassResponse])
def get_asset_class(
    class_id: UUID,
    scope: ViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[AssetClassResponse]:
    """Return one asset class."""
    service = FixedAssetService(db)
    row = service.get_class(class_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.class_responses([row])[0])


@router.put("/classes/{class_id}", response_model=ApiResponse[AssetClassResponse])
def update_asset_class(
    class_id: UUID,
    data: AssetClassUpdate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[AssetClassResponse]:
    """Change an asset class; a field left out is left alone."""
    service = FixedAssetService(db)
    assert_version(
        service.get_class(class_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.update_class(
        class_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.class_responses([row])[0])


@router.delete("/classes/{class_id}", response_model=ApiResponse[None])
def delete_asset_class(
    class_id: UUID,
    scope: ManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Remove an asset class no asset belongs to."""
    FixedAssetService(db).delete_class(
        class_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Asset class deleted.")


# == depreciation runs ========================================================
@router.get(
    "/depreciation-runs", response_model=PaginatedResponse[DepreciationRunResponse]
)
def list_depreciation_runs(
    scope: ViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    run_type: Annotated[str | None, Query(max_length=20)] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DepreciationRunResponse]:
    """Return one page of the firm's depreciation runs, latest period first."""
    params = PaginationParams(page=page, page_size=page_size)
    service = FixedAssetService(db)
    rows, total = service.run_page(
        scope.firm_id,
        status=status_filter,
        run_type=run_type,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=service.run_responses(rows), pagination=params.metadata(total)
    )


@router.post(
    "/depreciation-runs",
    response_model=ApiResponse[DepreciationRunResponse],
    status_code=status.HTTP_201_CREATED,
)
def run_depreciation(
    data: DepreciationRunCreate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[DepreciationRunResponse]:
    """Charge the period's Companies Act depreciation and post one journal."""
    _may_post(scope)
    service = FixedAssetService(db)
    row = service.run(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.run_responses([row])[0], message="Posted.")


@router.get(
    "/depreciation-runs/{run_id}", response_model=ApiResponse[DepreciationRunResponse]
)
def get_depreciation_run(
    run_id: UUID,
    scope: ViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[DepreciationRunResponse]:
    """Return one depreciation run with its lines."""
    service = FixedAssetService(db)
    row = service.get_run(run_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.run_responses([row])[0])


@router.post(
    "/depreciation-runs/{run_id}/cancel",
    response_model=ApiResponse[DepreciationRunResponse],
)
def cancel_depreciation_run(
    run_id: UUID,
    data: DepreciationRunCancel,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[DepreciationRunResponse]:
    """Take the latest run back, reversing its journal."""
    _may_post(scope)
    service = FixedAssetService(db)
    assert_version(
        service.get_run(run_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.cancel_run(
        run_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.run_responses([row])[0], message="Cancelled.")


# == reports ==================================================================
@router.get("/reports/it-block-schedule", response_model=ApiResponse[ItBlockSchedule])
def it_block_schedule(
    financial_year_id: UUID,
    scope: ReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ItBlockSchedule]:
    """Return the Income-tax block schedule of a financial year; posts nothing."""
    return ApiResponse(
        data=FixedAssetService(db).it_block_schedule(
            financial_year_id, firm_id=scope.firm_id
        )
    )


# == the register =============================================================
@router.get("", response_model=PaginatedResponse[FixedAssetResponse])
def list_fixed_assets(
    scope: ViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    asset_class_id: UUID | None = None,
    branch_id: UUID | None = None,
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[FixedAssetResponse]:
    """Return one page of the asset register, by asset number.

    Each asset carries its cost, accumulated depreciation and net book value;
    ``as_of`` counts only depreciation charged up to that day.
    """
    params = PaginationParams(page=page, page_size=page_size)
    service = FixedAssetService(db)
    rows, total = service.page(
        scope.firm_id,
        search=search,
        status=status_filter,
        asset_class_id=asset_class_id,
        branch_id=branch_id,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=service.responses(rows, as_of=as_of), pagination=params.metadata(total)
    )


@router.post(
    "",
    response_model=ApiResponse[FixedAssetResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_fixed_asset(
    data: FixedAssetCreate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[FixedAssetResponse]:
    """Put an asset on the register by hand: an opening one, or one off-bill."""
    service = FixedAssetService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.get("/{asset_id}", response_model=ApiResponse[FixedAssetResponse])
def get_fixed_asset(
    asset_id: UUID,
    scope: ViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[FixedAssetResponse]:
    """Return one asset with where it stands."""
    service = FixedAssetService(db)
    row = service.get(asset_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.put("/{asset_id}", response_model=ApiResponse[FixedAssetResponse])
def update_fixed_asset(
    asset_id: UUID,
    data: FixedAssetUpdate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[FixedAssetResponse]:
    """Change an active asset; a field left out is left alone."""
    service = FixedAssetService(db)
    assert_version(
        service.get(asset_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.update(asset_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.delete("/{asset_id}", response_model=ApiResponse[None])
def delete_fixed_asset(
    asset_id: UUID,
    scope: ManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Take a hand-typed, undepreciated asset off the register."""
    FixedAssetService(db).delete(
        asset_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Fixed asset deleted.")


@router.get("/{asset_id}/schedule", response_model=ApiResponse[FixedAssetSchedule])
def fixed_asset_schedule(
    asset_id: UUID,
    scope: ViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[FixedAssetSchedule]:
    """Return the asset's depreciation: what was charged, then year by year."""
    return ApiResponse(
        data=FixedAssetService(db).schedule(asset_id, firm_id=scope.firm_id)
    )


@router.post("/{asset_id}/dispose", response_model=ApiResponse[FixedAssetResponse])
def dispose_fixed_asset(
    asset_id: UUID,
    data: FixedAssetDispose,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[FixedAssetResponse]:
    """Sell or scrap an asset: depreciation to the day, then off the books."""
    _may_post(scope)
    service = FixedAssetService(db)
    assert_version(
        service.get(asset_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.dispose(
        asset_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Disposed.")
