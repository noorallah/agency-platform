"""The people who belong to the firm the request is scoped to.

Three screens needed this list and no two could share one: assigning a route
reads it behind ``TERRITORY_ASSIGN_SALESMEN``, agreeing a commission rate reads
it behind ``COMMISSION_VIEW``, and the sales-order form -- which records which
salesman took a phone order -- holds neither. ``/api/v1/users`` is guarded by
``USER_VIEW``, a platform-admin permission none of those roles hold, so a
fourth copy behind a fourth permission was the direction of travel.

**Membership is the gate.** A firm's own directory of names is not a
privilege: everybody in the firm already knows who their colleagues are. What
needs a permission is *acting* on a person -- putting them on a route, setting
the rate they are paid -- and those gates stay exactly where they are. So this
endpoint composes ``RequiredFirmScope``, which resolves an authenticated
caller, an active firm, and an active membership in it, and nothing more.

``users`` and ``user_firms`` live only in the platform schema, which is why
the query runs through ``FirmMetadataReader`` -- the one module allowed to
touch them. The router deliberately takes no ``get_db`` dependency, so no
tenant session is opened at all.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.common.scope import RequiredFirmScope
from app.core.database.dependencies import get_platform_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse

router = APIRouter(
    prefix="/api/v1/firm-members",
    tags=["Firm directory"],
    responses=STANDARD_ERROR_RESPONSES,
)


class FirmMemberResponse(BaseModel):
    """One person who belongs to this firm."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    full_name: str
    email: str


@router.get("", response_model=ApiResponse[list[FirmMemberResponse]])
def list_firm_members(
    scope: RequiredFirmScope,
    db: Annotated[Session, Depends(get_platform_db)],
) -> ApiResponse[list[FirmMemberResponse]]:
    """List the firm's active members, in name order.

    Args:
        scope: The resolved firm scope; membership in it is the only gate.
        db: A platform-schema session -- `users` and `user_firms` are there
            and nowhere else.

    Returns:
        Every active, undeleted member of the firm named by ``X-Firm-ID``.

    """
    members = FirmMetadataReader(db).active_members(scope.firm_id)
    return ApiResponse(
        data=[
            FirmMemberResponse(
                user_id=member.user_id,
                full_name=member.full_name,
                email=member.email,
            )
            for member in members
        ]
    )
