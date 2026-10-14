"""The pieces every Settings subject's reader is built from.

They live apart from the registry so that each subject's module can import
them without importing the registry that imports it. Like the readers, every
helper here only selects.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

DONE: Literal["DONE"] = "DONE"
TODO: Literal["TODO"] = "TODO"
OPTIONAL: Literal["OPTIONAL"] = "OPTIONAL"

NONE_YET = "None yet"
SAVED = "Set for this firm"
LEFT_AS_IT_COMES = "Left as it comes"


@dataclass(frozen=True, slots=True)
class SettingsStep:
    """One set-up step and where the firm stands on it."""

    code: str
    state: Literal["DONE", "TODO", "OPTIONAL"]
    detail: str


SectionReader = Callable[[Session, UUID], list[SettingsStep]]


def counted(count: int, singular: str, plural: str) -> str:
    """Return ``count`` with the noun that agrees with it."""
    return f"{count} {singular if count == 1 else plural}"


def live_count(
    session: Session,
    model: type[Any],
    firm_id: UUID,
    *conditions: ColumnElement[bool],
) -> int:
    """Count the firm's live rows of ``model`` that meet ``conditions``."""
    return (
        session.scalar(
            select(func.count())
            .select_from(model)
            .where(
                model.firm_id == firm_id,
                model.is_deleted.is_(False),
                *conditions,
            )
        )
        or 0
    )


def saved_step(
    session: Session, model: type[Any], firm_id: UUID, code: str
) -> SettingsStep:
    """Say whether the firm has saved its own row of a one-row settings table."""
    saved = live_count(session, model, firm_id)
    return SettingsStep(code, OPTIONAL, SAVED if saved else LEFT_AS_IT_COMES)


def counted_step(
    session: Session,
    model: type[Any],
    firm_id: UUID,
    code: str,
    nouns: tuple[str, str],
    *conditions: ColumnElement[bool],
) -> SettingsStep:
    """Count what the firm holds of an optional list, or say it holds none."""
    count = live_count(session, model, firm_id, *conditions)
    return SettingsStep(code, OPTIONAL, counted(count, *nouns) if count else NONE_YET)


def switch_step(
    session: Session, model: type[Any], firm_id: UUID, code: str
) -> SettingsStep:
    """Say whether a firm's one-row ``is_enabled`` switch is on.

    A firm that never saved the row reads as off, which is what every one of
    these switches defaults to.
    """
    enabled = session.scalar(
        select(model.is_enabled).where(
            model.firm_id == firm_id, model.is_deleted.is_(False)
        )
    )
    return SettingsStep(code, OPTIONAL, "On" if enabled else "Off")


__all__ = [
    "DONE",
    "LEFT_AS_IT_COMES",
    "NONE_YET",
    "OPTIONAL",
    "SAVED",
    "TODO",
    "SectionReader",
    "SettingsStep",
    "counted",
    "counted_step",
    "live_count",
    "saved_step",
    "switch_step",
]
