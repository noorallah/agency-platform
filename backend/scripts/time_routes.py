"""Time every list and report route of one firm against a running backend.

Backlog 56 C, step 5 (``docs/PERFORMANCE_AT_VOLUME.md``): a list must open in
under a second and a report in under three. This asks the running backend,
over HTTP, signed in the way the desktop signs in, so what it measures is what
a person waits for -- routing, the tenant session, serialisation and all.

    uv run python scripts/time_routes.py --firm-code PERF01
    uv run python scripts/time_routes.py --base-url http://127.0.0.1:8010
    uv run python scripts/time_routes.py --only sales-invoices --csv si.csv

The routes come from the application's own OpenAPI document, so a route added
tomorrow is timed tomorrow without anybody listing it here. Taken: every GET
outside the platform paths (``_is_platform_path``) with no path parameter,
plus the few per-party reports named in ``PER_PARTY_REPORTS``. Left out:
single-record reads (``/{id}``), file exports and templates (unless
``--include-exports``), and routes whose required parameters cannot be
filled from the firm's own data -- those are listed as SKIP with the reason.

A list is called once, with default paging. A report is called for the last
calendar month and for the last complete financial year where it takes a date
range, once otherwise. Each call is repeated ``--repeat`` times (default 3)
and the median kept. OK / SLOW / FAIL is judged against the targets; a route
that errors is FAIL with its status and message.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import http.client
import json
import os
import statistics
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

LIST_TARGET_MS = 1_000
REPORT_TARGET_MS = 3_000

#: Path segments that make a route a report rather than a list.
REPORT_SEGMENTS = frozenset(
    {
        "reports",
        "report",
        "ageing",
        "gstr1",
        "gstr3b",
        "trial-balance",
        "opening-trial-balance",
        "balance-sheet",
        "profit-loss",
        "account-summaries",
        "statement",
        "achievement",
        "expiry-dashboard",
        "ledger",
        "charged-versus-due",
        "coverage",
        "by-branch",
        "by-firm",
        "by-product",
        "by-warehouse",
        "outstanding",
        "overdue",
    }
)

#: Last segments that are a download, not a screen.
EXPORT_SEGMENTS = frozenset({"export", "csv", "import-template"})

#: Routes with a path parameter that are reports about one party rather than
#: reads of one record, and the list the parameter's value is taken from.
PER_PARTY_REPORTS = {
    "/api/v1/customers/{customer_id}/statement": "customer_id",
    "/api/v1/customers/{customer_id}/receivables/transactions": "customer_id",
    "/api/v1/customers/{customer_id}/receivables/summary": "customer_id",
    "/api/v1/customers/{customer_id}/credit-status": "customer_id",
    "/api/v1/vendors/{vendor_id}/opening-bills": "vendor_id",
}

#: Where the value of an id parameter is found: the first row of this list.
ID_SOURCES = {
    "customer_id": "/api/v1/customers",
    "vendor_id": "/api/v1/vendors",
    "product_id": "/api/v1/products",
    "warehouse_id": "/api/v1/warehouses",
    "branch_id": "/api/v1/branches",
}

#: Date-range parameter pairs, in the order they are looked for.
RANGE_PAIRS = (
    ("from_date", "to_date"),
    ("date_from", "date_to"),
    ("invoice_from", "invoice_to"),
    ("order_from", "order_to"),
    ("delivery_from", "delivery_to"),
    ("return_from", "return_to"),
    ("settlement_from", "settlement_to"),
    ("transaction_from", "transaction_to"),
    ("journal_from", "journal_to"),
    ("posting_from", "posting_to"),
    ("credit_note_from", "credit_note_to"),
    ("proforma_from", "proforma_to"),
    ("quotation_from", "quotation_to"),
)


@dataclass(frozen=True)
class Window:
    """A date range a report is asked about."""

    name: str
    start: date
    end: date


@dataclass
class Route:
    """One GET operation from the OpenAPI document."""

    path: str
    kind: str
    query: dict[str, dict[str, Any]]
    required: list[str]
    path_params: list[str]

    @property
    def date_pair(self) -> tuple[str, str] | None:
        """Return the date-range parameters this route takes, if any."""
        for pair in RANGE_PAIRS:
            if pair[0] in self.query and pair[1] in self.query:
                return pair
        return None


@dataclass
class Result:
    """What one route did in one window."""

    route: str
    kind: str
    window: str
    status: str
    median_ms: float | None = None
    rows: str = "-"
    detail: str = ""
    samples: list[float] = field(default_factory=list)


def last_month(today: date) -> Window:
    """Return the last complete calendar month before ``today``."""
    end = today.replace(day=1) - timedelta(days=1)
    return Window("month", end.replace(day=1), end)


def last_financial_year(today: date, start_month: int = 4) -> Window:
    """Return the last complete financial year before ``today``."""
    year = today.year if today.month >= start_month else today.year - 1
    start = date(year - 1, start_month, 1)
    end = date(year, start_month, 1) - timedelta(days=1)
    return Window("year", start, end)


def classify(path: str) -> str:
    """Say whether a route is a ``report`` or a ``list``.

    A page summary (``/sales-invoices/summary``) is loaded when the list
    opens, so it is judged as a list; a summary broken down by something
    (``/inventory/summary/by-warehouse``) is a report.
    """
    segments = [segment for segment in path.split("/") if segment]
    return "report" if REPORT_SEGMENTS.intersection(segments) else "list"


def select_routes(spec: dict[str, Any], *, include_exports: bool) -> list[Route]:
    """Pick the firm-owned list and report routes out of an OpenAPI document."""
    from app.core.database.dependencies import _is_platform_path

    routes: list[Route] = []
    for path, operations in sorted(spec["paths"].items()):
        operation = operations.get("get")
        if operation is None or _is_platform_path(path):
            continue
        last = path.rstrip("/").rsplit("/", 1)[-1]
        if last in EXPORT_SEGMENTS and not include_exports:
            continue
        parameters = operation.get("parameters", [])
        path_params = [p["name"] for p in parameters if p["in"] == "path"]
        if path_params and path not in PER_PARTY_REPORTS:
            continue
        query = {p["name"]: p for p in parameters if p["in"] == "query"}
        required = [name for name, p in query.items() if p.get("required")]
        kind = "report" if path in PER_PARTY_REPORTS else classify(path)
        routes.append(Route(path, kind, query, required, path_params))
    return routes


def rows_in(body: object) -> str:
    """Return how many rows a response carried, as the envelope says."""
    if not isinstance(body, dict):
        return "-"
    pagination = body.get("pagination")
    if isinstance(pagination, dict) and "total_records" in pagination:
        return str(pagination["total_records"])
    data = body.get("data")
    if isinstance(data, list):
        return str(len(data))
    if isinstance(data, dict):
        for key in ("items", "rows", "lines", "entries", "accounts", "invoices"):
            if isinstance(data.get(key), list):
                return str(len(data[key]))
    return "-"


def judge(kind: str, median_ms: float) -> str:
    """Return OK or SLOW against the target for the route's kind."""
    target = REPORT_TARGET_MS if kind == "report" else LIST_TARGET_MS
    return "OK" if median_ms <= target else "SLOW"


class HttpError(Exception):
    """A response that was not a success, with what the server said."""

    def __init__(self, status: int, message: str, elapsed_ms: float) -> None:
        """Keep the status, the server's message and how long it took."""
        super().__init__(f"{status} {message}")
        self.status = status
        self.message = message
        self.elapsed_ms = elapsed_ms


class Client:
    """A signed-in HTTP client for one firm, as the desktop holds one.

    One kept-alive connection, as the desktop keeps one. ``urllib`` opens a
    connection per call and, on Windows, intermittently had multi-megabyte
    answers reset under it (``WinError 10054``) while curl and a persistent
    connection read the same answer every time.
    """

    def __init__(
        self, base_url: str, email: str, password: str, timeout: float
    ) -> None:
        """Remember where and as whom to sign in; nothing is sent yet."""
        parts = urllib.parse.urlsplit(base_url)
        self._host = parts.hostname or "127.0.0.1"
        self._port = parts.port or (443 if parts.scheme == "https" else 80)
        self._https = parts.scheme == "https"
        self._prefix = parts.path.rstrip("/")
        self._email = email
        self._password = password
        self._timeout = timeout
        self._token = ""
        self._connection: http.client.HTTPConnection | None = None
        self.firm_id = ""

    def sign_in(self) -> None:
        """Sign in through ``/api/v1/auth/login`` and keep the access token."""
        body = self._send(
            "POST",
            "/api/v1/auth/login",
            {"email": self._email, "password": self._password},
            authorised=False,
        )[1]
        self._token = str(body["data"]["access_token"])

    def choose_firm(self, code: str) -> None:
        """Pick the firm to send in ``X-Firm-ID`` from the user's own firms."""
        body = self._send("GET", "/api/v1/me/firms")[1]
        rows = body.get("data") or []
        for row in rows:
            firm = row.get("firm", row) if isinstance(row, dict) else {}
            if str(firm.get("code", "")).upper() == code.upper():
                self.firm_id = str(firm.get("id") or row.get("firm_id"))
                return
        raise SystemExit(f"{self._email} is not a member of a firm coded {code}.")

    def get(self, path: str, params: dict[str, str]) -> tuple[int, Any, float]:
        """GET a path; return status, parsed body and elapsed milliseconds.

        A 401 signs in again once and repeats the call, as the desktop's
        refresh does -- an access token can expire in the middle of a run.
        """
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        try:
            return self._timed(f"{path}{query}")
        except HttpError as error:
            if error.status != 401:
                raise
            self.sign_in()
            return self._timed(f"{path}{query}")

    def _timed(self, target: str) -> tuple[int, Any, float]:
        """Send one GET and time it until the whole body has arrived."""
        started = time.perf_counter()
        status, body = self._send("GET", target, started=started)
        return status, body, (time.perf_counter() - started) * 1000

    def _open(self) -> http.client.HTTPConnection:
        """Return the kept-alive connection, opening it if need be."""
        if self._connection is None:
            kind = (
                http.client.HTTPSConnection
                if self._https
                else http.client.HTTPConnection
            )
            self._connection = kind(self._host, self._port, timeout=self._timeout)
        return self._connection

    def _send(
        self,
        method: str,
        target: str,
        payload: dict[str, Any] | None = None,
        *,
        authorised: bool = True,
        started: float | None = None,
    ) -> tuple[int, Any]:
        """Send one request and parse its JSON answer.

        A connection the server has closed between calls is reopened once;
        anything else is the route's failure and is raised.
        """
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if authorised:
            headers["Authorization"] = f"Bearer {self._token}"
            if self.firm_id:
                headers["X-Firm-ID"] = self.firm_id
        begun = started if started is not None else time.perf_counter()
        for attempt in (1, 2):
            connection = self._open()
            try:
                connection.request(
                    method, f"{self._prefix}{target}", body=data, headers=headers
                )
                response = connection.getresponse()
                raw = response.read()
                break
            except (http.client.RemoteDisconnected, ConnectionResetError):
                connection.close()
                self._connection = None
                if attempt == 2:
                    raise
        if response.status >= 400:
            message = raw.decode(errors="replace")[:300]
            with contextlib.suppress(ValueError, AttributeError, TypeError):
                parsed = json.loads(raw)
                error = parsed.get("error") or {}
                message = error.get("message") or parsed.get("message") or message
            raise HttpError(
                response.status, message, (time.perf_counter() - begun) * 1000
            )
        try:
            return response.status, json.loads(raw) if raw else None
        except ValueError:
            return response.status, None


def first_id(client: Client, source: str) -> str | None:
    """Return the id of the first row of a list, or None if it is empty."""
    _, body, _ = client.get(source, {"page": "1", "page_size": "1"})
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, list) and data:
        return str(data[0].get("id"))
    return None


class Resolver:
    """Fill the parameters a route insists on, from the firm's own data."""

    def __init__(self, client: Client, month: Window) -> None:
        """Bind to the client; ids are looked up once, on first use."""
        self._client = client
        self._month = month
        self._cache: dict[str, str | None] = {}

    def value(self, name: str) -> str | None:
        """Return a value for a required parameter, or None if there is none."""
        if name in self._cache:
            return self._cache[name]
        found: str | None = None
        if name in ID_SOURCES:
            found = first_id(self._client, ID_SOURCES[name])
        elif name == "accounting_period_id":
            found = self._period_covering(self._month.end)
        elif name == "entity_type":
            found = "CUSTOMER"
        elif name in {"q", "query"}:
            found = "P0001"
        self._cache[name] = found
        return found

    def _period_covering(self, on: date) -> str | None:
        """Return the id of the accounting period covering a date."""
        _, body, _ = self._client.get(
            "/api/v1/finance/accounting-periods", {"page_size": "100"}
        )
        for row in body.get("data") or []:
            if row["starts_on"] <= on.isoformat() <= row["ends_on"]:
                return str(row["id"])
        return None


def time_route(
    client: Client,
    route: Route,
    resolver: Resolver,
    windows: list[Window],
    repeat: int,
) -> list[Result]:
    """Call one route in each window that applies and time it."""
    path = route.path
    for name in route.path_params:
        value = resolver.value(name)
        if value is None:
            return [Result(path, route.kind, "-", "SKIP", detail=f"no {name}")]
        path = path.replace("{" + name + "}", value)
    pair = route.date_pair
    applies = windows if route.kind == "report" and pair else [None]
    results: list[Result] = []
    for window in applies:
        params: dict[str, str] = {}
        if window is not None and pair is not None:
            params[pair[0]] = window.start.isoformat()
            params[pair[1]] = window.end.isoformat()
        if "as_of" in route.query and window is not None:
            params["as_of"] = window.end.isoformat()
        missing = [name for name in route.required if name not in params]
        unresolved = []
        for name in missing:
            value = resolver.value(name)
            if value is None:
                unresolved.append(name)
            else:
                params[name] = value
        label = window.name if window is not None else "-"
        if unresolved:
            results.append(
                Result(
                    route.path,
                    route.kind,
                    label,
                    "SKIP",
                    detail=f"needs {', '.join(unresolved)}",
                )
            )
            continue
        results.append(_measure(client, route, path, params, label, repeat))
    return results


def _measure(
    client: Client,
    route: Route,
    path: str,
    params: dict[str, str],
    label: str,
    repeat: int,
) -> Result:
    """Call a route ``repeat`` times and keep the median."""
    samples: list[float] = []
    rows = "-"
    for _ in range(repeat):
        try:
            _, body, elapsed = client.get(path, params)
        except HttpError as error:
            return Result(
                route.path,
                route.kind,
                label,
                "FAIL",
                median_ms=error.elapsed_ms,
                detail=f"{error.status} {error.message}",
            )
        except (http.client.HTTPException, TimeoutError, OSError) as error:
            return Result(route.path, route.kind, label, "FAIL", detail=repr(error))
        samples.append(elapsed)
        rows = rows_in(body)
    median = statistics.median(samples)
    return Result(
        route.path,
        route.kind,
        label,
        judge(route.kind, median),
        median_ms=median,
        rows=rows,
        samples=samples,
    )


def render(results: list[Result]) -> str:
    """Return the results as a table, slowest first, failures on top."""
    ordered = sorted(
        results,
        key=lambda r: (r.status != "FAIL", -(r.median_ms or -1), r.route),
    )
    lines = [
        f"{'route':<62} {'kind':<6} {'window':<6} {'median ms':>10} "
        f"{'rows':>8}  status"
    ]
    for result in ordered:
        median = f"{result.median_ms:,.0f}" if result.median_ms is not None else "-"
        lines.append(
            f"{result.route:<62} {result.kind:<6} {result.window:<6} "
            f"{median:>10} {result.rows:>8}  {result.status}"
            + (f"  {result.detail}" if result.detail else "")
        )
    counts = {s: sum(r.status == s for r in results) for s in ("OK", "SLOW", "FAIL")}
    skipped = sum(r.status == "SKIP" for r in results)
    lines.append(
        f"\n{len(results)} timings: {counts['OK']} OK, {counts['SLOW']} SLOW, "
        f"{counts['FAIL']} FAIL, {skipped} SKIP (list target "
        f"{LIST_TARGET_MS} ms, report target {REPORT_TARGET_MS} ms)"
    )
    return "\n".join(lines)


def write_csv(results: list[Result], target: str) -> None:
    """Write every result to a CSV file."""
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["route", "kind", "window", "median_ms", "rows", "status", "detail"]
        )
        for r in results:
            writer.writerow(
                [
                    r.route,
                    r.kind,
                    r.window,
                    f"{r.median_ms:.1f}" if r.median_ms is not None else "",
                    r.rows,
                    r.status,
                    r.detail,
                ]
            )


def main(argv: list[str] | None = None) -> int:
    """Sign in, time every list and report route, and print the table."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--firm-code", default="PERF01")
    parser.add_argument(
        "--email",
        default=os.environ.get("TIME_ROUTES_EMAIL", "perf01.admin@agency.local"),
    )
    parser.add_argument(
        "--password", default=os.environ.get("TIME_ROUTES_PASSWORD", "PerfAdmin@12345")
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--csv", default="route_timings.csv")
    parser.add_argument(
        "--only", help="Time only routes whose path contains this text."
    )
    parser.add_argument("--include-exports", action="store_true")
    args = parser.parse_args(argv)

    from app.core.utils.dates import utc_now
    from app.main import create_app

    routes = select_routes(create_app().openapi(), include_exports=args.include_exports)
    if args.only:
        routes = [route for route in routes if args.only in route.path]
    client = Client(args.base_url, args.email, args.password, args.timeout)
    client.sign_in()
    client.choose_firm(args.firm_code)
    today = utc_now().date()
    windows = [last_month(today), last_financial_year(today)]
    resolver = Resolver(client, windows[0])
    print(
        f"Timing {len(routes)} routes for {args.firm_code} at {args.base_url}, "
        f"{args.repeat} calls each; month {windows[0].start}..{windows[0].end}, "
        f"year {windows[1].start}..{windows[1].end}",
        flush=True,
    )
    results: list[Result] = []
    for route in routes:
        for result in time_route(client, route, resolver, windows, args.repeat):
            results.append(result)
            print(
                f"  {result.status:<4} {result.median_ms or 0:>9,.0f} ms  "
                f"{result.route} [{result.window}]",
                flush=True,
            )
    print()
    print(render(results))
    write_csv(results, args.csv)
    print(f"\nCSV: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
