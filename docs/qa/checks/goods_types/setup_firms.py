"""Make the two firms of their own that TC-MAST-019, 026 and 029 need.

    python setup_firms.py                      # build what the state does not name
    python setup_firms.py PHARMA_CODE GEN_CODE  # adopt two firms made by
                                               # ``test_fixture.py unfinished-firm``

Needs ``setup.py`` to have run (the ``platform`` account). Records the firms and
their users under ``own_firms`` / ``accounts`` and can be re-run: anything the
state or the server already holds is found, not made again.

* ``pharma`` -- first profile Pharmacy (hands out Medicine once)
* ``generic`` -- first profile Generic (hands out nothing)
* ``test02``  -- fixture firm TEST02, with an administrator of this run
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import PASSWORD, data, message, save_state, sign_in, state  # noqa: E402

BACKEND = pathlib.Path(__file__).resolve().parents[4] / "backend"
PROFILE = {"pharma": "PHARMACY", "generic": "GENERIC"}
ROLES = {"admin": "FIRM_ADMIN", "manager": "FIRM_MANAGER", "cashier": "CASHIER"}


def make_unfinished() -> str:
    """Run the fixture once and return the code of the firm it made."""
    python = BACKEND / ".venv" / "Scripts" / "python.exe"
    out = subprocess.run(  # noqa: S603
        [str(python), "scripts/test_fixture.py", "unfinished-firm"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    found = re.search(r"New firm\s*:\s*(\S+)", out)
    if not found:
        raise SystemExit("fixture printed no firm code:\n" + out)
    return found.group(1)


def user(platform, email: str, title: str, firm_id: str, role_code: str) -> None:  # noqa: ANN001
    """Find or make a user in one firm with one role."""
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
    """Build or adopt the firms, their profiles and their users."""
    held = state()
    platform = sign_in(held["accounts"]["platform"]["email"])
    own = dict(held.get("own_firms", {}))
    adopt = dict(zip(("pharma", "generic"), sys.argv[1:3], strict=False))
    accounts = dict(held["accounts"])
    for handle, profile_code in PROFILE.items():
        if handle not in own:
            code = adopt.get(handle) or make_unfinished()
            status, body = platform.get(f"/api/v1/firms?search={code}&page_size=10")
            row = next(r for r in data(body) if r["code"] == code)
            own[handle] = {
                "code": code,
                "id": row["id"],
                "schema": row.get("schema_name"),
                "profile": profile_code,
                "suffix": code.split("-")[0].lower(),
            }
        firm_id = own[handle]["id"]
        status, body = platform.get(
            f"/api/v1/business-framework/firms/{firm_id}/profile-assignment"
        )
        if not data(body):
            status, body = platform.get(
                f"/api/v1/business-framework/firms/{firm_id}/profiles"
            )
            wanted = next(p for p in data(body) if p["code"] == profile_code)
            status, body = platform.put(
                f"/api/v1/business-framework/firms/{firm_id}/profile-assignment",
                {"business_profile_id": wanted["id"], "is_active": True},
            )
            print(f"  {own[handle]['code']}: profile {profile_code} -> {status}")
        # Set up only as far as the cases need: a GST template (products need a tax
        # group) and the head office (warehouses and routes need a branch).
        readiness = platform.get(f"/api/v1/firms/{firm_id}/readiness")[1]
        steps = {x["key"]: x["status"] for x in data(readiness)["steps"]}
        if handle == "generic":
            for key, path in (("tax", "apply-tax-template"), ("branches", "create-default-branch")):
                if steps.get(key) != "DONE":
                    status, body = platform.post(f"/api/v1/firms/{firm_id}/{path}", None)
                    print(f"  {own[handle]['code']}: {path} -> {status}")
        for who, role_code in ROLES.items():
            email = f"{own[handle]['suffix']}.{handle}{who}@fixtures.local"
            user(platform, email, f"{handle} {who}", firm_id, role_code)
            accounts[f"{handle}_{who}"] = {
                "email": email,
                "firm_id": firm_id,
                "role": role_code,
            }
        accounts[f"{handle}_platform"] = {
            "email": held["accounts"]["platform"]["email"],
            "firm_id": firm_id,
        }
    test02 = held["firms"]["TEST02"]
    email = f"{held['admin_suffix']}.t2admin@fixtures.local"
    user(platform, email, "TEST02 admin", test02, "FIRM_ADMIN")
    accounts["test02_admin"] = {"email": email, "firm_id": test02, "role": "FIRM_ADMIN"}
    save_state({"own_firms": own, "accounts": accounts})
    for handle, row in own.items():
        print(f"  {handle}: {row['code']} schema {row['schema']} profile {row['profile']}")
    print("state written")


if __name__ == "__main__":
    main()
