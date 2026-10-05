"""Guard the codebase-wide rule that clocks are read in UTC.

Everything persisted here is UTC: ``BaseEntity`` timestamps, ``UTCDateTime``
columns, ``utc_now()``. ``date.today()`` reads the *server's* local date, so on
any deployment not running in UTC it can already be tomorrow -- or still
yesterday -- relative to the data it is compared against.

That is not hypothetical. It shipped three times before anyone noticed:

* ``uom`` selected a conversion rule that was not yet effective;
* ``batch_serial`` bucketed expiry windows a day out;
* the overdue reports in ``sales_invoice``, ``purchase_invoice`` and
  ``purchase_return``, plus document numbering in ``document_framework``,
  carried the same defect until 2026-08-10.

Each was found and fixed separately, which is the argument for a test rather
than a fourth fix. If a genuine local-time need ever arises, add the site to
``ALLOWED`` with the reason -- do not delete the guard.

**The second guard is about which day, not which clock** (D-CFG-25).
``utc_now().date()`` reads the right clock and the wrong calendar: between
00:00 and 05:30 in India the UTC day is still yesterday. It dated a tax invoice
the day before it was raised, undid a cancelled bill the day before, read a
batch on its last day as having one day left, and listed a shift opened at
02:31 on the 6th under the 5th. Ninety-odd sites were moved to ``firm_today``
/ ``firm_date_of`` / ``firm_day_after`` in four pull requests on 2026-10-06;
this keeps the next one from arriving.
"""

import ast
from collections.abc import Callable
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

# Sites permitted to read the server's local date, with the reason. Empty on
# purpose: nothing in this codebase has a local-time requirement today.
ALLOWED: dict[str, str] = {}


def _local_clock_calls(source: str) -> list[int]:
    """Return the line numbers where a module reads the local date or time.

    Only the stdlib clocks count. ``func.now()`` is SQLAlchemy's SQL ``now()``
    and is evaluated by the database, not by Python, so it is not a local read
    at all -- an earlier version of this guard flagged all four uses of it and
    was wrong, not the code.
    """
    tree = ast.parse(source)
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func
        owner = target.value
        # date.x() / datetime.x() only -- not func.x(), not some_obj.x().
        if not isinstance(owner, ast.Name) or owner.id not in {"date", "datetime"}:
            continue
        naive_today = target.attr == "today"
        # ``now()`` is only naive without an explicit timezone argument.
        naive_now = target.attr == "now" and not node.args and not node.keywords
        if naive_today or naive_now:
            found.append(node.lineno)
    return found


def test_no_application_module_reads_the_servers_local_clock() -> None:
    """Application code must call ``utc_now()``, never a naive local clock."""
    offenders: dict[str, list[int]] = {}
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP.parent).as_posix()
        if relative in ALLOWED:
            continue
        lines = _local_clock_calls(path.read_text(encoding="utf-8"))
        if lines:
            offenders[relative] = lines

    assert not offenders, (
        "these read the server's local clock instead of utc_now(): "
        f"{offenders}. Everything persisted here is UTC, so a local read "
        "compares against a date the data does not use."
    )


def test_the_guard_sees_local_clocks_and_ignores_the_database_clock() -> None:
    """A guard that cannot fail is not a guard, and one that cries wolf is worse.

    Pins the detector against the shapes it exists to catch *and* the ones it
    must leave alone. ``func.now()`` is the important negative: it is SQL
    evaluated by the database, and the first version of this guard reported all
    four uses of it as defects.
    """
    source = (
        "from datetime import date, datetime\n"
        "a = date.today()\n"
        "b = datetime.now()\n"
        "c = datetime.today()\n"
        "d = datetime.now(tz=None)\n"
        "e = func.now()\n"
        "f = utc_now()\n"
        "g = something.now()\n"
    )

    # Lines 2-4 are naive stdlib reads. Line 5 passes an explicit tz, line 6 is
    # the database clock, line 7 is the helper this rule points people at, and
    # line 8 is some unrelated object.
    assert _local_clock_calls(source) == [2, 3, 4]


# -- which day: the firm's, not UTC's (D-CFG-25) ------------------------------

#: Where the UTC day is still read on purpose, each with its reason. Anything
#: else that turns "now" into a day is a business date and takes
#: ``firm_today(session, firm_id)`` (or ``firm_date_of`` for a stored instant).
UTC_DAY_ALLOWED: dict[str, str] = {
    "app/diagnostics/quick_check.py": (
        "a command-line client of a running server, with no session and no "
        "firm row; it only picks last month as a window that holds data"
    ),
}

#: Where a day's boundary is still drawn at UTC midnight on purpose. A new
#: boundary round a firm's day takes ``firm_day_start`` / ``firm_day_after``.
UTC_MIDNIGHT_ALLOWED: dict[str, str] = {
    "app/common/audit/services/reader.py": (
        "the audit trail's date filters are inclusive UTC calendar days by "
        "the documented convention, and the platform trail has no firm"
    ),
    "app/customers/repositories/customer_repository.py": (
        "created_from / created_to: the same documented UTC convention"
    ),
    "app/vendors/repositories/vendor_repository.py": (
        "created_from / created_to: the same documented UTC convention"
    ),
    "app/branches/repositories/branch_warehouse_repository.py": (
        "created_from / created_to: the same documented UTC convention"
    ),
}


def _is_utc_now(node: ast.AST) -> bool:
    """Say whether an expression is ``utc_now()``, bare or behind an ``or``."""
    if isinstance(node, ast.BoolOp):
        return any(_is_utc_now(value) for value in node.values)
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "utc_now"
    )


def _utc_day_reads(source: str) -> list[int]:
    """Return the lines where a module turns the UTC "now" into a calendar day.

    Two shapes: ``utc_now().date()`` itself, and ``now = utc_now()`` followed
    by ``now.date()`` in the same function, which is how three of the sites
    were written. A ``.date()`` on anything else -- a parsed string, a stored
    column -- is not a read of today and is left alone.
    """
    found: set[int] = set()
    scopes = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module))
    ]
    for scope in scopes:
        clocks: set[str] = set()
        if not isinstance(scope, ast.Module):
            for node in ast.walk(scope):
                if isinstance(node, ast.Assign) and _is_utc_now(node.value):
                    clocks.update(
                        target.id
                        for target in node.targets
                        if isinstance(target, ast.Name)
                    )
        for node in ast.walk(scope):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "date"
                and not node.args
            ):
                continue
            owner = node.func.value
            if _is_utc_now(owner) or (
                isinstance(owner, ast.Name) and owner.id in clocks
            ):
                found.add(node.lineno)
    return sorted(found)


def _utc_midnights(source: str) -> list[int]:
    """Return the lines building a day's boundary by ``datetime.combine`` in UTC."""
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "combine"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "datetime"
        ):
            continue
        zones = [*node.args[2:], *(keyword.value for keyword in node.keywords)]
        if any(isinstance(zone, ast.Name) and zone.id == "UTC" for zone in zones):
            found.append(node.lineno)
    return found


def _offenders(
    detector: Callable[[str], list[int]], allowed: dict[str, str]
) -> dict[str, list[int]]:
    """Run a detector over ``app/``, leaving out the allowed files."""
    offenders: dict[str, list[int]] = {}
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP.parent).as_posix()
        if relative in allowed:
            continue
        lines = detector(path.read_text(encoding="utf-8"))
        if lines:
            offenders[relative] = lines
    return offenders


def test_no_application_module_reads_today_as_the_utc_day() -> None:
    """A business date is the firm's own day: ``firm_today``, not the UTC day."""
    offenders = _offenders(_utc_day_reads, UTC_DAY_ALLOWED)

    assert not offenders, (
        f"these read today as the UTC day: {offenders}. Until 05:30 in India "
        "that is yesterday. Use firm_today(session, firm_id), or "
        "firm_date_of(session, firm_id, instant) for a stored timestamp "
        "(app/common/firm_metadata.py); thread the day in from the caller "
        "where there is no firm to hand. If the UTC day really is meant, add "
        "the file to UTC_DAY_ALLOWED with the reason."
    )


def test_no_application_module_draws_a_firms_day_at_utc_midnight() -> None:
    """A day's boundary on a timestamp is ``firm_day_start``/``firm_day_after``."""
    offenders = _offenders(_utc_midnights, UTC_MIDNIGHT_ALLOWED)

    assert not offenders, (
        f"these draw a day's boundary at UTC midnight: {offenders}. For a "
        "firm in India that is five and a half hours late. Use "
        "firm_day_start / firm_day_after (app/common/firm_metadata.py), or "
        "add the file to UTC_MIDNIGHT_ALLOWED with the reason."
    )


def test_the_allow_lists_name_files_that_still_need_them() -> None:
    """An entry that no longer offends is a hole left open for the next one."""
    for detector, allowed in (
        (_utc_day_reads, UTC_DAY_ALLOWED),
        (_utc_midnights, UTC_MIDNIGHT_ALLOWED),
    ):
        for relative in allowed:
            source = (APP.parent / relative).read_text(encoding="utf-8")
            assert detector(source), f"{relative} no longer needs its exemption"


def test_the_day_guards_see_what_they_exist_to_catch() -> None:
    """Both shapes of a UTC day, the UTC midnight, and what must be left alone."""
    source = (
        "def f(row, now=None):\n"
        "    a = utc_now().date()\n"
        "    moment = now or utc_now()\n"
        "    b = moment.date()\n"
        "    c = row.created_at.date()\n"
        "    d = firm_today(session, firm_id)\n"
        "    e = datetime.strptime(text, '%d-%m-%Y').date()\n"
        "def g(stamp):\n"
        "    moment = stamp\n"
        "    return moment.date()\n"
    )
    # Line 5 is a stored instant (firm_date_of's job, but not a read of
    # today), 6 is the helper, 7 parses a string, and g's `moment` was never
    # the clock.
    assert _utc_day_reads(source) == [2, 4]

    boundaries = (
        "a = datetime.combine(day, time.min, tzinfo=UTC)\n"
        "b = datetime.combine(day, time.max, UTC)\n"
        "c = datetime.combine(day, time.min, tzinfo=business_zone(code))\n"
        "d = datetime.combine(day, time.min)\n"
    )
    assert _utc_midnights(boundaries) == [1, 2]
