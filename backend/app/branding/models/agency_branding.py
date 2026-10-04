"""Persistence model for the agency's name, tagline and logo."""

from sqlalchemy import Index, LargeBinary, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity


class AgencyBranding(BaseEntity):
    """The agency that bought the product: its name, tagline and logo.

    One live row per installation, in the **platform** store. Sign-in happens
    before a firm is chosen, so the agency sits above its firms and cannot
    live in any one firm's store (``docs/BRANDING_AND_NAMES.md`` section 4.1).
    No row means the branding has not been given yet; the desktop then falls
    back to its ``branding.json``.

    The logo is held in the row rather than as a path, so every PC reads the
    same image from the server instead of each needing its own copy of a file.
    It is capped at 1 MB by the service, which keeps that cheap.
    """

    __tablename__ = "agency_branding"
    __table_args__ = (
        # "One live row" is a fact about a set of rows, so a read-then-insert
        # cannot hold it: two first saves at once would both find none. The
        # constant key gives the database something to refuse the second on.
        Index(
            "UQ_agency_branding_key_active",
            "branding_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    #: Always ``AGENCY``; exists only for the unique index above.
    branding_key: Mapped[str] = mapped_column(
        String(16), nullable=False, default="AGENCY", server_default="AGENCY"
    )

    agency_name: Mapped[str] = mapped_column(String(150), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(200))
    #: ``#RRGGBB``, or none for the product's own accent.
    accent_color: Mapped[str | None] = mapped_column(String(7))
    logo: Mapped[bytes | None] = mapped_column(LargeBinary)
    #: ``image/png`` or ``image/jpeg``, read from the bytes, never the filename.
    logo_content_type: Mapped[str | None] = mapped_column(String(20))
