"""A period that ends before it starts is refused on every route (D-RPT-23).

About seventy dated reports answered 200 with an empty list for
``from_date=2026-12-31&to_date=2025-04-01``. One application dependency now
refuses it with the 422 sales analysis always gave; these tests call it
directly and check that ``create_app`` puts it on every route.
"""

import asyncio
import json
from datetime import date
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI
from starlette.requests import Request

from app.core.config.settings import Environment, Settings
from app.core.exceptions.base import ValidationError
from app.core.exceptions.handlers import register_exception_handlers
from app.core.validation.periods import (
    BACKWARDS_PERIOD_MESSAGE,
    refuse_backwards_period,
)
from app.main import create_app


def _request(query: str) -> Request:
    """Build a GET request carrying ``query`` as its query string."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/reports/anything",
            "query_string": query.encode("ascii"),
            "headers": [],
        }
    )


def test_a_period_running_backwards_is_refused_with_a_422() -> None:
    """``from_date`` after ``to_date`` answers 422 naming the period."""
    with pytest.raises(ValidationError) as refused:
        refuse_backwards_period(_request("from_date=2026-12-31&to_date=2025-04-01"))

    assert refused.value.status_code == 422
    assert refused.value.message == BACKWARDS_PERIOD_MESSAGE
    assert refused.value.details == [
        {
            "field": "from_date",
            "message": "2026-12-31 is after the to_date 2025-04-01.",
        }
    ]


@pytest.mark.parametrize(
    "query",
    [
        "from_date=2026-04-01&to_date=2026-04-01",
        "from_date=2025-04-01&to_date=2026-03-31",
        "from_date=2026-12-31",
        "to_date=2025-04-01",
        "",
        "created_from=2026-12-31&created_to=2025-04-01",
    ],
    ids=["same-day", "forwards", "no-end", "no-start", "neither", "other-names"],
)
def test_a_period_that_does_not_run_backwards_passes(query: str) -> None:
    """A single day, a normal range and an open end are all allowed."""
    refuse_backwards_period(_request(query))


@pytest.mark.parametrize(
    "query",
    [
        "from_date=last-month&to_date=2025-04-01",
        "from_date=2026-12-31&to_date=",
    ],
    ids=["not-a-date", "blank-end"],
)
def test_a_value_that_is_not_a_date_is_left_to_the_route(query: str) -> None:
    """What the check cannot read, the route's own validation answers."""
    refuse_backwards_period(_request(query))


def test_create_app_registers_the_check_for_every_route() -> None:
    """The check sits on the application router, which every include inherits."""
    application = create_app(
        Settings(
            environment=Environment.TESTING,
            bootstrap_admin_password="test-bootstrap-password",
        )
    )

    assert any(
        dependency.dependency is refuse_backwards_period
        for dependency in application.router.dependencies
    )


def _probe_application() -> FastAPI:
    """Build an app shaped like ``create_app``: the check, the handlers, nesting."""
    application = FastAPI(dependencies=[Depends(refuse_backwards_period)])
    register_exception_handlers(application)
    reports = APIRouter(prefix="/reports")

    @reports.get("/period")
    def period(
        from_date: date | None = None, to_date: date | None = None
    ) -> dict[str, bool]:
        """Answer for any period it is let through with."""
        del from_date, to_date
        return {"answered": True}

    api = APIRouter(prefix="/api/v1")
    api.include_router(reports)
    application.include_router(api)
    return application


def _get(application: FastAPI, query: str) -> tuple[int, dict[str, Any]]:
    """Send one GET through the ASGI app and return its status and JSON body."""
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        """Hand over an empty request body."""
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        """Keep each message the app sends."""
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/reports/period",
        "raw_path": b"/api/v1/reports/period",
        "root_path": "",
        "query_string": query.encode("ascii"),
        "headers": [],
        "client": ("testclient", 1),
        "server": ("testserver", 80),
    }
    asyncio.run(application(scope, receive, send))  # type: ignore[arg-type]
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    return status, json.loads(body)


def test_a_nested_route_answers_the_standard_422_envelope() -> None:
    """Through two levels of include, the refusal is the project's own 422."""
    backwards = "from_date=2026-12-31&to_date=2025-04-01"
    status, body = _get(_probe_application(), backwards)

    assert status == 422
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == BACKWARDS_PERIOD_MESSAGE


@pytest.mark.parametrize(
    "query",
    [
        "from_date=2026-04-01&to_date=2026-04-01",
        "from_date=2025-04-01&to_date=2026-03-31",
    ],
    ids=["same-day", "forwards"],
)
def test_a_nested_route_answers_a_forward_period(query: str) -> None:
    """A single day and a normal range reach the handler."""
    assert _get(_probe_application(), query) == (200, {"answered": True})
