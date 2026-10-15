"""TC-CONF-015: Settings > People and Firms state, as a Firm admin and as the platform admin."""

from _settings import (
    PASSWORD, Check, count_of, data, lead, message, must, ORDER, rows_of, suffix, total, who,
)

c = Check("tc_conf_015")
ready = who("ready_admin", "ready")
plat = who("platform")
held = __import__("common").state()
PEOPLE = "/api/v1/settings-sections/platform/people/state"
FIRMS = "/api/v1/settings-sections/platform/firms/state"


def read(api, path):  # noqa: ANN001, ANN201
    """Return {code: (state, detail)} of a platform section, or None after a failed check."""
    status, body = api.get(path)
    if not c.eq(status, 200, f"GET {path} {message(body)[:100] if status != 200 else ''}"):
        return None
    doc = data(body)
    c.eq(doc["todo_count"], sum(1 for s in doc["steps"] if s["state"] == "TODO"), f"{path} todo_count")
    return {s["code"]: (s["state"], s["detail"]) for s in doc["steps"]}


# Step 1: as a Firm admin, Roles / User templates / Users, and no user-firms row.
got = read(ready, PEOPLE)
if got:
    c.eq([k for k in got if k != "user-firms"], ORDER["platform/people"][:3], "firm admin: people steps in order")
    c.ok("user-firms" not in got, "firm admin: no user-firm assignments row (platform admin's alone)", got.get("user-firms"))
    c.eq(got["roles"][0], "DONE", "firm admin: roles done")
    c.ok(got["roles"][1].startswith("13 ready-made"), "firm admin: ready-made roles a firm is offered", got["roles"])
    c.eq(got["user-templates"][0], "OPTIONAL", "firm admin: templates optional")
    c.eq(lead(got["user-templates"][1]), total(ready, "/api/v1/user-templates"), "firm admin: templates counted as its list holds them")
    c.eq(got["users"][0], "DONE", "firm admin: users done")
    c.eq(lead(got["users"][1]), total(ready, "/api/v1/users"), "firm admin: users counted as its list holds them")

# Step 2: the platform administrator, the whole installation.
pgot = read(plat, PEOPLE)
if pgot:
    c.eq(list(pgot), ORDER["platform/people"], "platform: people steps in order")
    c.eq(pgot["user-firms"][0], "OPTIONAL", "platform: memberships optional")
    c.ok("memberships in" in pgot["user-firms"][1], "platform: memberships say how many firms they span", pgot["user-firms"])
    c.eq(lead(pgot["users"][1]), total(plat, "/api/v1/users"), "platform: users counted as its list holds them")
    c.eq(count_of(pgot["roles"][1], "ready-made"), 16, "platform: sixteen ready-made roles")
fgot = read(plat, FIRMS)
if fgot:
    c.eq(list(fgot), ORDER["platform/firms"], "platform: firms steps in order")
    c.eq(fgot["business-profiles"][0], "OPTIONAL", "platform: profiles optional")
    c.eq(fgot["firms"][0], "DONE", "platform: firms done")
    c.eq(lead(fgot["firms"][1]), total(plat, "/api/v1/firms"), "platform: firms counted as its list holds them")

# Saved: a role of the firm's own, a template on it, a user in the firm.
before = read(ready, PEOPLE)
role = ready.post("/api/v1/roles", {"code": f"s{suffix(5).lower()}", "name": f"Settings check role {suffix(4)}"})
if c.ok(role[0] in (200, 201), "role saves", f"{role[0]} {message(role[1])[:160]}") and before:
    after = read(ready, PEOPLE)
    if after:
        c.eq(count_of(after["roles"][1], "your own"), count_of(before["roles"][1], "your own") + 1,
             f"roles {before['roles'][1]!r} -> {after['roles'][1]!r}")
    template = ready.post("/api/v1/user-templates", {"code": f"s{suffix(5).lower()}", "name": f"Settings check template {suffix(4)}",
                                                     "role_ids": [data(role[1])["id"]]})
    if c.ok(template[0] in (200, 201), "template saves", f"{template[0]} {message(template[1])[:160]}") and after:
        again = read(ready, PEOPLE)
        if again:
            c.eq(lead(again["user-templates"][1]), lead(after["user-templates"][1]) + 1, "templates count one more")
email = f"{suffix(6).lower()}.setcheck@fixtures.local"
pbefore = read(plat, PEOPLE)
made = plat.post("/api/v1/users", {"email": email, "full_name": "Settings Check", "password": PASSWORD,
                                   "is_active": True, "force_password_change": False})
if c.ok(made[0] in (200, 201), "user saves", f"{made[0]} {message(made[1])[:160]}"):
    uid = data(made[1])["id"]
    member = plat.put(f"/api/v1/users/{uid}/firms", {"assignments": [
        {"firm_id": held["ready_id"], "is_primary": True, "is_active": True}]})
    c.ok(member[0] in (200, 201), "membership saves", f"{member[0]} {message(member[1])[:160]}")
    cur = read(ready, PEOPLE)
    if cur and before:
        c.eq(lead(cur["users"][1]), lead(before["users"][1]) + 1, f"firm users {before['users'][1]!r} -> {cur['users'][1]!r}")
    pnow = read(plat, PEOPLE)
    if pnow and pbefore:
        c.eq(lead(pnow["users"][1]), lead(pbefore["users"][1]) + 1, "platform users count one more")
        c.eq(lead(pnow["user-firms"][1]), lead(pbefore["user-firms"][1]) + 1, "platform memberships count one more")
c.done()
