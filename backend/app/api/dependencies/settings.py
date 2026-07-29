"""Dependencies that expose application settings to HTTP adapters."""

from functools import lru_cache
from typing import cast

from fastapi import Request

from app.core.config.settings import Settings


@lru_cache
def get_settings() -> Settings:
    """Load and cache process-wide application settings.

    Returns:
        The validated settings for the current process.

    """
    return Settings()


def get_request_settings(request: Request) -> Settings:
    """Return settings attached to the active FastAPI application.

    Args:
        request: Current HTTP request.

    Returns:
        The settings instance used to construct the application.

    """
    return cast(Settings, request.app.state.settings)
