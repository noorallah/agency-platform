r"""The installer must lock the data folder on every install and upgrade (D-QA-3).

`C:\ProgramData\Agency Platform` holds the raw database files. Left to
inherit from ProgramData, every local Windows user can read them, which reads
every firm's data without signing in. Nothing on a build machine can run the
ACL change, so this reads the script: the lock is defined, it removes
inheritance, and the server path calls it before anything goes in the folder.
"""

import re
from pathlib import Path

_SETUP = Path(__file__).resolve().parents[3] / "packaging" / "server_setup.ps1"


def _function_body(text: str, name: str) -> str:
    """Return the text of one PowerShell function, up to the next one."""
    match = re.search(rf"^function {name} \{{(.*?)^function ", text, re.S | re.M)
    assert match, f"{name} is not defined in server_setup.ps1"
    return match.group(1)


def test_the_data_root_drops_inherited_access() -> None:
    """Inheritance is removed and only Administrators and SYSTEM keep full."""
    body = _function_body(_SETUP.read_text(encoding="utf-8"), "Protect-DataRoot")
    assert "'/inheritance:r'" in body
    assert "${SidAdministrators}:(OI)(CI)F" in body
    assert "${SidSystem}:(OI)(CI)F" in body


def test_the_server_path_locks_the_folder_before_using_it() -> None:
    """Invoke-Server calls the lock before it creates or reads the cluster."""
    body = _function_body(_SETUP.read_text(encoding="utf-8"), "Invoke-Server")
    lock = body.find("Protect-DataRoot")
    assert lock != -1, "an install or upgrade would leave the folder open"
    assert lock < body.find("Initialize-Cluster")
