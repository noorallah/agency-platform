"""``agency-server quick-check``: the owner's sanity check of an installation."""

from datetime import UTC, datetime
from pathlib import Path

from app.cli import build_parser
from app.diagnostics.quick_check import (
    FAIL,
    PASS,
    SKIP,
    SLOW,
    Check,
    QuickCheckReport,
    run_quick_check,
    summary,
    write_html,
)


def _report(*checks: Check) -> QuickCheckReport:
    """Return a run holding these checks."""
    report = QuickCheckReport(
        base_url="http://127.0.0.1:8000",
        email="owner@example.com",
        started=datetime(2026, 10, 2, 18, 30, tzinfo=UTC),
    )
    report.checks.extend(checks)
    return report


def test_a_server_that_does_not_answer_is_one_plain_failure() -> None:
    """Nothing listening: one FAIL that says what to look at, and no more."""
    lines: list[str] = []
    report = run_quick_check(
        # Port 9 (discard) is never this server.
        base_url="http://127.0.0.1:9",
        email="owner@example.com",
        password="unused",
        check_stores=False,
        timeout=2.0,
        say=lines.append,
    )
    [check] = report.checks
    assert (check.section, check.status) == ("Server", FAIL)
    assert "is the server running?" in check.detail
    assert report.failed


def test_the_summary_counts_and_names_every_failure() -> None:
    """The totals, then each failure with its section and the server's words."""
    text = summary(
        _report(
            Check("Server", "The server answers", PASS),
            Check("KUMAR", "/api/v1/sales-invoices", FAIL, "500 Internal error"),
            Check("KUMAR", "/api/v1/products", SLOW, "1,400 ms"),
            Check("Platform", "Users", SKIP, "not permitted for this person"),
        )
    )
    assert "4 checks: 1 PASS, 1 SLOW, 1 SKIP, 1 FAIL" in text
    assert "FAIL  [KUMAR] /api/v1/sales-invoices  500 Internal error" in text
    assert text.endswith("RESULT: FAILED -- see above")


def test_a_clean_run_says_so() -> None:
    """Skips and slow answers are not failures."""
    report = _report(
        Check("Server", "The server answers", PASS),
        Check("Platform", "Users", SKIP, "not permitted for this person"),
        Check("KUMAR", "/api/v1/products", SLOW, "1,400 ms"),
    )
    assert not report.failed
    assert summary(report).endswith("RESULT: everything answered")


def test_the_page_lists_failures_first_and_escapes_what_the_server_said(
    tmp_path: Path,
) -> None:
    """One self-contained page; a message is text, never markup."""
    target = write_html(
        _report(
            Check("KUMAR", "/api/v1/products", PASS),
            Check("KUMAR", "/api/v1/sales-invoices", FAIL, "<b>boom</b>"),
        ),
        tmp_path / "quick.html",
    )
    page = target.read_text(encoding="utf-8")
    assert "&lt;b&gt;boom&lt;/b&gt;" in page and "<b>boom</b>" not in page
    assert page.index("/api/v1/sales-invoices") < page.index("/api/v1/products")
    assert "FAILED" in page


def test_the_command_is_offered_by_the_shipped_binary() -> None:
    """``quick-check`` is a subcommand of ``app/cli.py``, not a script."""
    args = build_parser().parse_args(
        [
            "quick-check",
            "--email",
            "owner@example.com",
            "--firm",
            "KUMAR",
            "--firm",
            "WHOLE01",
            "--no-stores",
        ]
    )
    assert args.firm == ["KUMAR", "WHOLE01"]
    assert args.no_stores and args.base_url == "http://127.0.0.1:8000"


def test_routes_are_grouped_into_the_modules_the_sanity_cases_use() -> None:
    """A route belongs to the module its first segment names."""
    from app.diagnostics.quick_check import module_of

    assert module_of("/api/v1/sales-invoices/summary") == "Selling"
    assert module_of("/api/v1/goods-receipts") == "Buying"
    assert module_of("/api/v1/finance/trial-balance") == "Accounts"
    assert module_of("/api/v1/gst-returns/gstr1") == "GST and compliance"
    # A module named nowhere still shows, under its own segment.
    assert module_of("/api/v1/something-new") == "something-new"


def test_every_walked_route_has_a_named_module() -> None:
    """A new top-level resource must be filed, or the report scatters it."""
    from app.diagnostics.quick_check import MODULES, module_of
    from app.diagnostics.route_walk import select_routes
    from app.main import create_app

    named = {name for name, _ in MODULES}
    routes = select_routes(create_app().openapi(), include_exports=False)
    loose = sorted({module_of(r.path) for r in routes} - named)
    assert not loose, f"file these under a module in MODULES: {loose}"


def test_the_summary_and_page_show_each_firm_module_by_module(
    tmp_path: Path,
) -> None:
    """Per firm: one row per module with its counts, in the cases' order."""
    report = _report(
        Check("WHOLE01", "/api/v1/goods-receipts", PASS, module="Buying"),
        Check("WHOLE01", "/api/v1/sales-invoices", FAIL, "500", module="Selling"),
        Check("WHOLE01", "/api/v1/quotations", SLOW, "1,200 ms", module="Selling"),
    )
    text = summary(report)
    assert text.index("Selling") < text.index("Buying")
    assert "  Selling                          0     1     0     1" in text
    page = write_html(report, tmp_path / "q.html").read_text(encoding="utf-8")
    assert "<th>Module</th>" in page and "<td class='FAIL'>Selling</td>" in page
