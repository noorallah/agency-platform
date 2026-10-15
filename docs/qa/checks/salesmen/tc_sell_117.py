"""TC-SELL-117: Order By on the printed bill, Standard and Trade layouts."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_sell_117")
a = admin()
sc = Scene(a, stock="50")
asha = sc.salesman(f"Asha {sc.tag}")
with counter(a):
    named = must(a.post(SI, sc.bill_body("1", salesman_id=asha["id"])), "bill with Asha")
    bare = must(a.post(SI, sc.bill_body("1")), "bill with none")

for layout in ("STANDARD", "TRADE"):
    with template(a, bill_layout=layout, page_size="A4"):
        text = printed(a, named["id"])
        c.ok("Order By" in text, f"{layout}: the named bill prints an Order By row")
        c.ok(asha["name"] in text, f"{layout}: the row reads {asha['name']}", text[:80])
        c.ok("Order By" not in printed(a, bare["id"]), f"{layout}: the bill with none prints no Order By")

# Delete the entry; the bill keeps the name it was saved with.
status, body = a.delete(f"{SM}/{asha['id']}")
c.ok(status in (200, 204, 409, 422), f"delete of an entry a bill names answers ({status} {message(body)[:100]})")
with template(a, bill_layout="STANDARD", page_size="A4"):
    c.ok(asha["name"] in printed(a, named["id"]), "after the entry is deleted the bill still prints Asha")
with template(a, bill_layout="TRADE", page_size="A4"):
    c.ok(asha["name"] in printed(a, named["id"]), "trade layout after the entry is deleted still prints Asha")

# The half page and the roll have no Order By row.
for size in ("HALF", "THERMAL80"):
    with template(a, page_size=size):
        c.ok("Order By" not in printed(a, named["id"]), f"{size}: no Order By row")
c.done()
