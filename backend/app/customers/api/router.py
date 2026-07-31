"""Firm-scoped REST endpoints for customer management."""

import csv
import io
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_permission,
)
from app.customers.schemas import (
    CustomerAddressResponse,
    CustomerContactResponse,
    CustomerCreate,
    CustomerImportRequest,
    CustomerResponse,
    CustomerSummary,
    CustomerUpdate,
)
from app.customers.schemas.customer import (
    CustomerListFilters,
    CustomerStatus,
    CustomerType,
)
from app.customers.services import CustomerService
from app.firms.models import Firm
from app.identity.models import UserFirm

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customers"],
    responses=STANDARD_ERROR_RESPONSES,
)


class CustomerScope:
    """Carry the authenticated principal and optional firm restriction."""

    def __init__(self, principal: Principal, firm_id: UUID | None) -> None:
        """Store the authenticated identity and validated firm scope."""
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        """Return the user UUID responsible for mutations."""
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Customer management requires a user principal.")
        return self.principal.subject


def customer_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> CustomerScope:
    """Validate active firm access for every customer operation."""
    if "platform_admin" in principal.roles:
        if x_firm_id is None:
            raise AuthorizationError("X-Firm-ID is required for firm-owned resources.")
        firm = db.scalar(
            select(Firm.id).where(
                Firm.id == x_firm_id,
                Firm.is_active.is_(True),
                Firm.is_deleted.is_(False),
            )
        )
        if firm is None:
            raise AuthorizationError("The selected firm is inactive or unavailable.")
        return CustomerScope(principal, x_firm_id)
    if not isinstance(principal.subject, UUID) or x_firm_id is None:
        raise AuthorizationError("An authorized active firm is required.")
    membership = db.scalar(
        select(UserFirm.id)
        .join(Firm, Firm.id == UserFirm.firm_id)
        .where(
            UserFirm.user_id == principal.subject,
            UserFirm.firm_id == x_firm_id,
            UserFirm.is_active.is_(True),
            UserFirm.is_deleted.is_(False),
            Firm.is_active.is_(True),
            Firm.is_deleted.is_(False),
        )
    )
    if membership is None:
        raise AuthorizationError("You are not authorized for the selected firm.")
    return CustomerScope(principal, x_firm_id)


def _permission(code: str) -> object:
    """Compose permission and customer-scope dependencies."""

    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[CustomerScope, Depends(customer_scope)],
    ) -> CustomerScope:
        return scope

    return Depends(dependency)


CustomerViewScope = Annotated[CustomerScope, _permission("CUSTOMER_VIEW")]
CustomerCreateScope = Annotated[CustomerScope, _permission("CUSTOMER_CREATE")]
CustomerUpdateScope = Annotated[CustomerScope, _permission("CUSTOMER_UPDATE")]
CustomerDeleteScope = Annotated[CustomerScope, _permission("CUSTOMER_DELETE")]
CustomerRestoreScope = Annotated[CustomerScope, _permission("CUSTOMER_RESTORE")]
CustomerExportScope = Annotated[CustomerScope, _permission("CUSTOMER_EXPORT")]
CustomerImportScope = Annotated[CustomerScope, _permission("CUSTOMER_IMPORT")]


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
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "code", "name", "status", "credit_limit", "created_at"
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


@router.get("/{customer_id}", response_model=ApiResponse[CustomerResponse])
def get_customer(
    customer_id: UUID,
    scope: CustomerViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerResponse]:
    """Return one visible customer."""
    customer = CustomerService(db).get(
        customer_id,
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    return ApiResponse(data=CustomerResponse.model_validate(customer))


@router.put("/{customer_id}", response_model=ApiResponse[CustomerResponse])
def update_customer(
    customer_id: UUID,
    data: CustomerUpdate,
    scope: CustomerUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerResponse]:
    """Replace one visible customer."""
    customer = CustomerService(db).update(
        customer_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
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
