"""Validated contracts for the firm's salesman list."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SalesmanSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _clean_code(value: object) -> object:
    """Keep codes in capitals, and read a blank code as none."""
    if isinstance(value, str):
        stripped = value.strip().upper()
        return stripped or None
    return value


def _clean_text(value: object) -> object:
    """Trim a typed value, reading a blank one as none."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class SalesmanCreate(SalesmanSchema):
    """Add one entry to the list."""

    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=30)
    user_id: UUID | None = None
    phone: str | None = Field(default=None, max_length=20)
    earns_commission: bool = True
    is_active: bool = True
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: object) -> object:
        """Trim the name; a name of spaces is refused by its length."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, value: object) -> object:
        """Normalise the code."""
        return _clean_code(value)

    @field_validator("phone", "notes", mode="before")
    @classmethod
    def _text(cls, value: object) -> object:
        """Trim the free-text fields."""
        return _clean_text(value)


class SalesmanUpdate(SalesmanSchema):
    """Change one entry. A field left out is left alone; `null` clears it."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=30)
    user_id: UUID | None = None
    phone: str | None = Field(default=None, max_length=20)
    earns_commission: bool | None = None
    is_active: bool | None = None
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: object) -> object:
        """Trim the name."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, value: object) -> object:
        """Normalise the code."""
        return _clean_code(value)

    @field_validator("phone", "notes", mode="before")
    @classmethod
    def _text(cls, value: object) -> object:
        """Trim the free-text fields."""
        return _clean_text(value)


class SalesmanResponse(SalesmanSchema):
    """One entry of the list."""

    id: UUID
    version: int
    code: str | None
    name: str
    user_id: UUID | None
    phone: str | None
    earns_commission: bool
    is_active: bool
    notes: str | None
