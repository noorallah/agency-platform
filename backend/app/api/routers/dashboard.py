"""Protected platform administration dashboard endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.core.security.authorization import Principal, require_platform_admin
from app.firms.models import Firm
from app.identity.models import Permission, Role, User

router = APIRouter(
    prefix="/api/v1/dashboard", tags=["Dashboard"], responses=STANDARD_ERROR_RESPONSES
)


class DashboardSummary(BaseModel):
    """Return platform administration counts for the authenticated administrator."""

    model_config = ConfigDict(extra="forbid")

    firms: int
    users: int
    roles: int
    permissions: int


@router.get("", response_model=ApiResponse[DashboardSummary])
def get_dashboard(
    _: Annotated[Principal, Depends(require_platform_admin())],
    db: Session = Depends(get_db),
) -> ApiResponse[DashboardSummary]:
    """Return counts of currently visible platform administration resources."""
    return ApiResponse(
        data=DashboardSummary(
            firms=_count_visible(db, Firm),
            users=_count_visible(db, User),
            roles=_count_visible(db, Role),
            permissions=_count_visible(db, Permission),
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
