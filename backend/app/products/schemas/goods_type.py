"""API contracts for goods types (backlog 89)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoodsTypeSchema(BaseModel):
    """Strict schema configuration for goods types."""

    model_config = ConfigDict(extra="forbid")


class GoodsTypeCreate(GoodsTypeSchema):
    """Add a goods type of the firm's own."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    track_batch: bool = False
    track_expiry: bool = False
    track_manufacturing_date: bool = False
    track_serial: bool = False
    track_warranty: bool = False
    is_active: bool = True
    #: What a new product of this type starts with, in this firm.
    default_hsn_sac: str | None = Field(default=None, max_length=20)
    default_tax_profile_group_code: str | None = Field(default=None, max_length=50)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Match codes regardless of case."""
        return value.strip().upper()

    @field_validator("default_hsn_sac", "default_tax_profile_group_code", mode="before")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        """Read an empty box as no default."""
        if value is None:
            return None
        return value.strip() or None


class GoodsTypeUpdate(GoodsTypeSchema):
    """Change a goods type of the firm's own; absent leaves a field alone."""

    code: str | None = Field(
        default=None, min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$"
    )
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    track_batch: bool | None = None
    track_expiry: bool | None = None
    track_manufacturing_date: bool | None = None
    track_serial: bool | None = None
    track_warranty: bool | None = None
    is_active: bool | None = None
    default_hsn_sac: str | None = Field(default=None, max_length=20)
    default_tax_profile_group_code: str | None = Field(default=None, max_length=50)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        """Match codes regardless of case."""
        return None if value is None else value.strip().upper()

    @field_validator("default_hsn_sac", "default_tax_profile_group_code", mode="before")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        """Read an empty box as no default."""
        if value is None:
            return None
        return value.strip() or None


class GoodsTypeUse(GoodsTypeSchema):
    """Say whether the firm trades in a type, and its defaults there.

    The one write a firm has over a shared type. A default left out is left
    alone; an explicit null clears it.
    """

    in_use: bool
    default_hsn_sac: str | None = Field(default=None, max_length=20)
    default_tax_profile_group_code: str | None = Field(default=None, max_length=50)

    @field_validator("default_hsn_sac", "default_tax_profile_group_code", mode="before")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        """Read an empty box as no default."""
        if value is None:
            return None
        return value.strip() or None


class GoodsTypeResponse(GoodsTypeSchema):
    """One goods type as a firm sees it."""

    id: UUID
    #: Null for the shared catalogue, which a firm reads and cannot change.
    firm_id: UUID | None
    code: str
    name: str
    description: str | None
    track_batch: bool
    track_expiry: bool
    track_manufacturing_date: bool
    track_serial: bool
    track_warranty: bool
    is_active: bool
    #: Whether this firm trades in it: offered on its categories.
    in_use: bool
    default_hsn_sac: str | None
    default_tax_profile_group_code: str | None
    #: The concurrency counter, echoed as ``If-Match`` on the next edit.
    version: int


class ProductGoodsTypeOption(GoodsTypeSchema):
    """One goods type as the product form needs it.

    Rides in the product metadata so the form opens on the call it already
    makes.
    """

    id: UUID
    code: str
    name: str
    #: Every tracking switch a new product of the type starts with, by the
    #: product's own field name, for the form to apply as they stand.
    switches: dict[str, bool]
    default_hsn_sac: str | None
    #: Only ever a tax group the firm has today.
    default_tax_profile_group_code: str | None
