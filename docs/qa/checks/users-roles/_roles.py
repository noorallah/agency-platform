"""The Night Desk custom role the role checks share (not a check; run.py skips it)."""

from __future__ import annotations

from _ur import R, Scene, all_rows, must

NIGHT_DESK = ("SALES_VIEW", "CUSTOMER_VIEW", "RECEIPT_VIEW", "RECEIPT_CREATE")


def night_desk(sc: Scene, codes: tuple[str, ...] = NIGHT_DESK) -> dict:
    """Make a TEST01 custom role holding exactly these codes (as the firm admin)."""
    role = sc.role(sc.admin)
    ids = []
    for want in codes:
        match = next(r for r in all_rows(sc.admin, f"/api/v1/permissions?search={want}") if r["code"] == want)
        ids.append(match["id"])
    must(sc.admin.put(f"{R}/{role['id']}/permissions", {"ids": ids}), "night desk codes")
    return role
