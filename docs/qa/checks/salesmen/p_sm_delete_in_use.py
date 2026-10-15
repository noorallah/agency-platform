"""Probe: a salesman a document names is not lost; one nothing names deletes and restores."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("p_sm_delete_in_use")
a = admin()
sc = Scene(a, stock="50")
used = sc.salesman()
free = sc.salesman()
must(a.post(SO, sc.order_body("1", salesman_id=used["id"])), "order naming him")

status, body = a.delete(f"{SM}/{used['id']}")
after = a.get(f"{SM}/{used['id']}")
if status in (409, 422):
    c.ok(after[0] == 200, "refused, and still there", after[0])
else:
    # The router says an entry in use is made inactive instead of lost.
    c.eq(status, 200, f"delete of an entry a document names answers ({message(body)[:100]})")
    c.ok(after[0] == 200 and data(after[1]).get("is_active") is False,
         "if it is not refused it is kept, inactive", f"{after[0]} {str(after[1])[:150]}")

status, body = a.delete(f"{SM}/{free['id']}")
c.eq(status, 200, f"an entry nothing names deletes ({message(body)[:100]})")
c.eq(a.get(f"{SM}/{free['id']}")[0], 404, "and is gone")
status, body = a.post(f"{SM}/{free['id']}/restore", {})
c.eq(status, 200, f"it restores ({message(body)[:100]})")
status, body = a.get(f"{SM}/{free['id']}")
c.eq(status, 200, "and reads again")
c.eq(data(body).get("name"), free["name"], "under its own name")
c.done()
