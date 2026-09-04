"""Firm-scoped REST endpoints for the loyalty ledger."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.loyalty.schemas import (
    LoyaltyAdjust,
    LoyaltyBalance,
    LoyaltyBalanceRecord,
    LoyaltyEntryResponse,
    LoyaltyExpiringRecord,
    LoyaltyMovementRecord,
    LoyaltyRedeem,
    LoyaltySettingsResponse,
    LoyaltySettingsWrite,
)
from app.loyalty.services import LoyaltyService

router = APIRouter(
    prefix="/api/v1/loyalty",
    tags=["Loyalty"],
    responses=STANDARD_ERROR_RESPONSES,
)

LoyaltyViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("LOYALTY_VIEW")]

#: Spending a customer's credit settles a bill with money the firm owes them,
#: so it is its own authority rather than part of reading a balance.
LoyaltyManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("LOYALTY_MANAGE")
]

#: Setting the conversion rate decides what every customer's credit is worth,
#: which is the firm's decision rather than the sales desk's -- the same split
#: as the credit-control policy.
LoyaltySettingsScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("LOYALTY_MANAGE_SETTINGS")
]


# Declared above `/{customer_id}`: FastAPI matches in declaration order, and
# below it "settings" is read as a customer id and answered 422.
@router.get("/settings", response_model=ApiResponse[LoyaltySettingsResponse])
def read_settings(
    scope: LoyaltyViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LoyaltySettingsResponse]:
    """Return this firm's scheme, or the shape one would take."""
    return ApiResponse(data=LoyaltyService(db).read_settings(scope.firm_id))


@router.put("/settings", response_model=ApiResponse[LoyaltySettingsResponse])
def write_settings(
    payload: LoyaltySettingsWrite,
    scope: LoyaltySettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LoyaltySettingsResponse]:
    """Change this firm's scheme. An omitted field is left alone."""
    return ApiResponse(
        data=LoyaltyService(db).write_settings(
            scope.firm_id, payload, actor_id=scope.actor_id
        ),
        message="Loyalty settings saved.",
    )


@router.get("/entries", response_model=PaginatedResponse[LoyaltyEntryResponse])
def list_entries(
    scope: LoyaltyViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    customer_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[LoyaltyEntryResponse]:
    """List the ledger, newest first."""
    params = PaginationParams(page=page, page_size=page_size)
    service = LoyaltyService(db)
    rows, total = service.entries(
        firm_scope=scope.firm_id,
        customer_id=customer_id,
        offset=(params.page - 1) * params.page_size,
        limit=params.page_size,
    )
    return PaginatedResponse(
        data=service.describe(rows), pagination=params.metadata(total)
    )


@router.post("/redeem", response_model=ApiResponse[LoyaltyEntryResponse])
def redeem(
    payload: LoyaltyRedeem,
    scope: LoyaltyManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LoyaltyEntryResponse]:
    """Spend a customer's credit against one of their bills.

    Refused rather than trimmed when the balance or the bill cannot take it:
    a customer told their points cleared a bill and finding otherwise is worse
    than being told no.
    """
    service = LoyaltyService(db)
    row = service.redeem(
        firm_scope=scope.firm_id,
        invoice_id=payload.sales_invoice_id,
        points=payload.points,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=service.describe([row])[0], message="Points redeemed.")


@router.post("/adjust", response_model=ApiResponse[LoyaltyEntryResponse])
def adjust(
    payload: LoyaltyAdjust,
    scope: LoyaltyManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LoyaltyEntryResponse]:
    """Correct a balance by hand, saying why. Posts nothing."""
    service = LoyaltyService(db)
    row = service.adjust(
        firm_scope=scope.firm_id,
        customer_id=payload.customer_id,
        points=payload.points,
        reason=payload.reason,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=service.describe([row])[0], message="Balance adjusted.")


@router.post("/expire", response_model=ApiResponse[dict[str, int]])
def expire(
    scope: LoyaltyManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Write off points that have run out of time.

    Safe to run twice: each expiry names the entry it takes, so a second sweep
    cannot take the same points again.
    """
    lapsed = LoyaltyService(db).expire(
        firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"expired": lapsed}, message=f"{lapsed} entries lapsed.")


@router.get(
    "/reports/balances",
    response_model=ApiResponse[list[LoyaltyBalanceRecord]],
)
def loyalty_balances(
    scope: LoyaltyViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LoyaltyBalanceRecord]]:
    """Report what every customer holds, and what it is worth today."""
    return ApiResponse(
        data=LoyaltyService(db).balances_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/movements",
    response_model=ApiResponse[list[LoyaltyMovementRecord]],
)
def loyalty_movements(
    scope: LoyaltyViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LoyaltyMovementRecord]]:
    """Every movement of credit: earned, spent, adjusted and lapsed."""
    return ApiResponse(
        data=LoyaltyService(db).movements_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/expiring",
    response_model=ApiResponse[list[LoyaltyExpiringRecord]],
)
def loyalty_expiring(
    scope: LoyaltyViewScope,
    within_days: Annotated[int, Query(ge=1, le=730)] = 90,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LoyaltyExpiringRecord]]:
    """Points that will lapse, soonest first."""
    return ApiResponse(
        data=LoyaltyService(db).expiring_report(
            firm_scope=scope.firm_id, within_days=within_days
        )
    )


@router.get("/{customer_id}", response_model=ApiResponse[LoyaltyBalance])
def balance(
    customer_id: UUID,
    scope: LoyaltyViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LoyaltyBalance]:
    """Return what one customer holds, and whether they can spend it."""
    return ApiResponse(
        data=LoyaltyService(db).balance(customer_id, firm_scope=scope.firm_id)
    )
