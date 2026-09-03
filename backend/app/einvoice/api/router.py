"""Firm-scoped REST endpoints for e-invoice registration and e-way bills.

Literal paths are declared **above** `/{invoice_id}`, because FastAPI matches
in declaration order and nine endpoints in eight routers were unreachable
until 2026-08-22 for exactly that reason.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.einvoice.models import EInvoiceRegistration, EWayBill
from app.einvoice.services import EInvoiceService

router = APIRouter(
    prefix="/api/v1/einvoice",
    tags=["E-Invoice"],
    responses=STANDARD_ERROR_RESPONSES,
)

EInvoiceViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("EINVOICE_VIEW")]
#: Registering files a document with the tax authority. Even in sandbox it is
#: the action that will file one the day a firm switches, so it carries its own
#: code rather than riding on a general sales permission.
EInvoiceManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("EINVOICE_MANAGE")
]


class RegistrationResponse(BaseModel):
    """What the portal knows about one invoice."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sales_invoice_id: UUID
    #: SANDBOX or LIVE. Never absent, so a rehearsal can never be read as a
    #: filing.
    mode: str
    status: str
    irn: str | None
    acknowledgement_number: str | None
    acknowledged_at: datetime | None
    signed_qr_code: str | None
    error_code: str | None
    error_message: str | None
    attempts: int
    cancellation_reason: str | None


class EWayBillResponse(BaseModel):
    """What the portal knows about one consignment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sales_invoice_id: UUID
    mode: str
    status: str
    eway_bill_number: str | None
    valid_until: date | None
    distance_km: Decimal
    transport_mode: str
    transporter_id: str | None
    transporter_name: str | None
    vehicle_number: str | None
    error_code: str | None
    error_message: str | None


class CancellationRequest(BaseModel):
    """Why a registration or bill is being withdrawn."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=200)


class EWayBillRequest(BaseModel):
    """Raise an e-way bill for the goods an invoice covers."""

    model_config = ConfigDict(extra="forbid")

    distance_km: Decimal = Field(gt=0, max_digits=9, decimal_places=2)
    transport_mode: str = Field(default="ROAD", max_length=20)
    transporter_id: str | None = Field(default=None, max_length=40)
    transporter_name: str | None = Field(default=None, max_length=200)
    #: Required for road, which the service enforces: goods on a lorry with no
    #: registration on the bill is a consignment nobody can check.
    vehicle_number: str | None = Field(default=None, max_length=20)


@router.get("/registrations", response_model=PaginatedResponse[RegistrationResponse])
def list_registrations(
    scope: EInvoiceViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    registration_status: Annotated[str | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[RegistrationResponse]:
    """Return a page of e-invoice registrations."""
    rows, total = EInvoiceService(db).list_registrations(
        firm_scope=scope.firm_id,
        page=page,
        page_size=page_size,
        status=registration_status,
    )
    return PaginatedResponse(
        data=[RegistrationResponse.model_validate(row) for row in rows],
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get(
    "/invoices/{invoice_id}", response_model=ApiResponse[RegistrationResponse | None]
)
def get_registration(
    invoice_id: UUID,
    scope: EInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RegistrationResponse | None]:
    """Return one invoice's registration, or nothing where it has none."""
    row: EInvoiceRegistration | None = EInvoiceService(db).registration_for(
        invoice_id, firm_scope=scope.firm_id
    )
    return ApiResponse(
        data=None if row is None else RegistrationResponse.model_validate(row)
    )


@router.post(
    "/invoices/{invoice_id}/register",
    response_model=ApiResponse[RegistrationResponse],
)
def register_invoice(
    invoice_id: UUID,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RegistrationResponse]:
    """Register one approved invoice with the portal."""
    service = EInvoiceService(db)
    row = service.register(
        invoice_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=RegistrationResponse.model_validate(row),
        message=(
            f"Registered in {row.mode} mode."
            if row.status == "REGISTERED"
            else "The portal refused this invoice."
        ),
    )


@router.post(
    "/invoices/{invoice_id}/cancel", response_model=ApiResponse[RegistrationResponse]
)
def cancel_registration(
    invoice_id: UUID,
    payload: CancellationRequest,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RegistrationResponse]:
    """Withdraw a registration, inside the window the authority allows."""
    service = EInvoiceService(db)
    row = service.cancel(
        invoice_id,
        reason=payload.reason,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=RegistrationResponse.model_validate(row),
        message="Registration withdrawn.",
    )


@router.get(
    "/invoices/{invoice_id}/eway-bill",
    response_model=ApiResponse[EWayBillResponse | None],
)
def get_eway_bill(
    invoice_id: UUID,
    scope: EInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EWayBillResponse | None]:
    """Return one invoice's e-way bill, or nothing where it has none."""
    row: EWayBill | None = EInvoiceService(db).eway_bill_for(
        invoice_id, firm_scope=scope.firm_id
    )
    return ApiResponse(
        data=None if row is None else EWayBillResponse.model_validate(row)
    )


@router.post(
    "/invoices/{invoice_id}/eway-bill",
    response_model=ApiResponse[EWayBillResponse],
)
def generate_eway_bill(
    invoice_id: UUID,
    payload: EWayBillRequest,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EWayBillResponse]:
    """Raise an e-way bill for the goods a registered invoice covers."""
    service = EInvoiceService(db)
    row = service.generate_eway_bill(
        invoice_id,
        distance_km=payload.distance_km,
        transport_mode=payload.transport_mode,
        transporter_id=payload.transporter_id,
        transporter_name=payload.transporter_name,
        vehicle_number=payload.vehicle_number,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=EWayBillResponse.model_validate(row),
        message=(
            f"E-way bill raised in {row.mode} mode."
            if row.status == "GENERATED"
            else "The portal refused this consignment."
        ),
    )


@router.post(
    "/invoices/{invoice_id}/eway-bill/cancel",
    response_model=ApiResponse[EWayBillResponse],
)
def cancel_eway_bill(
    invoice_id: UUID,
    payload: CancellationRequest,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EWayBillResponse]:
    """Withdraw an e-way bill."""
    service = EInvoiceService(db)
    row = service.cancel_eway_bill(
        invoice_id,
        reason=payload.reason,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=EWayBillResponse.model_validate(row),
        message="E-way bill withdrawn.",
    )
