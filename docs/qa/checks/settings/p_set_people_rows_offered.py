"""Probe: a role that is not offered a step gets no row for it (People: user-firm assignments)."""

from _settings import Check, who

c = Check("p_set_people_rows_offered")
ready = who("ready_admin", "ready")
plat = who("platform")
S = "/api/v1/settings-sections/platform/people/state"

status, body = ready.get(S)
codes = [s["code"] for s in body["data"]["steps"]] if status == 200 else []
c.ok("user-firms" not in codes, "a firm admin is offered no user-firm assignments row", codes)
c.ok("roles" in codes and "users" in codes, "a firm admin does see roles and users", codes)
status, body = plat.get(S)
c.ok("user-firms" in [s["code"] for s in body["data"]["steps"]], "the platform admin does see it")
c.done()
