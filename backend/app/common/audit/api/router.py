"""Read-only REST access to the audit trail.

The trail is not centralised. Platform administration writes to the platform
schema; every firm-owned mutation writes to that firm's own store. This router
exposes one endpoint whose scope follows the request's firm context, so the
session that ``get_db`` resolves is already the correct trail to read:

* no ``X-Firm-ID`` and platform authority -> the platform trail
* ``X-Firm-ID`` plus an active membership -> that firm's trail

There is deliberately no cross-firm view. Reading every firm's history means
iterating firm stores, which no single query can do.
"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.schemas import AuditLogFilters, AuditLogResponse
from app.common.audit.services import AuditLogReader
from app.core.database.dependencies import get_db, get_platform_db
from app.core.exceptions import AuthorizationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import PaginatedResponse
from app.core.security.authorization import Principal, require_permission
from app.firms.models import Firm
from app.identity.models import UserFirm

router = APIRouter(
    prefix="/api/v1/audit-logs",
    tags=["Audit"],
    responses=STANDARD_ERROR_RESPONSES,
)


class AuditScope:
    """Carry the authenticated principal and the trail it may read."""

    def __init__(self, principal: Principal, firm_id: UUID | None) -> None:
        """Store the identity and the firm whose trail is in scope."""
        self.principal = principal
        self.firm_id = firm_id


def audit_scope(
    principal: Annotated[Principal, Depends(require_permission("AUDIT_LOG_VIEW"))],
    platform_db: Annotated[Session, Depends(get_platform_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> AuditScope:
    """Resolve which audit trail the caller may read."""
    if x_firm_id is None:
        # The platform trail records user, role, and firm administration.
        if "platform_admin" not in principal.roles:
            raise AuthorizationError(
                "Reading the platform audit trail requires platform authority."
            )
        return AuditScope(principal, None)
    if "platform_admin" in principal.roles:
        firm = platform_db.scalar(
            select(Firm.id).where(
                Firm.id == x_firm_id,
                Firm.is_active.is_(True),
                Firm.is_deleted.is_(False),
            )
        )
        if firm is None:
            raise AuthorizationError("The selected firm is inactive or unavailable.")
        return AuditScope(principal, x_firm_id)
    if not isinstance(principal.subject, UUID):
        raise AuthorizationError("An authorized active firm is required.")
    membership = platform_db.scalar(
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
    return AuditScope(principal, x_firm_id)


@router.get("", response_model=PaginatedResponse[AuditLogResponse])
def list_audit_logs(
    scope: Annotated[AuditScope, Depends(audit_scope)],
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    actor_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_direction: Annotated[Literal["asc", "desc"], Query()] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[AuditLogResponse]:
    """Return one page of audit events for the trail in scope."""
    params = PaginationParams(page=page, page_size=page_size)
    filters = AuditLogFilters(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
    )
    rows, total = AuditLogReader(db).list_events(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[AuditLogResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )
