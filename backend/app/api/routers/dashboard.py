"""Protected platform administration dashboard endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.core.security.authorization import Principal, require_any_permission
from app.firms.models import Firm
from app.identity.models import Permission, Role, User

router = APIRouter(
    prefix="/api/v1/dashboard", tags=["Dashboard"], responses=STANDARD_ERROR_RESPONSES
)


class DashboardSummary(BaseModel):
    """Return platform administration counts for the authenticated administrator."""

    model_config = ConfigDict(extra="forbid")

    firms: int | None
    users: int | None
    roles: int | None
    permissions: int | None


@router.get("", response_model=ApiResponse[DashboardSummary])
def get_dashboard(
    principal: Annotated[
        Principal,
        Depends(
            require_any_permission(
                "FIRM_VIEW", "USER_VIEW", "ROLE_VIEW", "PERMISSION_VIEW"
            )
        ),
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
        )
    )


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
