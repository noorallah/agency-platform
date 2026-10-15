"""Probe: an unknown section is a 404, a missing token a 401, a missing/garbled firm a 4xx -- never a 500."""

import uuid

from _settings import Api, Check, ORDER, message, who

c = Check("p_set_unknown_and_unauthenticated")
ready = who("ready_admin", "ready")
plat = who("platform")
S = "/api/v1/settings-sections"

for api, label in ((ready, "firm admin"), (plat.inside(ready.firm_id), "platform admin in a firm")):
    c.refused(api.get(f"{S}/nope/state"), 404, "not found", f"{label}: unknown section")
    c.refused(api.get(f"{S}/platform/nope/state"), 404, "not found", f"{label}: unknown platform section")
    c.refused(api.get(f"{S}/Tax/state"), 404, "not found", f"{label}: section names are case-exact")
c.refused(plat.get(f"{S}/platform/nope/state"), 404, "not found", "platform admin, no firm: unknown platform section")
c.refused(ready.get(f"{S}/platform/tax/state"), 404, "not found", "a firm section under /platform/ is unknown")
c.refused(ready.get(f"{S}/people/state"), 404, "not found", "a platform section without /platform/ is unknown")

anon = Api()
got = anon.get(f"{S}/tax/state")
c.eq(got[0], 401, "no token: firm section answers 401")
got = anon.get(f"{S}/platform/people/state")
c.eq(got[0], 401, "no token: platform section answers 401")

# A firm section needs a firm: none, a stranger's id, and a garbled one.
nofirm = ready.inside(None)
for name in ORDER:
    if name.startswith("platform/"):
        continue
    got = nofirm.get(f"{S}/{name}/state")
    c.ok(got[0] in (400, 403, 422), f"{name} without X-Firm-ID is refused, not {got[0]}", message(got[1]))
c.ok(ready.inside(str(uuid.uuid4())).get(f"{S}/tax/state")[0] in (400, 403, 404),
     "an unknown firm id is refused")
got = ready.inside("not-a-uuid").get(f"{S}/tax/state")
c.ok(got[0] in (400, 403, 404, 422), f"a garbled X-Firm-ID is refused, not {got[0]}", message(got[1]))
# People without a firm: a firm admin must name one; a platform admin need not.
got = nofirm.get(f"{S}/platform/people/state")
c.ok(got[0] in (400, 403), f"platform/people for a firm admin without X-Firm-ID is refused, not {got[0]}", message(got[1]))
c.eq(plat.get(f"{S}/platform/people/state")[0], 200, "platform admin without a firm reads people")
c.done()
