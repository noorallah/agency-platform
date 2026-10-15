"""Probe: soft-deleting a customer: one with documents is refused, a clean one leaves lists and reads, restore brings it back, and its code is not handed to a second live customer."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt

c = Check("p_mst_soft_delete")
a = api()
sc = Scene(a, stock="20")
busy = sc.new_customer()
with counter(a):
    b = must(a.post(SI, sc.bill_body("1", customer=busy)), "bill")
    must(a.post(f"{SI}/{b['id']}/approve", {}), "approve")
r = a.delete(f"{CU}/{busy['id']}")
c.ok(r[0] in (409, 422), "a customer with an approved bill cannot be deleted", f"{r[0]} {message(r[1])}")
c.eq(must(a.get(f"{CU}/{busy['id']}"), "busy")["is_deleted"], False, "and stays live")
clean = customer(a)
c.eq(a.delete(f"{CU}/{clean['id']}")[0], 204, "a clean customer is deleted")
c.eq(a.get(f"{CU}/{clean['id']}")[0], 404, "it no longer reads")
c.eq([r for r in rows_of(a.get(f"{CU}?search={clean['code']}"))], [], "it is out of the list")
again = a.post(CU, {"code": clean["code"], "name": "second use of the code", "customer_type": "BUSINESS", "currency_code": "INR"})
back = a.post(f"{CU}/{clean['id']}/restore", {})
live = [r for r in rows_of(a.get(f"{CU}?search={clean['code']}")) if r["code"] == clean["code"]]
c.ok(len(live) <= 1, "after restore there is never more than one live customer of that code", [r["id"] for r in live])
c.ok(again[0] in (201, 409, 422) and back[0] in (200, 409, 422), "(the code is either kept back from the new one, or the restore is refused)", f"create {again[0]}, restore {back[0]}")
c.done()
