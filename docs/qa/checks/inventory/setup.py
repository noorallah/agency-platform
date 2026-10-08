"""Set up the accounts the inventory checks sign in as (idempotent).

    python docs/qa/checks/inventory/setup.py

Needs ``.state/goods_types.json`` (the goods-type round made the platform
administrator, the generic firm T1008FTRV-F with its head office, and the
pharmacy firm used here as "the other firm").  On the generic firm it finds or
makes one user per role:

* ``admin``    FIRM_ADMIN (reused from the goods-type state)
* ``manager``  FIRM_MANAGER (reused)
* ``store``    INVENTORY_MANAGER   -- the warehouse role
* ``sales``    SALES_MANAGER
* ``viewer``   VIEWER              -- read only
* ``other_admin`` FIRM_ADMIN of the pharmacy firm (cross-firm probes)

No new firm is made.  Writes ``.state/inventory.json``.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import PASSWORD, data, message, save_state, sign_in, state_path  # noqa: E402

NEW_ROLES = {
    "store": ("INVENTORY_MANAGER", "inv store"),
    "sales": ("SALES_MANAGER", "inv sales"),
    "viewer": ("VIEWER", "inv viewer"),
}


def user(platform, email: str, title: str, firm_id: str, role_code: str) -> None:  # noqa: ANN001
    """Find or make a user in one firm holding one role."""
    status, body = platform.get(f"/api/v1/users?search={email}&page_size=10")
    found = [row for row in data(body) if row.get("email") == email]
    if found:
        user_id = found[0]["id"]
    else:
        status, body = platform.post(
            "/api/v1/users",
            {
                "email": email,
                "full_name": title,
                "password": PASSWORD,
                "is_active": True,
                "force_password_change": False,
            },
        )
        if status not in (200, 201):
            raise SystemExit(f"user {email}: {status} {message(body)}")
        user_id = data(body)["id"]
        status, body = platform.put(
            f"/api/v1/users/{user_id}/firms",
            {"assignments": [{"firm_id": firm_id, "is_primary": True, "is_active": True}]},
        )
        if status != 200:
            raise SystemExit(f"membership {email}: {status} {message(body)}")
    status, body = platform.get(f"/api/v1/roles?search={role_code}&page_size=50")
    role = next(row for row in data(body) if row["code"] == role_code)
    status, body = platform.put(
        f"/api/v1/users/{user_id}/firms/{firm_id}/roles", {"ids": [role["id"]]}
    )
    if status != 200:
        raise SystemExit(f"role {role_code} for {email}: {status} {message(body)}")


def main() -> None:
    """Write the state."""
    src = json.loads((state_path("goods_types")).read_text(encoding="utf-8"))
    acc = src["accounts"]
    platform = sign_in(acc["platform"]["email"])
    generic = src["own_firms"]["generic"]
    pharma = src["own_firms"]["pharma"]
    suffix = generic["suffix"]
    accounts = {
        "platform": acc["platform"],
        "platform_in_firm": {**acc["platform"], "firm_id": generic["id"]},
        "admin": acc["generic_admin"],
        "manager": acc["generic_manager"],
        "other_admin": acc["test02_admin"],
    }
    for handle, (role_code, title) in NEW_ROLES.items():
        email = f"{suffix}.inv{handle}@fixtures.local"
        user(platform, email, title, generic["id"], role_code)
        accounts[handle] = {"email": email, "firm_id": generic["id"], "role": role_code}
    save_state(
        {
            "accounts": accounts,
            "firm": generic,
            "other_firm": {"code": "TEST02", "id": src["firms"]["TEST02"]},
            "firm_id": generic["id"],
            "other_firm_id": src["firms"]["TEST02"],
        }
    )
    print("state written:", ", ".join(accounts))


if __name__ == "__main__":
    main()
