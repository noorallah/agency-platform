"""TC-SELL-114: a salesman with no sign-in is saved, listed, offered and picked on a bill."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_sell_114")
a = admin()
sc = Scene(a, stock="50")
name = f"Phone order {sc.tag}"

status, body = a.post(SM, {"name": name, "earns_commission": False})
c.eq(status, 201, f"the salesman is saved ({message(body)[:120]})")
made = data(body)
c.eq(made.get("user_id"), None, "saved with no user")
c.eq(made.get("earns_commission"), False, "earns commission off is kept")
status, body = a.get(f"{SM}?search={sc.tag}&page_size=20")
c.ok(any(r["id"] == made["id"] for r in data(body)), "appears in the list", data(body))
status, body = a.get(f"{SM}?active=true&page_size=100&search={sc.tag}")
c.ok(any(r["id"] == made["id"] for r in data(body)), "offered in the Salesman box (active list)")

with counter(a):
    status, body = a.post(SI, sc.bill_body("1", salesman_id=made["id"]))
    if c.eq(status, 201, f"the counter bill names the salesman ({message(body)[:150]})"):
        bill = data(body)
        status, body = a.get(f"{SI}/{bill['id']}")
        c.eq(data(body).get("salesman_id"), made["id"], "the saved bill shows the salesman")
c.done()
