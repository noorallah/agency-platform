"""Firm-scoped REST endpoints for receipts and payments.

One router serves both directions. They differ only in which service they
build, so a second copy would be a second place for the same rules to drift.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import set_etag
from app.core.constants.core import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.pagination.reports import ReportWindow
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.customers.schemas.statement import CashDiscountRow
from app.finance.schemas import LedgerAttachmentResponse, LedgerAttachmentsAdd
from app.finance.services.ledger_attachments import (
    PAYMENT_DIRECTIONS,
    RECEIPT_DIRECTIONS,
    LedgerAttachmentService,
)
from app.settlements.models import Settlement, SettlementMethod
from app.settlements.schemas import (
    CustomerCreditApplicationRecord,
    CustomerCreditApplyRequest,
    CustomerCreditRecord,
    CustomerCreditReverseRequest,
    OutstandingInvoiceRecord,
    SettlementAllocateRequest,
    SettlementAllocationResponse,
    SettlementCreate,
    SettlementPartyRecord,
    SettlementResponse,
    SettlementReverseRequest,
    SupplierCreditApplyRequest,
    SupplierCreditRecord,
    SupplierRefundCreate,
    SupplierRefundResponse,
    SupplierRefundReverse,
)
from app.settlements.schemas.cheque import ChequeLayoutResponse, ChequeLayoutUpdate
from app.settlements.services import (
    PaymentService,
    ReceiptService,
    RefundService,
    SettlementService,
)
from app.settlements.services.cheque_print import ChequeService
from app.settlements.services.collection_report import CollectionReportService
from app.settlements.services.customer_credits import (
    CustomerCredit,
    CustomerCreditUse,
    application_record,
    apply_customer_credit,
    customer_credits,
    reverse_customer_credit_application,
)
from app.settlements.services.receipt_print import ReceiptPrintService
from app.settlements.services.supplier_credits import (
    SupplierCredit,
    apply_supplier_credit,
    live_refunds,
    refund_supplier_credit,
    reverse_supplier_refund,
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
    return _to_responses(service, [row])[0]


def _to_responses(
    service: SettlementService, rows: Sequence[Settlement]
) -> list[SettlementResponse]:
    """Build the responses for a page of settlements, one read per table.

    Parties, allocations, the invoices they name, orders and ledger accounts
    are each read once for the whole page rather than once per settlement
    (backlog 56 C, step 3). The single-row builder is this with a list of one.
    """
    if not rows:
        return []
    parties = service.parties_of(rows)
    allocations = service.allocations_for_many([row.id for row in rows])
    summaries = service.invoice_summaries(
        [item for group in allocations.values() for item in group]
    )
    orders = service.order_numbers_of(rows)
    accounts = service.ledger_account_names([row.ledger_account_id for row in rows])
    responses: list[SettlementResponse] = []
    for row in rows:
        allocation_rows: list[SettlementAllocationResponse] = []
        for allocation in allocations.get(row.id, []):
            invoice_id = (
                allocation.sales_invoice_id
                or allocation.purchase_invoice_id
                or allocation.vendor_opening_bill_id
                or allocation.customer_opening_bill_id
            )
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
                    # Against a bill in another currency (PG-12).
                    currency_amount=allocation.currency_amount,
                    base_amount=allocation.base_amount,
                    exchange_difference=(
                        Decimal("0")
                        if allocation.base_amount is None
                        else allocation.amount - allocation.base_amount
                    ),
                )
            )
        exchange_difference = sum(
            (
                allocation.amount - allocation.base_amount
                for allocation in allocations.get(row.id, [])
                if allocation.base_amount is not None
            ),
            Decimal("0"),
        )
        party_id, party_code, party_name = parties[row.id]
        responses.append(
            SettlementResponse(
                id=row.id,
                direction=row.direction,
                party_id=party_id,
                party_code=party_code,
                party_name=party_name,
                settlement_number=row.settlement_number,
                settlement_date=row.settlement_date,
                amount=row.amount,
                tds_amount=row.tds_amount,
                tds_section=row.tds_section,
                tds_proposed_amount=row.tds_proposed_amount,
                rounding_amount=row.rounding_amount,
                bank_charges_amount=row.bank_charges_amount,
                discount_amount=row.discount_amount,
                cash_amount=(
                    row.amount
                    - row.tds_amount
                    - row.rounding_amount
                    - row.bank_charges_amount
                    - row.discount_amount
                ),
                allocated_amount=row.allocated_amount,
                unallocated_amount=row.unallocated_amount,
                currency_code=row.currency_code,
                exchange_rate=row.exchange_rate,
                currency_amount=row.currency_amount,
                exchange_difference=exchange_difference,
                sales_order_id=row.sales_order_id,
                sales_order_number=(
                    None
                    if row.sales_order_id is None
                    else orders.get(row.sales_order_id)
                ),
                method=row.method,
                payment_mode=row.payment_mode,
                ledger_account_id=row.ledger_account_id,
                ledger_account_name=accounts.get(row.ledger_account_id, ""),
                instrument_reference=row.instrument_reference,
                instrument_date=row.instrument_date,
                narration=row.narration,
                status=row.status,
                journal_entry_id=row.journal_entry_id,
                reversal_journal_entry_id=row.reversal_journal_entry_id,
                reversed_at=row.reversed_at,
                reversal_reason=row.reversal_reason,
                allocations=allocation_rows,
                version=row.version,
            )
        )
    return responses


def _list(
    service: SettlementService,
    *,
    firm_id: UUID,
    page: int,
    page_size: int,
    search: str,
    party_id: UUID | None,
    settlement_from: date | None = None,
    settlement_to: date | None = None,
) -> PaginatedResponse[SettlementResponse]:
    """Return one page of settlements."""
    rows, total = service.list_settlements(
        firm_id=firm_id,
        page=page,
        page_size=page_size,
        search=search,
        party_id=party_id,
        date_from=settlement_from,
        date_to=settlement_to,
    )
    return PaginatedResponse(
        data=_to_responses(service, rows),
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
    settlement_from: Annotated[date | None, Query()] = None,
    settlement_to: Annotated[date | None, Query()] = None,
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
        settlement_from=settlement_from,
        settlement_to=settlement_to,
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
    "/cash-discounts", response_model=ApiResponse[list[CashDiscountRow]]
)
def customer_cash_discounts(
    customer_id: UUID,
    on: date,
    scope: ReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CashDiscountRow]]:
    """Return the bills a receipt dated ``on`` may take a cash discount on.

    The customer's own terms, else the firm's (SEL-14); the discount goes on
    the receipt as the discount allowed deduction.
    """
    from app.customers.services.payment_terms import PaymentTermsService

    rows = PaymentTermsService(db).cash_discounts(
        customer_id, firm_id=scope.firm_id, on=on
    )
    return ApiResponse(
        data=[
            CashDiscountRow(
                invoice_id=row.invoice_id,
                invoice_number=row.invoice_number,
                invoice_date=row.invoice_date,
                outstanding=row.outstanding,
                percent=row.percent,
                discount_until=row.discount_until,
                amount=row.amount,
            )
            for row in rows
        ]
    )


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


def _credit_use_record(use: CustomerCreditUse) -> CustomerCreditApplicationRecord:
    """Build the response for one place a customer credit went."""
    return CustomerCreditApplicationRecord(
        id=use.id,
        target_type=use.target_type,
        target_id=use.target_id,
        target_number=use.target_number,
        amount=use.amount,
        applied_on=use.applied_on,
        version=use.version,
    )


def _customer_credit_record(credit: CustomerCredit) -> CustomerCreditRecord:
    """Build the response for one customer credit."""
    return CustomerCreditRecord(
        source_id=credit.source_id,
        source_type=credit.source_type,
        source_number=credit.source_number,
        source_date=credit.source_date,
        customer_id=credit.customer_id,
        credit_amount=credit.credit_amount,
        applied_amount=credit.applied_amount,
        refunded_amount=credit.refunded_amount,
        available_amount=credit.available_amount,
        held_amount=credit.held_amount,
        applied_to=credit.applied_to,
        applications=[_credit_use_record(use) for use in credit.uses],
    )


@receipts_router.get(
    "/customer-credits", response_model=ApiResponse[list[CustomerCreditRecord]]
)
def customer_unapplied_credits(
    party_id: UUID,
    scope: ReceiptViewScope,
    include_applied: Annotated[bool, Query()] = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerCreditRecord]]:
    """Return what the customer's returns and credit notes left on account.

    A return or credit note against a bill already paid has nothing left on
    that bill to come off, so the excess stands on the customer's account
    and belongs to no receipt (D-PRC-75). Only credits with something left
    are listed unless ``include_applied`` asks for the used ones too, which
    is where an application to take back is found.
    """
    return ApiResponse(
        data=[
            _customer_credit_record(credit)
            for credit in customer_credits(
                db, firm_id=scope.firm_id, customer_id=party_id
            )
            if include_applied or credit.available_amount > 0
        ]
    )


@receipts_router.post(
    "/customer-credits/{source_id}/apply",
    response_model=ApiResponse[CustomerCreditRecord],
)
def apply_customer_unapplied_credit(
    source_id: UUID,
    payload: CustomerCreditApplyRequest,
    scope: ReceiptCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerCreditRecord]:
    """Set a return's or credit note's credit against another bill.

    Nothing is posted: the return credited receivables when it completed and
    the bill debited them when it was approved; this says which bill the
    credit belongs to, so the bill owes that much less.
    """
    credit = apply_customer_credit(
        db,
        firm_id=scope.firm_id,
        source_id=source_id,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        applied_on=payload.applied_on,
        actor_id=scope.actor_id,
    )
    db.commit()
    return ApiResponse(
        data=_customer_credit_record(credit),
        message="Customer credit applied to the bill.",
    )


@receipts_router.post(
    "/customer-credits/applications/{application_id}/reverse",
    response_model=ApiResponse[CustomerCreditApplicationRecord],
)
def reverse_customer_credit(
    application_id: UUID,
    payload: CustomerCreditReverseRequest,
    scope: ReceiptCreateScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerCreditApplicationRecord]:
    """Take a credit back off the bill it was set against in error.

    The bill owes that much again and the credit is free again. Nothing is
    posted, as nothing was when it was applied.
    """
    row = reverse_customer_credit_application(
        db,
        firm_id=scope.firm_id,
        application_id=application_id,
        reason=payload.reason,
        actor_id=scope.actor_id,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=_credit_use_record(application_record(db, row)),
        message="Customer credit taken off the bill.",
    )


class CollectionRecord(BaseModel):
    """One day's, salesman's or mode's collections (backlog 67 row 9).

    ``collected`` is what receipts dated in the window settled; ``reversed``
    what reversals dated in it took back; ``net_collected`` the difference.
    """

    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    receipts: int
    collected: Decimal
    reversals: int
    reversed: Decimal
    net_collected: Decimal


#: A report opens to whoever may read receipts or holds REPORT_VIEW (D-RPT-4).
CollectionReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("RECEIPT_VIEW", "REPORT_VIEW")
]


def _collections(
    grouping: str, firm_id: UUID, db: Session, window: ReportWindow
) -> PaginatedResponse[CollectionRecord]:
    """Answer the collections by one grouping, one page."""
    rows = CollectionReportService(db).by(firm_id, grouping, window)
    return window.respond(
        [CollectionRecord.model_validate(row, from_attributes=True) for row in rows]
    )


@receipts_router.get(
    "/reports/collections-by-day",
    response_model=PaginatedResponse[CollectionRecord],
)
def collections_by_day(
    scope: CollectionReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CollectionRecord]:
    """Money received from customers each day, reversals netted (67 row 9)."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return _collections("day", scope.firm_id, db, window)


@receipts_router.get(
    "/reports/collections-by-salesman",
    response_model=PaginatedResponse[CollectionRecord],
)
def collections_by_salesman(
    scope: CollectionReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CollectionRecord]:
    """Money received by the salesman of the bill it cleared (67 row 9).

    What cleared no bill is *On account*.
    """
    window = ReportWindow(from_date, to_date, page, page_size)
    return _collections("salesman", scope.firm_id, db, window)


@receipts_router.get(
    "/reports/collections-by-mode",
    response_model=PaginatedResponse[CollectionRecord],
)
def collections_by_mode(
    scope: CollectionReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CollectionRecord]:
    """Money received by mode, cash or bank, reversals netted (67 row 9)."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return _collections("method", scope.firm_id, db, window)


@receipts_router.get("/{receipt_id}/print", response_class=StreamingResponse)
def print_receipt(
    receipt_id: UUID,
    scope: ReceiptViewScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Render one receipt as the voucher the customer keeps (MSG-4)."""
    pdf, filename = ReceiptPrintService(db).render(receipt_id, firm_scope=scope.firm_id)
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
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
    settlement_from: Annotated[date | None, Query()] = None,
    settlement_to: Annotated[date | None, Query()] = None,
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
        settlement_from=settlement_from,
        settlement_to=settlement_to,
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
    settlement_from: Annotated[date | None, Query()] = None,
    settlement_to: Annotated[date | None, Query()] = None,
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
        settlement_from=settlement_from,
        settlement_to=settlement_to,
    )


@payments_router.get(
    "/cheque-layouts", response_model=ApiResponse[list[ChequeLayoutResponse]]
)
def list_cheque_layouts(
    scope: PaymentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ChequeLayoutResponse]]:
    """Return the cheque layout saved for each bank account (ACC-12)."""
    rows = ChequeService(db).layouts(firm_id=scope.firm_id)
    return ApiResponse(data=[ChequeLayoutResponse.model_validate(r) for r in rows])


@payments_router.get(
    "/cheque-layouts/{ledger_account_id}",
    response_model=ApiResponse[ChequeLayoutResponse],
)
def get_cheque_layout(
    ledger_account_id: UUID,
    scope: PaymentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ChequeLayoutResponse]:
    """Return one bank account's layout; one never saved reads as zero."""
    row = ChequeService(db).layout_for(ledger_account_id, firm_id=scope.firm_id)
    return ApiResponse(data=ChequeLayoutResponse.model_validate(row))


@payments_router.put(
    "/cheque-layouts/{ledger_account_id}",
    response_model=ApiResponse[ChequeLayoutResponse],
)
def save_cheque_layout(
    ledger_account_id: UUID,
    payload: ChequeLayoutUpdate,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ChequeLayoutResponse]:
    """Store how far this bank's cheques print off the standard positions."""
    row = ChequeService(db).save_layout(
        ledger_account_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        offset_x_mm=payload.offset_x_mm,
        offset_y_mm=payload.offset_y_mm,
        print_ac_payee=payload.print_ac_payee,
    )
    return ApiResponse(
        data=ChequeLayoutResponse.model_validate(row),
        message="Cheque layout saved.",
    )


@payments_router.get(
    "/cheque-layouts/{ledger_account_id}/test", response_class=StreamingResponse
)
def cheque_test_print(
    ledger_account_id: UUID,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Draw a sample cheque with the account's offsets, to line the leaf up."""
    pdf = ChequeService(db).test_print(ledger_account_id, firm_id=scope.firm_id)
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="cheque-test.pdf"'},
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
        debit_note_id=credit.debit_note_id,
        source_id=credit.source_id,
        source_type=credit.source_type,
        return_number=credit.return_number,
        return_date=credit.return_date,
        vendor_id=credit.vendor_id,
        credit_amount=credit.credit_amount,
        applied_amount=credit.applied_amount,
        available_amount=credit.available_amount,
        applied_to=credit.applied_to,
        refunded_amount=credit.refunded_amount,
        outcome=credit.outcome,
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
        source_id=return_id,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        actor_id=scope.actor_id,
    )
    db.commit()
    return ApiResponse(
        data=_credit_record(credit), message="Supplier credit applied to the bill."
    )


@payments_router.get(
    "/supplier-credits/{return_id}/refunds",
    response_model=ApiResponse[list[SupplierRefundResponse]],
)
def list_supplier_refunds(
    return_id: UUID,
    scope: PaymentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SupplierRefundResponse]]:
    """Return the money a supplier paid back against one return."""
    return ApiResponse(
        data=[
            SupplierRefundResponse.model_validate(row)
            for row in live_refunds(db, firm_id=scope.firm_id, source_id=return_id)
        ]
    )


@payments_router.post(
    "/supplier-credits/{return_id}/refunds",
    response_model=ApiResponse[SupplierRefundResponse],
)
def record_supplier_refund(
    return_id: UUID,
    payload: SupplierRefundCreate,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierRefundResponse]:
    """Receive money a supplier paid back against a return (69 row 7)."""
    row = refund_supplier_credit(
        db,
        firm_id=scope.firm_id,
        source_id=return_id,
        amount=payload.amount,
        refunded_on=payload.refunded_on,
        method=SettlementMethod(payload.method.value),
        reference=payload.reference,
        remarks=payload.remarks,
        actor_id=scope.actor_id,
    )
    db.commit()
    return ApiResponse(
        data=SupplierRefundResponse.model_validate(row),
        message="Supplier refund received.",
    )


@payments_router.post(
    "/supplier-credits/refunds/{refund_id}/reverse",
    response_model=ApiResponse[SupplierRefundResponse],
)
def reverse_vendor_supplier_refund(
    refund_id: UUID,
    payload: SupplierRefundReverse,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierRefundResponse]:
    """Take back a supplier refund recorded in error."""
    row = reverse_supplier_refund(
        db,
        firm_id=scope.firm_id,
        refund_id=refund_id,
        reason=payload.reason,
        actor_id=scope.actor_id,
    )
    db.commit()
    return ApiResponse(
        data=SupplierRefundResponse.model_validate(row),
        message="Supplier refund reversed.",
    )


@payments_router.get("/{payment_id}/cheque", response_class=StreamingResponse)
def payment_cheque(
    payment_id: UUID,
    scope: PaymentCreateScope,
    payee: Annotated[str | None, Query(max_length=120)] = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Print a bank payment onto the bank's cheque leaf (ACC-12).

    Writing a cheque is paying, so it needs the right to record a payment,
    not only to read one. ``payee`` names someone other than the supplier.
    """
    pdf, filename = ChequeService(db).payment_cheque(
        payment_id, firm_id=scope.firm_id, payee=payee
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
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


@receipts_router.get(
    "/{settlement_id}/attachments",
    response_model=ApiResponse[list[LedgerAttachmentResponse]],
)
def list_receipt_attachments(
    settlement_id: UUID,
    scope: ReceiptViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LedgerAttachmentResponse]]:
    """List the files kept with one receipt (ACC-10)."""
    rows = LedgerAttachmentService(db).for_settlement(
        settlement_id, firm_id=scope.firm_id, directions=RECEIPT_DIRECTIONS
    )
    return ApiResponse(
        data=[LedgerAttachmentResponse.model_validate(row) for row in rows]
    )


@receipts_router.post(
    "/{settlement_id}/attachments",
    response_model=ApiResponse[list[LedgerAttachmentResponse]],
)
def attach_to_receipt(
    settlement_id: UUID,
    data: LedgerAttachmentsAdd,
    scope: ReceiptCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LedgerAttachmentResponse]]:
    """Keep files with a receipt: the advice or bill behind it (ACC-10)."""
    rows = LedgerAttachmentService(db).attach_to_settlement(
        settlement_id,
        data.attachments,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        directions=RECEIPT_DIRECTIONS,
    )
    db.commit()
    return ApiResponse(
        data=[LedgerAttachmentResponse.model_validate(row) for row in rows]
    )


@receipts_router.delete(
    "/{settlement_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_receipt_attachment(
    settlement_id: UUID,
    attachment_id: UUID,
    scope: ReceiptCreateScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove one file from a receipt; the trail keeps that it was there."""
    LedgerAttachmentService(db).remove(
        attachment_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        settlement_id=settlement_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@payments_router.get(
    "/{settlement_id}/attachments",
    response_model=ApiResponse[list[LedgerAttachmentResponse]],
)
def list_payment_attachments(
    settlement_id: UUID,
    scope: PaymentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LedgerAttachmentResponse]]:
    """List the files kept with one payment (ACC-10)."""
    rows = LedgerAttachmentService(db).for_settlement(
        settlement_id, firm_id=scope.firm_id, directions=PAYMENT_DIRECTIONS
    )
    return ApiResponse(
        data=[LedgerAttachmentResponse.model_validate(row) for row in rows]
    )


@payments_router.post(
    "/{settlement_id}/attachments",
    response_model=ApiResponse[list[LedgerAttachmentResponse]],
)
def attach_to_payment(
    settlement_id: UUID,
    data: LedgerAttachmentsAdd,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LedgerAttachmentResponse]]:
    """Keep files with a payment: the advice or bill behind it (ACC-10)."""
    rows = LedgerAttachmentService(db).attach_to_settlement(
        settlement_id,
        data.attachments,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        directions=PAYMENT_DIRECTIONS,
    )
    db.commit()
    return ApiResponse(
        data=[LedgerAttachmentResponse.model_validate(row) for row in rows]
    )


@payments_router.delete(
    "/{settlement_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_payment_attachment(
    settlement_id: UUID,
    attachment_id: UUID,
    scope: PaymentCreateScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove one file from a payment; the trail keeps that it was there."""
    LedgerAttachmentService(db).remove(
        attachment_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        settlement_id=settlement_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
