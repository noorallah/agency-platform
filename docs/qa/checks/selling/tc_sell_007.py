"""TC-SELL-007: approving reserves the stock (the promotion-claims report is not driven)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_007")
a = admin()
sc = Scene(a, stock="100")
pid = sc.product["id"]
order = new_order(sc, "12")
c.eq(stock(a, pid), (D(100), D(0)), "a draft reserves nothing")
must(a.post(f"{SO}/{order['id']}/approve", {}), "approve")
c.eq(stock(a, pid), (D(100), D(12)), "on hand 100, reserved 12")
rows = [r for r in ledger(a, pid) if r["transaction_type"] == "RESERVE"]
c.eq(sum(D(r["reserved_quantity_delta"]) for r in rows), D(12), "the ledger shows RESERVE 12")
c.done()
