"""Server-side enforcement of a firm's business profile.

Each firm is assigned a business profile — pharmacy, food, restaurant and so on —
which declares the features and modules that firm operates with. Until now that
declaration only filtered the desktop menu, so any firm could call any endpoint
regardless of its profile.

These dependencies close that gap. They are deliberately **write-only**: a
disabled feature or module blocks creates, updates and deletes but never reads,
so turning enforcement on cannot hide data a firm already has. A firm with no
profile assigned resolves to the platform default profile rather than being
denied.

Usage mirrors ``require_permission``::

    @router.post("", dependencies=[require_feature("BATCH_TRACKING")])
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Header, Request, params
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models import (
    BusinessFeature,
    BusinessModule,
    BusinessProfile,
    FirmBusinessProfile,
    ProfileFeature,
    ProfileModule,
)
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError

#: Methods that never mutate state and are therefore never gated.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True, slots=True)
class BusinessCapabilities:
    """Hold the feature and module codes a firm's profile enables."""

    profile_code: str | None
    features: frozenset[str]
    modules: frozenset[str]

    def has_feature(self, code: str) -> bool:
        """Return whether the profile enables one feature."""
        return code in self.features

    def has_module(self, code: str) -> bool:
        """Return whether the profile enables one module."""
        return code in self.modules


def resolve_capabilities(
    session: Session, firm_id: UUID | None
) -> BusinessCapabilities:
    """Resolve the active profile's capabilities, falling back to the default.

    A profile that carries no mapping row for a feature or module inherits that
    catalogue entry's ``default_enabled``. This used to be an inner join, which
    silently read a missing row as "disabled" while
    ``BusinessProfileFrameworkService.active_features`` -- the endpoint the
    desktop reads to decide what to render -- applied the default. The two
    disagreed for any profile missing a row: ``/active-features`` advertised
    BARCODE to RESTAURANT and SERVICE firms, whose forms then offered the field
    and were refused on save. A profile created through the API starts with no
    mapping rows at all, so seeding the missing rows would only have hidden it.
    One rule, both paths.
    """
    profile = resolve_profile(session, firm_id)
    if profile is None:
        # No profile and no platform default: enforce nothing rather than
        # locking every firm out on a configuration gap.
        return BusinessCapabilities(
            profile_code=None, features=frozenset(), modules=frozenset()
        )

    feature_rows = session.scalars(
        select(BusinessFeature).where(
            BusinessFeature.is_active.is_(True),
            BusinessFeature.is_deleted.is_(False),
        )
    ).all()
    feature_assignments = {
        row.feature_id: row.is_enabled
        for row in session.scalars(
            select(ProfileFeature).where(
                ProfileFeature.business_profile_id == profile.id,
                ProfileFeature.is_deleted.is_(False),
            )
        )
    }
    module_rows = session.scalars(
        select(BusinessModule).where(
            BusinessModule.is_active.is_(True),
            BusinessModule.is_deleted.is_(False),
        )
    ).all()
    # ProfileModule.is_visible is deliberately not read. Visibility decides
    # whether a workspace appears in the desktop's menu; it must not decide
    # whether a write is refused, or hiding a module from the sidebar would
    # quietly revoke the right to use it.
    module_assignments = {
        row.module_id: row.is_enabled
        for row in session.scalars(
            select(ProfileModule).where(
                ProfileModule.business_profile_id == profile.id,
                ProfileModule.is_deleted.is_(False),
            )
        )
    }
    return BusinessCapabilities(
        profile_code=profile.code,
        features=_enabled_codes(feature_rows, feature_assignments),
        modules=_enabled_codes(module_rows, module_assignments),
    )


def _enabled_codes(
    catalogue: Sequence[BusinessFeature] | Sequence[BusinessModule],
    assignments: Mapping[UUID, bool],
) -> frozenset[str]:
    """Return the codes enabled, an explicit row beating ``default_enabled``."""
    return frozenset(
        row.code for row in catalogue if assignments.get(row.id, row.default_enabled)
    )


def resolve_profile_id(session: Session, firm_id: UUID | None) -> UUID | None:
    """Return the id of the profile a firm operates under, or None.

    Exposed so other modules can key profile-scoped configuration off the same
    answer the gate uses. A firm-owned module must not resolve the assignment
    itself: two resolvers drift, and this one already handles the assignment,
    the platform default, and the case where neither exists.
    """
    profile = resolve_profile(session, firm_id)
    return None if profile is None else profile.id


def resolve_profile(session: Session, firm_id: UUID | None) -> BusinessProfile | None:
    """Return the firm's assigned profile, or the platform default.

    Public for the same reason ``resolve_profile_id`` is: a module that needs
    the profile row itself -- its code, for a response, or its settings -- must
    not re-resolve the assignment locally. Callers wanting only the id should
    take ``resolve_profile_id``.
    """
    if firm_id is not None:
        assigned = session.scalar(
            select(BusinessProfile)
            .join(
                FirmBusinessProfile,
                FirmBusinessProfile.business_profile_id == BusinessProfile.id,
            )
            .where(
                FirmBusinessProfile.firm_id == firm_id,
                FirmBusinessProfile.is_deleted.is_(False),
                FirmBusinessProfile.is_active.is_(True),
                BusinessProfile.is_deleted.is_(False),
            )
        )
        if assigned is not None:
            return assigned
    return session.scalar(
        select(BusinessProfile).where(
            BusinessProfile.is_default.is_(True),
            BusinessProfile.status == "ACTIVE",
            BusinessProfile.is_deleted.is_(False),
        )
    )


def get_capabilities(
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> BusinessCapabilities:
    """Expose the active firm's capabilities to a route that wants to branch."""
    return resolve_capabilities(db, x_firm_id)


def require_feature(*codes: str) -> params.Depends:
    """Block mutations when the firm's profile disables any named feature."""
    if not codes:
        raise ValueError("At least one feature code is required.")
    required = frozenset(codes)

    def dependency(
        request: Request,
        capabilities: Annotated[BusinessCapabilities, Depends(get_capabilities)],
    ) -> BusinessCapabilities:
        if request.method in SAFE_METHODS:
            return capabilities
        missing = sorted(required - capabilities.features)
        if missing:
            raise AuthorizationError(
                f"This firm's business profile does not enable: {', '.join(missing)}."
            )
        return capabilities

    return cast(params.Depends, Depends(dependency))


def require_module(code: str) -> params.Depends:
    """Block mutations when the firm's profile disables the named module."""

    def dependency(
        request: Request,
        capabilities: Annotated[BusinessCapabilities, Depends(get_capabilities)],
    ) -> BusinessCapabilities:
        if request.method in SAFE_METHODS:
            return capabilities
        if not capabilities.has_module(code):
            raise AuthorizationError(
                f"The {code} module is not enabled for this firm's business profile."
            )
        return capabilities

    return cast(params.Depends, Depends(dependency))


def _is_populated(value: object) -> bool:
    """Return whether a submitted value actually exercises a feature.

    Blank is not populated, and an empty collection is blank: a document that
    carries no attachments must not be refused because the field was present
    and empty. ``False`` is blank too -- an unticked box is not a use of the
    feature. A zero *number* is populated, because somebody typed it.
    """
    if value is None or value is False:
        return False
    if isinstance(value, str | bytes | list | tuple | set | dict):
        return len(value) > 0
    return True


def assert_feature_fields(
    session: Session,
    firm_id: UUID | None,
    *,
    feature: str,
    values: Mapping[str, object],
) -> None:
    """Refuse a write that fills in fields belonging to a disabled feature.

    ``require_feature`` gates whole endpoints, which suits a feature that owns
    its own resource — a firm without BATCH_TRACKING has no business posting a
    batch at all. Most features are not like that. Expiry dates, barcodes,
    warranty periods and drug licences are optional *fields* on a resource
    every firm uses, so gating the endpoint would stop a firm creating products
    because it does not scan barcodes.

    This gates the capability instead of the resource: the write is refused
    only when it actually populates one of the named fields. A firm without
    EXPIRY_TRACKING can still create batches; it just cannot give one an expiry
    date, which is the thing the feature is about.

    Blank is not populated. Clearing a field, or leaving it alone, is always
    allowed -- otherwise turning a feature off would freeze every record that
    already carried the field, and the framework's rule is that enabling
    enforcement must never take away what a firm already has.

    Args:
        session: The request session, used to resolve the firm's profile.
        firm_id: The firm whose profile decides, or None for the platform
            default.
        feature: The feature code that owns these fields.
        values: The submitted field values, keyed by the name to report.

    Raises:
        AuthorizationError: If the profile disables the feature and the write
            populates at least one of the fields.

    """
    populated = sorted(name for name, value in values.items() if _is_populated(value))
    if not populated:
        return
    capabilities = resolve_capabilities(session, firm_id)
    if capabilities.profile_code is None:
        # No profile and no platform default. resolve_capabilities already
        # treats that as a configuration gap rather than a decision, and the
        # framework's rule is to enforce nothing rather than lock every firm
        # out of a field because nobody has seeded the catalogue yet.
        return
    if capabilities.has_feature(feature):
        return
    raise AuthorizationError(
        f"This firm's business profile does not enable {feature}, so "
        f"{', '.join(populated)} cannot be set."
    )
