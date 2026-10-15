"""TC-BUY-004: cancelling a completed receipt undoes its stock and its journal."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_004")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order()
r4 = sc.receive(order, "4")
r6 = sc.receive(order, "6")
c.eq(stock(a, pid), D(10), "10 on hand")
before = journal(a, r4["grn_number"])
c.ok(len(before) >= 1, "the receipt posted a journal", len(before))
done = must(a.post(f"{GR}/{r4['id']}/cancel", {"reason": "check"}), "cancel")
c.eq(done["status"], "CANCELLED", "the receipt is CANCELLED")
rows = [r for r in ledger(a, pid) if r["transaction_type"] == "GOODS_RECEIPT_REVERSAL"]
c.eq([D(r["quantity"]) for r in rows], [D(-4)], "one GOODS_RECEIPT_REVERSAL of -4")
c.eq(stock(a, pid), D(6), "MAIN holds 6")
c.eq(sc.reload(order)["status"], "PARTIALLY_RECEIVED", "the order drops back to PARTIALLY_RECEIVED")
after = journal(a, r4["grn_number"])
c.ok(len(after) >= 2, "the journal shows a reversal beside the original", len(after))
nets = [entry_net(a, e) for e in after]
c.ok(any(n.get("INVENTORY") == D(-400) for n in nets), "the reversal credits inventory 400.00", nets)
c.ok(any(n.get("INVENTORY") == D(400) for n in nets), "the original debited inventory 400.00", nets)
c.done()
