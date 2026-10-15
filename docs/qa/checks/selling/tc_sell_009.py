"""TC-SELL-009: part deliveries move the order's status."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_009")
a = admin()
sc = Scene(a, stock="100")
pid = sc.product["id"]
order = new_order(sc, "12", approve=True)
n1 = new_note(sc, order, "5")
c.eq(n1["status"], "DRAFT", "a note is a draft first")
c.eq(stock(a, pid), (D(100), D(12)), "a draft note moves nothing")
must(a.post(f"{DN}/{n1['id']}/approve", {}), "approve")
c.eq(stock(a, pid), (D(100), D(12)), "an approved note moves nothing")
n1 = must(a.post(f"{DN}/{n1['id']}/dispatch", {}), "dispatch")
c.eq(n1["status"], "DISPATCHED", "dispatched")
c.eq(must(a.get(f"{SO}/{order['id']}"), "o")["status"], "PARTIALLY_DELIVERED", "order partially delivered")
c.eq(stock(a, pid), (D(95), D(7)), "on hand 95, reserved 7")
d = [r for r in ledger(a, pid) if r["transaction_type"] == "DISPATCH"]
c.eq([D(r["current_quantity_delta"]) for r in d], [D(-5)], "ledger DISPATCH -5")
c.ok(len(journal(a, n1["delivery_note_number"])) >= 1, "the note's cost entry is in the journal")
n2 = new_note(sc, order, "7", dispatch=True)
c.eq(must(a.get(f"{SO}/{order['id']}"), "o")["status"], "DELIVERED", "order delivered")
c.eq(stock(a, pid), (D(88), D(0)), "on hand 88, reserved 0")
c.eq(sorted(D(r["current_quantity_delta"]) for r in ledger(a, pid) if r["transaction_type"] == "DISPATCH"), [D(-7), D(-5)], "ledger DISPATCH -5 and -7")
c.done()
