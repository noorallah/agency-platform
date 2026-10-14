"""Where the firm stands on each step of a Settings subject.

The desktop calls this once when a subject is opened. **Membership is the
gate**, as it is for ``/api/v1/firm-members``: the answer is counts and on/off
words, nothing a member of the firm could act on, and the screens it leads to
keep their own permissions.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.scope import RequiredFirmScope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.settings_sections.schemas import (
    SettingsSectionStateResponse,
    SettingsStepResponse,
)
from app.settings_sections.services import TODO, section_state

router = APIRouter(
    prefix="/api/v1/settings-sections",
    tags=["Settings sections"],
    responses=STANDARD_ERROR_RESPONSES,
)


@router.get(
    "/{section}/state", response_model=ApiResponse[SettingsSectionStateResponse]
)
def settings_section_state(
    section: str,
    scope: RequiredFirmScope,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[SettingsSectionStateResponse]:
    """Return every step of one Settings subject, in set-up order.

    Args:
        section: The subject's code, such as ``tax``.
        scope: The resolved firm scope; membership in it is the only gate.
        db: The firm's own store. Nothing is written to it.

    Returns:
        The steps, and how many of them the firm still has to do.

    """
    steps = section_state(db, scope.firm_id, section)
    return ApiResponse(
        data=SettingsSectionStateResponse(
            section=section,
            todo_count=sum(1 for step in steps if step.state == TODO),
            steps=[
                SettingsStepResponse(
                    code=step.code, state=step.state, detail=step.detail
                )
                for step in steps
            ],
        )
    )
