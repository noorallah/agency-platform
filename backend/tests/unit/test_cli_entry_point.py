"""The compiled build has one entry point, and these are its promises.

``app/cli.py`` is what a customer machine actually runs: there is no
interpreter there and no ``.py`` file to hand one, so anything the product does
on that machine has to be reachable as a subcommand. These tests pin the four
that the installer and the start script call by name -- a renamed subcommand is
a silently broken installation, and nothing else in this suite would see it.

They deliberately do **not** run any of them. Each needs a real PostgreSQL
server; ``tests/integration/`` is where that lives. What is checkable here is
the surface: the commands exist, they parse the arguments their callers pass,
and the two that can destroy something require an explicit ``--yes``.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.cli import build_parser
from app.core.paths import alembic_ini_path, alembic_script_location, application_root

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Exactly the invocations install.ps1 and start_backend.ps1 make. If one of
#: these stops parsing, an installed copy fails at the step that uses it.
_CALLERS = [
    ["create-database"],
    ["migrate-all", "--yes"],
    ["migrate-all", "--dry-run"],
    # The installer refuses a fresh install onto a database that holds firms.
    ["firm-count"],
    ["purge-retention", "--dry-run"],
    ["serve", "--host", "0.0.0.0", "--port", "8000"],
    # The Windows service definition server_setup.ps1 writes for WinSW.
    ["serve", "--host", "127.0.0.1", "--port", "8000"],
    ["serve", "--host", "127.0.0.1", "--port", "8000", "--reload"],
    [
        "serve",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--ssl-certfile",
        "c:\\certs\\erp.crt",
        "--ssl-keyfile",
        "c:\\certs\\erp.key",
    ],
]


@pytest.mark.parametrize("argv", _CALLERS, ids=lambda argv: " ".join(argv))
def test_every_invocation_the_scripts_make_still_parses(argv: list[str]) -> None:
    """Each command line a shipped script writes is one the CLI accepts."""
    parsed = build_parser().parse_args(argv)
    assert callable(parsed.handler)


@pytest.mark.parametrize("command", ["migrate-all", "purge-retention"])
def test_a_command_that_changes_data_refuses_to_guess(command: str) -> None:
    """Neither runs without being told which of --dry-run and --yes is meant.

    A default would make the safe reading and the destructive one one keystroke
    apart, in a command an operator schedules and then stops reading.
    """
    with pytest.raises(SystemExit):
        build_parser().parse_args([command])


def test_dry_run_and_yes_cannot_both_be_given() -> None:
    """Asking for both is a mistake worth refusing rather than resolving."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["migrate-all", "--dry-run", "--yes"])


def test_the_version_flag_reports_the_declared_version() -> None:
    """`agency-server --version` is how an installed copy says what it is."""
    declared = (_REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    completed = subprocess.run(
        [sys.executable, "-m", "app.cli", "--version"],
        cwd=_REPO_ROOT / "backend",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.stdout.strip() == declared, completed.stderr


def test_the_application_root_holds_the_things_alembic_needs() -> None:
    """One answer to "where am I", rather than a parents[n] count per caller.

    Three places each worked this out from ``__file__``, with three different
    counts. The counts were right in a checkout and wrong in a built copy,
    where ``__file__`` names a path inside the binary that nothing was written
    to -- so provisioning a firm would have failed on a customer machine.
    """
    assert application_root() == _REPO_ROOT / "backend"
    assert alembic_ini_path().is_file()
    assert (alembic_script_location() / "env.py").is_file()


def test_the_application_root_is_overridable() -> None:
    """An installed layout that matches neither case can still say where it is."""
    previous = os.environ.get("AGENCY_APPLICATION_ROOT")
    os.environ["AGENCY_APPLICATION_ROOT"] = str(_REPO_ROOT)
    try:
        assert application_root() == _REPO_ROOT
    finally:
        if previous is None:
            del os.environ["AGENCY_APPLICATION_ROOT"]
        else:
            os.environ["AGENCY_APPLICATION_ROOT"] = previous


#: The scripts a customer machine runs. Everything they invoke has to exist in
#: a build with no interpreter and no .py files. server_setup.ps1 is what the
#: Windows installer runs to create the database, the services and the
#: pre-upgrade backup, and it calls agency-server by subcommand like the others.
_SHIPPED_SCRIPTS = (
    _REPO_ROOT / "install" / "install.ps1",
    _REPO_ROOT / "backend" / "scripts" / "start_backend.ps1",
    _REPO_ROOT / "packaging" / "server_setup.ps1",
)

#: Ways of running Python that a built copy does not have. `sys.executable -m
#: alembic` is the specific one that broke firm provisioning: the executable is
#: the application, and there is no `alembic` module to hand it.
#:
#: `seed_multi_firm_demo.py` is the one exception, and deliberately so. It is
#: reached only through `-WithDemoData` -- a switch for showing the product,
#: not for running it -- and build_installer.ps1 does not stage it, because it
#: is tooling for selling this and carries its own passwords. install.ps1
#: refuses the switch outright when there is no interpreter, so the failure is
#: a sentence rather than a stack trace.
#: The quotes and comma in the first two matter: PowerShell writes an argument
#: list as `@('-m', 'alembic', 'upgrade', 'head')`, so a pattern looking for
#: `-m alembic` finds nothing and passes on exactly the code it exists to
#: catch. That was true of the first version of this test, and checking it
#: against the pre-change scripts is what showed it.
_NEEDS_AN_INTERPRETER = (
    (r"-m['\"]?\s*,?\s*['\"]?alembic\b", "runs alembic as a module"),
    (r"-m['\"]?\s*,?\s*['\"]?uvicorn\b", "runs uvicorn as a module"),
    (r"app\.main:app", "names the ASGI app, so it is starting a server itself"),
    (r"scripts[/\\](?!seed_multi_firm_demo)[A-Za-z_]+\.py", "runs a .py script"),
)


@pytest.mark.parametrize("script", _SHIPPED_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_script_reaches_for_nothing_a_build_lacks(script: Path) -> None:
    """Neither script may invoke Python in a way a compiled copy cannot answer.

    This is the guard for the whole arrangement. Both scripts ran `-m alembic`
    and `-m uvicorn` and called scripts by path until 2026-09-17; each would
    have failed on a customer machine at the step that used it, and no other
    test in this suite looks at a .ps1 at all.

    Comments are stripped first: the reasoning above each call names what it
    replaced, and a guard that fails on its own explanation gets deleted.
    """
    source = script.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    for pattern, what in _NEEDS_AN_INTERPRETER:
        found = re.search(pattern, code)
        assert found is None, (
            f"{script.name} {what} ({found.group(0)!r} at offset {found.start()}). "
            "A built copy has no interpreter: use a subcommand of app/cli.py."
        )


def test_a_source_checkout_does_not_think_it_is_a_compiled_build() -> None:
    """The negative case, which is the one running here."""
    from app.core.paths import is_compiled_build

    assert is_compiled_build() is False


def test_nothing_detects_a_compiled_build_by_sys_frozen_alone() -> None:
    """`sys.frozen` is PyInstaller's marker. Nuitka does not set it.

    The first real compiled build of this product, on 2026-09-17, printed
    `frozen: False` from `agency-server.exe` -- so every branch written for a
    built copy was dead in one. `application_root()` happened to return the
    right answer anyway, because Nuitka keeps `__file__` pointing at the layout
    beside the executable, and `serve --reload` silently lost its guard.

    `is_compiled_build()` asks for `__compiled__` as well, and this fails the
    build if somebody reaches for the single marker again.
    """
    for module in ("app/cli.py", "app/core/paths.py"):
        source = (_REPO_ROOT / "backend" / module).read_text(encoding="utf-8")
        code = "\n".join(
            line
            for line in source.splitlines()
            if not line.lstrip().startswith("#") and '"""' not in line
        )
        if "frozen" not in code:
            continue
        assert "__compiled__" in code, (
            f"{module} tests sys.frozen without testing __compiled__. Nuitka "
            "sets only the latter, so the check is dead in the build it is "
            "written for. Use is_compiled_build()."
        )
