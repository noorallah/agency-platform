"""Probe: a note and a bill raised from an order keep the order's salesman."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("p_sm_order_keeps")
a = admin()
sc = Scene(a, stock="100")
manager = sc.salesman(f"Manager {sc.tag}")
taker = sc.salesman(f"Taker {sc.tag}")
customer = sc.new_customer(salesman_id=manager["id"])
inv = sell(sc, taker["id"], "3", "100", today(), customer=customer)
order = must(a.get(f"{SO}/{inv['order_id']}"), "order")
note = must(a.get(f"{DN}/{inv['note_id']}"), "note")
c.eq(order.get("salesman_id"), taker["id"], "the order names who took it, not the account manager")
c.eq(note.get("salesman_id"), taker["id"], "the note keeps the order's salesman")
c.eq(inv.get("salesman_id"), taker["id"], "the bill keeps the order's salesman")
back = must(a.get(f"{SI}/{inv['id']}"), "bill read")
c.eq(back.get("salesman_id"), taker["id"], "and reads it back")
c.done()
