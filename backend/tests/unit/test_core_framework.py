"""Tests for reusable core framework contracts and HTTP infrastructure."""

import asyncio
import json
from datetime import date

import pytest
from fastapi import Request
from starlette.responses import Response

from app.core.config.settings import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import ValidationError
from app.core.exceptions.handlers import application_error_handler
from app.core.filtering import Filter, FilterOperator
from app.core.middleware import CoreRequestMiddleware
from app.core.pagination import PaginationParams
from app.core.security import JwtService, PasswordSecurity
from app.core.sorting import SortDirection, SortField
from app.core.utils.collections import chunked
from app.core.utils.json import json_dumps
from app.core.validation import (
    validate_date_range,
    validate_email,
    validate_password_policy,
    validate_phone,
)


def test_pagination_calculates_offset_and_metadata() -> None:
    """Ensure page parameters produce repository and response values."""
    pagination = PaginationParams(page=3, page_size=25)

    assert pagination.offset == 50
    assert pagination.metadata(76).model_dump() == {
        "page": 3,
        "page_size": 25,
        "total_records": 76,
        "total_pages": 4,
    }


def test_filtering_and_sorting_validate_generic_query_contracts() -> None:
    """Ensure collection-query inputs reject invalid operator/value combinations."""
    filter_expression = Filter(
        field="status", operator=FilterOperator.IN, value=["active", "inactive"]
    )
    sort = SortField(field="created_at", direction=SortDirection.DESCENDING)

    assert filter_expression.value == ["active", "inactive"]
    assert sort.direction is SortDirection.DESCENDING
    with pytest.raises(ValueError, match="exactly two"):
        Filter(field="amount", operator=FilterOperator.BETWEEN, value=[1])


def test_validation_utilities_are_reusable_and_policy_only() -> None:
    """Ensure common validators normalize valid values and reject invalid input."""
    assert validate_email("  ADMIN@EXAMPLE.COM ") == "admin@example.com"
    assert validate_phone("+1 (415) 555-2671") == "+14155552671"
    validate_password_policy("Secure-Passphrase1")
    validate_date_range(date(2026, 1, 1), date(2026, 1, 2))

    with pytest.raises(ValidationError):
        validate_password_policy("short")
    with pytest.raises(ValidationError):
        validate_date_range(date(2026, 1, 2), date(2026, 1, 1))


def test_utilities_are_stateless_and_serializable() -> None:
    """Ensure shared utility helpers have deterministic public behavior."""
    assert list(chunked(range(5), 2)) == [[0, 1], [2, 3], [4]]
    assert json_dumps({"date": date(2026, 1, 1)}) == '{"date":"2026-01-01"}'


def test_application_errors_use_the_standardized_error_envelope() -> None:
    """Ensure expected exceptions serialize with centralized error codes."""
    request = Request({"type": "http", "method": "GET", "path": "/"})
    response = asyncio.run(
        application_error_handler(request, ValidationError(details=["field invalid"]))
    )

    assert response.status_code == 422
    payload = json.loads(bytes(response.body))
    assert payload["success"] is False
    assert payload["timestamp"]
    assert payload["error"] == {
        "code": ErrorCode.VALIDATION_ERROR,
        "message": "The request validation failed.",
        "details": ["field invalid"],
    }


def test_core_middleware_sets_trace_security_and_timing_headers() -> None:
    """Ensure middleware adds the standard cross-cutting response headers."""
    response = Response()
    correlation_id = "upstream-trace-123"

    CoreRequestMiddleware._set_response_headers(
        response, correlation_id, "request-id", 1.25
    )

    assert response.headers["X-Correlation-ID"] == correlation_id
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Process-Time-Ms"] == "1.25"


def test_password_and_jwt_utilities_are_reusable() -> None:
    """Ensure shared security utilities operate without authentication APIs."""
    password_security = PasswordSecurity()
    password_hash = password_security.hash_password("Secure-Passphrase1")
    assert password_security.verify_password("Secure-Passphrase1", password_hash)
    assert not password_security.verify_password("wrong-password", password_hash)

    settings = Settings()
    jwt_service = JwtService(settings.jwt)
    token = jwt_service.generate_access_token("user-123", claims={"roles": ["admin"]})
    claims = jwt_service.validate_token(token)
    assert claims.subject == "user-123"
    assert claims.token_type.value == "access"
