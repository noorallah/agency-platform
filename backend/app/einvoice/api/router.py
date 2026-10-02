"""Firm-scoped REST endpoints for e-invoice registration and e-way bills.

Literal paths are declared **above** `/{invoice_id}`, because FastAPI matches
in declaration order and nine endpoints in eight routers were unreachable
until 2026-08-22 for exactly that reason.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ResourceNotFoundError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.einvoice.models import EInvoiceRegistration, EWayBill
from app.einvoice.services import EInvoiceService
from app.einvoice.services.eway_bills import EWayBillService
from app.einvoice.services.note_registration import (
    CREDIT_NOTE,
    DEBIT_NOTE,
    SALES_RETURN,
    NoteRegistrationService,
)
from app.einvoice.services.offline import OfflineEInvoiceService
from app.einvoice.services.reporting_window import DUE_SOON_DAYS, last_day, pending
from app.einvoice.services.settings import (
    AVAILABLE_PROVIDERS,
    EInvoiceSettingsService,
)

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
    sales_invoice_id: UUID | None
    #: A credit note or a debit note to a customer (77 row 4), else null.
    credit_note_id: UUID | None = None
    customer_debit_note_id: UUID | None = None
    #: A sales return's credit note (D-TAX-2), else null.
    sales_return_id: UUID | None = None
    #: SALES_INVOICE, CREDIT_NOTE, DEBIT_NOTE or SALES_RETURN.
    document_type: str = "SALES_INVOICE"
    #: What the grid needs to tell one registration from another: an id
    #: alone left the screen a list of references nobody could match to a
    #: bill (mapping section 12, 2026-09-13).
    invoice_number: str = ""
    customer_name: str = ""
    #: SANDBOX or LIVE. Never absent, so a rehearsal can never be read as a
    #: filing.
    mode: str
    #: The route it took (A42): SANDBOX, OFFLINE, NIC_DIRECT or GSP.
    provider: str | None = None
    status: str
    irn: str | None
    acknowledgement_number: str | None
    acknowledged_at: datetime | None
    signed_qr_code: str | None
    error_code: str | None
    error_message: str | None
    attempts: int
    cancellation_reason: str | None


def _labelled(
    db: Session, row: EInvoiceRegistration, *, firm_id: UUID
) -> RegistrationResponse:
    """Return one registration with the bill number and buyer filled in.

    The list filled them and every single-row answer left them blank, so the
    screen showed a registration it had just made as a nameless row
    (D-CMP-13).
    """
    kind, number, name = EInvoiceService(db).document_labels(
        firm_scope=firm_id, rows=[row]
    )[row.id]
    return RegistrationResponse.model_validate(row).model_copy(
        update={"document_type": kind, "invoice_number": number, "customer_name": name}
    )


class EWayBillResponse(BaseModel):
    """What the portal knows about one consignment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sales_invoice_id: UUID | None
    #: The challan it travels on, where no invoice bills the goods (77.9).
    delivery_note_id: UUID | None = None
    #: Raised by hand on the portal and its number recorded here (A42).
    entered_by_hand: bool = False
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

    #: Every field may be left blank, and a blank is filled from the delivery
    #: note the invoice billed -- its distance, mode, transporter, vehicle and
    #: LR (backlog 67 row 5). What is still missing after that is refused by
    #: name: a distance always, a vehicle for road.
    distance_km: Decimal | None = Field(
        default=None, gt=0, max_digits=9, decimal_places=2
    )
    transport_mode: str | None = Field(default=None, max_length=20)
    transporter_id: str | None = Field(default=None, max_length=40)
    transporter_name: str | None = Field(default=None, max_length=200)
    #: Required for road, which the service enforces: goods on a lorry with no
    #: registration on the bill is a consignment nobody can check.
    vehicle_number: str | None = Field(default=None, max_length=20)


#: Choosing how the firm files is a tax setting, held by whoever holds the
#: firm's other GST settings.
EInvoiceSettingsScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TAX_MANAGE_SETTINGS")
]


class EInvoiceSettingsResponse(BaseModel):
    """The firm's e-invoice route, and the routes it may choose (A42)."""

    provider: str
    available: list[str]


class EInvoiceSettingsWrite(BaseModel):
    """Change the firm's e-invoice route."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=20)


class OfflineExportRequest(BaseModel):
    """The approved invoices to export for the portal's bulk upload."""

    model_config = ConfigDict(extra="forbid")

    invoice_ids: list[UUID] = Field(default_factory=list, max_length=500)
    #: Notes go with the invoices in one upload (77 row 4).
    credit_note_ids: list[UUID] = Field(default_factory=list, max_length=500)
    debit_note_ids: list[UUID] = Field(default_factory=list, max_length=500)
    #: A sales return's credit note (D-TAX-2).
    sales_return_ids: list[UUID] = Field(default_factory=list, max_length=500)


class OfflineImportResponse(BaseModel):
    """What importing the portal's result did, by invoice number."""

    registered: list[str]
    failed: list[str]
    unmatched: list[str]
    already: list[str]


@router.get("/settings", response_model=ApiResponse[EInvoiceSettingsResponse])
def get_einvoice_settings(
    scope: EInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EInvoiceSettingsResponse]:
    """Report how the firm registers e-invoices (decision A42)."""
    return ApiResponse(
        data=EInvoiceSettingsResponse(
            provider=EInvoiceSettingsService(db).provider(scope.firm_id),
            available=list(AVAILABLE_PROVIDERS),
        )
    )


@router.put("/settings", response_model=ApiResponse[EInvoiceSettingsResponse])
def update_einvoice_settings(
    data: EInvoiceSettingsWrite,
    scope: EInvoiceSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EInvoiceSettingsResponse]:
    """Change how the firm registers e-invoices."""
    provider = EInvoiceSettingsService(db).update(
        scope.firm_id, data.provider, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=EInvoiceSettingsResponse(
            provider=provider, available=list(AVAILABLE_PROVIDERS)
        )
    )


@router.post("/offline/export")
def export_offline(
    data: OfflineExportRequest,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Export approved invoices as the portal's bulk-upload JSON (A42).

    Each becomes a registration waiting for its IRN; upload the file on the
    e-invoice portal and import the result it gives back.
    """
    payloads = OfflineEInvoiceService(db).export(
        data.invoice_ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        credit_note_ids=data.credit_note_ids,
        debit_note_ids=data.debit_note_ids,
        sales_return_ids=data.sales_return_ids,
    )
    stamp = utc_now().strftime("%Y%m%d-%H%M")
    return Response(
        content=json.dumps(payloads, indent=2, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="einvoice-{stamp}.json"'
        },
    )


@router.post("/offline/import", response_model=ApiResponse[OfflineImportResponse])
async def import_offline(
    scope: EInvoiceManageScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
) -> ApiResponse[OfflineImportResponse]:
    """Import the portal's result file: IRN, acknowledgement and QR per invoice."""
    name = (file.filename or "").lower()
    file_format = (
        "json" if name.endswith(".json") else "csv" if name.endswith(".csv") else "xlsx"
    )
    report = OfflineEInvoiceService(db).import_result(
        await file.read(),
        file_format,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(
        data=OfflineImportResponse(
            registered=report.registered,
            failed=report.failed,
            unmatched=report.unmatched,
            already=report.already,
        ),
        message=(
            f"{len(report.registered)} registered, {len(report.failed)} refused, "
            f"{len(report.unmatched)} not matched."
        ),
    )


class EWayBillDueItem(BaseModel):
    """A consignment above the firm's limit with no live e-way bill."""

    document_type: str
    document_id: UUID
    number: str
    on: date
    value: Decimal


class EWayBillDueResponse(BaseModel):
    """The firm's limit and what is above it without an e-way bill (77.10)."""

    limit: Decimal
    items: list[EWayBillDueItem]


class PendingRegistrationItem(BaseModel):
    """A B2B document the firm must register and has not (77 row 7)."""

    document_type: str
    document_id: UUID
    number: str
    on: date
    customer_name: str
    amount: Decimal
    #: PENDING (exported, awaiting the portal's file), FAILED, CANCELLED, or
    #: None when nobody has tried.
    registration_status: str | None
    registration_error: str | None
    #: The last day the IRP accepts it; None while the 30-day limit does not
    #: bind the firm.
    last_day: date | None
    days_left: int | None
    #: OPEN, DUE_SOON (within the warning days of the last day) or LATE.
    state: str


class PendingRegistrationResponse(BaseModel):
    """Every document still to be registered, oldest first."""

    thirty_day_rule_applies: bool
    due_soon_days: int
    items: list[PendingRegistrationItem]


class EWayBillRecordRequest(BaseModel):
    """An e-way bill raised by hand on the portal, for one document (A42)."""

    model_config = ConfigDict(extra="forbid")

    sales_invoice_id: UUID | None = None
    delivery_note_id: UUID | None = None
    eway_bill_number: str = Field(min_length=12, max_length=20)
    valid_until: date | None = None
    distance_km: Decimal | None = Field(
        default=None, gt=0, max_digits=9, decimal_places=2
    )
    vehicle_number: str | None = Field(default=None, max_length=20)


def _eway_service(db: Session, firm_id: UUID) -> EWayBillService:
    """Return the e-way bill service on the firm's route."""
    base = EInvoiceService.for_firm(db, firm_id)
    return EWayBillService(db, mode=base.mode, provider=base.provider)


@router.get("/eway-bills/due", response_model=ApiResponse[EWayBillDueResponse])
def eway_bills_due(
    scope: EInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EWayBillDueResponse]:
    """List consignments above the firm's limit with no e-way bill (77.10)."""
    service = _eway_service(db, scope.firm_id)
    return ApiResponse(
        data=EWayBillDueResponse(
            limit=service.limit(scope.firm_id),
            items=[
                EWayBillDueItem(
                    document_type=item.document_type,
                    document_id=item.document_id,
                    number=item.number,
                    on=item.on,
                    value=item.value,
                )
                for item in service.due(scope.firm_id)
            ],
        )
    )


@router.get("/pending", response_model=ApiResponse[PendingRegistrationResponse])
def pending_registrations(
    scope: EInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PendingRegistrationResponse]:
    """List the B2B documents still to be registered, with days left (77.7).

    Invoices, credit notes and debit notes past the firm's e-invoicing date
    with no live IRN. Where the 30-day limit binds the firm each carries its
    last day and whether it is due soon or already late.
    """
    items = pending(db, scope.firm_id)
    today = utc_now().date()
    return ApiResponse(
        data=PendingRegistrationResponse(
            thirty_day_rule_applies=last_day(
                db, firm_scope=scope.firm_id, on=today, today=today
            )
            is not None,
            due_soon_days=DUE_SOON_DAYS,
            items=[
                PendingRegistrationItem(
                    document_type=item.document_type,
                    document_id=item.document_id,
                    number=item.number,
                    on=item.on,
                    customer_name=item.customer_name,
                    amount=Decimal(str(item.amount or 0)),
                    registration_status=item.registration_status,
                    registration_error=item.registration_error,
                    last_day=item.last_day,
                    days_left=item.days_left,
                    state=item.state,
                )
                for item in items
            ],
        )
    )


@router.post("/eway-bills/record", response_model=ApiResponse[EWayBillResponse])
def record_eway_bill(
    payload: EWayBillRecordRequest,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EWayBillResponse]:
    """Record an e-way bill raised by hand on the portal (A42)."""
    row = _eway_service(db, scope.firm_id).record(
        invoice_id=payload.sales_invoice_id,
        note_id=payload.delivery_note_id,
        eway_bill_number=payload.eway_bill_number,
        valid_until=payload.valid_until,
        distance_km=payload.distance_km,
        vehicle_number=payload.vehicle_number,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=EWayBillResponse.model_validate(row),
        message=f"E-way bill {row.eway_bill_number} recorded.",
    )


@router.get(
    "/delivery-notes/{note_id}/eway-bill",
    response_model=ApiResponse[EWayBillResponse | None],
)
def get_note_eway_bill(
    note_id: UUID,
    scope: EInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EWayBillResponse | None]:
    """Return a delivery note's e-way bill, or nothing."""
    row = _eway_service(db, scope.firm_id).for_note(note_id, firm_scope=scope.firm_id)
    return ApiResponse(
        data=None if row is None else EWayBillResponse.model_validate(row)
    )


@router.post(
    "/delivery-notes/{note_id}/eway-bill",
    response_model=ApiResponse[EWayBillResponse],
)
def generate_note_eway_bill(
    note_id: UUID,
    payload: EWayBillRequest,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EWayBillResponse]:
    """Raise an e-way bill for a delivery note no invoice bills (77 row 9)."""
    row = _eway_service(db, scope.firm_id).generate_for_note(
        note_id,
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
    "/delivery-notes/{note_id}/eway-bill/cancel",
    response_model=ApiResponse[EWayBillResponse],
)
def cancel_note_eway_bill(
    note_id: UUID,
    payload: CancellationRequest,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EWayBillResponse]:
    """Withdraw a delivery note's e-way bill."""
    row = _eway_service(db, scope.firm_id).cancel_for_note(
        note_id,
        reason=payload.reason,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=EWayBillResponse.model_validate(row), message="E-way bill withdrawn."
    )


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
    labels = EInvoiceService(db).document_labels(firm_scope=scope.firm_id, rows=rows)
    return PaginatedResponse(
        data=[
            RegistrationResponse.model_validate(row).model_copy(
                update={
                    "document_type": labels[row.id][0],
                    "invoice_number": labels[row.id][1],
                    "customer_name": labels[row.id][2],
                }
            )
            for row in rows
        ],
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
        data=None if row is None else _labelled(db, row, firm_id=scope.firm_id)
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
    service = EInvoiceService.for_firm(db, scope.firm_id)
    row = service.register(
        invoice_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=_labelled(db, row, firm_id=scope.firm_id),
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
    service = EInvoiceService.for_firm(db, scope.firm_id)
    row = service.cancel(
        invoice_id,
        reason=payload.reason,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=_labelled(db, row, firm_id=scope.firm_id),
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
    service = EInvoiceService.for_firm(db, scope.firm_id)
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
    service = EInvoiceService.for_firm(db, scope.firm_id)
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


# Declared last: the first path segment is a parameter, and FastAPI matches in
# declaration order, so declared earlier these would answer the invoice routes.
_NOTE_KINDS = {
    "credit-notes": CREDIT_NOTE,
    "debit-notes": DEBIT_NOTE,
    # A sales return's credit note (D-TAX-2).
    "sales-returns": SALES_RETURN,
}


def _note_kind(segment: str) -> str:
    """Return the note kind a path segment names, or refuse it."""
    kind = _NOTE_KINDS.get(segment)
    if kind is None:
        raise ResourceNotFoundError(
            "Choose credit-notes, debit-notes or sales-returns."
        )
    return kind


@router.get(
    "/{notes}/{note_id}/registration",
    response_model=ApiResponse[RegistrationResponse | None],
)
def get_note_registration(
    notes: str,
    note_id: UUID,
    scope: EInvoiceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RegistrationResponse | None]:
    """Return a credit or debit note's registration, or nothing (77 row 4)."""
    service = NoteRegistrationService(
        db, base=EInvoiceService.for_firm(db, scope.firm_id)
    )
    row = service.registration_for(_note_kind(notes), note_id, firm_scope=scope.firm_id)
    return ApiResponse(
        data=None if row is None else _labelled(db, row, firm_id=scope.firm_id)
    )


@router.post(
    "/{notes}/{note_id}/register", response_model=ApiResponse[RegistrationResponse]
)
def register_note(
    notes: str,
    note_id: UUID,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RegistrationResponse]:
    """Register an approved credit or debit note with the portal (77 row 4)."""
    service = NoteRegistrationService(
        db, base=EInvoiceService.for_firm(db, scope.firm_id)
    )
    row = service.register(
        _note_kind(notes), note_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=_labelled(db, row, firm_id=scope.firm_id),
        message=(
            f"Registered in {row.mode} mode."
            if row.status == "REGISTERED"
            else "The portal refused this note."
        ),
    )


@router.post(
    "/{notes}/{note_id}/cancel", response_model=ApiResponse[RegistrationResponse]
)
def cancel_note_registration(
    notes: str,
    note_id: UUID,
    payload: CancellationRequest,
    scope: EInvoiceManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RegistrationResponse]:
    """Withdraw a note's registration within 24 hours."""
    service = NoteRegistrationService(
        db, base=EInvoiceService.for_firm(db, scope.firm_id)
    )
    row = service.cancel(
        _note_kind(notes),
        note_id,
        reason=payload.reason,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=_labelled(db, row, firm_id=scope.firm_id),
        message="Registration withdrawn.",
    )
