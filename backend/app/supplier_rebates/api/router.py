"""Firm-scoped REST endpoints for supplier volume rebates (BUY-13)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.supplier_rebates.models import SupplierRebateStatus
from app.supplier_rebates.schemas import (
    SupplierRebateAccrue,
    SupplierRebateCreate,
    SupplierRebateResponse,
    SupplierRebateUpdate,
)
from app.supplier_rebates.services import SupplierRebateService

router = APIRouter(
    prefix="/api/v1/supplier-rebates",
    tags=["Supplier Rebates"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: Reading a rebate is reading purchases; agreeing and accruing one is the
#: purchase manager's call, as approving an order is.
RebateViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PURCHASE_VIEW")]
RebateManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")
]


def _one(db: Session, row_id: UUID, firm_id: UUID) -> SupplierRebateResponse:
    """Build one agreement's response."""
    service = SupplierRebateService(db)
    return service.responses([service.get(row_id, firm_id=firm_id)])[0]


@router.get("", response_model=ApiResponse[list[SupplierRebateResponse]])
def list_supplier_rebates(
    scope: RebateViewScope,
    vendor_id: UUID | None = None,
    status_value: Annotated[SupplierRebateStatus | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SupplierRebateResponse]]:
    """Return the firm's rebate agreements with each one's progress."""
    service = SupplierRebateService(db)
    rows = service.list_agreements(
        firm_id=scope.firm_id,
        vendor_id=vendor_id,
        status=None if status_value is None else status_value.value,
    )
    return ApiResponse(data=service.responses(rows))


@router.post(
    "",
    response_model=ApiResponse[SupplierRebateResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_rebate(
    data: SupplierRebateCreate,
    scope: RebateManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierRebateResponse]:
    """Agree a volume rebate with a supplier for a period."""
    row = SupplierRebateService(db).create(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_one(db, row.id, scope.firm_id))


@router.get("/{agreement_id}", response_model=ApiResponse[SupplierRebateResponse])
def get_supplier_rebate(
    agreement_id: UUID,
    scope: RebateViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierRebateResponse]:
    """Return one agreement with its volume, slab reached and settlements."""
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id))


@router.put("/{agreement_id}", response_model=ApiResponse[SupplierRebateResponse])
def update_supplier_rebate(
    agreement_id: UUID,
    data: SupplierRebateUpdate,
    scope: RebateManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierRebateResponse]:
    """Change an agreement that is still counting."""
    SupplierRebateService(db).update(
        agreement_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id))


@router.post(
    "/{agreement_id}/cancel", response_model=ApiResponse[SupplierRebateResponse]
)
def cancel_supplier_rebate(
    agreement_id: UUID,
    scope: RebateManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierRebateResponse]:
    """Withdraw an agreement nothing was accrued on."""
    SupplierRebateService(db).cancel(
        agreement_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id))


@router.post(
    "/{agreement_id}/accrue", response_model=ApiResponse[SupplierRebateResponse]
)
def accrue_supplier_rebate(
    agreement_id: UUID,
    data: SupplierRebateAccrue,
    scope: RebateManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierRebateResponse]:
    """Book what the period earned, once it is over."""
    SupplierRebateService(db).accrue(
        agreement_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        accrual_date=data.accrual_date,
    )
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id))


@router.post(
    "/{agreement_id}/reverse-accrual",
    response_model=ApiResponse[SupplierRebateResponse],
)
def reverse_supplier_rebate_accrual(
    agreement_id: UUID,
    scope: RebateManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierRebateResponse]:
    """Take an accrual back off the books while nothing is settled."""
    SupplierRebateService(db).reverse_accrual(
        agreement_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id))
