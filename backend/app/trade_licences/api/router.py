"""Firm-scoped REST endpoints for trade licences (backlog 54)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.trade_licences.schemas import (
    LicenceCheckResponse,
    LicenceHolderType,
    TradeLicenceResponse,
    TradeLicenceSettingsResponse,
    TradeLicenceSettingsWrite,
    TradeLicenceTypeResponse,
    TradeLicenceTypeWrite,
    TradeLicenceWrite,
)
from app.trade_licences.services import TradeLicenceService
from app.trade_licences.services.licence_check import (
    LicenceCheckService,
    LicenceDocument,
)
from app.trade_licences.services.trade_licence_service import EXPIRY_WARNING_DAYS

router = APIRouter(
    prefix="/api/v1/trade-licences",
    tags=["Trade Licences"],
    responses=STANDARD_ERROR_RESPONSES,
)

LicenceViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TRADE_LICENCE_VIEW")
]
LicenceManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TRADE_LICENCE_MANAGE")
]
#: Whether a sale without a licence is refused is a control over the people
#: who sell, so it is not `TRADE_LICENCE_MANAGE`, which sales managers hold --
#: the split `CUSTOMER_MANAGE_SETTINGS` makes for the credit policy.
LicenceSettingsScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TRADE_LICENCE_MANAGE_SETTINGS")
]


# Every literal path is declared above `/{licence_id}`: FastAPI matches in
# declaration order, and below it "types" or "expiring" is read as an id.
@router.get("/types", response_model=ApiResponse[list[TradeLicenceTypeResponse]])
def list_licence_types(
    scope: LicenceViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[TradeLicenceTypeResponse]]:
    """List the firm's licence types, seeding the usual ones on first read."""
    rows = TradeLicenceService(db).list_types(scope.firm_id, scope.actor_id)
    return ApiResponse(
        data=[TradeLicenceTypeResponse.model_validate(row) for row in rows]
    )


@router.post(
    "/types",
    response_model=ApiResponse[TradeLicenceTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_licence_type(
    data: TradeLicenceTypeWrite,
    scope: LicenceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TradeLicenceTypeResponse]:
    """Add a licence type this firm trades under."""
    row = TradeLicenceService(db).create_type(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=TradeLicenceTypeResponse.model_validate(row))


@router.put("/types/{type_id}", response_model=ApiResponse[TradeLicenceTypeResponse])
def update_licence_type(
    type_id: UUID,
    data: TradeLicenceTypeWrite,
    scope: LicenceManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[TradeLicenceTypeResponse]:
    """Replace one licence type."""
    service = TradeLicenceService(db)
    assert_version(
        service.get_type(type_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.update_type(
        type_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=TradeLicenceTypeResponse.model_validate(row))


@router.delete("/types/{type_id}", response_model=ApiResponse[dict[str, str]])
def delete_licence_type(
    type_id: UUID,
    scope: LicenceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Delete a type no licence names."""
    TradeLicenceService(db).delete_type(
        type_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"status": "deleted"})


@router.get("/settings", response_model=ApiResponse[TradeLicenceSettingsResponse])
def get_licence_settings(
    scope: LicenceViewScope, db: Session = Depends(get_db)
) -> ApiResponse[TradeLicenceSettingsResponse]:
    """Return what a missing licence does to a sale and to a purchase."""
    return ApiResponse(data=LicenceCheckService(db).settings_response(scope.firm_id))


@router.put("/settings", response_model=ApiResponse[TradeLicenceSettingsResponse])
def update_licence_settings(
    data: TradeLicenceSettingsWrite,
    scope: LicenceSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TradeLicenceSettingsResponse]:
    """Set whether a missing licence warns or blocks a sale, and the purchase."""
    return ApiResponse(
        data=LicenceCheckService(db).update_settings(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.get(
    "/check/{document}/{document_id}",
    response_model=ApiResponse[LicenceCheckResponse],
)
def check_document_licences(
    document: LicenceDocument,
    document_id: UUID,
    scope: LicenceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LicenceCheckResponse]:
    """Say, before approving, what a document's lines need and who lacks it.

    The same judgement the approval makes, on the document's own date; a
    screen shows it and offers the override where the policy blocks.
    """
    return ApiResponse(
        data=LicenceCheckService(db).check_document(
            document, document_id, firm_id=scope.firm_id
        )
    )


@router.get("/expiring", response_model=ApiResponse[list[TradeLicenceResponse]])
def expiring_licences(
    scope: LicenceViewScope,
    within_days: Annotated[int, Query(ge=0, le=366)] = EXPIRY_WARNING_DAYS,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TradeLicenceResponse]]:
    """Licences that ran out or run out within the window, the firm's first.

    What the Home alert shows: a firm trading on its own lapsed drug licence
    is the case that matters most, so its own come before its customers'.
    """
    return ApiResponse(
        data=TradeLicenceService(db).list_licences(
            firm_id=scope.firm_id, expiring_within_days=within_days
        )
    )


@router.get("", response_model=ApiResponse[list[TradeLicenceResponse]])
def list_licences(
    scope: LicenceViewScope,
    holder_type: LicenceHolderType | None = None,
    branch_id: UUID | None = None,
    customer_id: UUID | None = None,
    vendor_id: UUID | None = None,
    licence_type_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TradeLicenceResponse]]:
    """List the register, filtered by holder or type, the firm's own first.

    Not paged: a firm holds a handful of its own and one or two per customer
    or vendor, and every caller asks for one holder or the whole expiry list.
    """
    return ApiResponse(
        data=TradeLicenceService(db).list_licences(
            firm_id=scope.firm_id,
            holder_type=holder_type,
            branch_id=branch_id,
            customer_id=customer_id,
            vendor_id=vendor_id,
            licence_type_id=licence_type_id,
        )
    )


@router.post(
    "",
    response_model=ApiResponse[TradeLicenceResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_licence(
    data: TradeLicenceWrite,
    scope: LicenceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TradeLicenceResponse]:
    """Record one licence of the firm, a customer or a vendor."""
    service = TradeLicenceService(db)
    row = service.create_licence(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.responses([row])[0])


@router.get("/{licence_id}", response_model=ApiResponse[TradeLicenceResponse])
def get_licence(
    licence_id: UUID,
    scope: LicenceViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[TradeLicenceResponse]:
    """Return one licence."""
    service = TradeLicenceService(db)
    row = service.get_licence(licence_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.put("/{licence_id}", response_model=ApiResponse[TradeLicenceResponse])
def update_licence(
    licence_id: UUID,
    data: TradeLicenceWrite,
    scope: LicenceManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[TradeLicenceResponse]:
    """Replace one licence -- a renewal or a correction."""
    service = TradeLicenceService(db)
    assert_version(
        service.get_licence(licence_id, firm_id=scope.firm_id).version,
        expected_version,
    )
    row = service.update_licence(
        licence_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.delete("/{licence_id}", response_model=ApiResponse[dict[str, str]])
def delete_licence(
    licence_id: UUID,
    scope: LicenceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Withdraw a licence recorded by mistake."""
    TradeLicenceService(db).delete_licence(
        licence_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"status": "deleted"})
