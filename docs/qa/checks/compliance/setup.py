"""Set up the accounts the compliance checks sign in as.

    python docs/qa/checks/compliance/setup.py            # builds two firms
    python docs/qa/checks/compliance/setup.py --adopt A.txt B.txt   # reuse printouts

Runs the ``compliance-firm`` fixture twice (two GST-registered Wholesale firms,
each with a registered buyer, a walk-in buyer and invoices A, B and C). Firm one
is read by most checks; firm two is the one a check may change (cancel an
invoice, raise an e-way bill) and the "other firm" of the isolation probe.
Writes ``.state/compliance.json``.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import Api, data, save_state, sign_in  # noqa: E402

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


def describe(platform: Api, text: str) -> dict:
    """Turn one printout into the firm's account and its three invoices."""
    code = grab(r"New firm\s*:\s*(\S+)", text)
    firm_id = ""
    status, body = platform.get(f"/api/v1/firms?search={code}&page_size=50")
    for row in data(body):
        if row.get("code") == code:
            firm_id = str(row["id"])
    if not firm_id:
        raise SystemExit(f"PRECONDITION no firm {code}")
    admin = sign_in(grab(r"Firm admin\s*:\s*(\S+)", text), firm_id=firm_id)
    ids = {}
    for key in ("A", "B", "C"):
        number = grab(rf"Invoice {key}\s*:\s*(\S+):", text)
        rows = data(admin.get(f"/api/v1/sales-invoices?search={number}&page_size=20")[1])
        ids[key] = next(str(r["id"]) for r in rows if r["invoice_number"] == number)
    return {
        "email": grab(r"Firm admin\s*:\s*(\S+)", text),
        "firm_id": firm_id,
        "code": code,
        "gstin": grab(r"Firm GSTIN\s*:\s*(\S+)", text),
        "buyer_gstin": grab(r"GSTIN (\S+)", text),
        "suffix": grab(r"Suffix\s*:\s*(\S+)", text),
        "invoices": ids,
    }


def main() -> None:
    """Run the fixtures (or adopt printouts) and write the state."""
    if len(sys.argv) == 4 and sys.argv[1] == "--adopt":
        one, two = (pathlib.Path(p).read_text(encoding="utf-8") for p in sys.argv[2:4])
    else:
        one, two = fixture("compliance-firm"), fixture("compliance-firm")
    plat = grab(r"Platform admin\s*:\s*(\S+)", one)
    platform = sign_in(plat)
    first, second = describe(platform, one), describe(platform, two)
    save_state(
        {
            "accounts": {
                "platform": {"email": plat},
                "admin": {"email": first["email"], "firm_id": first["firm_id"]},
                "admin2": {"email": second["email"], "firm_id": second["firm_id"]},
            },
            "one": first,
            "two": second,
        },
        "compliance",
    )
    print("state written;", first["code"], second["code"])


if __name__ == "__main__":
    main()
