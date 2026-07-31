"""OpenAPI metadata owned by the application composition root."""

from typing import Any

from app.core.config.settings import Settings
from app.core.constants.core import API_VERSION
from app.core.responses.models import ErrorResponse, ValidationErrorResponse

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "System",
        "description": "Operational endpoints for service monitoring.",
    },
    {"name": "Authentication", "description": "Session and password operations."},
    {"name": "Users", "description": "Platform user administration."},
    {"name": "Roles", "description": "Dynamic role administration."},
    {"name": "Permissions", "description": "Capability administration."},
    {"name": "Firms", "description": "Platform firm administration."},
    {
        "name": "Customers",
        "description": "Firm-scoped customer master management.",
    },
    {"name": "Dashboard", "description": "Platform administration summary."},
]
STANDARD_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "model": ErrorResponse,
        "description": "Authentication is required or the token is invalid.",
    },
    403: {
        "model": ErrorResponse,
        "description": "The authenticated principal lacks the required access.",
    },
    400: {
        "model": ErrorResponse,
        "description": "The request could not be processed.",
    },
    404: {
        "model": ErrorResponse,
        "description": "The requested resource was not found.",
    },
    409: {
        "model": ErrorResponse,
        "description": "The request conflicts with current state.",
    },
    422: {
        "model": ValidationErrorResponse,
        "description": "The request validation failed.",
    },
    500: {"model": ErrorResponse, "description": "An unexpected error occurred."},
    502: {"model": ErrorResponse, "description": "An external dependency failed."},
}


def build_openapi_metadata(settings: Settings) -> dict[str, Any]:
    """Build FastAPI OpenAPI metadata from typed settings.

    Args:
        settings: Active application settings.

    Returns:
        Keyword arguments for the FastAPI constructor.

    """
    return {
        "title": settings.app_name,
        "version": f"{API_VERSION}.0",
        "summary": "Agency Platform ERP API",
        "description": (
            "Enterprise ERP backend API. All future endpoints use the shared "
            "response, validation, error, pagination, filtering, and sorting contracts."
        ),
        "contact": {"name": "Agency Platform Engineering"},
        "license_info": {"name": "Proprietary"},
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }
