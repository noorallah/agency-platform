"""Every catalogue report reads once as admin: 200, success, under 3 s."""

from _rep import SLOW_MS, Check, admin, catalogue, first_id, message, read

c = Check("tc_rep_001")
api = admin()
vendor = first_id(api, "/api/v1/vendors")
entries = catalogue()
c.ok(len(entries) > 90, "the catalogue was read", len(entries))
bad = 0
for e in entries:
    status, body, ms = read(api, e, vendor)
    ok = status == 200 and isinstance(body, dict) and body.get("success") is True
    if not ok:
        print(f"FAIL {e['path']} {status} {message(body)[:200]}")
        bad += 1
    elif ms > SLOW_MS:
        print(f"FAIL {e['path']} SLOW {ms} ms")
        bad += 1
    c.passed += ok
print(f"tally: {len(entries)} reports, {bad} not clean")
c.done()
