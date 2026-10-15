"""Probe: a user of another firm is refused every section; a Viewer and a firm admin are refused Firms."""

from _settings import Check, ORDER, message, who

c = Check("p_set_other_firm_and_roles")
held = __import__("common").state()
ready = who("ready_admin", "ready")
bare = who("bare_admin", "bare")
viewer = who("viewer", "ready")
S = "/api/v1/settings-sections"

# Membership is the gate: the ready firm's admin naming the bare firm (and back) is a 403.
for name in ORDER:
    path = f"{S}/{name}/state" if not name.startswith("platform/") else f"{S}/{name}/state"
    if name == "platform/firms":
        continue
    c.refused(ready.inside(held["bare_id"]).get(path), 403, "", f"ready admin in the bare firm: {name}")
    c.refused(bare.inside(held["ready_id"]).get(path), 403, "", f"bare admin in the ready firm: {name}")

# The Firms section is the platform administrator's alone.
c.refused(ready.get(f"{S}/platform/firms/state"), 403, "not offered", "firm admin: platform/firms")
c.refused(viewer.get(f"{S}/platform/firms/state"), 403, "not offered", "viewer: platform/firms")
c.refused(viewer.get(f"{S}/platform/people/state"), 403, "not offered", "viewer: platform/people")
# A viewer is a member: the firm sections (counts and words only) are answered.
c.eq(viewer.get(f"{S}/tax/state")[0], 200, "viewer: a member reads the Tax state")
c.done()
