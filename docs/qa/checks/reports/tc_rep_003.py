"""Seller refused 403 on finance reports; inverted range is 4xx, not 500."""

from _rep import FROM, TO, Check, admin, catalogue, client, first_id, message, read

c = Check("tc_rep_003")
adm = admin()
seller = client("seller", "reports")
vendor = first_id(adm, "/api/v1/vendors")
entries = catalogue()
for e in entries:
    if "/finance/reports/" in e["path"]:
        status, body, _ = read(seller, e, vendor)
        c.ok(status == 403, f"seller on {e['path']} must be 403", f"{status} {message(body)[:120]}")
n = 0
for e in entries:
    if e["period"] and not e["quarterly"] and not e["supplier"] and not e["on_param"]:
        n += 1
        status, body = adm.get(
            f"{e['path']}?from_date={TO}&to_date={FROM}&page=1&page_size=10"
        )
        c.ok(status in (400, 422), f"inverted range on {e['path']}", f"{status} {message(body)[:120]}")
print(f"tally: inverted range tried on {n} reports")
c.done()
