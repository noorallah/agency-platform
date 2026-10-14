"""Set up the accounts the costing-by-lot checks (TC-LOT-001..014) sign in as.

    python docs/qa/checks/lots/setup.py

Runs the ``lot-firm`` fixture once (TEST03: by lot from 2026-04-01, LOT-BATCH
with lots of 10 at 50 [TEST03-B1] and 10 at 65 [no batch], LOT-PLAIN, LOT-V,
LOT-C) and the ``platform-admin`` fixture (the account that makes firms and
users), parses their printouts, makes an Inventory manager and a Viewer in
TEST03, makes one firm still on Average for TC-LOT-001, and writes
``.state/lots.json``. Running it again refreshes the fixtures' admins and finds
the users.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from _lot import ensure_user, new_average_firm  # noqa: E402
from common import PASSWORD, data, message, save_state, sign_in  # noqa: E402

BACKEND = pathlib.Path(r"D:\ws\agencyApp\agency-platform\backend")


def fixture(name: str) -> str:
    """Run one fixture and return its printout."""
    done = subprocess.run(  # noqa: S603
        [str(BACKEND / ".venv" / "Scripts" / "python.exe"), "scripts\\test_fixture.py", name],
        cwd=BACKEND, capture_output=True, text=True, timeout=1200, check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"fixture {name} failed: {done.stdout[-600:]} {done.stderr[-600:]}")
    return done.stdout


def main() -> None:
    """Run the fixtures, make the role users and write the state."""
    lot_out = fixture("lot-firm")
    pa_out = fixture("platform-admin")
    firm_id = re.search(r"id ([0-9a-f-]{36})", lot_out).group(1)  # type: ignore[union-attr]
    admin_email = re.search(r"Firm admin\s*:\s*(\S+)", lot_out).group(1)  # type: ignore[union-attr]
    platform_email = re.search(r"Platform admin\s*:\s*(\S+)", pa_out).group(1)  # type: ignore[union-attr]
    suffix = admin_email.split(".")[0]
    platform = sign_in(platform_email)
    accounts = {
        "platform": {"email": platform_email},
        "admin": {"email": admin_email, "firm_id": firm_id},
    }
    for handle, role, title in (("store", "INVENTORY_MANAGER", "Lot store"),
                                ("viewer", "VIEWER", "Lot viewer")):
        email = f"{suffix}.lot{handle}@fixtures.local"
        ensure_user(platform, email, f"{title} ({suffix})", firm_id, role)
        accounts[handle] = {"email": email, "firm_id": firm_id, "role": role}
    average = new_average_firm(platform, "A")
    save_state({"accounts": accounts, "firm_id": firm_id, "average_firm": average,
                "suffix": suffix}, "lots")
    print("state written; TEST03", firm_id, "average firm", average["code"])


if __name__ == "__main__":
    main()
