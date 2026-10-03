"""Firm-scoped REST endpoints for customer management."""

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.business.schemas import AttributeValueResponse
from app.common.balance_confirmation import BalanceConfirmationService, PartySide
from app.common.file_import import (
    ImportReportResponse,
    file_format_of,
    report_response,
)
from app.common.pan_report import PanReportRow, customer_pan_report
from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.customers.schemas import (
    CreditControlSettingsResponse,
    CreditControlSettingsWrite,
    CreditStatusResponse,
    CustomerAddressResponse,
    CustomerAgeing,
    CustomerContactResponse,
    CustomerCreate,
    CustomerGroupResponse,
    CustomerGroupWrite,
    CustomerIdentityCheck,
    CustomerIdentityHolder,
    CustomerImportRequest,
    CustomerReceivableSummary,
    CustomerReceivableTransactionResponse,
    CustomerResponse,
    CustomerStatement,
    CustomerSummary,
    CustomerUpdate,
)
from app.customers.schemas.customer import (
    CustomerListFilters,
    CustomerStatus,
    CustomerType,
)
from app.customers.schemas.opening_bill import (
    CustomerOpeningBillCancel,
    CustomerOpeningBillImportRequest,
    CustomerOpeningBillResponse,
    CustomerOpeningBillWrite,
)
from app.customers.schemas.records import (
    CustomerAttachmentResponse,
    CustomerAttachmentsWrite,
    CustomerBankAccountResponse,
    CustomerBankAccountsWrite,
)
from app.customers.schemas.statement import (
    CombinedStatementLine,
    CombinedStatementResponse,
)
from app.customers.services import (
    CreditControlService,
    CustomerGroupService,
    CustomerService,
    CustomerStatementService,
)
from app.customers.services.combined_statement import CombinedStatementService
from app.customers.services.customer_import import (
    CustomerFileImporter,
    template_csv,
    template_workbook,
)
from app.customers.services.customer_records import CustomerRecordsService
from app.customers.services.opening_bill_import import CustomerOpeningBillFileImporter
from app.customers.services.opening_bill_service import CustomerOpeningBillService
from app.imports.services import columns_for_kind, mapped_content, parse_mapping

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customers"],
    responses=STANDARD_ERROR_RESPONSES,
)


CustomerViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("CUSTOMER_VIEW")]
#: A report opens to whoever reads the module or holds REPORT_VIEW (D-RPT-4).
PanReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("CUSTOMER_VIEW", "REPORT_VIEW")
]
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
#: Changing where a customer's refunds are paid (MST-4).
CustomerBankScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOMER_MANAGE_BANK_DETAILS")
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


def _response(
    row: Customer,
    db: Session,
    *,
    attributes: list[AttributeValueResponse] | None = None,
) -> CustomerResponse:
    """Build one customer response with its custom fields attached.

    The values live in their own table and `CustomerResponse` cannot reach
    them through the row, so every site goes through here -- the product
    router does the same, and a site that skipped it would answer an empty
    list for a customer that has values.
    """
    payload = CustomerResponse.model_validate(row).model_dump(mode="python")
    payload["attributes"] = (
        CustomerService(db).attribute_responses(row)
        if attributes is None
        else attributes
    )
    return CustomerResponse.model_validate(payload)


def _responses(rows: list[Customer], db: Session) -> list[CustomerResponse]:
    """Build a page of responses, reading every row's custom fields at once."""
    attributes = CustomerService(db).attribute_responses_for_many(rows)
    return [_response(row, db, attributes=attributes.get(row.id, [])) for row in rows]


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
        data=_responses(rows, db),
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


@router.get("/identity-check", response_model=ApiResponse[CustomerIdentityCheck])
def check_customer_identity(
    scope: CustomerViewScope,
    gst_number: Annotated[str | None, Query(max_length=32)] = None,
    pan_number: Annotated[str | None, Query(max_length=32)] = None,
    excluding_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerIdentityCheck]:
    """Name the other customers holding a GSTIN or PAN, before a save (A7).

    A repeat is allowed -- a branch per state shares the company's PAN -- so
    the form warns and lets the person decide. ``excluding_id`` is the
    customer being edited.
    """
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required to check a customer's GSTIN.")
    gst = (gst_number or "").strip().upper() or None
    pan = (pan_number or "").strip().upper() or None
    service = CustomerService(db)
    holders = service.identity_holders(
        scope.firm_id, gst_number=gst, pan_number=pan, excluding_id=excluding_id
    )
    return ApiResponse(
        data=CustomerIdentityCheck(
            holders=[
                CustomerIdentityHolder(
                    id=row.id,
                    code=row.code,
                    name=row.name,
                    gst_number=row.gst_number,
                    pan_number=row.pan_number,
                )
                for row in holders
            ],
            message=service.identity_warning(
                scope.firm_id,
                gst_number=gst,
                pan_number=pan,
                excluding_id=excluding_id,
            ),
        )
    )


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
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        # A standing discount is a price decision, so giving one takes the code
        # that writes a segment's rate, not the one that adds a shop (D-MST-2).
        may_set_standing_discount=scope.principal.has_permission(
            "CUSTOMER_MANAGE_SETTINGS"
        ),
    )
    return ApiResponse(
        data=_response(customer, db),
        message=_identity_message(customer, db),
    )


def _identity_message(customer: Customer, db: Session) -> str | None:
    """Say which other customers share this one's GSTIN or PAN (A7)."""
    return CustomerService(db).identity_warning(
        customer.firm_id,
        gst_number=customer.gst_number,
        pan_number=customer.pan_number,
        excluding_id=customer.id,
    )


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
        may_set_standing_discount=scope.principal.has_permission(
            "CUSTOMER_MANAGE_SETTINGS"
        ),
    )
    return ApiResponse(data=_responses(customers, db))


def _firm(scope: ResolvedFirmScope) -> UUID:
    """Return the firm a customer's opening bills belong to, or refuse."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for a customer's opening bills.")
    return scope.firm_id


# Opening bills: what each customer owed the firm on its first day here, bill
# by bill. The literal paths come before `/{customer_id}`, for the reason
# given at `/ageing` below.
@router.post(
    "/opening-bills/import",
    response_model=ApiResponse[list[CustomerOpeningBillResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_customer_opening_bills(
    data: CustomerOpeningBillImportRequest,
    scope: CustomerImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerOpeningBillResponse]]:
    """Record a file of opening bills, naming customers by code; all or none."""
    firm_id = _firm(scope)
    service = CustomerOpeningBillService(db)
    rows = service.import_bills(data.records, firm_id=firm_id, actor_id=scope.actor_id)
    return ApiResponse(
        data=[service.response_for(row, firm_id=firm_id) for row in rows]
    )


@router.get("/opening-bills/import-template")
def customer_opening_bill_import_template(
    scope: CustomerImportScope,
    format: Literal["csv", "xlsx"] = "xlsx",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the customers' opening-bill template (D-GOLIVE-1).

    The workbook carries the sheet to fill, a notes sheet naming every column,
    and a lists sheet with this firm's customers; the example row names one of
    them, so the template imports as it comes.
    """
    importer = CustomerOpeningBillFileImporter(db)
    firm_id = _firm(scope)
    if format == "csv":
        return StreamingResponse(
            iter([importer.template_csv(firm_id)]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="customer-opening-bills-template.csv"'
                )
            },
        )
    return StreamingResponse(
        iter([importer.template_workbook(firm_id)]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                'attachment; filename="customer-opening-bills-template.xlsx"'
            )
        },
    )


@router.post(
    "/opening-bills/import-file", response_model=ApiResponse[ImportReportResponse]
)
async def import_customer_opening_bill_file(
    scope: CustomerImportScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    posting_date: Annotated[str | None, Form()] = None,
    apply: Annotated[bool, Form()] = False,
    mapping: Annotated[str | None, Form()] = None,
) -> ApiResponse[ImportReportResponse]:
    """Check a CSV or XLSX file of opening bills, and with ``apply`` post it.

    Every bill is posted on ``posting_date`` (today when left out). Every
    problem is returned with its row and column; an apply that finds any
    writes nothing and says so with ``imported: false``.
    """
    firm_id = _firm(scope)
    file_format = file_format_of(file.filename)
    # A file mapped on the import screen is read as mapped (decision B3).
    content, file_format = mapped_content(
        await file.read(),
        file_format,
        parse_mapping(mapping),
        columns_for_kind(db, "customer-opening-bills"),
    )
    if posting_date:
        try:
            on = date.fromisoformat(posting_date)
        except ValueError as error:
            raise ValidationError("posting_date must be a date, yyyy-mm-dd.") from error
    else:
        on = utc_now().date()
    report = CustomerOpeningBillFileImporter(db).run(
        content,
        file_format=file_format,
        firm_id=firm_id,
        actor_id=scope.actor_id,
        posting_date=on,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


@router.post(
    "/opening-bills/{bill_id}/cancel",
    response_model=ApiResponse[CustomerOpeningBillResponse],
)
def cancel_customer_opening_bill(
    bill_id: UUID,
    data: CustomerOpeningBillCancel,
    scope: CustomerUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerOpeningBillResponse]:
    """Take back an opening bill entered in error; refused once received against."""
    firm_id = _firm(scope)
    service = CustomerOpeningBillService(db)
    row = service.cancel(
        bill_id, reason=data.reason, firm_id=firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.response_for(row, firm_id=firm_id))


@router.get(
    "/{customer_id}/opening-bills",
    response_model=ApiResponse[list[CustomerOpeningBillResponse]],
)
def list_customer_opening_bills(
    customer_id: UUID,
    scope: CustomerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerOpeningBillResponse]]:
    """List one customer's opening bills with what is received and owed on each."""
    return ApiResponse(
        data=CustomerOpeningBillService(db).list_for_customer(
            customer_id, firm_id=_firm(scope)
        )
    )


@router.post(
    "/{customer_id}/opening-bills",
    response_model=ApiResponse[CustomerOpeningBillResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_customer_opening_bill(
    customer_id: UUID,
    data: CustomerOpeningBillWrite,
    scope: CustomerUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerOpeningBillResponse]:
    """Record one bill the customer owed at cutover, and post it."""
    firm_id = _firm(scope)
    service = CustomerOpeningBillService(db)
    row = service.create(customer_id, data, firm_id=firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.response_for(row, firm_id=firm_id))


@router.get("/import-template")
def customer_import_template(
    scope: CustomerImportScope,
    format: Literal["csv", "xlsx"] = "xlsx",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the customer import template (backlog 46).

    The workbook carries the sheet to fill, a notes sheet naming every column
    and what it takes, and a lists sheet with this firm's segments.
    """
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when importing customers.")
    if format == "csv":
        return StreamingResponse(
            iter([template_csv()]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="customer-template.csv"'
            },
        )
    return StreamingResponse(
        iter([template_workbook(db, scope.firm_id)]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="customer-template.xlsx"'
        },
    )


@router.post("/import-file", response_model=ApiResponse[ImportReportResponse])
async def import_customer_file(
    scope: CustomerImportScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    existing: Annotated[Literal["refuse", "update"], Form()] = "refuse",
    apply: Annotated[bool, Form()] = False,
    mapping: Annotated[str | None, Form()] = None,
) -> ApiResponse[ImportReportResponse]:
    """Check a CSV or XLSX customer file, and with ``apply`` import it whole.

    Every row is checked and every problem returned with its row number. An
    apply that finds any problem writes nothing and says so with
    ``imported: false``.
    """
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when importing customers.")
    file_format = file_format_of(file.filename)
    # A file mapped on the import screen is read as mapped (decision B3).
    content, file_format = mapped_content(
        await file.read(),
        file_format,
        parse_mapping(mapping),
        columns_for_kind(db, "customers"),
    )
    if existing == "update" and not scope.principal.has_permission("CUSTOMER_UPDATE"):
        raise AuthorizationError(
            "Updating existing customers from a file needs the right to edit "
            "customers."
        )
    report = CustomerFileImporter(
        db,
        CustomerService(db),
        may_manage_settings=scope.principal.has_permission("CUSTOMER_MANAGE_SETTINGS"),
    ).run(
        content,
        file_format=file_format,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        existing=existing,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


# Declared with the other literals above `/{customer_id}`: FastAPI matches in
# declaration order, and below it "groups" is read as a customer id and
# answered 422 -- the trap that made nine routes across eight routers
# unreachable from the day they were written.
# Declared above `/{customer_id}`: FastAPI matches in declaration order, and
# below it "ageing" is read as a customer id and answered 422. Nine routes in
# eight routers had shipped that way before the guard test existed.
@router.get("/ageing", response_model=ApiResponse[list[CustomerAgeing]])
def customer_ageing(
    scope: CustomerViewScope,
    customer_id: UUID | None = None,
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerAgeing]]:
    """Report what every customer still owes, by how long they have owed it.

    Derived from the settlement allocations, because what a bill still owes is
    a fact about the money received against it and is deliberately stored
    nowhere.
    """
    return ApiResponse(
        data=CustomerStatementService(db).ageing(
            firm_scope=scope.firm_id, customer_id=customer_id, as_of=as_of
        )
    )


# Declared above `/{customer_id}`, for the reason `/ageing` is.
@router.get("/reports/pan", response_model=ApiResponse[list[PanReportRow]])
def customer_pan_check(
    scope: PanReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PanReportRow]]:
    """List the customers with no PAN, or one that disagrees with the GSTIN.

    PLT-11: a PAN missing, malformed, or not inside the GSTIN -- records
    written before `settle_pan` checked them. Each row names the problem.
    """
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for the PAN report.")
    return ApiResponse(data=customer_pan_report(db, firm_id=scope.firm_id))


# Declared above `/{customer_id}`, for the reason `/ageing` is.
@router.get("/balance-confirmations", response_class=StreamingResponse)
def customer_balance_confirmations(
    scope: CustomerViewScope,
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Draw a balance confirmation letter for every customer with a balance.

    One PDF per customer, zipped, because each goes to its own address.
    `as_of` defaults to today in UTC.
    """
    day = as_of or utc_now().date()
    archive, filename, _ = BalanceConfirmationService(db).letters_for_everyone(
        PartySide.CUSTOMER, firm_id=scope.firm_id, as_of=day
    )
    return StreamingResponse(
        iter([archive]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@router.get(
    "/{customer_id}/bank-accounts",
    response_model=ApiResponse[list[CustomerBankAccountResponse]],
)
def customer_bank_accounts(
    customer_id: UUID,
    scope: CustomerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerBankAccountResponse]]:
    """Return the customer's bank accounts (MST-4).

    Each number is masked to its last four digits unless the caller may
    change it (``CUSTOMER_MANAGE_BANK_DETAILS``).
    """
    rows = CustomerRecordsService(db).bank_accounts(
        customer_id,
        firm_id=scope.firm_id,
        unmasked=scope.principal.has_permission("CUSTOMER_MANAGE_BANK_DETAILS"),
    )
    return ApiResponse(data=rows)


@router.put(
    "/{customer_id}/bank-accounts",
    response_model=ApiResponse[list[CustomerBankAccountResponse]],
)
def replace_customer_bank_accounts(
    customer_id: UUID,
    payload: CustomerBankAccountsWrite,
    scope: CustomerBankScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerBankAccountResponse]]:
    """Replace the customer's bank accounts with the list sent."""
    rows = CustomerRecordsService(db).replace_bank_accounts(
        customer_id,
        payload.accounts,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=rows, message="Bank accounts saved.")


@router.get(
    "/{customer_id}/attachments",
    response_model=ApiResponse[list[CustomerAttachmentResponse]],
)
def customer_attachments(
    customer_id: UUID,
    scope: CustomerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerAttachmentResponse]]:
    """Return the files kept on record for the customer (MST-4)."""
    rows = CustomerRecordsService(db).attachments(customer_id, firm_id=scope.firm_id)
    return ApiResponse(
        data=[CustomerAttachmentResponse.model_validate(row) for row in rows]
    )


@router.post(
    "/{customer_id}/attachments",
    response_model=ApiResponse[list[CustomerAttachmentResponse]],
    status_code=status.HTTP_201_CREATED,
)
def attach_customer_files(
    customer_id: UUID,
    payload: CustomerAttachmentsWrite,
    scope: CustomerUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerAttachmentResponse]]:
    """Keep KYC copies, agreements or licences on record for the customer."""
    rows = CustomerRecordsService(db).attach(
        customer_id, payload.files, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=[CustomerAttachmentResponse.model_validate(row) for row in rows],
        message="Files kept.",
    )


@router.delete(
    "/{customer_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_customer_file(
    customer_id: UUID,
    attachment_id: UUID,
    scope: CustomerUpdateScope,
    db: Session = Depends(get_db),
) -> None:
    """Remove one file from the customer's record; the trail keeps it."""
    CustomerRecordsService(db).remove_attachment(
        customer_id, attachment_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )


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
    return ApiResponse(data=_response(customer, db))


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
        # The limit is a credit control, so moving it takes the code that
        # writes the credit policy rather than the one that edits a phone
        # number (D-CFG-17).
        may_change_credit_limit=scope.principal.has_permission(
            "CUSTOMER_MANAGE_SETTINGS"
        ),
        # So is the standing discount: whoever sells at a price must not be
        # the one who sets it (D-MST-2).
        may_change_standing_discount=scope.principal.has_permission(
            "CUSTOMER_MANAGE_SETTINGS"
        ),
    )
    set_etag(response, customer)
    return ApiResponse(
        data=_response(customer, db),
        message=_identity_message(customer, db),
    )


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
    return ApiResponse(data=_response(customer, db))


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


@router.get(
    "/{customer_id}/statement",
    response_model=ApiResponse[CustomerStatement],
)
def customer_statement(
    customer_id: UUID,
    scope: CustomerViewScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerStatement]:
    """Return one customer's account movement over a period.

    The opening balance is summed from the deltas before the period and the
    running balance is recomputed in date order -- the stored
    `outstanding_after` is a snapshot taken in the order rows were *written*,
    which a backdated document makes disagree with the order they are *read*.
    """
    return ApiResponse(
        data=CustomerStatementService(db).statement(
            customer_id,
            firm_scope=scope.firm_id,
            from_date=from_date,
            to_date=to_date,
        )
    )


@router.get(
    "/{customer_id}/combined-statement",
    response_model=ApiResponse[CombinedStatementResponse],
)
def customer_combined_statement(
    customer_id: UUID,
    scope: CustomerViewScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    db: Session = Depends(get_db),
) -> ApiResponse[CombinedStatementResponse]:
    """Return a customer's account and its linked supplier's, netted (ACC-11).

    Both halves come from their own statements, interleaved in date order;
    the net is receivable less payable. Reading the supplier half takes
    VENDOR_VIEW as well, since it is the supplier's account.
    """
    if not scope.principal.has_permission("VENDOR_VIEW"):
        raise AuthorizationError(
            "The combined statement shows the supplier account too, which "
            "needs the view suppliers permission (VENDOR_VIEW)."
        )
    found = CombinedStatementService(db).for_customer(
        customer_id, firm_scope=scope.firm_id, from_date=from_date, to_date=to_date
    )
    return ApiResponse(
        data=CombinedStatementResponse(
            customer_id=found.customer_id,
            customer_name=found.customer_name,
            vendor_id=found.vendor_id,
            vendor_name=found.vendor_name,
            from_date=found.from_date,
            to_date=found.to_date,
            receivable_opening=found.receivable_opening,
            payable_opening=found.payable_opening,
            net_opening=found.net_opening,
            receivable_closing=found.receivable_closing,
            payable_closing=found.payable_closing,
            net_closing=found.net_closing,
            lines=[
                CombinedStatementLine(
                    transaction_date=line.transaction_date,
                    account=line.account,
                    transaction_type=line.transaction_type,
                    reference_number=line.reference_number,
                    remarks=line.remarks,
                    debit=line.debit,
                    credit=line.credit,
                    net_balance=line.net_balance,
                )
                for line in found.lines
            ],
        )
    )


@router.get("/{customer_id}/statement/print", response_class=StreamingResponse)
def customer_statement_pdf(
    customer_id: UUID,
    scope: CustomerViewScope,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Draw one customer's statement of account with their unpaid bills.

    What a payment reminder attaches (MSG-3). The period defaults to the
    oldest unpaid bill's date up to today (UTC); the figures are the
    statement's and the ageing's own.
    """
    from app.customers.services.statement_pdf import CustomerStatementPdfService

    pdf, filename = CustomerStatementPdfService(db).render(
        customer_id, firm_id=scope.firm_id, from_date=from_date, to_date=to_date
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{customer_id}/balance-confirmation", response_class=StreamingResponse)
def customer_balance_confirmation(
    customer_id: UUID,
    scope: CustomerViewScope,
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Draw one customer's balance confirmation letter as of a day.

    The balance is the statement's own arithmetic -- receivable movements
    dated on or before the day, less what is held on account -- so the letter
    and the statement printed for the same day agree. `as_of` defaults to
    today in UTC.
    """
    pdf, filename = BalanceConfirmationService(db).letter(
        PartySide.CUSTOMER,
        customer_id,
        firm_id=scope.firm_id,
        as_of=as_of or utc_now().date(),
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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


# `POST /{customer_id}/receivables/transactions` was retired on 2026-09-30
# (D-FIN-23). It moved a customer's balance by hand; every type but a credit
# note had already been refused and pointed at the module that records it with
# its journal (D-FIN-4), and the credit note it still took reversed no output
# tax. A credit note is raised at `/api/v1/credit-notes`, which names the
# invoice line and reverses the tax that line was charged. The list above
# stays: it reads the account, it does not move it.
