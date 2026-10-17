"""Helpers the commission PAYOUT checks share (not a check).

Actors, on the firm the salesmen state points at:
  admin   Firm admin; accrues payouts.
  acct1   ACCOUNTANT; approves (not the accruer).
  acct2   ACCOUNTANT; pays (not the approver).
  mgr     custom role holding COMMISSION_VIEW + COMMISSION_MANAGE only.
  smgr    SALES_MANAGER (holds neither MANAGE nor PAY).
Users and the custom role are found or made once per firm, never reset.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *  # noqa: E402,F401,F403
from _sm import (  # noqa: E402
    COMM, Api, D, Decimal, Scene, admin, ensure_user, must, rows_of, rule, sell,
    sign_in, state, suffix, timedelta, today,
)

JE = "/api/v1/finance/journal-entries"
PAYOUTS = f"{COMM}/payouts"
MGR_ROLE = "comm-mgr-only"


def _firm() -> str:
    return str(state("salesmen")["firm_id"])


def _tag() -> str:
    return str(state("salesmen")["suffix"])


def _mgr_role(platform: Api, firm_id: str) -> None:
    """Find or make the custom role holding view + manage commission only."""
    inside = admin()
    found = [
        r
        for r in rows_of(inside.get(f"/api/v1/roles?search={MGR_ROLE}&page_size=50"))
        if r["code"] == MGR_ROLE
    ]
    role = found[0] if found else must(
        inside.post("/api/v1/roles", {"code": MGR_ROLE, "name": "Commission manage only"}),
        "custom role",
    )
    perms = rows_of(inside.get("/api/v1/permissions?search=COMMISSION_&page_size=100"))
    ids = [p["id"] for p in perms if p["code"] in ("COMMISSION_VIEW", "COMMISSION_MANAGE")]
    if len(ids) != 2:
        raise SystemExit("PRECONDITION commission permissions not found")
    must(inside.put(f"/api/v1/roles/{role['id']}/permissions", {"ids": ids}), "role perms")


def actors() -> dict[str, Api]:
    """Return signed-in clients of the five actors, each inside the firm."""
    firm_id, tag = _firm(), _tag()
    platform = admin("platform")
    _mgr_role(platform, firm_id)
    spec = {
        "acct1": ("commacct1", "ACCOUNTANT"),
        "acct2": ("commacct2", "ACCOUNTANT"),
        "mgr": ("commmgr", MGR_ROLE),
        "smgr": ("commsmgr", "SALES_MANAGER"),
    }
    out: dict[str, Api] = {"admin": admin()}
    for key, (name, role) in spec.items():
        email = f"{tag}.{name}@fixtures.local"
        ensure_user(platform, email, f"Commission payout check {name}", firm_id, role)
        out[key] = sign_in(email, firm_id=firm_id)
    return out


def earner(api: Api, sc: Scene, rate: str = "10") -> tuple[dict, dict, object]:
    """Make a salesman with one flat rule and one collected sale; return both + day."""
    day = today() - timedelta(days=2)
    sm = sc.salesman(f"Pay {sc.tag}{suffix(3)}")
    r = rule(api, sm["id"], day - timedelta(days=5), percentage=rate)
    sell(sc, sm["id"], "10", "100", day, collect=True)
    return sm, r, day


def accrue(api: Api, sm: dict, start: object, end: object | None = None) -> tuple[int, object]:
    """Accrue one salesman's payout for a period."""
    return api.post(
        f"{PAYOUTS}/accrue",
        {
            "period_start": start.isoformat(),
            "period_end": (end or start).isoformat(),
            "salesman_id": sm["id"],
        },
    )


def draft(api: Api, sc: Scene, rate: str = "10") -> tuple[dict, dict, dict, object]:
    """Return (salesman, rule, DRAFT payout, day) for a fresh earner."""
    sm, r, day = earner(api, sc, rate)
    rows = must(accrue(api, sm, day), "accrue")
    if not rows:
        raise SystemExit("PRECONDITION accrue made no payout")
    return sm, r, rows[0], day


def payout(api: Api, payout_id: str) -> dict:
    """Read one payout."""
    return must(api.get(f"{PAYOUTS}/{payout_id}"), "payout read")


def journal(api: Api, entry_id: str) -> dict:
    """Read one journal entry."""
    return must(api.get(f"{JE}/{entry_id}"), "journal read")
