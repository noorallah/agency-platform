"""Set up the accounts the Settings-section checks (TC-CONF-010..015) sign in as.

    python docs/qa/checks/settings/setup.py

Runs the ``ready-firm`` fixture (a finished Wholesale firm: books open, GST
template applied, head office; its Firm admin and a Viewer; a platform admin),
then ``unfinished-firm`` (a provisioned firm with nothing set up, and a second
platform admin), makes a Firm admin of that bare firm, and writes
``.state/settings.json``.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _settings import must, rows_of  # noqa: E402
from common import PASSWORD, save_state, sign_in  # noqa: E402

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
        raise SystemExit(
            f"fixture {name} failed: {done.stdout[-600:]} {done.stderr[-600:]}"
        )
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
    """Run the fixtures, make the bare firm's admin and write the state."""
    ready_out = fixture("ready-firm")
    ready_code = grab(r"New firm\s*:\s*(\S+)", ready_out)
    ready_admin = grab(r"Firm admin\s*:\s*(\S+)", ready_out)
    viewer = grab(r"Viewer\s*:\s*(\S+)", ready_out)
    plat = grab(r"Platform admin\s*:\s*(\S+)", ready_out)
    bare_out = fixture("unfinished-firm")
    bare_code = grab(r"New firm\s*:\s*(\S+)", bare_out)
    platform = sign_in(plat)
    ready_id = firm_id_of(platform, ready_code)
    bare_id = firm_id_of(platform, bare_code)
    tag = ready_admin.split(".")[0]
    bare_admin = f"{tag}.bareadmin@fixtures.local"
    found = [
        r
        for r in rows_of(platform.get(f"/api/v1/users?search={bare_admin}&page_size=10"))
        if r.get("email") == bare_admin
    ]
    if not found:
        uid = must(
            platform.post(
                "/api/v1/users",
                {
                    "email": bare_admin,
                    "full_name": f"Bare Firm Admin {tag}",
                    "password": PASSWORD,
                    "is_active": True,
                    "force_password_change": False,
                },
            ),
            "bare admin",
        )["id"]
        must(
            platform.put(
                f"/api/v1/users/{uid}/firms",
                {
                    "assignments": [
                        {"firm_id": bare_id, "is_primary": True, "is_active": True}
                    ]
                },
            ),
            "bare membership",
        )
        roles = rows_of(
            platform.inside(bare_id).get("/api/v1/roles?search=FIRM_ADMIN&page_size=50")
        )
        role = next(r for r in roles if r["code"] == "FIRM_ADMIN")
        must(
            platform.put(
                f"/api/v1/users/{uid}/firms/{bare_id}/roles", {"ids": [role["id"]]}
            ),
            "bare role",
        )
    save_state(
        {
            "accounts": {
                "platform": {"email": plat},
                "ready_admin": {"email": ready_admin, "firm_id": ready_id},
                "viewer": {"email": viewer, "firm_id": ready_id},
                "bare_admin": {"email": bare_admin, "firm_id": bare_id},
            },
            "ready_id": ready_id,
            "ready_code": ready_code,
            "bare_id": bare_id,
            "bare_code": bare_code,
            "suffix": tag,
        }
    )
    print("state written;", ready_code, bare_code)


if __name__ == "__main__":
    main()
