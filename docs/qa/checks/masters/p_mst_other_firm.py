"""Probe: another firm's customer, vendor, product and branch are not readable or writable with this firm's header (TEST01 admin against TEST02)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt

c = Check("p_mst_other_firm")
a1, a2 = api("admin"), api("admin2")
t = tag()
cu2 = customer(a2)
ve2 = vendor(a2)
pr2 = product(a2)
br2 = by_code(a2, BR, two()["branch_code"])
c.eq(Api().get(CU)[0], 401, "no token: 401")
b = a1.inside(two()["firm_id"])
for path in (CU, VE, PR, BR, WH):
    c.eq(b.get(path)[0], 403, f"{path} under another firm's header: 403")
for path, row in ((CU, cu2), (VE, ve2), (PR, pr2), (BR, br2)):
    st = a1.get(f"{path}/{row['id']}")[0]
    c.eq(st, 404, f"{path}/<other firm's id> from this firm: 404")
c.eq(a1.put(f"{CU}/{cu2['id']}", {"code": cu2["code"], "customer_type": "BUSINESS", "name": "hijack", "currency_code": "INR"})[0], 404, "cannot edit the other firm's customer")
c.eq(a1.delete(f"{VE}/{ve2['id']}")[0], 404, "cannot delete the other firm's vendor")
c.eq(a1.put(f"{PR}/{pr2['id']}", {"name": "hijack"})[0] in (404, 422), True, "cannot edit the other firm's product")
c.eq(a1.post(f"{CU}/{cu2['id']}/merge", {"duplicate_id": cu2["id"], "reason": "x"})[0] in (404, 422), True, "cannot merge the other firm's customer")
c.eq(must(a2.get(f"{CU}/{cu2['id']}"), "still there")["name"], cu2["name"], "the other firm's customer is untouched")
c.eq([r for r in rows_of(a1.get(f"{CU}?search={cu2['code']}"))], [], "and is absent from this firm's list")
c.done()
