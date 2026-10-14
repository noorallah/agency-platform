"""TC-LOT-014: a lot's Trace page (the trail the screen reads)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_014")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
g = c.receive([{"product": p, "qty": 10, "rate": 40, "batch": "LOTA", "expiry": today() + timedelta(days=200), "mrp": 150}])
a = batch_of(c, p, "LOTA")
made = c.sell([{"product": p, "qty": 3, "picks": [(a["id"], 3)]}])
draft = c.bill(made["note"], approve=False)
t0 = data(trail(api, a["id"])[1])
c0.ok(not [e for e in t0["events"] if e["document_type"] == "SALES_INVOICE"], "a draft bill is not on the trail",
      [e["document_type"] for e in t0["events"]])
inv = must(api.post(f"/api/v1/sales-invoices/{draft['id']}/approve", {}), "approve")
inv = must(api.get(f"/api/v1/sales-invoices/{draft['id']}"), "read")
s, rb = sales_return(c, inv, "1"); ret = data(rb); complete_return(c, ret)
s, wb = c.write_off(p, "1", batch_id=a["id"]); wo = data(wb)
sb_status, sb = supplier_bill(c, g, "10", "41")
s, tb = trail(api, a["id"])
c0.eq(s, 200, "the trail answers")
t = data(tb)
ev = t["events"]
kinds = [e["document_type"] for e in ev]
c0.eq(kinds[0], "GOODS_RECEIPT", "the arrival comes first")
c0.eq((ev[0]["document_number"], D(ev[0]["quantity"]), ev[0]["party_name"]), (g["grn_number"], D(10), c.vendor["name"]),
      "arrival: the receipt, +10, from the supplier")
def one(kind):
    """Return the events of one kind."""
    return [e for e in ev if e["document_type"] == kind]
c0.eq([D(e["quantity"]) for e in one("DELIVERY_NOTE")], [D(-3)], "the dispatch is -3")
c0.eq([(e["document_number"], D(e["quantity"])) for e in one("SALES_INVOICE")], [(inv["invoice_number"], D(0))],
      "the approved sales bill appears once, found by its number, at quantity 0")
c0.eq([D(e["quantity"]) for e in one("SALES_RETURN")], [D(1)], "the sales return is +1")
c0.eq([D(e["quantity"]) for e in one("PURCHASE_INVOICE")], [D(0)], "the supplier's bill appears at quantity 0")
c0.eq(len(one("COST_CORRECTION")), 1, "and its cost correction")
others = [e for e in ev if e["document_type"] not in ("GOODS_RECEIPT", "DELIVERY_NOTE", "SALES_INVOICE", "SALES_RETURN", "PURCHASE_INVOICE", "COST_CORRECTION")]
c0.eq([D(e["quantity"]) for e in others], [D(-1)], "the write-off is -1 and is the only other event (no reservation or release listed)")
if others:
    c0.eq(others[0]["document_number"], wo.get("reference_number"), "the write-off shows with its own number")
    c0.eq(others[0]["document_date"], today().isoformat(), "and its date")
c0.eq(sum(D(e["quantity"]) for e in ev), D(7), "events add up to the 7 units the lot holds")
c0.eq((t["lot_reference"] or "")[:4], "LOT-", "the lot reference")
c0.eq(t["has_printed_batch"], True, "carries a printed batch")
c0.eq(D(t["unit_cost"]), D(41), "unit cost now (bill at 41 corrects the lot to 41)")
c0.eq(t["batch"]["id"], a["id"], "the batch")
# (3) a made-up id.
fake = api.get("/api/v1/batch-serial/batches/00000000-0000-4000-8000-000000000000/trail")
c0.eq(fake[0], 404, "an unknown id answers 404")
c0.done()
