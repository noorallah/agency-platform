"""FastAPI routes for the reusable document lifecycle framework."""

# ruff: noqa: D102, D103, D107

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError, ConflictError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_platform_admin,
)
from app.document_framework.schemas import (
    DocumentLifecycleEventCreate,
    DocumentLifecycleEventResponse,
    DocumentNumberingRuleCreate,
    DocumentNumberingRuleResponse,
    DocumentNumberingRuleUpdate,
    DocumentStateCreate,
    DocumentStateResponse,
    DocumentStateUpdate,
    DocumentTypeCreate,
    DocumentTypeResponse,
    DocumentTypeUpdate,
)
from app.document_framework.services import DocumentFrameworkService
from app.firms.models import Firm
from app.identity.models import UserFirm

router = APIRouter(
    prefix="/api/v1/document-framework",
    tags=["Document framework"],
    responses=STANDARD_ERROR_RESPONSES,
)

PlatformPrincipal = Annotated[Principal, Depends(require_platform_admin())]


class DocumentScope:
    """Carry authenticated principal and resolved firm context."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError(
                "Document framework management requires a user principal."
            )
        return self.principal.subject


def document_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> DocumentScope:
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
        return DocumentScope(principal, x_firm_id)
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
    return DocumentScope(principal, x_firm_id)


def _service(db: Session) -> DocumentFrameworkService:
    return DocumentFrameworkService(db)


def _actor_id(principal: Principal) -> UUID:
    if not isinstance(principal.subject, UUID):
        raise RuntimeError(
            "Document framework administration requires a user principal."
        )
    return principal.subject


@router.get("/document-types", response_model=PaginatedResponse[DocumentTypeResponse])
def list_document_types(
    scope: Annotated[DocumentScope, Depends(document_scope)],
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[DocumentTypeResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_types(
        scope.firm_id,
        params.page,
        params.page_size,
        search,
        sort_by,
        sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[DocumentTypeResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/document-types",
    response_model=ApiResponse[DocumentTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_document_type(
    data: DocumentTypeCreate,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentTypeResponse]:
    row = _service(db).create_type(scope.firm_id, data, _actor_id(principal))
    db.commit()
    return ApiResponse(data=DocumentTypeResponse.model_validate(row))


@router.put(
    "/document-types/{document_type_id}",
    response_model=ApiResponse[DocumentTypeResponse],
)
def update_document_type(
    document_type_id: UUID,
    data: DocumentTypeUpdate,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentTypeResponse]:
    row = _service(db).update_type(
        scope.firm_id, document_type_id, data, _actor_id(principal)
    )
    db.commit()
    return ApiResponse(data=DocumentTypeResponse.model_validate(row))


@router.delete(
    "/document-types/{document_type_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_document_type(
    document_type_id: UUID,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_type(scope.firm_id, document_type_id, _actor_id(principal))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/document-states", response_model=PaginatedResponse[DocumentStateResponse])
def list_document_states(
    scope: Annotated[DocumentScope, Depends(document_scope)],
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    document_type_id: UUID | None = None,
    sort_by: Literal["code", "name", "sort_order", "created_at"] = "sort_order",
    sort_direction: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[DocumentStateResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_states(
        scope.firm_id,
        params.page,
        params.page_size,
        search,
        document_type_id,
        sort_by,
        sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[DocumentStateResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/document-states",
    response_model=ApiResponse[DocumentStateResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_document_state(
    data: DocumentStateCreate,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentStateResponse]:
    row = _service(db).create_state(scope.firm_id, data, _actor_id(principal))
    db.commit()
    return ApiResponse(data=DocumentStateResponse.model_validate(row))


@router.put(
    "/document-states/{state_id}",
    response_model=ApiResponse[DocumentStateResponse],
)
def update_document_state(
    state_id: UUID,
    data: DocumentStateUpdate,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentStateResponse]:
    row = _service(db).update_state(scope.firm_id, state_id, data, _actor_id(principal))
    db.commit()
    return ApiResponse(data=DocumentStateResponse.model_validate(row))


@router.delete("/document-states/{state_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_state(
    state_id: UUID,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_state(scope.firm_id, state_id, _actor_id(principal))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/numbering-rules",
    response_model=PaginatedResponse[DocumentNumberingRuleResponse],
)
def list_numbering_rules(
    scope: Annotated[DocumentScope, Depends(document_scope)],
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    document_type_id: UUID | None = None,
    sort_by: Literal["code", "name", "next_sequence", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[DocumentNumberingRuleResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_numbering_rules(
        scope.firm_id,
        params.page,
        params.page_size,
        search,
        document_type_id,
        sort_by,
        sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[DocumentNumberingRuleResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/numbering-rules",
    response_model=ApiResponse[DocumentNumberingRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_numbering_rule(
    data: DocumentNumberingRuleCreate,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentNumberingRuleResponse]:
    row = _service(db).create_numbering_rule(scope.firm_id, data, _actor_id(principal))
    db.commit()
    return ApiResponse(data=DocumentNumberingRuleResponse.model_validate(row))


@router.put(
    "/numbering-rules/{rule_id}",
    response_model=ApiResponse[DocumentNumberingRuleResponse],
)
def update_numbering_rule(
    rule_id: UUID,
    data: DocumentNumberingRuleUpdate,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentNumberingRuleResponse]:
    row = _service(db).update_numbering_rule(
        scope.firm_id, rule_id, data, _actor_id(principal)
    )
    db.commit()
    return ApiResponse(data=DocumentNumberingRuleResponse.model_validate(row))


@router.delete("/numbering-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_numbering_rule(
    rule_id: UUID,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_numbering_rule(scope.firm_id, rule_id, _actor_id(principal))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/numbering-rules/{rule_id}/preview",
    response_model=ApiResponse[str],
)
def preview_numbering_rule(
    rule_id: UUID,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    document_date: Annotated[date | None, Query()] = None,
    financial_year_label: str | None = None,
    branch_code: str | None = None,
    company_code: str | None = None,
    manual_number: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[str]:
    preview = _service(db).preview_number(
        rule_id,
        firm_id=scope.firm_id,
        financial_year_label=financial_year_label,
        branch_code=branch_code,
        company_code=company_code,
        document_date=document_date,
        manual_number=manual_number,
    )
    return ApiResponse(data=preview)


@router.get(
    "/documents/{document_id}/timeline",
    response_model=PaginatedResponse[DocumentLifecycleEventResponse],
)
def list_document_timeline(
    document_id: UUID,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    page: int = 1,
    page_size: int = 20,
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[DocumentLifecycleEventResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_timeline(
        scope.firm_id,
        document_id,
        params.page,
        params.page_size,
        sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[DocumentLifecycleEventResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/documents/{document_id}/events",
    response_model=ApiResponse[DocumentLifecycleEventResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_document_event(
    document_id: UUID,
    data: DocumentLifecycleEventCreate,
    principal: PlatformPrincipal,
    scope: Annotated[DocumentScope, Depends(document_scope)],
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentLifecycleEventResponse]:
    if data.source_document_id != document_id:
        raise ConflictError("The document identifier does not match the request body.")
    row = _service(db).record_event(scope.firm_id, data, _actor_id(principal))
    db.commit()
    return ApiResponse(data=DocumentLifecycleEventResponse.model_validate(row))
