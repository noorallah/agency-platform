"""Set up the TEST01 accounts the concurrency check signs in as.

    python docs/qa/checks/concurrency/setup.py            # runs three fixtures
    python docs/qa/checks/concurrency/setup.py --adopt CM_SFX SM_SFX ACC_SFX

Fixtures: ``customer-master`` (TEST01 Firm admin + Seller), ``loyalty-viewer``
(a SALES_MANAGER of TEST01) and ``accountant`` (an ACCOUNTANT of TEST01) --
the same three the masters checks use, so ``--adopt`` can reuse the suffixes
in ``.state/masters.json``. Never a demo firm. Writes
``.state/concurrency.json``.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import data, save_state, sign_in  # noqa: E402

BACKEND = pathlib.Path(r"D:\ws\agencyApp\agency-platform\backend")
NAMES = ("customer-master", "loyalty-viewer", "accountant")


def fixture(name: str) -> str:
    """Run one fixture and return the suffix it printed."""
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
    found = re.search(r"Suffix\s*:\s*(\S+)", done.stdout)
    if done.returncode != 0 or not found:
        raise SystemExit(
            f"fixture {name} failed: {done.stdout[-500:]} {done.stderr[-500:]}"
        )
    return found.group(1)


def firm_of(email: str, code: str) -> str:
    """Return the id of the firm with this code that the user belongs to."""
    me = sign_in(email)
    for row in data(me.get("/api/v1/me/firms")[1]):
        if row.get("code") == code or row.get("firm_code") == code:
            return str(row.get("id") or row.get("firm_id"))
    raise SystemExit(f"{email} is not in {code}")


def main() -> None:
    """Run the fixtures (or adopt suffixes) and write the state."""
    if len(sys.argv) == 5 and sys.argv[1] == "--adopt":
        cm, sm, acc = sys.argv[2:5]
    else:
        cm, sm, acc = (fixture(n) for n in NAMES)

    def mail(sfx: str, who: str) -> str:
        """Return a fixture account's address."""
        return f"{sfx}.{who}@fixtures.local"

    one = firm_of(mail(cm, "admin"), "TEST01")
    save_state(
        {
            "accounts": {
                "admin": {"email": mail(cm, "admin"), "firm_id": one},
                "seller": {"email": mail(cm, "seller"), "firm_id": one},
                "manager": {"email": mail(sm, "loyaltyview"), "firm_id": one},
                "accountant": {"email": mail(acc, "accountant"), "firm_id": one},
            },
            "firm_id": one,
            "firm_code": "TEST01",
        },
        "concurrency",
    )
    print("state written;", cm, sm, acc)


if __name__ == "__main__":
    main()
