"""Operational health endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies.settings import get_request_settings
from app.core.config.settings import Environment, Settings
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse, ErrorResponse

router = APIRouter(prefix="/health", tags=["System"])


class HealthStatus(BaseModel):
    """Describe the service state exposed to orchestration systems."""

    model_config = ConfigDict(extra="forbid")

    status: str
    environment: Environment
    #: Which build is installed. Nothing reported this before 2026-09-17, so
    #: the only way to tell one deployment from another was to read files on
    #: the machine -- and the client's own version comes from a JSON file
    #: beside the exe, which anyone can edit. This comes from the application
    #: itself and is the honest answer to "what is running here".
    version: str


class DatabaseHealthStatus(BaseModel):
    """Describe the database connectivity state."""

    model_config = ConfigDict(extra="forbid")

    status: str


@router.get(
    "",
    response_model=ApiResponse[HealthStatus],
    status_code=status.HTTP_200_OK,
    summary="Check service health",
    responses=STANDARD_ERROR_RESPONSES,
)
async def get_health(
    settings: Settings = Depends(get_request_settings),
) -> ApiResponse[HealthStatus]:
    """Return a lightweight service health result.

    Args:
        settings: Active application settings.

    Returns:
        The operational status and deployment environment.

    """
    return ApiResponse(
        data=HealthStatus(
            status="healthy",
            environment=settings.environment,
            version=settings.app_version,
        )
    )


@router.get(
    "/database",
    response_model=ApiResponse[DatabaseHealthStatus],
    status_code=status.HTTP_200_OK,
    summary="Check database connectivity",
    responses={
        **STANDARD_ERROR_RESPONSES,
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "The database is unavailable.",
        },
    },
)
def get_database_health(
    db: Session = Depends(get_db),
) -> ApiResponse[DatabaseHealthStatus]:
    """Verify that the configured database accepts a lightweight query."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from error

    return ApiResponse(data=DatabaseHealthStatus(status="connected"))
