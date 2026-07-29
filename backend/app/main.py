"""FastAPI application composition root and ASGI entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dependencies.settings import get_settings
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.health import router as health_router
from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.exceptions.handlers import register_exception_handlers
from app.core.logging.configuration import configure_logging
from app.core.middleware import CoreRequestMiddleware
from app.core.openapi import OPENAPI_TAGS, build_openapi_metadata
from app.firms.api import router as firms_router
from app.identity.api import router as identity_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance.

    Args:
        settings: Explicit settings, primarily for isolated application tests.

    Returns:
        A fully configured FastAPI application.

    """
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Manage application-level startup and shutdown hooks."""
        logger.info(
            "Application startup: name=%s environment=%s",
            settings.app_name,
            settings.environment,
        )
        try:
            yield
        finally:
            application.state.database.dispose()
            logger.info("Application shutdown: name=%s", settings.app_name)

    application = FastAPI(
        **build_openapi_metadata(settings),
        debug=settings.debug,
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
    )
    application.state.settings = settings
    application.state.database = DatabaseManager.from_settings(settings)
    application.add_middleware(CoreRequestMiddleware)
    application.include_router(health_router)
    application.include_router(dashboard_router)
    application.include_router(identity_router)
    application.include_router(firms_router)
    register_exception_handlers(application)
    return application


def create_application() -> FastAPI:
    """Create an application using the legacy factory name.

    Returns:
        A fully configured FastAPI application.

    """
    return create_app()


app = create_app()
