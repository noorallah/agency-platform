"""Probe: an inactive salesman is refused on a new bill and is not the starting choice."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("p_sm_inactive")
a = admin()
sc = Scene(a, stock="50")
person = sc.salesman()
customer = sc.new_customer(salesman_id=person["id"])
c.eq(data(a.get(f"{SM}/starting-choice?customer_id={customer['id']}")[1]).get("salesman_id"),
     person["id"], "while active he is the customer's starting choice")
must(a.put(f"{SM}/{person['id']}", {"is_active": False}), "deactivate")
choice = data(a.get(f"{SM}/starting-choice?customer_id={customer['id']}")[1])
c.ok(choice.get("salesman_id") != person["id"],
     "once inactive he is not offered as the starting choice", choice)
c.ok(all(r["id"] != person["id"] for r in all_rows(a, f"{SM}?active=true&search={sc.tag}")),
     "nor in the active list")
with counter(a):
    status, body = a.post(SI, sc.bill_body("1", salesman_id=person["id"]))
    c.ok(status in (409, 422), "a new bill naming him is refused", f"{status} {message(body)[:150]}")
status, body = a.post(SO, sc.order_body("1", salesman_id=person["id"]))
c.ok(status in (409, 422), "a new order naming him is refused", f"{status} {message(body)[:150]}")
c.done()
