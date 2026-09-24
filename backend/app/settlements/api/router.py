"""Firm-scoped REST endpoints for receipts and payments.

One router serves both directions. They differ only in which service they
build, so a second copy would be a second place for the same rules to drift.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.constants.core import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.settlements.models import Settlement
from app.settlements.schemas import (
    OutstandingInvoiceRecord,
    SettlementAllocateRequest,
    SettlementAllocationResponse,
    SettlementCreate,
    SettlementPartyRecord,
    SettlementResponse,
    SettlementReverseRequest,
    SupplierCreditApplyRequest,
    SupplierCreditRecord,
)
from app.settlements.services import (
    PaymentService,
    ReceiptService,
    RefundService,
    SettlementService,
)
from app.settlements.services.supplier_credits import (
    SupplierCredit,
    apply_supplier_credit,
    supplier_credits,
)

receipts_router = APIRouter(
    prefix="/api/v1/receipts",
    tags=["Receipts"],
    responses=STANDARD_ERROR_RESPONSES,
)
refunds_router = APIRouter(
    prefix="/api/v1/refunds",
    tags=["Refunds"],
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
# A refund is money leaving the firm, so it takes the money-out grants rather
# than the receipt ones: the person trusted to collect is not automatically the
# person trusted to hand money back.
RefundViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PAYMENT_VIEW")]
RefundCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PAYMENT_CREATE")
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
                # Rows older than the column carry nothing; the settlement's
                # date is what the backfill wrote for them.
                allocated_on=allocation.allocated_on or row.settlement_date,
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
        sales_order_id=row.sales_order_id,
        sales_order_number=service.order_number_of(row),
        method=row.method,
        ledger_account_id=row.ledger_account_id,
        ledger_account_name=service.ledger_account_name(row.ledger_account_id),
        instrument_reference=row.instrument_reference,
        narration=row.narration,
        status=row.status,
        journal_entry_id=row.journal_entry_id,
        reversal_journal_entry_id=row.reversal_journal_entry_id,
        reversed_at=row.reversed_at,
        reversal_reason=row.reversal_reason,
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


def _parties(
    service: SettlementService,
    *,
    firm_id: UUID,
    search: str,
    page: int,
    page_size: int,
) -> ApiResponse[list[SettlementPartyRecord]]:
    """Answer one direction's party picker.

    See `SettlementPartyRecord` for why the money screens do not read the
    customer or vendor master for this. **Declared above `/{id}` in every
    router below**: FastAPI matches in declaration order, and under it
    "parties" is read as an id and answered 422 -- which is how nine routes in
    eight routers spent months unreachable.
    """
    return ApiResponse(
        data=[
            SettlementPartyRecord(id=party_id, code=code, name=name)
            for party_id, code, name in service.parties(
                firm_id=firm_id, search=search, page=page, page_size=page_size
            )
        ]
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


@receipts_router.get(
    "/parties", response_model=ApiResponse[list[SettlementPartyRecord]]
)
def receipt_parties(
    scope: ReceiptViewScope,
    search: str = Query(default=""),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SettlementPartyRecord]]:
    """List the customers money can be received from."""
    return _parties(
        ReceiptService(db),
        firm_id=scope.firm_id,
        search=search,
        page=page,
        page_size=page_size,
    )


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


@receipts_router.post(
    "/{receipt_id}/reverse", response_model=ApiResponse[SettlementResponse]
)
def reverse_receipt(
    receipt_id: UUID,
    payload: SettlementReverseRequest,
    scope: ReceiptCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Take a receipt back, in the ledger and on the customer's account."""
    service = ReceiptService(db)
    row = service.reverse(
        receipt_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_to_response(service, row), message="Receipt reversed.")


@receipts_router.post(
    "/{receipt_id}/allocate", response_model=ApiResponse[SettlementResponse]
)
def allocate_receipt(
    receipt_id: UUID,
    payload: SettlementAllocateRequest,
    scope: ReceiptCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Set money already received against an invoice raised since.

    The missing half of an advance: a deposit taken before the bill existed
    could sit on the customer's account with no way to say which bill it
    settled. Nothing is posted to the general ledger -- the money already
    moved when the receipt was recorded, and this decides which invoice the
    receivable credit belongs to.
    """
    service = ReceiptService(db)
    row = service.allocate(
        receipt_id,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.refresh(row)
    return ApiResponse(
        data=_to_response(service, row),
        message=f"{row.settlement_number} applied.",
    )


@refunds_router.get("", response_model=PaginatedResponse[SettlementResponse])
def list_refunds(
    scope: RefundViewScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default=""),
    customer_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SettlementResponse]:
    """List money handed back to customers."""
    return _list(
        RefundService(db),
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        party_id=customer_id,
    )


@refunds_router.post(
    "",
    response_model=ApiResponse[SettlementResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_refund(
    payload: SettlementCreate,
    scope: RefundCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Hand money back to a customer and post it to the ledger."""
    service = RefundService(db)
    row = service.create(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=_to_response(service, row), message="Refund recorded and posted."
    )


@refunds_router.get("/parties", response_model=ApiResponse[list[SettlementPartyRecord]])
def refund_parties(
    scope: RefundViewScope,
    search: str = Query(default=""),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SettlementPartyRecord]]:
    """List the customers money can be refunded to."""
    return _parties(
        RefundService(db),
        firm_id=scope.firm_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@refunds_router.get("/{refund_id}", response_model=ApiResponse[SettlementResponse])
def get_refund(
    refund_id: UUID,
    scope: RefundViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Return one refund."""
    service = RefundService(db)
    return ApiResponse(
        data=_to_response(service, service.get(refund_id, firm_id=scope.firm_id))
    )


@refunds_router.post(
    "/{refund_id}/reverse", response_model=ApiResponse[SettlementResponse]
)
def reverse_refund(
    refund_id: UUID,
    payload: SettlementReverseRequest,
    scope: RefundCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Take a refund back, in the ledger and on the customer's account.

    Receipts and payments have had this since the module was written and
    refunds did not, while the desktop offers Reverse on every settlement row
    whatever its direction -- so the button answered 405 on the one screen out
    of three. `SettlementService.reverse` was always inherited; only the route
    was missing, and the reversal of the customer's advance with it.
    """
    service = RefundService(db)
    row = service.reverse(
        refund_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_to_response(service, row), message="Refund reversed.")


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


@payments_router.get(
    "/parties", response_model=ApiResponse[list[SettlementPartyRecord]]
)
def payment_parties(
    scope: PaymentViewScope,
    search: str = Query(default=""),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SettlementPartyRecord]]:
    """List the vendors money can be paid to."""
    return _parties(
        PaymentService(db),
        firm_id=scope.firm_id,
        search=search,
        page=page,
        page_size=page_size,
    )


def _credit_record(credit: SupplierCredit) -> SupplierCreditRecord:
    """Build the response for one supplier credit."""
    return SupplierCreditRecord(
        purchase_return_id=credit.purchase_return_id,
        return_number=credit.return_number,
        return_date=credit.return_date,
        vendor_id=credit.vendor_id,
        credit_amount=credit.credit_amount,
        applied_amount=credit.applied_amount,
        available_amount=credit.available_amount,
        applied_to=credit.applied_to,
    )


@payments_router.get(
    "/supplier-credits", response_model=ApiResponse[list[SupplierCreditRecord]]
)
def vendor_supplier_credits(
    vendor_id: UUID,
    scope: PaymentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SupplierCreditRecord]]:
    """Return what the vendor owes the firm from returns, not yet set off.

    A purchase return raised from the goods receipt debits payables but names
    no bill, so it stands on the vendor's account as a credit until it is set
    against one (D-FIN-19). Only credits with something left are listed.
    """
    return ApiResponse(
        data=[
            _credit_record(credit)
            for credit in supplier_credits(
                db, firm_id=scope.firm_id, vendor_id=vendor_id
            )
            if credit.available_amount > 0
        ]
    )


@payments_router.post(
    "/supplier-credits/{return_id}/apply",
    response_model=ApiResponse[SupplierCreditRecord],
)
def apply_vendor_supplier_credit(
    return_id: UUID,
    payload: SupplierCreditApplyRequest,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierCreditRecord]:
    """Set a return's supplier credit against one of the vendor's bills.

    Nothing is posted: the return debited payables when it completed and the
    bill credited them when it was approved; this says which bill the debit
    belongs to, so the bill owes that much less.
    """
    credit = apply_supplier_credit(
        db,
        firm_id=scope.firm_id,
        purchase_return_id=return_id,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        actor_id=scope.actor_id,
    )
    db.commit()
    return ApiResponse(
        data=_credit_record(credit), message="Supplier credit applied to the bill."
    )


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


@payments_router.post(
    "/{payment_id}/reverse", response_model=ApiResponse[SettlementResponse]
)
def reverse_payment(
    payment_id: UUID,
    payload: SettlementReverseRequest,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Take a payment back, in the ledger."""
    service = PaymentService(db)
    row = service.reverse(
        payment_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_to_response(service, row), message="Payment reversed.")


@payments_router.post(
    "/{payment_id}/allocate", response_model=ApiResponse[SettlementResponse]
)
def allocate_payment(
    payment_id: UUID,
    payload: SettlementAllocateRequest,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SettlementResponse]:
    """Set money already paid against a bill that arrived since.

    A supplier advance is the mirror of a customer's deposit, and it had the
    same hole: a payment recorded with no allocation could never be set
    against a bill afterwards, so the supplier's account showed the bill owed
    in full beside cash they had already been sent (D-BUY-8). Nothing is
    posted to the ledger -- the money moved when the payment was recorded, and
    this decides which bill it clears.
    """
    service = PaymentService(db)
    row = service.allocate(
        payment_id,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    db.refresh(row)
    return ApiResponse(
        data=_to_response(service, row),
        message=f"{row.settlement_number} applied.",
    )
