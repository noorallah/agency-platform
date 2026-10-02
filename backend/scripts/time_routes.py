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
import csv
import http.client
import os
import statistics
import sys

from app.diagnostics.route_walk import (
    LIST_TARGET_MS,
    REPORT_TARGET_MS,
    Client,
    HttpError,
    Resolver,
    Result,
    Route,
    Window,
    classify,
    judge,
    last_financial_year,
    last_month,
    rows_in,
    select_routes,
)

#: Re-exported: ``tests/unit/test_time_routes.py`` reads them from here.
__all__ = [
    "classify",
    "judge",
    "last_financial_year",
    "last_month",
    "main",
    "rows_in",
    "select_routes",
]


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
