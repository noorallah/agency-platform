"""Tests for reusable core framework contracts and HTTP infrastructure."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import Request
from starlette.responses import Response

from app.core.config.settings import Settings
from app.core.context import RequestContext, reset_request_context, set_request_context
from app.core.enums import TokenType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.exceptions.handlers import application_error_handler
from app.core.filtering import Filter, FilterOperator
from app.core.middleware import CoreRequestMiddleware
from app.core.pagination import PaginationParams
from app.core.security import (
    JwtService,
    PasswordSecurity,
    Principal,
    TokenClaims,
    require_any_permission,
    require_permission,
)
from app.core.sorting import SortDirection, SortField
from app.core.utils.collections import chunked
from app.core.utils.dates import financial_year_label, utc_now
from app.core.utils.json import json_dumps
from app.core.utils.money import quantize_money
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
    token = set_request_context(
        RequestContext(
            request_id="request-id",
            correlation_id="correlation-id",
            client_ip=None,
            requested_at=utc_now(),
        )
    )
    try:
        response = asyncio.run(
            application_error_handler(
                request, ValidationError(details=["field invalid"])
            )
        )
    finally:
        reset_request_context(token)

    assert response.status_code == 422
    payload = json.loads(bytes(response.body))
    assert payload["success"] is False
    assert payload["timestamp"]
    assert payload["error"] == {
        "code": ErrorCode.VALIDATION_ERROR,
        "message": "The request validation failed.",
        "details": ["field invalid"],
    }
    assert payload["requestId"] == "request-id"
    assert "request_id" not in payload


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


def test_permission_dependencies_allow_non_admin_claims() -> None:
    """Ensure endpoint permissions rely on claims rather than an admin role."""
    claims = TokenClaims(
        sub=str(uuid4()),
        type=TokenType.ACCESS,
        iat=1,
        exp=2,
        permissions=["USER_VIEW"],
    )
    principal = Principal(
        subject=uuid4(),
        roles=frozenset(),
        permissions=frozenset({"USER_VIEW"}),
        claims=claims,
    )

    assert require_permission("USER_VIEW")(principal) is principal
    assert require_any_permission("FIRM_VIEW", "USER_VIEW")(principal) is principal
    with pytest.raises(AuthorizationError):
        require_permission("USER_UPDATE")(principal)
    password_change_claims = TokenClaims(
        sub=str(uuid4()),
        type=TokenType.ACCESS,
        iat=1,
        exp=2,
        permissions=["USER_VIEW"],
        password_change_required=True,
    )
    restricted_principal = Principal(
        subject=uuid4(),
        roles=frozenset(),
        permissions=frozenset({"USER_VIEW"}),
        claims=password_change_claims,
    )
    with pytest.raises(AuthorizationError):
        require_permission("USER_VIEW")(restricted_principal)


def test_money_rounds_half_up_at_the_shared_scale() -> None:
    """One rounding rule for every transactional module.

    ``goods_receipt`` used to quantize without a rounding mode, so it applied
    banker's rounding and produced different money from every other document.
    """
    assert quantize_money(None) == Decimal("0")
    assert quantize_money("1.00005") == Decimal("1.0001")
    assert quantize_money(Decimal("2.00015")) == Decimal("2.0002")
    # ROUND_HALF_EVEN would give 2.0002 here; half-up must give 2.0003.
    assert quantize_money(Decimal("2.00025")) == Decimal("2.0003")
    assert quantize_money(7) == Decimal("7.0000")
    assert quantize_money(Decimal("-1.00005")) == Decimal("-1.0001")


def test_financial_year_label_follows_the_firms_year_start() -> None:
    """One label format, anchored on the firm's own financial year."""
    assert financial_year_label(date(2026, 8, 9)) == "2026-2027"
    assert financial_year_label(date(2026, 3, 31)) == "2025-2026"
    assert financial_year_label(date(2026, 4, 1)) == "2026-2027"
    # A firm on a calendar financial year.
    assert financial_year_label(date(2026, 3, 31), start_month=1) == "2026-2027"
    # A firm whose year starts in July.
    assert financial_year_label(date(2026, 6, 30), start_month=7) == "2025-2026"
    assert financial_year_label(date(2026, 7, 1), start_month=7) == "2026-2027"
    with pytest.raises(ValueError):
        financial_year_label(date(2026, 1, 1), start_month=13)
