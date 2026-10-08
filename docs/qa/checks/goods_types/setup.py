"""Set up the accounts the goods-type checks (backlog 89) sign in as.

Run once, from anywhere, after these two fixtures (``backend`` folder)::

    .venv\\Scripts\\python.exe scripts\\test_fixture.py product-master
    .venv\\Scripts\\python.exe scripts\\test_fixture.py platform-admin
    .venv\\Scripts\\python.exe ..\\docs\\qa\\checks\\goods_types\\setup.py <admin suffix> <platform suffix>

It makes three more TEST01 users under the admin's suffix -- a Firm manager, a
Sales manager and an Inventory manager -- and writes the state file the checks
read. Running it again with the same suffixes finds the users and rewrites the
file.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import PASSWORD, data, message, save_state, sign_in  # noqa: E402

ROLES = {
    "manager": ("FIRM_MANAGER", "Firm Manager"),
    "sales": ("SALES_MANAGER", "Sales Manager"),
    "store": ("INVENTORY_MANAGER", "Inventory Manager"),
}


def main() -> None:
    """Create the role holders and write the state."""
    admin_suffix, platform_suffix = sys.argv[1], sys.argv[2]
    platform_email = f"{platform_suffix}.platform@fixtures.local"
    platform = sign_in(platform_email)
    status, body = platform.get("/api/v1/firms?search=TEST0&page_size=50")
    firms = {row["code"]: row["id"] for row in data(body)}
    test01, test02 = firms["TEST01"], firms["TEST02"]
    accounts = {
        "platform": {"email": platform_email},
        "platform_in_test01": {"email": platform_email, "firm_id": test01},
        "admin": {
            "email": f"{admin_suffix}.admin@fixtures.local",
            "firm_id": test01,
        },
    }
    for handle, (role_code, title) in ROLES.items():
        email = f"{admin_suffix}.gt{handle}@fixtures.local"
        status, body = platform.get(f"/api/v1/users?search={email}&page_size=10")
        found = [row for row in data(body) if row.get("email") == email]
        if found:
            user_id = found[0]["id"]
        else:
            status, body = platform.post(
                "/api/v1/users",
                {
                    "email": email,
                    "full_name": f"{title} ({admin_suffix})",
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
                {
                    "assignments": [
                        {"firm_id": test01, "is_primary": True, "is_active": True}
                    ]
                },
            )
            if status != 200:
                raise SystemExit(f"membership {email}: {status} {message(body)}")
        status, body = platform.get(f"/api/v1/roles?search={role_code}&page_size=50")
        role = next(row for row in data(body) if row["code"] == role_code)
        status, body = platform.put(
            f"/api/v1/users/{user_id}/firms/{test01}/roles", {"ids": [role["id"]]}
        )
        if status != 200:
            raise SystemExit(f"role {role_code} for {email}: {status} {message(body)}")
        accounts[handle] = {"email": email, "firm_id": test01, "role": role_code}
        print(f"  {handle:8} {email}  {role_code}")
    save_state(
        {
            "accounts": accounts,
            "firms": {"TEST01": test01, "TEST02": test02},
            "admin_suffix": admin_suffix,
        },
        "goods_types",
    )
    print("state written")


if __name__ == "__main__":
    main()
