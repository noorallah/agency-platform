"""Request and response models for the agency's branding."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgencyBrandingWrite(BaseModel):
    """Replace the agency's name, tagline and accent colour.

    The logo is not here: it is an image, sent on its own endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    agency_name: str = Field(min_length=1, max_length=150)
    tagline: str | None = Field(default=None, max_length=200)
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("agency_name")
    @classmethod
    def _name_is_not_blank(cls, value: str) -> str:
        """Refuse a name that is only spaces, and trim the rest."""
        value = value.strip()
        if not value:
            raise ValueError("The agency's name cannot be blank.")
        return value

    @field_validator("tagline")
    @classmethod
    def _blank_tagline_is_none(cls, value: str | None) -> str | None:
        """Store a blank tagline as no tagline."""
        if value is None:
            return None
        return value.strip() or None


class AgencyBrandingResponse(BaseModel):
    """The agency's branding as anyone may read it, before signing in.

    ``is_set`` is false until somebody gives the branding; every other field
    is then empty and the desktop keeps its own ``branding.json``. ``version``
    changes on every save, including a new logo, so a client caching the
    image knows when to fetch it again.
    """

    is_set: bool
    agency_name: str | None = None
    tagline: str | None = None
    accent_color: str | None = None
    has_logo: bool = False
    version: int | None = None
