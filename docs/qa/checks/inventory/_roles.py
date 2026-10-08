"""Role -> permission codes from the live platform (not a check)."""
from _inv import *


def role_codes(platform: Api) -> dict[str, set[str]]:
    """Return the permission codes each seeded role holds, read from the API."""
    perms = {p["id"]: p["code"] for p in all_rows(platform, "/api/v1/permissions", size=100)}
    out: dict[str, set[str]] = {}
    for role in ("FIRM_ADMIN", "FIRM_MANAGER", "INVENTORY_MANAGER", "SALES_MANAGER", "VIEWER"):
        st, b = platform.get(f"/api/v1/roles?search={role}&page_size=50")
        row = next(x for x in data(b) if x["code"] == role)
        st, b = platform.get(f"/api/v1/roles/{row['id']}/permissions")
        out[role] = {perms[i] for i in data(b)["ids"] if i in perms}
    return out
