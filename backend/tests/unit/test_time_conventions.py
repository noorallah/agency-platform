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
"""

import ast
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
