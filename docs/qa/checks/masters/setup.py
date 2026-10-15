"""Set up the accounts the masters checks sign in as.

    python docs/qa/checks/masters/setup.py            # runs four fixtures
    python docs/qa/checks/masters/setup.py --adopt CM_SFX BR_SFX SM_SFX ACC_SFX

Fixtures: ``customer-master`` (TEST01 Firm admin + Seller + a described
customer), ``branch-master`` (TEST02 admin with a branch, warehouse and two
import files), ``loyalty-viewer`` (a SALES_MANAGER of TEST01) and
``accountant`` (an ACCOUNTANT of TEST01). ``--adopt`` reuses earlier runs by
their suffix. Writes ``.state/masters.json``. The vendors and products the
checks need they make themselves.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import data, save_state, sign_in  # noqa: E402

BACKEND = pathlib.Path(r"D:\ws\agencyApp\agency-platform\backend")
NAMES = ("customer-master", "branch-master", "loyalty-viewer", "accountant")


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


def firm_of(email: str, code: str) -> str:
    """Return the id of the firm with this code that the user belongs to."""
    me = sign_in(email)
    for row in data(me.get("/api/v1/me/firms")[1]):
        if row.get("code") == code or row.get("firm_code") == code:
            return str(row.get("id") or row.get("firm_id"))
    raise SystemExit(f"{email} is not in {code}")


def main() -> None:
    """Run the fixtures (or adopt suffixes) and write the state."""
    if len(sys.argv) == 6 and sys.argv[1] == "--adopt":
        cm, br, sm, acc = sys.argv[2:6]
    else:
        cm, br, sm, acc = (fixture(n) for n in NAMES)
    mail = lambda sfx, who: f"{sfx}.{who}@fixtures.local"  # noqa: E731
    one = firm_of(mail(cm, "admin"), "TEST01")
    two = firm_of(mail(br, "t2admin"), "TEST02")
    save_state(
        {
            "accounts": {
                "admin": {"email": mail(cm, "admin"), "firm_id": one},
                "seller": {"email": mail(cm, "seller"), "firm_id": one},
                "manager": {"email": mail(sm, "loyaltyview"), "firm_id": one},
                "accountant": {"email": mail(acc, "accountant"), "firm_id": one},
                "admin2": {"email": mail(br, "t2admin"), "firm_id": two},
            },
            "one": {"firm_id": one, "suffix": cm, "customer_code": f"{cm.upper()}-CM",
                    "product_code": f"{cm.upper()}-P"},
            "two": {"firm_id": two, "suffix": br, "branch_code": f"{br.upper()}-BR",
                    "warehouse_code": f"{br.upper()}-WH"},
        },
        "masters",
    )
    print("state written;", cm, br, sm, acc)


if __name__ == "__main__":
    main()
