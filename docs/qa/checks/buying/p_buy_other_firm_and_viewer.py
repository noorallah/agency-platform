"""Probe: another firm's administrator, a Viewer and an outsider are refused on the buying documents."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("p_buy_other_firm_and_viewer")
a = admin()
viewer = admin("viewer")
other = admin("admin2")
sc = Scene(a)
order = sc.order()
rc = sc.receive(order, "6")
bill = sc.bill(rc)
firm1 = state("buying")["firm_id"]
# a Viewer reads but cannot write or act
c.eq(viewer.get(f"{PO}/{order['id']}")[0], 200, "a Viewer can read the order")
c.eq(viewer.post(PO, sc.order_body())[0], 403, "a Viewer cannot raise an order")
c.eq(viewer.post(f"{PO}/{order['id']}/cancel", {"reason": "x"})[0], 403, "a Viewer cannot cancel it")
c.eq(viewer.post(GR, sc.receipt_body(order, "1"))[0], 403, "a Viewer cannot receive")
c.eq(viewer.post(f"{PI}/{bill['id']}/cancel", {"reason": "x"})[0], 403, "a Viewer cannot cancel a bill")
c.eq(viewer.post(PAY, {"party_id": sc.vendor["id"], "settlement_date": today().isoformat(), "amount": "10", "method": "CASH"})[0], 403, "a Viewer cannot pay")
c.eq(viewer.post(PR, sc.return_body(rc, "1"))[0], 403, "a Viewer cannot return")
# the other firm's administrator, inside his own firm, does not see this firm's documents
for path in (f"{PO}/{order['id']}", f"{GR}/{rc['id']}", f"{PI}/{bill['id']}"):
    st, _ = other.get(path)
    c.ok(st in (403, 404), f"another firm's administrator is refused {path.split('/')[3]}", st)
# ...nor by naming this firm
named = other.inside(firm1)
for path in (f"{PO}/{order['id']}", f"{PI}/{bill['id']}"):
    st, _ = named.get(path)
    c.eq(st, 403, f"naming this firm in X-Firm-ID is refused: {path.split('/')[3]}")
c.eq(named.post(PO, sc.order_body())[0], 403, "...and so is raising an order there")
anon = Api(None, firm1)
c.eq(anon.get(f"{PO}/{order['id']}")[0], 401, "no sign-in is 401")
ids = [r["id"] for r in rows_of(other.get(f"{PO}?page_size=100"))]
c.ok(order["id"] not in ids, "his own list does not hold this firm's order")
c.done()
