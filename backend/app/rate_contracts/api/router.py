"""Rate contracts with suppliers and their releases (PG-9)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.rate_contracts.schemas import (
    RateContractCancel,
    RateContractCreate,
    RateContractReleaseResponse,
    RateContractResponse,
    RateContractUpdate,
)
from app.rate_contracts.services import RateContractService

router = APIRouter(
    prefix="/api/v1/rate-contracts",
    tags=["Rate contracts"],
    responses=STANDARD_ERROR_RESPONSES,
)

ViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("RATE_CONTRACT_VIEW")]
ManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("RATE_CONTRACT_MANAGE")
]
#: Activating a contract commits the firm to its rates, as approving an order
#: commits it to buy: the same code.
ApproveScope = Annotated[ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")]


def _one(
    service: RateContractService, response: Response, row_id: UUID, firm_id: UUID
) -> RateContractResponse:
    """Return one contract's response and publish its version."""
    row = service.get(row_id, firm_id=firm_id)
    set_etag(response, row)
    return service.responses([row])[0]


@router.get("", response_model=PaginatedResponse[RateContractResponse])
def list_rate_contracts(
    scope: ViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    vendor_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[RateContractResponse]:
    """Return one page of the firm's rate contracts, newest first.

    ``status`` may be ``EXPIRED``, which is derived from the dates.
    """
    params = PaginationParams(page=page, page_size=page_size)
    service = RateContractService(db)
    rows, total = service.page(
        scope.firm_id,
        vendor_id=vendor_id,
        status=status_filter,
        search=search,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=service.responses(rows), pagination=params.metadata(total)
    )


@router.post(
    "",
    response_model=ApiResponse[RateContractResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_rate_contract(
    data: RateContractCreate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RateContractResponse]:
    """Type a draft rate contract."""
    service = RateContractService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.get("/{contract_id}", response_model=ApiResponse[RateContractResponse])
def get_rate_contract(
    contract_id: UUID,
    scope: ViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RateContractResponse]:
    """Return one rate contract with what has been drawn per line."""
    return ApiResponse(
        data=_one(RateContractService(db), response, contract_id, scope.firm_id)
    )


@router.put("/{contract_id}", response_model=ApiResponse[RateContractResponse])
def update_rate_contract(
    contract_id: UUID,
    data: RateContractUpdate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[RateContractResponse]:
    """Change a draft rate contract; a field left out is left alone."""
    service = RateContractService(db)
    assert_version(
        service.get(contract_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.update(
        contract_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.delete("/{contract_id}", response_model=ApiResponse[None])
def delete_rate_contract(
    contract_id: UUID,
    scope: ManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Delete a draft rate contract."""
    RateContractService(db).delete(
        contract_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Rate contract deleted.")


@router.post("/{contract_id}/approve", response_model=ApiResponse[RateContractResponse])
def approve_rate_contract(
    contract_id: UUID,
    scope: ApproveScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RateContractResponse]:
    """Make a draft contract active; refused if it overlaps another."""
    service = RateContractService(db)
    row = service.approve(contract_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.post("/{contract_id}/close", response_model=ApiResponse[RateContractResponse])
def close_rate_contract(
    contract_id: UUID,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RateContractResponse]:
    """End an active contract; orders already drawn keep their prices."""
    service = RateContractService(db)
    row = service.close(contract_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.post("/{contract_id}/cancel", response_model=ApiResponse[RateContractResponse])
def cancel_rate_contract(
    contract_id: UUID,
    data: RateContractCancel,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[RateContractResponse]:
    """Call off a draft or active contract."""
    service = RateContractService(db)
    row = service.cancel(
        contract_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.get(
    "/{contract_id}/releases",
    response_model=ApiResponse[list[RateContractReleaseResponse]],
)
def list_rate_contract_releases(
    contract_id: UUID,
    scope: ViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[RateContractReleaseResponse]]:
    """Return every purchase order line priced from the contract."""
    return ApiResponse(
        data=RateContractService(db).releases(contract_id, firm_id=scope.firm_id)
    )
