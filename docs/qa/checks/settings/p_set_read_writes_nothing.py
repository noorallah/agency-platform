"""Probe: reading every section's state writes nothing -- no audit event, no change in any state."""

from _settings import Check, ORDER, audit_count, who, state_of

c = Check("p_set_read_writes_nothing")
ready = who("ready_admin", "ready")
bare = who("bare_admin", "bare")
plat = who("platform")

for api, label, names in (
    (ready, "ready", [n for n in ORDER if not n.startswith("platform/")]),
    (bare, "bare", [n for n in ORDER if not n.startswith("platform/")]),
):
    before_audit = audit_count(api)
    before = {n: state_of(api, n) for n in names}
    for _ in range(2):
        for n in names:
            state_of(api, n)
    after = {n: state_of(api, n) for n in names}
    c.eq(audit_count(api), before_audit, f"{label}: the firm's audit trail after reading {len(names)} sections 3 times")
    c.eq(after, before, f"{label}: reading changed no section's state")
# The platform sections: the platform trail.
status, body = plat.get("/api/v1/audit-logs?page=1&page_size=1")
c.eq(status, 200, "platform admin reads the platform trail")
p_before = body["pagination"]["total_records"]
for n in ("platform/people",):
    state_of(plat, n)
    state_of(ready, n)
status, body = plat.get("/api/v1/audit-logs?page=1&page_size=1")
c.eq(body["pagination"]["total_records"], p_before, "the platform audit trail after reading people")
c.done()
