"""Set up the accounts the offers-on-the-line checks (TC-OFR-001..012) sign in as.

    python docs/qa/checks/offers/setup.py                  # runs selling-firm
    python docs/qa/checks/offers/setup.py <admin email>    # reuses a built one

Runs the ``selling-firm`` fixture once (a Wholesale firm of its own: BULK5 at
25+, CLEARANCE at 40+, BIGORDER on a bill of 4,500+, WELCOME by coupon) and
the ``platform-admin`` fixture, finds the firm, makes a Sales executive
("clerk", who holds SALES_OFFER_CHOOSE) and a user of a custom role holding
the Sales executive's codes less SALES_OFFER_CHOOSE ("nochoose"), and writes
``.state/offers.json``. Every check keeps its lines below 13 pieces and its
bills below 4,500, so the fixture's own offers never reach them.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from _offer import ensure_user, must, rows_of  # noqa: E402
from common import Api, save_state, sign_in  # noqa: E402

BACKEND = pathlib.Path(r"D:\ws\agencyApp\agency-platform\backend")


def fixture(name: str) -> str:
    """Run one fixture and return its printout."""
    done = subprocess.run(  # noqa: S603
        [
            str(BACKEND / ".venv" / "Scripts" / "python.exe"),
            "scripts\\test_fixture.py",
            name,
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=1200,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(
            f"fixture {name} failed: {done.stdout[-600:]} {done.stderr[-600:]}"
        )
    return done.stdout


def no_choose_role(api: Api, code: str) -> None:
    """Make the firm's custom role: a Sales executive less SALES_OFFER_CHOOSE.

    ``api`` is the firm's administrator, so the role is the firm's own.
    """
    roles = rows_of(api.get(f"/api/v1/roles?search={code}&page_size=50"))
    role = next((r for r in roles if r["code"] == code), None)
    if role is None:
        role = must(
            api.post(
                "/api/v1/roles",
                {"code": code, "name": "Sales executive, no offer choice"},
            ),
            "custom role",
        )
    base = rows_of(api.get("/api/v1/roles?search=SALES_EXECUTIVE&page_size=50"))
    executive = next(r for r in base if r["code"] == "SALES_EXECUTIVE")
    ids = must(api.get(f"/api/v1/roles/{executive['id']}/permissions"), "perms")["ids"]
    perms = rows_of(
        api.get("/api/v1/permissions?search=SALES_OFFER_CHOOSE&page_size=50")
    )
    choose = next(p["id"] for p in perms if p["code"] == "SALES_OFFER_CHOOSE")
    kept = [i for i in ids if i != choose]
    if len(kept) != len(ids) - 1:
        raise SystemExit(
            "PRECONDITION the Sales executive does not hold SALES_OFFER_CHOOSE"
        )
    must(
        api.put(f"/api/v1/roles/{role['id']}/permissions", {"ids": kept}), "role perms"
    )


def main() -> None:
    """Run the fixtures, make the users and write the state."""
    if len(sys.argv) > 1:
        admin_email = sys.argv[1]
    else:
        out = fixture("selling-firm")
        admin_email = re.search(r"Firm admin\s*:\s*(\S+)", out).group(1)  # type: ignore[union-attr]
    pa_out = fixture("platform-admin")
    platform_email = re.search(r"Platform admin\s*:\s*(\S+)", pa_out).group(1)  # type: ignore[union-attr]
    firms = must(sign_in(admin_email).get("/api/v1/me/firms"), "my firms")
    firms = firms if isinstance(firms, list) else firms.get("firms", [])
    firm = next(f for f in firms if str(f.get("code", "")).endswith("-S"))
    firm_id = str(firm.get("firm_id") or firm["id"])
    suffix = admin_email.split(".")[0]
    platform = sign_in(platform_email)
    no_choose = f"ofr-no-choose-{suffix}"
    no_choose_role(sign_in(admin_email, firm_id=firm_id), no_choose)
    accounts = {
        "platform": {"email": platform_email},
        "admin": {"email": admin_email, "firm_id": firm_id},
    }
    for handle, role, title in (
        ("clerk", "SALES_EXECUTIVE", "Offer clerk"),
        ("nochoose", no_choose, "Offer clerk without the choice"),
    ):
        email = f"{suffix}.ofr{handle}@fixtures.local"
        ensure_user(platform, email, f"{title} ({suffix})", firm_id, role)
        accounts[handle] = {"email": email, "firm_id": firm_id, "role": role}
    save_state(
        {
            "accounts": accounts,
            "firm_id": firm_id,
            "firm_code": firm.get("code"),
            "suffix": suffix,
        },
        "offers",
    )
    print("state written;", firm.get("code"), firm_id)


if __name__ == "__main__":
    main()
