"""One command that says whether this installation works: ``quick-check``.

The owner's sanity check (2026-10-02): before testing screens by hand, prove
the server answers, a person can sign in, every store is migrated, and every
list and report a firm's screens open comes back -- for every firm the person
can open. It asks the **running** server over HTTP, signed in the way the
desktop signs in, so what it proves is what a person would get.

Read only. It sends nothing but GETs and the sign-in, so it is safe on a
firm's live books and can be run as often as wanted.

Each check ends PASS, SLOW (answered, but past the target a person waits:
1 s for a list, 3 s for a report), SKIP (this person may not open it, or the
firm has no data to fill a parameter the route insists on) or FAIL (an error;
the server's own message is kept). The result is printed and written to an
HTML page beside where it was run, and the exit code is 1 when anything
failed, so a scheduled run can alert on it.

The routes come from the application's own OpenAPI document
(:mod:`app.diagnostics.route_walk`), so a screen added tomorrow is checked
tomorrow without anybody listing it here.
"""

from __future__ import annotations

import html
import http.client
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.diagnostics.route_walk import (
    LIST_TARGET_MS,
    REPORT_TARGET_MS,
    Client,
    HttpError,
    Resolver,
    Route,
    Window,
    judge,
    last_month,
    select_routes,
)

PASS = "PASS"
SLOW = "SLOW"
SKIP = "SKIP"
FAIL = "FAIL"

#: Which module a route belongs to, by the first segment after ``/api/v1/``,
#: in the order the sanity cases take them (``docs/qa/SANITY_CHECK.md``). A
#: segment named nowhere is reported under its own name, so a module added
#: tomorrow still shows up -- just not grouped until it is named here.
MODULES: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "Masters",
        frozenset(
            {
                "customers",
                "vendors",
                "products",
                "branches",
                "warehouses",
                "branch-types",
                "warehouse-types",
                "branch-warehouse",
                "trade-licences",
                "uom-framework",
                "firm-members",
            }
        ),
    ),
    (
        "Pricing and promotions",
        frozenset({"price-lists", "price-levels", "promotions", "loyalty"}),
    ),
    (
        "Selling",
        frozenset(
            {
                "enquiries",
                "quotations",
                "sales-orders",
                "delivery-notes",
                "sales-invoices",
                "sales-returns",
                "credit-notes",
                "customer-debit-notes",
                "proforma-invoices",
                "receipts",
                "refunds",
            }
        ),
    ),
    (
        "Buying",
        frozenset(
            {
                "purchases",
                "goods-receipts",
                "purchase-invoices",
                "purchase-returns",
                "debit-notes",
                "payments",
                "payment-runs",
                "supplier-rebates",
                "landed-costs",
                "principal-claims",
                "rfqs",
                "rate-contracts",
                "supplier-schemes",
                "bills-of-entry",
            }
        ),
    ),
    ("Stock", frozenset({"inventory", "batch-serial"})),
    (
        "Accounts",
        frozenset(
            {
                "finance",
                "expenses",
                "contra-vouchers",
                "party-adjustments",
                "post-dated-cheques",
                "bank-reconciliation",
                "fixed-assets",
            }
        ),
    ),
    (
        "GST and compliance",
        frozenset({"gst-returns", "einvoice", "tcs", "tax-framework"}),
    ),
    (
        "Field sales and incentives",
        frozenset({"sales-territories", "sales-targets", "commission"}),
    ),
    (
        "Configuration and audit",
        frozenset(
            {
                "business-framework",
                "document-framework",
                "audit-logs",
                "search",
                "notifications",
                "messaging",
                "report-layouts",
                "approvals",
            }
        ),
    ),
)


def module_of(path: str) -> str:
    """Return the module a route belongs to, for grouping the result."""
    parts = [part for part in path.split("/") if part]
    segment = parts[2] if len(parts) > 2 else path
    for name, segments in MODULES:
        if segment in segments:
            return name
    return segment


#: Platform screens a signed-in person opens before choosing a firm. A 403
#: is a SKIP: the person is not an administrator, which is not a defect.
PLATFORM_READS = (
    ("Who am I", "/api/v1/me"),
    ("My firms", "/api/v1/me/firms"),
    ("Firms", "/api/v1/firms"),
    ("Users", "/api/v1/users"),
    ("Roles", "/api/v1/roles"),
)


@dataclass
class Check:
    """One thing checked and what became of it."""

    section: str
    name: str
    status: str
    detail: str = ""
    ms: float | None = None
    #: The module of a firm's route (``module_of``); empty for the checks
    #: that are not about one.
    module: str = ""


@dataclass
class QuickCheckReport:
    """Every check of one run, in the order they ran."""

    base_url: str
    email: str
    started: datetime
    checks: list[Check] = field(default_factory=list)

    def count(self, status: str) -> int:
        """Return how many checks ended in ``status``."""
        return sum(check.status == status for check in self.checks)

    @property
    def failed(self) -> bool:
        """Whether anything failed."""
        return self.count(FAIL) > 0


def _status_of(error: HttpError) -> str:
    """Judge an error answer: not permitted is a SKIP, anything else a FAIL."""
    return SKIP if error.status == 403 else FAIL


def _firms(client: Client) -> list[tuple[str, str, str]]:
    """Return (id, code, name) of every firm the signed-in person can open."""
    _, body, _ = client.get("/api/v1/me/firms", {})
    found: list[tuple[str, str, str]] = []
    for row in (body or {}).get("data") or []:
        if not isinstance(row, dict):
            continue
        firm = row.get("firm", row)
        firm_id = str(firm.get("id") or row.get("firm_id") or "")
        if firm_id:
            found.append(
                (firm_id, str(firm.get("code") or ""), str(firm.get("name") or ""))
            )
    return found


def _stores(report: QuickCheckReport, say: Callable[[str], None]) -> None:
    """Check every store is at the newest migration, where this machine can see.

    Run on the server, this reads the registry the way ``migrate-all`` does.
    Run elsewhere, the database is not reachable and the section is a SKIP.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.core.config.settings import Settings
    from app.core.database.engine import DatabaseManager
    from app.core.paths import alembic_ini_path, alembic_script_location
    from app.core.tenancy.migrations import (
        count_firms,
        current_revision,
        migration_targets,
    )

    section = "Stores"
    try:
        config = Config(alembic_ini_path().as_posix())
        config.set_main_option("script_location", alembic_script_location().as_posix())
        head = ScriptDirectory.from_config(config).get_current_head() or "none"
        settings = Settings()
        platform = DatabaseManager.from_settings(settings)
        try:
            fresh = not count_firms(platform)
            targets = migration_targets(platform, settings, platform_only=fresh)
        finally:
            platform.dispose()
    except Exception as error:  # noqa: BLE001 - reported, not raised
        report.checks.append(
            Check(
                section,
                "Read the store registry",
                SKIP,
                f"the database is not reachable from here ({type(error).__name__})",
            )
        )
        return
    for target in targets:
        revision = current_revision(target)
        status = PASS if revision == head else FAIL
        detail = (
            f"at {revision}"
            if status == PASS
            else f"at {revision}, newest is {head}: run migrate-all"
        )
        report.checks.append(Check(section, target.label, status, detail))
        say(f"  {status:<4} {target.label}: {detail}")


def _walk_firm(
    client: Client,
    report: QuickCheckReport,
    routes: list[Route],
    month: Window,
    label: str,
    say: Callable[[str], None],
) -> None:
    """Open every list and report route of one firm, once each."""
    resolver = Resolver(client, month)
    for route in routes:
        path = route.path
        unresolved = [
            name for name in route.path_params if resolver.value(name) is None
        ]
        for name in route.path_params:
            value = resolver.value(name)
            if value is not None:
                path = path.replace("{" + name + "}", value)
        params: dict[str, str] = {}
        pair = route.date_pair
        if route.kind == "report" and pair is not None:
            params[pair[0]] = month.start.isoformat()
            params[pair[1]] = month.end.isoformat()
        if "as_of" in route.query:
            params["as_of"] = month.end.isoformat()
        for name in route.required:
            if name in params:
                continue
            value = resolver.value(name)
            if value is None:
                unresolved.append(name)
            else:
                params[name] = value
        if unresolved:
            report.checks.append(
                Check(
                    label,
                    route.path,
                    SKIP,
                    "the firm has no "
                    + ", ".join(sorted(set(unresolved)))
                    + " to ask about",
                    module=module_of(route.path),
                )
            )
            continue
        check = _call(client, label, route, path, params)
        check.module = module_of(route.path)
        report.checks.append(check)
        if check.status != PASS:
            say(f"  {check.status:<4} {route.path}  {check.detail}")
        if check.status == FAIL and not _answers(client):
            report.checks.append(
                Check(
                    "Server",
                    "The server kept answering",
                    FAIL,
                    f"it stopped answering after {route.path}; the rest of "
                    "the run was abandoned. Look at the server's log, and at "
                    "free memory on the machine.",
                )
            )
            raise _ServerGoneError


class _ServerGoneError(Exception):
    """The server stopped answering part-way through a run."""


def _answers(client: Client) -> bool:
    """Whether the server still answers its health check."""
    try:
        client.get("/health", {})
    except (HttpError, http.client.HTTPException, OSError):
        return False
    return True


def _call(
    client: Client, label: str, route: Route, path: str, params: dict[str, str]
) -> Check:
    """Open one route and judge the answer."""
    try:
        _, _, elapsed = client.get(path, params)
    except HttpError as error:
        return Check(
            label,
            route.path,
            _status_of(error),
            (
                "not permitted for this person"
                if error.status == 403
                else f"{error.status} {error.message}"
            ),
            error.elapsed_ms,
        )
    except (http.client.HTTPException, TimeoutError, OSError) as error:
        return Check(label, route.path, FAIL, repr(error))
    verdict = judge(route.kind, elapsed)
    target = REPORT_TARGET_MS if route.kind == "report" else LIST_TARGET_MS
    return Check(
        label,
        route.path,
        PASS if verdict == "OK" else SLOW,
        "" if verdict == "OK" else f"{elapsed:,.0f} ms against {target:,} ms",
        elapsed,
    )


def run_quick_check(
    *,
    base_url: str,
    email: str,
    password: str,
    firm_codes: list[str] | None = None,
    check_stores: bool = True,
    timeout: float = 60.0,
    say: Callable[[str], None] = print,
) -> QuickCheckReport:
    """Run every check and return what each found.

    Args:
        base_url: Where the server answers, e.g. ``http://127.0.0.1:8000``.
        email: Who to sign in as.
        password: Their password; never stored.
        firm_codes: Only these firms; every firm the person can open if None.
        check_stores: Whether to read the store registry (on the server).
        timeout: Seconds to wait for one answer.
        say: Where progress is written.

    """
    from app.core.utils.dates import utc_now
    from app.main import create_app

    report = QuickCheckReport(base_url=base_url, email=email, started=utc_now())
    client = Client(base_url, email, password, timeout)

    say(f"Quick check of {base_url} as {email}")
    try:
        _, body, elapsed = client.get("/health", {})
        data: dict[str, Any] = (body or {}).get("data") or {}
        report.checks.append(
            Check(
                "Server",
                "The server answers",
                PASS,
                f"version {data.get('version', '?')}, "
                f"{data.get('environment', '?')}",
                elapsed,
            )
        )
        _, _, elapsed = client.get("/health/database", {})
        report.checks.append(Check("Server", "The database answers", PASS, "", elapsed))
    except HttpError as error:
        report.checks.append(Check("Server", "The server answers", FAIL, str(error)))
        return report
    except (http.client.HTTPException, TimeoutError, OSError) as error:
        report.checks.append(
            Check(
                "Server",
                "The server answers",
                FAIL,
                f"nothing answered at {base_url} ({error}); is the server running?",
            )
        )
        return report

    try:
        client.sign_in()
    except HttpError as error:
        report.checks.append(Check("Sign-in", email, FAIL, error.message))
        return report
    report.checks.append(Check("Sign-in", email, PASS))

    if check_stores:
        say("Stores:")
        _stores(report, say)

    for name, path in PLATFORM_READS:
        try:
            _, _, elapsed = client.get(path, {})
            report.checks.append(Check("Platform", name, PASS, path, elapsed))
        except HttpError as error:
            report.checks.append(
                Check(
                    "Platform",
                    name,
                    _status_of(error),
                    (
                        "not permitted for this person"
                        if error.status == 403
                        else f"{error.status} {error.message}"
                    ),
                )
            )

    firms = _firms(client)
    if firm_codes:
        wanted = {code.upper() for code in firm_codes}
        missing = wanted - {code.upper() for _, code, _ in firms}
        for code in sorted(missing):
            report.checks.append(
                Check("Firms", code, FAIL, "this person cannot open a firm so coded")
            )
        firms = [row for row in firms if row[1].upper() in wanted]
    if not firms:
        report.checks.append(
            Check("Firms", "A firm to open", SKIP, "this person can open no firm")
        )
    routes = select_routes(create_app().openapi(), include_exports=False)
    month = last_month(utc_now().date())
    for firm_id, code, firm_name in firms:
        label = f"{code} {firm_name}".strip()
        say(f"{label}: {len(routes)} lists and reports")
        client.firm_id = firm_id
        try:
            _walk_firm(client, report, routes, month, label, say)
        except _ServerGoneError:
            break
    client.firm_id = ""
    return report


def _module_rank(name: str) -> int:
    """Order modules as the sanity cases take them; unnamed ones last."""
    names = [module for module, _ in MODULES]
    return names.index(name) if name in names else len(names)


def by_module(checks: list[Check]) -> list[tuple[str, dict[str, int]]]:
    """Count each module's checks by status, in the sanity cases' order."""
    counts: dict[str, dict[str, int]] = {}
    for check in checks:
        if not check.module:
            continue
        tally = counts.setdefault(check.module, {PASS: 0, SLOW: 0, SKIP: 0, FAIL: 0})
        tally[check.status] = tally.get(check.status, 0) + 1
    return sorted(counts.items(), key=lambda item: (_module_rank(item[0]), item[0]))


def summary(report: QuickCheckReport) -> str:
    """Return the run's totals, each firm module by module, and every failure."""
    lines = [
        "",
        f"{len(report.checks)} checks: {report.count(PASS)} PASS, "
        f"{report.count(SLOW)} SLOW, {report.count(SKIP)} SKIP, "
        f"{report.count(FAIL)} FAIL",
    ]
    sections: dict[str, list[Check]] = {}
    for check in report.checks:
        sections.setdefault(check.section, []).append(check)
    for section, checks in sections.items():
        modules = by_module(checks)
        if not modules:
            continue
        lines.append("")
        lines.append(section)
        lines.append(
            f"  {'module':<28} {'pass':>5} {'slow':>5} {'skip':>5} {'fail':>5}"
        )
        for module, tally in modules:
            lines.append(
                f"  {module:<28} {tally[PASS]:>5} {tally[SLOW]:>5} "
                f"{tally[SKIP]:>5} {tally[FAIL]:>5}"
            )
    lines.append("")
    for check in report.checks:
        if check.status == FAIL:
            lines.append(f"  FAIL  [{check.section}] {check.name}  {check.detail}")
    lines.append(
        "RESULT: " + ("FAILED -- see above" if report.failed else "everything answered")
    )
    return "\n".join(lines)


def write_html(report: QuickCheckReport, target: Path) -> Path:
    """Write the run as one self-contained HTML page and return its path."""
    order = {FAIL: 0, SLOW: 1, SKIP: 2, PASS: 3}
    sections: dict[str, list[Check]] = {}
    for check in report.checks:
        sections.setdefault(check.section, []).append(check)

    def cell(text: object) -> str:
        """Escape one value for the page."""
        return html.escape(str(text))

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Quick check</title><style>",
        "body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1f2937;"
        "background:#fff}",
        "h1{font-size:22px}h2{font-size:17px;margin-top:28px}",
        "table{border-collapse:collapse;width:100%;font-size:13px}",
        "td,th{border-bottom:1px solid #e5e7eb;padding:6px 8px;text-align:left;"
        "vertical-align:top}",
        ".PASS{color:#047857}.SLOW{color:#b45309}.SKIP{color:#6b7280}"
        ".FAIL{color:#b91c1c;font-weight:600}",
        ".total{font-size:15px;margin:8px 0 0}",
        "</style></head><body>",
        "<h1>Quick check</h1>",
        f"<p>{cell(report.base_url)} as {cell(report.email)}, "
        f"{report.started:%d %b %Y %H:%M} UTC</p>",
        f"<p class='total'><b class='{FAIL if report.failed else PASS}'>"
        f"{'FAILED' if report.failed else 'Everything answered'}</b> -- "
        f"{report.count(PASS)} pass, {report.count(SLOW)} slow, "
        f"{report.count(SKIP)} skipped, {report.count(FAIL)} failed</p>",
    ]
    for section, checks in sections.items():
        failed = sum(check.status == FAIL for check in checks)
        parts.append(
            f"<h2>{cell(section)} <span class='{FAIL if failed else PASS}'>"
            f"({len(checks)} checks, {failed} failed)</span></h2>"
        )
        modules = by_module(checks)
        if modules:
            parts.append(
                "<table><tr><th>Module</th><th>Pass</th><th>Slow</th>"
                "<th>Skipped</th><th>Failed</th></tr>"
            )
            for module, tally in modules:
                worst = next((status for status in (FAIL, SLOW) if tally[status]), PASS)
                parts.append(
                    f"<tr><td class='{worst}'>{cell(module)}</td>"
                    f"<td>{tally[PASS]}</td><td>{tally[SLOW]}</td>"
                    f"<td>{tally[SKIP]}</td><td>{tally[FAIL]}</td></tr>"
                )
            parts.append("</table><p></p>")
        parts.append("<table><tr><th>Status</th>")
        if modules:
            parts.append("<th>Module</th>")
        parts.append("<th>Check</th><th>ms</th><th>Detail</th></tr>")
        for check in sorted(
            checks,
            key=lambda item: (
                order.get(item.status, 9),
                _module_rank(item.module),
                item.module,
            ),
        ):
            ms = f"{check.ms:,.0f}" if check.ms is not None else ""
            module_cell = f"<td>{cell(check.module)}</td>" if modules else ""
            parts.append(
                f"<tr><td class='{check.status}'>{check.status}</td>"
                f"{module_cell}<td>{cell(check.name)}</td><td>{ms}</td>"
                f"<td>{cell(check.detail)}</td></tr>"
            )
        parts.append("</table>")
    parts.append("</body></html>")
    target.write_text("\n".join(parts), encoding="utf-8")
    return target
