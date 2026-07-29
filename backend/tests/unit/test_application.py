"""Tests for the application composition root."""

import asyncio

from fastapi import FastAPI

from app.api.routers.health import get_health
from app.core.config.settings import Environment, Settings
from app.main import create_app


def test_application_factory_registers_foundation_routes() -> None:
    """Ensure the factory includes health and Phase 5 API routers."""
    settings = Settings(
        environment=Environment.TESTING,
        bootstrap_admin_password="test-bootstrap-password",
    )
    application = create_app(settings)

    assert isinstance(application, FastAPI)
    assert {
        "/health",
        "/health/database",
        "/api/v1/auth/login",
        "/api/v1/dashboard",
        "/api/v1/firms",
    } <= set(application.openapi()["paths"])


def test_health_endpoint_returns_operational_status() -> None:
    """Ensure the health endpoint returns the standard success contract."""
    response = asyncio.run(
        get_health(
            Settings(
                environment=Environment.TESTING,
                bootstrap_admin_password="test-bootstrap-password",
            )
        )
    )

    payload = response.model_dump(mode="json", by_alias=True)
    assert payload["success"] is True
    assert payload["data"] == {"status": "healthy", "environment": "testing"}
    assert payload["message"] is None
    assert payload["requestId"] is None
    assert payload["timestamp"]
