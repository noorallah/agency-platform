"""Protected platform administration dashboard endpoint."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.core.security.authorization import Principal, require_platform_admin
from app.firms.models import Firm
from app.identity.models import Permission, Role, User, UserFirm

router = APIRouter(
    prefix="/api/v1/dashboard", tags=["Dashboard"], responses=STANDARD_ERROR_RESPONSES
)


RECENT_FIRMS_LIMIT = 5
SYSTEM_ACTIVITY_LIMIT = 10


class RecentFirm(BaseModel):
    """One firm on the dashboard's "Recent Firms" panel."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    status: str
    created_at: datetime


class SystemActivity(BaseModel):
    """One row of the platform audit trail on the "System Activity" panel."""

    model_config = ConfigDict(extra="forbid")

    action: str
    entity_type: str
    entity_id: UUID
    actor_id: UUID | None
    created_at: datetime


class DashboardSummary(BaseModel):
    """Return platform administration counts for the authenticated administrator.

    `recent_firms` and `system_activity` fill the two panels the desktop has
    rendered since it was built; before D-RPT-20 nothing sent them, so both
    said "No recent ... activity available" on every database.
    """

    model_config = ConfigDict(extra="forbid")

    firms: int | None
    users: int | None
    roles: int | None
    permissions: int | None
    recent_firms: list[RecentFirm] = []
    system_activity: list[SystemActivity] = []


@router.get("", response_model=ApiResponse[DashboardSummary])
def get_dashboard(
    principal: Annotated[
        Principal,
        Depends(require_platform_admin()),
    ],
    db: Session = Depends(get_db),
) -> ApiResponse[DashboardSummary]:
    """Return counts of currently visible platform administration resources."""
    return ApiResponse(
        data=DashboardSummary(
            firms=_count_if_permitted(principal, "FIRM_VIEW", db, Firm),
            users=_count_if_permitted(principal, "USER_VIEW", db, User),
            roles=_count_if_permitted(principal, "ROLE_VIEW", db, Role),
            permissions=_count_if_permitted(
                principal, "PERMISSION_VIEW", db, Permission
            ),
            recent_firms=_recent_firms(principal, db),
            system_activity=_system_activity(principal, db),
        )
    )


def _subject_id(principal: Principal) -> UUID | None:
    """Return the caller's user id, or None when the subject is not one."""
    try:
        return UUID(str(principal.subject))
    except ValueError:
        return None


def _recent_firms(principal: Principal, db: Session) -> list[RecentFirm]:
    """Return the newest live firms the caller can reach.

    An `ALL_FIRMS` designation reaches every firm, so it sees every live one.
    A `PLATFORM` designation carries no firm bypass -- `GET /api/v1/me/firms`
    offers it only its own memberships -- so here, too, it sees the firms it
    holds an active membership in and no others.
    """
    statement = select(Firm).where(Firm.is_deleted.is_(False))
    if not principal.may_act_in_any_firm:
        user_id = _subject_id(principal)
        if user_id is None:
            return []
        statement = statement.where(
            Firm.id.in_(
                select(UserFirm.firm_id).where(
                    UserFirm.user_id == user_id,
                    UserFirm.is_active.is_(True),
                    UserFirm.is_deleted.is_(False),
                )
            )
        )
    statement = statement.order_by(Firm.created_at.desc(), Firm.id.desc()).limit(
        RECENT_FIRMS_LIMIT
    )
    return [
        RecentFirm(
            id=firm.id,
            code=firm.code,
            name=firm.name,
            status=firm.status,
            created_at=firm.created_at,
        )
        for firm in db.scalars(statement).all()
    ]


def _system_activity(principal: Principal, db: Session) -> list[SystemActivity]:
    """Return the newest rows of the platform audit trail the caller may read.

    Every row for an `ALL_FIRMS` designation; only the caller's own actions for
    a `PLATFORM` one, which administers the platform without reach into what
    other administrators did in firms it cannot enter. The session is the
    platform store (`/api/v1/dashboard` is a platform path), so these are the
    platform's rows; each firm's own trail stays in its own store.
    """
    statement = select(AuditLog)
    if not principal.may_act_in_any_firm:
        user_id = _subject_id(principal)
        if user_id is None:
            return []
        statement = statement.where(AuditLog.actor_id == user_id)
    statement = statement.order_by(
        AuditLog.created_at.desc(), AuditLog.id.desc()
    ).limit(SYSTEM_ACTIVITY_LIMIT)
    return [
        SystemActivity(
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            actor_id=row.actor_id,
            created_at=row.created_at,
        )
        for row in db.scalars(statement).all()
    ]


def _count_visible(
    db: Session, model: type[Firm] | type[User] | type[Role] | type[Permission]
) -> int:
    """Count a model's non-soft-deleted rows."""
    return int(
        db.scalar(
            select(func.count()).select_from(model).where(model.is_deleted.is_(False))
        )
        or 0
    )


def _count_if_permitted(
    principal: Principal,
    permission: str,
    db: Session,
    model: type[Firm] | type[User] | type[Role] | type[Permission],
) -> int | None:
    """Avoid exposing summary counts for resources the caller cannot view."""
    if permission not in principal.permissions:
        return None
    return _count_visible(db, model)
