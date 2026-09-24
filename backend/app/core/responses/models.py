"""Standard response contracts shared by every HTTP API."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.context import get_request_context
from app.core.utils.dates import utc_now

#: The classic spelling, deliberately. ``class ApiResponse[PayloadT](BaseModel)``
#: is what Python 3.12 offers and what ruff asks for, and it runs under the
#: interpreter -- but Nuitka compiles a class's type parameter into a plain
#: attribute of the class body, and pydantic then refuses the model with
#: "A non-annotated attribute was detected: `PayloadT = PayloadT`". The first
#: installed copy of this product failed to start on exactly that line
#: (2026-09-24), and nothing short of a compiled build can see it.
#: ``tests/unit/test_no_generic_class_syntax.py`` keeps the syntax out.
PayloadT = TypeVar("PayloadT")


def _request_id() -> str | None:
    """Return the active request identifier when serializing an API contract."""
    context = get_request_context()
    return context.request_id if context is not None else None


class ApiResponse(BaseModel, Generic[PayloadT]):  # noqa: UP046
    """Represent a successful API response with a typed payload.

    Attributes:
        data: The response payload.
        message: Optional human-readable success message.

    """

    model_config = ConfigDict(extra="forbid", validate_by_name=True)

    success: bool = True
    data: PayloadT
    message: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    request_id: str | None = Field(default_factory=_request_id, alias="requestId")


class ApiError(BaseModel):
    """Describe a machine-readable API error.

    Attributes:
        code: Stable error identifier for API consumers.
        message: Safe, human-readable explanation.
        details: Optional structured validation details.

    """

    model_config = ConfigDict(extra="forbid", validate_by_name=True)

    code: str
    message: str
    details: object | None = None


class ErrorResponse(BaseModel):
    """Represent a failed API response.

    Attributes:
        error: Error information safe to return to the client.

    """

    model_config = ConfigDict(extra="forbid", validate_by_name=True)

    success: bool = False
    error: ApiError = Field(...)
    timestamp: datetime = Field(default_factory=utc_now)
    request_id: str | None = Field(default_factory=_request_id, alias="requestId")


class ValidationErrorDetail(BaseModel):
    """Describe one invalid request field."""

    model_config = ConfigDict(extra="forbid", validate_by_name=True)

    field: str
    message: str
    code: str


class ValidationErrorResponse(ErrorResponse):
    """Represent a standardized response for request validation failures."""

    error: ApiError


class PaginationMetadata(BaseModel):
    """Describe pagination state for a collection response."""

    model_config = ConfigDict(extra="forbid", validate_by_name=True)

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_records: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedResponse(BaseModel, Generic[PayloadT]):  # noqa: UP046
    """Represent a successful, paginated collection response."""

    model_config = ConfigDict(extra="forbid", validate_by_name=True)

    success: bool = True
    data: list[PayloadT]
    pagination: PaginationMetadata
    message: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    request_id: str | None = Field(default_factory=_request_id, alias="requestId")
