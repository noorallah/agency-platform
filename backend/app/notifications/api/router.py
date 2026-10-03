"""Firm-scoped REST endpoints for the bell (PLT-2)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.common.scope import RequiredFirmScope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.notifications.schemas import (
    NotificationReadWrite,
    NotificationRecord,
    NotificationsRecord,
)
from app.notifications.services import NotificationService

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Notifications"],
    responses=STANDARD_ERROR_RESPONSES,
)


@router.get("", response_model=ApiResponse[NotificationsRecord])
def list_notifications(
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[NotificationsRecord]:
    """Return what waits for the caller in this firm, and how many are unseen.

    Membership is the only gate: each notification is offered only to a
    person holding a permission to act on it, so the list is empty rather
    than refused for someone who can act on nothing.
    """
    found = NotificationService(db).for_person(
        scope.firm_id, scope.principal, scope.actor_id
    )
    items = [
        NotificationRecord(
            key=item.key,
            kind=item.kind,
            title=item.title,
            detail=item.detail,
            count=item.count,
            at=item.at,
            read=read,
        )
        for item, read in found
    ]
    return ApiResponse(
        data=NotificationsRecord(
            items=items, unread=sum(1 for item in items if not item.read)
        )
    )


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_notifications_read(
    data: NotificationReadWrite,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> Response:
    """Mark notifications seen by the caller, by key."""
    NotificationService(db).mark_read(scope.firm_id, scope.actor_id, data.keys)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
