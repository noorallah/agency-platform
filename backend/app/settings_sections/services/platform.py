"""The People and Firms subjects: what lives in the platform store.

Users, roles, templates, memberships and firms exist only in the platform
schema, so these readers take a **platform** session and are registered apart
from ``SECTIONS``, whose readers take the firm's own store. Business profiles
are the exception: they live in the firm stores, so the Firms reader counts
them on the store the Business profiles screen reads (``get_db``), handed in
beside the platform one. Like every other reader, they only select.

Each reader takes the firm the caller administers, or ``None`` for a platform
administrator, and counts what the matching list screen shows that caller --
the same scoping as ``list_roles``, ``list_user_templates`` and ``list_users``
-- so a step never counts a row its screen would not list.

The orders: a user template bundles roles and a user is made from a template
or given roles, so roles come first and templates before users; a membership
needs a user and a firm. Business profiles before firms is **decided by the
loop**: a firm can be saved without one, but its profile is picked from that
list.
"""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.business.models.framework import BusinessProfile
from app.core.security.authorization import Principal
from app.firms.models import Firm
from app.identity.models import PlatformAdmin, Role, User, UserFirm, UserTemplate
from app.identity.system_seed import FIRM_ROLE_CODES, HIDDEN_SYSTEM_ROLE_CODES
from app.settings_sections.services.steps import (
    DONE,
    NONE_YET,
    OPTIONAL,
    TODO,
    SettingsStep,
    counted,
)

PlatformSectionReader = Callable[[Session, Session, UUID | None], list[SettingsStep]]


def _count(session: Session, model: type[object], *where: ColumnElement[bool]) -> int:
    """Count the rows of ``model`` that meet ``where``."""
    return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


def _roles_step(session: Session, firm_id: UUID | None) -> SettingsStep:
    """Count the roles the Roles screen lists, ready-made and the firm's own."""
    shown: list[ColumnElement[bool]] = [
        Role.is_deleted.is_(False),
        Role.code.not_in(HIDDEN_SYSTEM_ROLE_CODES),
    ]
    ready_made: ColumnElement[bool]
    own: ColumnElement[bool]
    if firm_id is None:
        ready_made = Role.is_system.is_(True)
        own = Role.is_system.is_(False)
    else:
        ready_made = Role.code.in_(FIRM_ROLE_CODES)
        own = Role.firm_id == firm_id
        shown.append(or_(own, ready_made))
    seeded = _count(session, Role, *shown, ready_made)
    made = _count(session, Role, *shown, own, ~ready_made)
    if not seeded + made:
        return SettingsStep("roles", TODO, NONE_YET)
    parts = [f"{seeded} ready-made"] if seeded else []
    if made:
        parts.append(f"{made} your own")
    return SettingsStep("roles", DONE, ", ".join(parts))


def _templates_step(session: Session, firm_id: UUID | None) -> SettingsStep:
    """Count the templates the User Templates screen lists."""
    shown: list[ColumnElement[bool]] = [UserTemplate.is_deleted.is_(False)]
    if firm_id is not None:
        shown.append(
            or_(UserTemplate.firm_id == firm_id, UserTemplate.firm_id.is_(None))
        )
    count = _count(session, UserTemplate, *shown)
    detail = counted(count, "template", "templates") if count else NONE_YET
    return SettingsStep("user-templates", OPTIONAL, detail)


def _members(firm_id: UUID) -> ColumnElement[bool]:
    """Say a membership is a live, switched-on one in the firm."""
    return (
        (UserFirm.firm_id == firm_id)
        & UserFirm.is_active.is_(True)
        & UserFirm.is_deleted.is_(False)
    )


def _users_step(session: Session, firm_id: UUID | None) -> SettingsStep:
    """Count the switched-on people the Users screen lists."""
    shown: list[ColumnElement[bool]] = [
        User.is_deleted.is_(False),
        User.is_active.is_(True),
    ]
    if firm_id is not None:
        # The firm's list leaves platform administrators out, as list_users does.
        shown += [
            User.id.in_(select(UserFirm.user_id).where(_members(firm_id))),
            ~User.id.in_(
                select(PlatformAdmin.user_id).where(PlatformAdmin.is_deleted.is_(False))
            ),
        ]
    count = _count(session, User, *shown)
    if not count:
        return SettingsStep("users", TODO, NONE_YET)
    return SettingsStep("users", DONE, counted(count, "person", "people"))


def _memberships_step(session: Session) -> SettingsStep:
    """Count the live memberships across firms, for a platform administrator."""
    live = (UserFirm.is_active.is_(True), UserFirm.is_deleted.is_(False))
    count = _count(session, UserFirm, *live)
    if not count:
        return SettingsStep("user-firms", OPTIONAL, NONE_YET)
    firms = (
        session.scalar(select(func.count(func.distinct(UserFirm.firm_id))).where(*live))
        or 0
    )
    detail = (
        f"{counted(count, 'membership', 'memberships')} in "
        f"{counted(firms, 'firm', 'firms')}"
    )
    return SettingsStep("user-firms", OPTIONAL, detail)


def people_section(
    session: Session, store: Session, firm_id: UUID | None
) -> list[SettingsStep]:
    """Return the steps of the People subject, in set-up order.

    User-firm assignments are a platform administrator's screen alone, so a
    caller working in one firm is answered no row for it, as they are offered
    no tab.
    """
    del store
    steps = [
        _roles_step(session, firm_id),
        _templates_step(session, firm_id),
        _users_step(session, firm_id),
    ]
    if firm_id is None:
        steps.append(_memberships_step(session))
    return steps


def firms_section(
    session: Session, store: Session, firm_id: UUID | None
) -> list[SettingsStep]:
    """Return the two steps of the Firms subject, in set-up order.

    Only a platform administrator is answered (``PLATFORM_SECTIONS``), so the
    counts are the whole installation's and ``firm_id`` is not read. The
    profiles are counted on ``store``: ``business_profiles`` is not a platform
    table, and reading it on the platform session answered 503.
    """
    del firm_id
    profiles = _count(
        store,
        BusinessProfile,
        BusinessProfile.is_deleted.is_(False),
        BusinessProfile.status == "ACTIVE",
    )
    firms = _count(session, Firm, Firm.is_deleted.is_(False), Firm.is_active.is_(True))
    return [
        SettingsStep(
            "business-profiles",
            OPTIONAL,
            counted(profiles, "profile", "profiles") if profiles else NONE_YET,
        ),
        SettingsStep(
            "firms",
            DONE if firms else TODO,
            counted(firms, "firm", "firms") if firms else NONE_YET,
        ),
    ]


def _may_see_people(principal: Principal) -> bool:
    """Say whether the caller is offered a People screen at all."""
    return principal.has_permission("USER_VIEW") or principal.has_permission(
        "ROLE_VIEW"
    )


def _may_see_firms(principal: Principal) -> bool:
    """Say whether the caller is offered the Firms screen, a platform one."""
    return principal.is_platform_admin


#: Each platform subject's reader, and who may ask about it. The answer is
#: counts of what the subject's own screens already list to the same caller.
PLATFORM_SECTIONS: dict[
    str, tuple[Callable[[Principal], bool], PlatformSectionReader]
] = {
    "people": (_may_see_people, people_section),
    "firms": (_may_see_firms, firms_section),
}


__all__ = ["PLATFORM_SECTIONS", "firms_section", "people_section"]
