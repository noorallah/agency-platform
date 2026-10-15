"""TC-BUY-026: landed cost spread over received goods.

The case sells 4 of the 10 so that on hand is below received; this module does not
sell, so 4 are sent back to the supplier instead (the same on-hand gap: 6 of 10).
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

LC = "/api/v1/landed-costs"
c = Check("tc_buy_026")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
transporter = sc.new_vendor()
order = sc.order()
r4 = sc.receive(order, "4")
r6 = sc.receive(order, "6")
sc.ret(r4, "4")
c.eq(stock(a, pid), D(6), "6 on hand of 10 received")
body = {
    "voucher_date": today().isoformat(), "basis": "VALUE", "goods_receipt_ids": [r4["id"], r6["id"]],
    "charges": [{"description": "Freight", "amount": "1000", "vendor_id": transporter["id"], "bill_reference": f"FRT-{sc.tag}"}],
}
made = a.post(LC, body)
c.ok(made[0] in (200, 201), "the voucher is posted", (made[0], message(made[1])))
if made[0] in (200, 201):
    v = data(made[1])
    c.eq(D(v["total_amount"]), D(1000), "total 1,000.00")
    allocs = {x["grn_number"]: x for x in v["allocations"]}
    c.eq(D(allocs[r4["grn_number"]]["amount"]), D(400), "by value: the receipt of 4 takes 400.00")
    c.eq(D(allocs[r6["grn_number"]]["amount"]), D(600), "the receipt of 6 takes 600.00")
    c.eq(D(v["inventory_amount"]) + D(v["cogs_amount"]), D(1000), "inventory and cost of goods sold add up to the charge")
    c.eq(D(v["inventory_amount"]), D(600), "the part still on hand (6 of 10) revalues the stock: 600.00")
    c.eq(D(v["cogs_amount"]), D(400), "the rest goes to cost of goods sold: 400.00")
    entries = journal(a, v["voucher_number"])
    c.ok(len(entries) >= 1, "the voucher has a journal entry")
    if entries:
        net = entry_net(a, entries[0])
        c.eq(net.get("INVENTORY"), D(600), "Dr Inventory 600.00")
        c.eq(net.get("COST_OF_GOODS_SOLD"), D(400), "Dr Cost of Goods Sold 400.00")
    for basis in ("QUANTITY", "WEIGHT"):
        other = a.post(LC, {**body, "basis": basis})
        c.ok(other[0] in (200, 201, 422), f"basis {basis} answers", other[0])
        if other[0] in (200, 201):
            cancelled = a.post(f"{LC}/{data(other[1])['id']}/cancel", {"reason": "check"})
            c.eq(cancelled[0], 200, f"the {basis} voucher cancels")
    cancel = a.post(f"{LC}/{v['id']}/cancel", {"reason": "check"})
    c.eq(cancel[0], 200, "cancel a voucher")
    if cancel[0] == 200:
        c.eq(data(cancel[1])["status"], "CANCELLED", "it reads CANCELLED")
c.done()
