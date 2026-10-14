"""Response schemas for the state of a Settings subject."""

from typing import Literal

from app.identity.schemas.api import ApiSchema

StepState = Literal["DONE", "TODO", "OPTIONAL"]


class SettingsStepResponse(ApiSchema):
    """One set-up step and where the firm stands on it."""

    code: str
    state: StepState
    detail: str


class SettingsSectionStateResponse(ApiSchema):
    """Every step of one Settings subject, in set-up order."""

    section: str
    todo_count: int
    steps: list[SettingsStepResponse]


__all__ = ["SettingsSectionStateResponse", "SettingsStepResponse", "StepState"]
