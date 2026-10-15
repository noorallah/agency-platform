"""Set up the accounts the users-roles checks sign in as.

    python docs/qa/checks/users-roles/setup.py            # runs two fixtures
    python docs/qa/checks/users-roles/setup.py --adopt SM_SFX SE_SFX

Fixtures: ``shared-member-roles`` (TEST01 Firm admin, a platform admin who
belongs to no firm, a user in both test firms, a TEST02-only user) and
``sales-executive`` (a TEST01 Seller). ``--adopt`` reuses earlier runs by
their suffix. Writes ``.state/users-roles.json``. Every user, role and
template the checks need they make themselves, under a fresh tag, so no check
spends the shared fixtures' people.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import data, save_state, sign_in  # noqa: E402

BACKEND = pathlib.Path(r"D:\ws\agencyApp\agency-platform\backend")
NAMES = ("shared-member-roles", "sales-executive")


def fixture(name: str) -> str:
    """Run one fixture and return the suffix it printed."""
    done = subprocess.run(  # noqa: S603
        [
            str(BACKEND / ".venv" / "Scripts" / "python.exe"),
            str(BACKEND / "scripts" / "test_fixture.py"),
            name,
        ],
        cwd=BACKEND, capture_output=True, text=True, timeout=1800, check=False,
    )
    found = re.search(r"Suffix\s*:\s*(\S+)", done.stdout)
    if done.returncode != 0 or not found:
        raise SystemExit(f"fixture {name} failed: {done.stdout[-500:]} {done.stderr[-500:]}")
    return found.group(1)


def main() -> None:
    """Run the fixtures (or adopt suffixes) and write the state."""
    if len(sys.argv) == 4 and sys.argv[1] == "--adopt":
        sm, se = sys.argv[2:4]
    else:
        sm, se = (fixture(n) for n in NAMES)
    mail = lambda sfx, who: f"{sfx}.{who}@fixtures.local"  # noqa: E731
    platform = sign_in(mail(sm, "platform"))
    firms = {r["code"]: str(r["id"]) for r in data(platform.get("/api/v1/firms?page_size=100")[1])}
    one, two = firms["TEST01"], firms["TEST02"]
    save_state(
        {
            "accounts": {
                "admin": {"email": mail(sm, "admin"), "firm_id": one},
                "platform": {"email": mail(sm, "platform")},
                "seller": {"email": mail(se, "seller"), "firm_id": one},
            },
            "one": one,
            "two": two,
            "shared_email": mail(sm, "shared"),
            "t2only_email": mail(sm, "t2only"),
        },
        "users-roles",
    )
    print("state written;", sm, se)


if __name__ == "__main__":
    main()
