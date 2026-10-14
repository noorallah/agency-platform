"""Where the firm stands on each step of a Settings subject.

The desktop calls this once when a subject is opened. **Membership is the
gate**, as it is for ``/api/v1/firm-members``: the answer is counts and on/off
words, nothing a member of the firm could act on, and the screens it leads to
keep their own permissions.

People and Firms are the exception, and have a route of their own: they live
in the platform store, so they are read there, and each is answered only to
whoever its screens are offered to (``PLATFORM_SECTIONS``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.scope import OptionalFirmScope, RequiredFirmScope
from app.core.database.dependencies import get_db, get_platform_db
from app.core.exceptions import AuthorizationError, ResourceNotFoundError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.settings_sections.schemas import (
    SettingsSectionStateResponse,
    SettingsStepResponse,
)
from app.settings_sections.services import TODO, SettingsStep, section_state
from app.settings_sections.services.platform import PLATFORM_SECTIONS

router = APIRouter(
    prefix="/api/v1/settings-sections",
    tags=["Settings sections"],
    responses=STANDARD_ERROR_RESPONSES,
)


def _section_response(
    section: str, steps: list[SettingsStep]
) -> ApiResponse[SettingsSectionStateResponse]:
    """Wrap a subject's steps, counting the ones still to do."""
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


@router.get(
    "/platform/{section}/state",
    response_model=ApiResponse[SettingsSectionStateResponse],
)
def platform_settings_section_state(
    section: str,
    scope: OptionalFirmScope,
    db: Annotated[Session, Depends(get_platform_db)],
) -> ApiResponse[SettingsSectionStateResponse]:
    """Return every step of a Settings subject kept in the platform store.

    People and Firms are users, roles and firms, which live only in the
    platform schema, so this reads the platform store whatever ``X-Firm-ID``
    says. A platform administrator is answered for the installation, as the
    People and Firms screens list it to them; anybody else for the firm they
    are working in, whose membership ``OptionalFirmScope`` has checked. Each
    subject names who may ask, which is who its screens are offered to.

    Args:
        section: The subject's code, ``people`` or ``firms``.
        scope: The caller, and the firm they are working in if they named one.
        db: The platform store. Nothing is written to it.

    Returns:
        The steps, and how many of them are still to do.

    Raises:
        ResourceNotFoundError: If no platform subject has this code.
        AuthorizationError: If the caller is not offered the subject, or names
            no firm without being a platform administrator.

    """
    entry = PLATFORM_SECTIONS.get(section)
    if entry is None:
        raise ResourceNotFoundError("Settings section not found.")
    may_ask, reader = entry
    principal = scope.principal
    if not may_ask(principal):
        raise AuthorizationError("This settings section is not offered to you.")
    if principal.is_platform_admin:
        firm_id = None
    elif scope.firm_id is None:
        raise AuthorizationError(
            "X-Firm-ID is required: people are set up in one firm unless you "
            "are a platform administrator."
        )
    else:
        firm_id = scope.firm_id
    return _section_response(section, reader(db, firm_id))


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
    return _section_response(section, section_state(db, scope.firm_id, section))
