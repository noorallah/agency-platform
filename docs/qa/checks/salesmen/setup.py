"""Set up the accounts the salesmen checks sign in as.

    python docs/qa/checks/salesmen/setup.py

Runs the ``ready-firm`` fixture twice (two finished Wholesale firms, each with
its Firm admin, a Viewer and a platform admin), makes a Sales executive in
firm one, and writes ``.state/salesmen.json``.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import ensure_user, rows_of  # noqa: E402
from common import save_state, sign_in  # noqa: E402

BACKEND = pathlib.Path(r"D:\ws\agencyApp\agency-platform\backend")


def fixture(name: str) -> str:
    """Run one fixture and return its printout."""
    done = subprocess.run(  # noqa: S603
        [
            str(BACKEND / ".venv" / "Scripts" / "python.exe"),
            str(BACKEND / "scripts" / "test_fixture.py"),
            name,
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"fixture {name} failed: {done.stdout[-600:]} {done.stderr[-600:]}")
    return done.stdout


def grab(pattern: str, text: str) -> str:
    """Return the first group of a pattern, or stop."""
    found = re.search(pattern, text)
    if not found:
        raise SystemExit(f"fixture printout lacks {pattern!r}:\n{text[-800:]}")
    return found.group(1)


def firm_id_of(platform_api, code: str) -> str:  # noqa: ANN001
    """Find a firm's id by code through the platform admin."""
    for row in rows_of(platform_api.get(f"/api/v1/firms?search={code}&page_size=50")):
        if row.get("code") == code:
            return str(row["id"])
    raise SystemExit(f"PRECONDITION no firm {code}")


def main() -> None:
    """Run the fixtures, make the executive and write the state."""
    one = fixture("ready-firm")
    two = fixture("ready-firm")
    plat = grab(r"Platform admin\s*:\s*(\S+)", one)
    platform = sign_in(plat)
    code1 = grab(r"New firm\s*:\s*(\S+)", one)
    code2 = grab(r"New firm\s*:\s*(\S+)", two)
    id1 = firm_id_of(platform, code1)
    id2 = firm_id_of(platform, code2)
    admin1 = grab(r"Firm admin\s*:\s*(\S+)", one)
    tag = admin1.split(".")[0]
    execu = f"{tag}.smexec@fixtures.local"
    ensure_user(platform, execu, f"Salesman check executive ({tag})", id1, "SALES_EXECUTIVE")
    save_state(
        {
            "accounts": {
                "platform": {"email": plat},
                "admin": {"email": admin1, "firm_id": id1},
                "viewer": {"email": grab(r"Viewer\s*:\s*(\S+)", one), "firm_id": id1},
                "exec": {"email": execu, "firm_id": id1},
                "admin2": {"email": grab(r"Firm admin\s*:\s*(\S+)", two), "firm_id": id2},
            },
            "firm_id": id1,
            "firm2_id": id2,
            "suffix": tag,
        },
        "salesmen",
    )
    print("state written;", code1, code2)


if __name__ == "__main__":
    main()
