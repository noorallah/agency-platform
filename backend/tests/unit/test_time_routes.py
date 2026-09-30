"""Keep the route timer's choices honest (backlog 56 C, step 5).

``scripts/time_routes.py`` decides from the OpenAPI document which routes are
lists, which are reports and which to leave out; a wrong call silently judges
a report against the list target, or times a download. These pin the pure
parts; the HTTP half is exercised by running it.
"""

from __future__ import annotations

from datetime import date

from scripts.time_routes import (
    classify,
    judge,
    last_financial_year,
    last_month,
    rows_in,
    select_routes,
)


def test_reports_and_lists_are_told_apart() -> None:
    """A page summary is part of opening a list; a breakdown is a report."""
    assert classify("/api/v1/sales-invoices") == "list"
    assert classify("/api/v1/sales-invoices/summary") == "list"
    assert classify("/api/v1/sales-invoices/reports/register") == "report"
    assert classify("/api/v1/inventory/summary/by-warehouse") == "report"
    assert classify("/api/v1/gst-returns/gstr1") == "report"
    assert judge("list", 999) == "OK" and judge("list", 1_001) == "SLOW"
    assert judge("report", 2_999) == "OK" and judge("report", 3_001) == "SLOW"


def test_the_windows_are_the_last_complete_month_and_year() -> None:
    """Reports are asked about periods that have finished."""
    month = last_month(date(2026, 10, 1))
    assert (month.start, month.end) == (date(2026, 9, 1), date(2026, 9, 30))
    year = last_financial_year(date(2026, 10, 1))
    assert (year.start, year.end) == (date(2025, 4, 1), date(2026, 3, 31))
    year = last_financial_year(date(2026, 2, 1))
    assert (year.start, year.end) == (date(2024, 4, 1), date(2025, 3, 31))


def test_rows_are_read_from_the_envelope() -> None:
    """Paged lists report their total; plain lists their length."""
    assert rows_in({"data": [1, 2], "pagination": {"total_records": 90}}) == "90"
    assert rows_in({"data": [1, 2, 3]}) == "3"
    assert rows_in({"data": {"rows": [1]}}) == "1"
    assert rows_in({"data": {"total": 4}}) == "-"


def test_platform_paths_record_reads_and_downloads_are_left_out() -> None:
    """Only a firm's own lists and reports are timed."""

    def get(*params: tuple[str, str, bool]) -> dict[str, object]:
        """Return an OpenAPI GET operation with the given parameters."""
        return {
            "get": {
                "parameters": [
                    {"name": name, "in": where, "required": required}
                    for name, where, required in params
                ]
            }
        }

    spec = {
        "paths": {
            "/api/v1/users": get(),
            "/api/v1/customers": get(("page", "query", False)),
            "/api/v1/customers/export": get(),
            "/api/v1/customers/{customer_id}": get(("customer_id", "path", True)),
            "/api/v1/customers/{customer_id}/statement": get(
                ("customer_id", "path", True),
                ("from_date", "query", True),
                ("to_date", "query", True),
            ),
            "/api/v1/gst-returns/gstr1": get(
                ("from_date", "query", True), ("to_date", "query", True)
            ),
        }
    }
    routes = {route.path: route for route in select_routes(spec, include_exports=False)}
    assert set(routes) == {
        "/api/v1/customers",
        "/api/v1/customers/{customer_id}/statement",
        "/api/v1/gst-returns/gstr1",
    }
    assert routes["/api/v1/gst-returns/gstr1"].date_pair == ("from_date", "to_date")
    assert routes["/api/v1/customers/{customer_id}/statement"].kind == "report"
    with_exports = select_routes(spec, include_exports=True)
    assert "/api/v1/customers/export" in {route.path for route in with_exports}
