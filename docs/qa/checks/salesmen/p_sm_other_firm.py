"""Probe: another firm's salesman id is refused on a bill, an order and a quotation."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("p_sm_other_firm")
a = admin()
b = admin("admin2")
sc = Scene(a, stock="50")
theirs = must(b.post(SM, {"name": f"Other firm {sc.tag}"}), "firm two salesman")
c.eq(a.get(f"{SM}/{theirs['id']}")[0], 404, "firm one cannot read firm two's salesman")
c.eq(a.put(f"{SM}/{theirs['id']}", {"phone": "1"})[0], 404, "firm one cannot edit it")
c.eq(a.delete(f"{SM}/{theirs['id']}")[0], 404, "firm one cannot delete it")
c.ok(all(r["id"] != theirs["id"] for r in all_rows(a, f"{SM}?search={sc.tag}")),
     "it is not in firm one's list")
with counter(a):
    status, body = a.post(SI, sc.bill_body("1", salesman_id=theirs["id"]))
    c.ok(status in (404, 422), "a bill naming it is refused", f"{status} {message(body)[:150]}")
status, body = a.post(SO, sc.order_body("1", salesman_id=theirs["id"]))
c.ok(status in (404, 422), "an order naming it is refused", f"{status} {message(body)[:150]}")
status, body = a.post(QT, sc.quote_body("1", salesman_id=theirs["id"]))
c.ok(status in (404, 422), "a quotation naming it is refused", f"{status} {message(body)[:150]}")
c.done()
