"""Firm-scoped REST endpoints for customer management."""

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.customers.schemas import (
    CreditControlSettingsResponse,
    CreditControlSettingsWrite,
    CreditStatusResponse,
    CustomerAddressResponse,
    CustomerContactResponse,
    CustomerCreate,
    CustomerGroupResponse,
    CustomerGroupWrite,
    CustomerImportRequest,
    CustomerReceivableSummary,
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionResponse,
    CustomerReceivableTransactionType,
    CustomerResponse,
    CustomerSummary,
    CustomerUpdate,
)
from app.customers.schemas.customer import (
    CustomerListFilters,
    CustomerStatus,
    CustomerType,
)
from app.customers.services import (
    CreditControlService,
    CustomerGroupService,
    CustomerService,
)
from app.finance.services.document_posting import DocumentPostingService

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customers"],
    responses=STANDARD_ERROR_RESPONSES,
)


CustomerViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("CUSTOMER_VIEW")]
CustomerCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_CREATE")
]
CustomerUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_UPDATE")
]
CustomerDeleteScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_DELETE")
]
CustomerRestoreScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_RESTORE")
]
CustomerExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_EXPORT")
]
CustomerSettingsScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_MANAGE_SETTINGS")
]
CustomerImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_IMPORT")
]
# Posting a receivable moves money, so it needs the accounting grant rather than
# the master-data one. Under CUSTOMER_UPDATE anyone who could edit a customer's
# phone number could also post a receipt against their balance.
CustomerReceiptScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("RECEIPT_CREATE")
]


def _filters(
    *,
    status_value: CustomerStatus | None,
    customer_type: CustomerType | None,
    firm_id: UUID | None,
    city: str | None,
    state_value: str | None,
    created_from: date | None,
    created_to: date | None,
    include_deleted: bool,
) -> CustomerListFilters:
    try:
        return CustomerListFilters(
            status=status_value,
            customer_type=customer_type,
            firm_id=firm_id,
            city=city,
            state=state_value,
            created_from=created_from,
            created_to=created_to,
            include_deleted=include_deleted,
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[CustomerResponse])
def list_customers(
    scope: CustomerViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "code", "name", "status", "credit_limit", "current_outstanding", "created_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: Annotated[CustomerStatus | None, Query(alias="status")] = None,
    customer_type: CustomerType | None = None,
    firm_id: UUID | None = None,
    city: str | None = None,
    state_value: Annotated[str | None, Query(alias="state")] = None,
    created_from: date | None = None,
    created_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CustomerResponse]:
    """Search, filter, sort, and paginate visible customers."""
    params = PaginationParams(page=page, page_size=page_size)
    filters = _filters(
        status_value=status_value,
        customer_type=customer_type,
        firm_id=firm_id if scope.firm_id is None else None,
        city=city,
        state_value=state_value,
        created_from=created_from,
        created_to=created_to,
        include_deleted=include_deleted,
    )
    rows, total = CustomerService(db).list_customers(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[CustomerResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[CustomerSummary])
def customer_summary(
    scope: CustomerViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerSummary]:
    """Return aggregate values for the visible firm scope."""
    summary = CustomerService(db).summary(
        firm_scope=scope.firm_id,
        filters=CustomerListFilters(include_deleted=include_deleted),
    )
    return ApiResponse(data=summary)


@router.get("/export")
def export_customers(
    scope: CustomerExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Export all matching visible customers as UTF-8 CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Code", "Name", "Type", "GST", "PAN", "Email", "Phone", "Status"])
    page = 1
    while True:
        rows, _ = CustomerService(db).list_customers(
            firm_scope=scope.firm_id,
            filters=CustomerListFilters(),
            page=page,
            page_size=1000,
            search=search,
            sort_by="code",
            descending=False,
        )
        for customer in rows:
            writer.writerow(
                [
                    customer.code,
                    customer.name,
                    customer.customer_type,
                    customer.gst_number or "",
                    customer.pan_number or "",
                    customer.email or "",
                    customer.phone or "",
                    customer.status,
                ]
            )
        if len(rows) < 1000:
            break
        page += 1
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="customers.csv"'},
    )


@router.post(
    "",
    response_model=ApiResponse[CustomerResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    data: CustomerCreate,
    scope: CustomerCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerResponse]:
    """Create a customer in the selected firm."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when creating a customer.")
    customer = CustomerService(db).create(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=CustomerResponse.model_validate(customer))


@router.post(
    "/import",
    response_model=ApiResponse[list[CustomerResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_customers(
    data: CustomerImportRequest,
    scope: CustomerImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerResponse]]:
    """Import a validated JSON customer batch atomically."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when importing customers.")
    customers = CustomerService(db).import_customers(
        data.records,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(
        data=[CustomerResponse.model_validate(customer) for customer in customers]
    )


# Declared with the other literals above `/{customer_id}`: FastAPI matches in
# declaration order, and below it "groups" is read as a customer id and
# answered 422 -- the trap that made nine routes across eight routers
# unreachable from the day they were written.
@router.get("/groups", response_model=PaginatedResponse[CustomerGroupResponse])
def list_customer_groups(
    scope: CustomerViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CustomerGroupResponse]:
    """List the segments this firm sells to."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = CustomerGroupService(db).list_groups(
        firm_id=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        search=search,
    )
    return PaginatedResponse(
        data=[CustomerGroupResponse.model_validate(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/groups",
    response_model=ApiResponse[CustomerGroupResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_customer_group(
    data: CustomerGroupWrite,
    scope: CustomerSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerGroupResponse]:
    """Record one segment."""
    row = CustomerGroupService(db).create_group(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=CustomerGroupResponse.model_validate(row))


@router.get("/groups/{group_id}", response_model=ApiResponse[CustomerGroupResponse])
def get_customer_group(
    group_id: UUID,
    scope: CustomerViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerGroupResponse]:
    """Return one segment."""
    row = CustomerGroupService(db).get_group(group_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=CustomerGroupResponse.model_validate(row))


@router.put("/groups/{group_id}", response_model=ApiResponse[CustomerGroupResponse])
def update_customer_group(
    group_id: UUID,
    data: CustomerGroupWrite,
    scope: CustomerSettingsScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerGroupResponse]:
    """Replace one segment's details."""
    service = CustomerGroupService(db)
    current = service.get_group(group_id, firm_id=scope.firm_id)
    assert_version(current.version, expected_version)
    row = service.update_group(
        group_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=CustomerGroupResponse.model_validate(row))


@router.delete("/groups/{group_id}", response_model=ApiResponse[dict[str, str]])
def delete_customer_group(
    group_id: UUID,
    scope: CustomerSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Retire a segment nobody is in."""
    CustomerGroupService(db).delete_group(
        group_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"status": "deleted"})


@router.get(
    "/credit-settings", response_model=ApiResponse[CreditControlSettingsResponse]
)
def get_credit_settings(
    scope: CustomerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CreditControlSettingsResponse]:
    """Return the firm's credit policy, or the default it falls back to."""
    settings = CreditControlService(db).settings_response(scope.firm_id)
    return ApiResponse(data=settings)


@router.put(
    "/credit-settings", response_model=ApiResponse[CreditControlSettingsResponse]
)
def update_credit_settings(
    data: CreditControlSettingsWrite,
    scope: CustomerSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CreditControlSettingsResponse]:
    """Replace the firm's credit policy."""
    settings = CreditControlService(db).update_settings(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=settings)


@router.get("/{customer_id}", response_model=ApiResponse[CustomerResponse])
def get_customer(
    customer_id: UUID,
    scope: CustomerViewScope,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerResponse]:
    """Return one visible customer."""
    customer = CustomerService(db).get(
        customer_id,
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    set_etag(response, customer)
    return ApiResponse(data=CustomerResponse.model_validate(customer))


@router.put("/{customer_id}", response_model=ApiResponse[CustomerResponse])
def update_customer(
    customer_id: UUID,
    data: CustomerUpdate,
    scope: CustomerUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[CustomerResponse]:
    """Replace one visible customer.

    The update replaces the whole address and contact collections, so two
    people editing the same customer do not merge badly -- one of them loses
    every row they entered. ``If-Match`` is how a client refuses that.
    """
    service = CustomerService(db)
    assert_version(
        service.get(customer_id, firm_scope=scope.firm_id).version, expected_version
    )
    customer = service.update(
        customer_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    set_etag(response, customer)
    return ApiResponse(data=CustomerResponse.model_validate(customer))


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: UUID,
    scope: CustomerDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete one visible customer."""
    CustomerService(db).delete(
        customer_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{customer_id}/restore", response_model=ApiResponse[CustomerResponse])
def restore_customer(
    customer_id: UUID,
    scope: CustomerRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerResponse]:
    """Restore one soft-deleted customer."""
    customer = CustomerService(db).restore(
        customer_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=CustomerResponse.model_validate(customer))


@router.get(
    "/{customer_id}/addresses",
    response_model=ApiResponse[list[CustomerAddressResponse]],
)
def list_customer_addresses(
    customer_id: UUID,
    scope: CustomerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerAddressResponse]]:
    """Return all active addresses for one visible customer."""
    rows = CustomerService(db).addresses(customer_id, firm_scope=scope.firm_id)
    return ApiResponse(
        data=[CustomerAddressResponse.model_validate(row) for row in rows]
    )


@router.get(
    "/{customer_id}/contacts",
    response_model=ApiResponse[list[CustomerContactResponse]],
)
def list_customer_contacts(
    customer_id: UUID,
    scope: CustomerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerContactResponse]]:
    """Return all active contacts for one visible customer."""
    rows = CustomerService(db).contacts(customer_id, firm_scope=scope.firm_id)
    return ApiResponse(
        data=[CustomerContactResponse.model_validate(row) for row in rows]
    )


@router.get(
    "/{customer_id}/credit-status",
    response_model=ApiResponse[CreditStatusResponse],
)
def customer_credit_status(
    customer_id: UUID,
    scope: CustomerViewScope,
    amount: Annotated[
        Decimal,
        Query(ge=0, description="Value of the document being considered, if any."),
    ] = Decimal("0"),
    db: Session = Depends(get_db),
) -> ApiResponse[CreditStatusResponse]:
    """Report where one customer stands against their credit limit.

    ``amount`` lets a client ask the question before saving -- "would this
    order breach the limit?" -- rather than after.
    """
    customer = CustomerService(db).get(customer_id, firm_scope=scope.firm_id)
    status_report = CreditControlService(db).status_for(
        customer, additional_amount=amount
    )
    return ApiResponse(data=status_report)


#: Receivable types that move money, and therefore belong to a document that
#: posts. `post_receivable_transaction` moves the customer's balance and writes
#: no journal, so recording a receipt through it puts the subsidiary ledger and
#: the general ledger further apart with every use -- silently, and
#: permanently. `/api/v1/receipts` does the same thing and posts.
#:
#: The service method stays general: the sales invoice and settlement services
#: call it as part of a larger unit of work that does post. It is this
#: endpoint, reachable by hand, that had no counterpart in the ledger.
POSTED_ELSEWHERE = {
    CustomerReceivableTransactionType.RECEIPT: "receipts",
    CustomerReceivableTransactionType.ADVANCE_RECEIPT: "receipts",
}


@router.get(
    "/{customer_id}/receivables/summary",
    response_model=ApiResponse[CustomerReceivableSummary],
)
def customer_receivable_summary(
    customer_id: UUID,
    scope: CustomerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerReceivableSummary]:
    """Return receivable balances for one visible customer."""
    summary = CustomerService(db).receivable_summary(
        customer_id,
        firm_scope=scope.firm_id,
    )
    return ApiResponse(data=summary)


@router.get(
    "/{customer_id}/receivables/transactions",
    response_model=PaginatedResponse[CustomerReceivableTransactionResponse],
)
def list_customer_receivable_transactions(
    customer_id: UUID,
    scope: CustomerViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CustomerReceivableTransactionResponse]:
    """List receivable transactions for one visible customer."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = CustomerService(db).receivable_transactions(
        customer_id,
        firm_scope=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=[
            CustomerReceivableTransactionResponse.model_validate(row) for row in rows
        ],
        pagination=params.metadata(total),
    )


@router.post(
    "/{customer_id}/receivables/transactions",
    response_model=ApiResponse[CustomerReceivableTransactionResponse],
)
def post_customer_receivable_transaction(
    customer_id: UUID,
    data: CustomerReceivableTransactionCreate,
    scope: CustomerReceiptScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerReceivableTransactionResponse]:
    """Post one receivable transaction that is not money arriving.

    Money in is recorded as a receipt, which posts to the ledger as well as to
    the customer, so accepting one here would leave the two disagreeing by the
    amount collected.

    What is left does not all sit outside the ledger. A credit note reduces
    what the customer owes, so it reduces the receivable control account and
    posts; an advance application moves nothing the ledger has not already
    recorded, because the advance was credited to receivables when the receipt
    posted.
    """
    service = CustomerService(db)
    destination = POSTED_ELSEWHERE.get(data.transaction_type)
    if destination is not None:
        raise ValidationError(
            f"A {data.transaction_type.value.lower().replace('_', ' ')} moves "
            f"money, so it is recorded at /api/v1/{destination} where it also "
            "reaches the ledger. This endpoint only moves the customer balance."
        )
    row = service.post_receivable_transaction(
        customer_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        commit=False,
    )
    # A credit note reduces what the customer owes, so it reduces the
    # receivable control account. Leaving it unposted drove the two apart by
    # its value -- the reasoning that it "moves no money" was the wrong test.
    #
    # Cancelling an invoice does not come through here: that reverses the
    # invoice's own journal, which mirrors the revenue and tax it raised.
    if data.transaction_type == CustomerReceivableTransactionType.CREDIT_NOTE:
        DocumentPostingService(db).post_credit_note(
            firm_id=scope.firm_id,
            customer_id=customer_id,
            reference_number=(data.reference_number or f"CN-{str(row.id)[:8].upper()}"),
            note_date=data.transaction_date,
            amount=data.amount,
            actor_id=scope.actor_id,
            narration=data.remarks,
        )
    db.commit()
    db.refresh(row)
    return ApiResponse(data=CustomerReceivableTransactionResponse.model_validate(row))
