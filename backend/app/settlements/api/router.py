"""Firm-scoped REST endpoints for receipts and payments.

One router serves both directions. They differ only in which service they
build, so a second copy would be a second place for the same rules to drift.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.settlements.models import Settlement
from app.settlements.schemas import (
    OutstandingInvoiceRecord,
    SettlementAllocationResponse,
    SettlementCreate,
    SettlementResponse,
)
from app.settlements.services import PaymentService, ReceiptService, SettlementService

receipts_router = APIRouter(
    prefix="/api/v1/receipts",
    tags=["Receipts"],
    responses=STANDARD_ERROR_RESPONSES,
)
payments_router = APIRouter(
    prefix="/api/v1/payments",
    tags=["Payments"],
    responses=STANDARD_ERROR_RESPONSES,
)

ReceiptViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("RECEIPT_VIEW")]
ReceiptCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("RECEIPT_CREATE")
]
PaymentViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PAYMENT_VIEW")]
PaymentCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PAYMENT_CREATE")
]


def _to_response(service: SettlementService, row: Settlement) -> SettlementResponse:
    """Build the response for one settlement, with its allocations."""
    party = service.party_of(row)
    allocations = service.allocations_for(row.id)
    summaries = service.invoice_summaries(allocations)
    allocation_rows: list[SettlementAllocationResponse] = []
    for allocation in allocations:
        invoice_id = allocation.sales_invoice_id or allocation.purchase_invoice_id
        if invoice_id is None:  # pragma: no cover - one side is always set
            continue
        number, invoice_date, total = summaries[invoice_id]
        allocation_rows.append(
            SettlementAllocationResponse(
                id=allocation.id,
                invoice_id=invoice_id,
                invoice_number=number,
                invoice_date=invoice_date,
                invoice_total=total,
                amount=allocation.amount,
            )
        )
    return SettlementResponse(
        id=row.id,
        direction=row.direction,
        party_id=party.id,
        party_code=party.code,
        party_name=party.name,
        settlement_number=row.settlement_number,
        settlement_date=row.settlement_date,
        amount=row.amount,
        allocated_amount=row.allocated_amount,
        unallocated_amount=row.unallocated_amount,
        method=row.method,
        ledger_account_id=row.ledger_account_id,
        ledger_account_name=service.ledger_account_name(row.ledger_account_id),
        instrument_reference=row.instrument_reference,
        narration=row.narration,
        status=row.status,
        journal_entry_id=row.journal_entry_id,
        allocations=allocation_rows,
        version=row.version,
    )


def _list(
    service: SettlementService,
    *,
    firm_id: UUID,
    page: int,
    page_size: int,
    search: str,
    party_id: UUID | None,
) -> PaginatedResponse[SettlementResponse]:
    """Return one page of settlements."""
    rows, total = service.list_settlements(
        firm_id=firm_id,
        page=page,
        page_size=page_size,
        search=search,
        party_id=party_id,
    )
    return PaginatedResponse(
        data=[_to_response(service, row) for row in rows],
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@receipts_router.get("", response_model=PaginatedResponse[SettlementResponse])
def list_receipts(
    scope: ReceiptViewScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default=""),
    customer_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SettlementResponse]:
    """List money received from customers."""
    return _list(
        ReceiptService(db),
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        party_id=customer_id,
    )


@receipts_router.get(
    "/outstanding", response_model=ApiResponse[list[OutstandingInvoiceRecord]]
)
def customer_outstanding_invoices(
    customer_id: UUID,
    scope: ReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[OutstandingInvoiceRecord]]:
    """Return the customer's invoices that still owe something."""
    rows = ReceiptService(db).outstanding_invoices(
        firm_id=scope.firm_id, party_id=customer_id
    )
    return ApiResponse(data=rows)


@receipts_router.get("/{receipt_id}", response_model=ApiResponse[SettlementResponse])
def get_receipt(
    receipt_id: UUID,
    scope: ReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Return one receipt."""
    service = ReceiptService(db)
    return ApiResponse(
        data=_to_response(service, service.get(receipt_id, firm_id=scope.firm_id))
    )


@receipts_router.post(
    "",
    response_model=ApiResponse[SettlementResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_receipt(
    payload: SettlementCreate,
    scope: ReceiptCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Record money received from a customer and post it to the ledger."""
    service = ReceiptService(db)
    row = service.create(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=_to_response(service, row), message="Receipt recorded and posted."
    )


@payments_router.get("", response_model=PaginatedResponse[SettlementResponse])
def list_payments(
    scope: PaymentViewScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default=""),
    vendor_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SettlementResponse]:
    """List money paid to vendors."""
    return _list(
        PaymentService(db),
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        party_id=vendor_id,
    )


@payments_router.get(
    "/outstanding", response_model=ApiResponse[list[OutstandingInvoiceRecord]]
)
def vendor_outstanding_invoices(
    vendor_id: UUID,
    scope: PaymentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[OutstandingInvoiceRecord]]:
    """Return the vendor's invoices that still owe something."""
    rows = PaymentService(db).outstanding_invoices(
        firm_id=scope.firm_id, party_id=vendor_id
    )
    return ApiResponse(data=rows)


@payments_router.get("/{payment_id}", response_model=ApiResponse[SettlementResponse])
def get_payment(
    payment_id: UUID,
    scope: PaymentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Return one payment."""
    service = PaymentService(db)
    return ApiResponse(
        data=_to_response(service, service.get(payment_id, firm_id=scope.firm_id))
    )


@payments_router.post(
    "",
    response_model=ApiResponse[SettlementResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_payment(
    payload: SettlementCreate,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Record money paid to a vendor and post it to the ledger."""
    service = PaymentService(db)
    row = service.create(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=_to_response(service, row), message="Payment recorded and posted."
    )
