"""Read and change the agency's branding."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branding.models import AgencyBranding
from app.branding.schemas import AgencyBrandingResponse, AgencyBrandingWrite
from app.common.audit.services import record_audit
from app.common.audit.services.changes import record_change, row_state
from app.core.concurrency import assert_version
from app.core.exceptions import BusinessRuleError, ValidationError

#: A logo is shown at sign-in on every PC, before anything is cached, so it is
#: kept small. 1 MB is what the proposal promised the administrator.
MAX_LOGO_BYTES = 1024 * 1024

_ENTITY = "agency_branding"
#: The image is not text; the trail records its type and size instead.
_NOT_AUDITED = ("logo",)

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def logo_content_type(content: bytes) -> str:
    """Name the image type from its first bytes, refusing anything else.

    The filename is not consulted: a ``.png`` that is really a text file is
    the case this exists for.
    """
    if not content:
        raise ValidationError("The logo file is empty.")
    if len(content) > MAX_LOGO_BYTES:
        raise ValidationError(
            f"The logo is {len(content) // 1024} KB; the most it may be is 1024 KB."
        )
    for signature, content_type in _SIGNATURES:
        if content.startswith(signature):
            return content_type
    raise ValidationError("The logo must be a PNG or JPG image.")


class AgencyBrandingService:
    """The one live branding row, read before sign-in and kept by administrators."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a platform-store session."""
        self._session = session

    def current(self) -> AgencyBranding | None:
        """Return the live branding row, or None while it has not been given."""
        return self._session.scalars(
            select(AgencyBranding)
            .where(AgencyBranding.is_deleted.is_(False))
            # The id settles a tie: created_at is shared by every row one
            # request wrote (test_pagination_is_a_total_order).
            .order_by(AgencyBranding.created_at, AgencyBranding.id.asc())
            .limit(1)
        ).first()

    def response(self) -> AgencyBrandingResponse:
        """Describe the branding as anyone may read it."""
        row = self.current()
        if row is None:
            return AgencyBrandingResponse(is_set=False)
        return AgencyBrandingResponse(
            is_set=True,
            agency_name=row.agency_name,
            tagline=row.tagline,
            accent_color=row.accent_color,
            has_logo=row.logo is not None,
            version=row.version,
        )

    def update(
        self,
        data: AgencyBrandingWrite,
        *,
        actor_id: UUID | None,
        expected_version: int | None,
    ) -> AgencyBranding:
        """Replace the name, tagline and colour, creating the row on first save."""
        row = self.current()
        before: dict[str, object] | None = None
        if row is None:
            row = AgencyBranding(agency_name=data.agency_name, created_by=actor_id)
            self._session.add(row)
        else:
            assert_version(row.version, expected_version)
            before = row_state(row, exclude=_NOT_AUDITED)
        row.agency_name = data.agency_name
        row.tagline = data.tagline
        row.accent_color = data.accent_color.upper() if data.accent_color else None
        row.updated_by = actor_id
        self._session.flush()
        record_change(
            self._session,
            action=f"{_ENTITY}.{'updated' if before is not None else 'created'}",
            entity_type=_ENTITY,
            row=row,
            actor_id=actor_id,
            before=before,
            exclude=_NOT_AUDITED,
        )
        self._session.commit()
        return row

    def set_logo(
        self,
        content: bytes,
        *,
        actor_id: UUID | None,
        expected_version: int | None,
    ) -> AgencyBranding:
        """Replace the logo with an image checked by its own bytes."""
        content_type = logo_content_type(content)
        row = self._existing(expected_version)
        before = self._logo_state(row)
        row.logo = content
        row.logo_content_type = content_type
        row.updated_by = actor_id
        self._session.flush()
        self._audit_logo(row, actor_id, before)
        self._session.commit()
        return row

    def clear_logo(
        self, *, actor_id: UUID | None, expected_version: int | None
    ) -> AgencyBranding:
        """Remove the logo; the desktop shows the agency's initials instead."""
        row = self._existing(expected_version)
        if row.logo is None:
            return row
        before = self._logo_state(row)
        row.logo = None
        row.logo_content_type = None
        row.updated_by = actor_id
        self._session.flush()
        self._audit_logo(row, actor_id, before)
        self._session.commit()
        return row

    def _existing(self, expected_version: int | None) -> AgencyBranding:
        """Return the row a logo belongs to, refusing before a name is given."""
        row = self.current()
        if row is None:
            raise BusinessRuleError(
                "Give the agency's name first; the logo is saved with it."
            )
        assert_version(row.version, expected_version)
        return row

    @staticmethod
    def _logo_state(row: AgencyBranding) -> dict[str, object]:
        """Describe the logo for the trail without copying the image."""
        return {
            "logo_content_type": row.logo_content_type,
            "logo_bytes": len(row.logo) if row.logo is not None else None,
        }

    def _audit_logo(
        self,
        row: AgencyBranding,
        actor_id: UUID | None,
        before: dict[str, object],
    ) -> None:
        """Record a logo change by its type and size."""
        record_audit(
            self._session,
            action=f"{_ENTITY}.logo_changed",
            entity_type=_ENTITY,
            entity_id=row.id,
            actor_id=actor_id,
            before_data=before,
            after_data=self._logo_state(row),
        )
