"""The Business profile subject: what the firm's profile switches on, and its fields.

Every reader selects and nothing else, like the Tax subject's. Nothing here is
owed: a firm with no profile is never gated, and every field, rule and unit
set is optional, so each step is OPTIONAL.

Fields, field rules and unit sets each come in two kinds: the firm's own, and
the shared catalogue (``firm_id`` null) offered to every firm. A step counts
both, because both are what the firm's forms offer, and says which is which.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.business.gating import resolve_capabilities, resolve_profile
from app.business.models.framework import (
    AttributeDefinition,
    BusinessFeature,
    BusinessModule,
    CategoryAttributeRule,
    FirmAttributeSwitch,
)
from app.settings_sections.services.firm import profile_step
from app.settings_sections.services.steps import (
    NONE_YET,
    OPTIONAL,
    SettingsStep,
)
from app.uom.models.unit_set import UnitSet

_NO_PROFILE = "No profile: nothing is switched off"


def _own_and_shared(
    session: Session,
    model: type[Any],
    firm_id: UUID,
    *conditions: ColumnElement[bool],
) -> tuple[int, int]:
    """Count the firm's own live rows of ``model`` and the shared ones."""
    rows = session.execute(
        select(model.firm_id.is_(None), func.count())
        .where(
            or_(model.firm_id == firm_id, model.firm_id.is_(None)),
            model.is_deleted.is_(False),
            *conditions,
        )
        .group_by(model.firm_id.is_(None))
    ).all()
    counts = {bool(shared): count for shared, count in rows}
    return counts.get(False, 0), counts.get(True, 0)


def _own_and_shared_detail(own: int, shared: int) -> str:
    """Say how many of the firm's own and how many shared, or none."""
    parts = [f"{own} own"] if own else []
    if shared:
        parts.append(f"{shared} shared")
    return ", ".join(parts) if parts else NONE_YET


def _capability_step(
    session: Session, firm_id: UUID, code: str, kind: str
) -> SettingsStep:
    """Count what the firm's profile switches on of features or modules.

    Read through ``resolve_capabilities``, the one resolver the gate uses, so
    the count is what the server enforces: an assigned profile or the platform
    default, a missing mapping row taking the catalogue's default.
    """
    if resolve_profile(session, firm_id) is None:
        return SettingsStep(code, OPTIONAL, _NO_PROFILE)
    capabilities = resolve_capabilities(session, firm_id)
    model: type[BusinessFeature] | type[BusinessModule]
    if kind == "features":
        model, enabled = BusinessFeature, capabilities.features
    else:
        model, enabled = BusinessModule, capabilities.modules
    total = (
        session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.is_active.is_(True), model.is_deleted.is_(False))
        )
        or 0
    )
    return SettingsStep(code, OPTIONAL, f"{len(enabled)} of {total} {kind} on")


def _definitions_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the active fields the firm is offered: its own and the shared.

    A shared field the firm switched off is not offered, so it is not counted.
    """
    hidden = select(FirmAttributeSwitch.attribute_definition_id).where(
        FirmAttributeSwitch.firm_id == firm_id,
        FirmAttributeSwitch.is_enabled.is_(False),
        FirmAttributeSwitch.is_deleted.is_(False),
    )
    own, shared = _own_and_shared(
        session,
        AttributeDefinition,
        firm_id,
        AttributeDefinition.is_active.is_(True),
        AttributeDefinition.id.not_in(hidden),
    )
    return SettingsStep(
        "attribute-definitions", OPTIONAL, _own_and_shared_detail(own, shared)
    )


def _mandatory_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the rules making a field compulsory: the firm's own and the shared.

    A rule names a field, so where the firm is offered no field at all the
    step says so rather than inviting a rule that has nothing to name.
    """
    own, shared = _own_and_shared(
        session,
        CategoryAttributeRule,
        firm_id,
        CategoryAttributeRule.is_mandatory.is_(True),
    )
    if own or shared:
        return SettingsStep(
            "mandatory-attributes", OPTIONAL, _own_and_shared_detail(own, shared)
        )
    fields = sum(
        _own_and_shared(
            session,
            AttributeDefinition,
            firm_id,
            AttributeDefinition.is_active.is_(True),
        )
    )
    return SettingsStep(
        "mandatory-attributes",
        OPTIONAL,
        NONE_YET if fields else f"{NONE_YET}: add a field first",
    )


def _unit_sets_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the active unit sets the firm is offered: its own and the shared."""
    own, shared = _own_and_shared(
        session, UnitSet, firm_id, UnitSet.is_active.is_(True)
    )
    return SettingsStep("unit-sets", OPTIONAL, _own_and_shared_detail(own, shared))


def business_profile_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the six steps of the Business profile subject, in set-up order."""
    return [
        profile_step(session, firm_id, "profile-assignment"),
        _capability_step(session, firm_id, "feature-management", "features"),
        _capability_step(session, firm_id, "module-configuration", "modules"),
        _definitions_step(session, firm_id),
        _mandatory_step(session, firm_id),
        _unit_sets_step(session, firm_id),
    ]


__all__ = ["business_profile_section"]
