"""Firm-scoped REST endpoints for approval rules, sign-offs and rejection (PLT-1)."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.approvals.services import (
    KINDS,
    ApprovalChainService,
    ApprovalDecisionWrite,
    ApprovalRejectWrite,
    ApprovalRuleResponse,
    ApprovalRulesWrite,
    ApprovalStatusResponse,
    kind_of,
)
from app.common.scope import ResolvedFirmScope, firm_any_permission_scope
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.document_framework.schemas.bulk_actions import BulkActionResult, BulkRow
from app.document_framework.services.bulk_actions import run_each

router = APIRouter(
    prefix="/api/v1/approvals",
    tags=["Approvals"],
    responses=STANDARD_ERROR_RESPONSES,
)

_APPROVE_CODES = sorted({kind.approve_code for kind in KINDS.values()})
_SETTINGS_CODES = sorted({kind.settings_code for kind in KINDS.values()})

#: Whoever may approve sales or purchases opens the queue; which documents a
#: person may decide is then judged per type.
ApprovalScope = Annotated[ResolvedFirmScope, firm_any_permission_scope(*_APPROVE_CODES)]
#: The rules are read by whoever approves under them or may change them.
ApprovalRulesReadScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope(*_APPROVE_CODES, *_SETTINGS_CODES),
]
#: The rules are a sales or purchase setting, judged per type.
ApprovalSettingsScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope(*_SETTINGS_CODES)
]


class ApprovalBulkRejectRequest(BaseModel):
    """Reject many documents of one type, for one reason."""

    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(min_length=1, max_length=30)
    items: list[BulkRow] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


def _require(scope: ResolvedFirmScope, code: str) -> None:
    """Refuse a person without the type's own permission."""
    if not scope.principal.has_permission(code):
        raise ValidationError(f"Deciding this needs {code}.")


def _approver(
    db: Session, scope: ResolvedFirmScope, document_type: str, document_id: UUID
) -> Callable[[], object]:
    """Return the module's own approval of one document, as its route runs it."""

    def approve() -> object:
        """Approve through the document's own service, which commits."""
        if document_type == "SALES_ORDER":
            from app.sales_order.services.sales_order_service import (
                SalesOrderService,
            )

            return SalesOrderService(db).approve_order(
                document_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
            )
        if document_type == "SALES_INVOICE":
            from app.sales_invoice.services.sales_invoice_service import (
                SalesInvoiceService,
            )

            return SalesInvoiceService(db).approve_invoice(
                document_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
            )
        if document_type == "PURCHASE_ORDER":
            from app.purchase.services.purchase_service import PurchaseService

            return PurchaseService(db).approve_order(
                document_id,
                firm_scope=scope.firm_id,
                actor_id=scope.actor_id,
                may_exceed_budget=scope.principal.has_permission(
                    "PURCHASE_APPROVE_OVER_BUDGET"
                ),
            )
        from app.purchase_invoice.services.purchase_invoice_service import (
            PurchaseInvoiceService,
        )

        return PurchaseInvoiceService(db).approve_invoice(
            document_id,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
            may_exceed_tolerance=scope.principal.has_permission(
                "PURCHASE_APPROVE_OVER_TOLERANCE"
            ),
        )

    return approve


def _rule_responses(rows: list[object]) -> list[ApprovalRuleResponse]:
    """Shape rule rows."""
    return [
        ApprovalRuleResponse.model_validate(row, from_attributes=True) for row in rows
    ]


@router.get("/rules", response_model=ApiResponse[list[ApprovalRuleResponse]])
def list_approval_rules(
    scope: ApprovalRulesReadScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ApprovalRuleResponse]]:
    """Return every approval rule of the firm."""
    return ApiResponse(
        data=_rule_responses(list(ApprovalChainService(db).rules(scope.firm_id)))
    )


@router.put(
    "/rules/{document_type}",
    response_model=ApiResponse[list[ApprovalRuleResponse]],
)
def replace_approval_rules(
    document_type: str,
    data: ApprovalRulesWrite,
    scope: ApprovalSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ApprovalRuleResponse]]:
    """Replace one document type's rules (levels 1 to 3, by amount and role)."""
    _require(scope, kind_of(document_type).settings_code)
    rows = ApprovalChainService(db).replace_rules(
        scope.firm_id, document_type, data, actor_id=scope.actor_id
    )
    return ApiResponse(data=_rule_responses(list(rows)), message="Rules saved.")


@router.get("/pending", response_model=ApiResponse[list[ApprovalStatusResponse]])
def pending_approvals(
    scope: ApprovalScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ApprovalStatusResponse]]:
    """Return what awaits the caller's sign-off, oldest first."""
    codes = {code for code in _APPROVE_CODES if scope.principal.has_permission(code)}
    return ApiResponse(
        data=ApprovalChainService(db).pending_for(
            scope.firm_id, scope.actor_id, approve_codes=codes
        )
    )


@router.post("/sign-off", response_model=ApiResponse[ApprovalStatusResponse])
def sign_off(
    data: ApprovalDecisionWrite,
    scope: ApprovalScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ApprovalStatusResponse]:
    """Sign the next level; the last sign-off approves the document."""
    _require(scope, kind_of(data.document_type).approve_code)
    answer = ApprovalChainService(db).sign_off(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        approve=_approver(db, scope, data.document_type, data.document_id),
    )
    return ApiResponse(data=answer, message="Signed off.")


@router.post("/reject", response_model=ApiResponse[ApprovalStatusResponse])
def reject(
    data: ApprovalRejectWrite,
    scope: ApprovalScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ApprovalStatusResponse]:
    """Reject one document with a reason."""
    _require(scope, kind_of(data.document_type).approve_code)
    answer = ApprovalChainService(db).reject(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=answer, message="Rejected.")


@router.post("/bulk-reject", response_model=ApiResponse[BulkActionResult])
def bulk_reject(
    data: ApprovalBulkRejectRequest,
    scope: ApprovalScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Reject each ticked document on its own, for one reason."""
    kind = kind_of(data.document_type)
    _require(scope, kind.approve_code)
    service = ApprovalChainService(db)

    def load(document_id: UUID) -> object:
        """Read one document for its version and number."""
        return service.document(kind, document_id, scope.firm_id)

    def act(document_id: UUID) -> object:
        """Reject one document; the service commits."""
        return service.reject(
            ApprovalRejectWrite(
                document_type=data.document_type,
                document_id=document_id,
                reason=data.reason,
            ),
            firm_id=scope.firm_id,
            actor_id=scope.actor_id,
        )

    result = run_each(
        db,
        data.items,
        load=load,
        act=act,
        number=lambda row: str(getattr(row, kind.number_field)),
    )
    return ApiResponse(data=result)


@router.get(
    "/{document_type}/{document_id}",
    response_model=ApiResponse[ApprovalStatusResponse],
)
def approval_status(
    document_type: str,
    document_id: UUID,
    scope: ApprovalScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ApprovalStatusResponse]:
    """Return where one document stands in its approval chain."""
    return ApiResponse(
        data=ApprovalChainService(db).status(
            document_type, document_id, firm_id=scope.firm_id
        )
    )
