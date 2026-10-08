"""Probe: the inventory, ledger and transaction lists filter and sort as asked and agree with each other."""
from _inv import *
from _flow import *

c = Check("p_list_filters")
w = World()
a, b2 = w.warehouse(), w.warehouse()
p, q, z = w.product(), w.product(), w.product()
w.opening(a["id"], [{"product_id": p["id"], "quantity": "3", "unit_cost": "5", "reorder_level": "5"},
                     {"product_id": q["id"], "quantity": "9", "unit_cost": "5"},
                     {"product_id": z["id"], "quantity": "2", "unit_cost": "5"}])
base = {"branch_id": w.branch_id, "transaction_date": w.today, "warehouse_id": a["id"]}
w.admin.post(f"{INV}/write-offs", {**base, "product_id": z["id"], "quantity": "2", "reason": "LOSS", "reference_number": f"Z{w.tag}"})
w.admin.post(f"{INV}/transfers", {"branch_id": w.branch_id, "transaction_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "product_id": q["id"], "quantity": "4", "reference_number": f"T{w.tag}"})
codes = lambda path: {x["product_code"] for x in all_rows(w.admin, path)}
c.eq(codes(f"{INV}?warehouse_id={a['id']}&low_stock_only=true") & {p["code"], q["code"], z["code"]}, {p["code"], z["code"]}, "low_stock_only: at or below reorder level (and the emptied one)")
c.eq(codes(f"{INV}?warehouse_id={a['id']}&out_of_stock_only=true") & {p["code"], q["code"], z["code"]}, {z["code"]}, "out_of_stock_only")
c.eq(codes(f"{INV}?warehouse_id={b2['id']}") & {p["code"], q["code"], z["code"]}, {q["code"]}, "warehouse filter: the transferred product only")
c.eq(codes(f"{INV}?search={p['code']}"), {p["code"]}, "search by code")
rows = all_rows(w.admin, f"{INV}?warehouse_id={a['id']}&sort_by=current_quantity&sort_direction=asc")
qs = [D(r["current_quantity"]) for r in rows]
c.eq(qs, sorted(qs), "sorted by current quantity ascending")
rows = all_rows(w.admin, f"{INV}?warehouse_id={a['id']}&sort_by=product_code&sort_direction=desc")
cs = [r["product_code"] for r in rows]
c.eq(cs, sorted(cs, reverse=True), "sorted by product code descending")
# ledger and transactions agree
led = w.ledger(q["id"])
tx = all_rows(w.admin, f"{INV}/transactions?product_id={q['id']}")
c.eq(sorted((x["transaction_type"], x["quantity"]) for x in led), sorted((x["transaction_type"], x["quantity"]) for x in tx), "ledger and transactions list the same movements")
for ttype in ("TRANSFER_OUT", "TRANSFER_IN", "OPENING_STOCK"):
    got = all_rows(w.admin, f"{INV}/ledger?product_id={q['id']}&transaction_type={ttype}")
    c.eq(len(got), 1, f"ledger filtered to {ttype}")
got = all_rows(w.admin, f"{INV}/ledger?product_id={q['id']}&reference_number=T{w.tag}")
c.eq(len(got), 2, "ledger filtered by the reference finds both legs")
got = all_rows(w.admin, f"{INV}/transactions?product_id={q['id']}&transaction_from={w.today}&transaction_to={w.today}")
c.eq(len(got), 3, "the date range is inclusive of today")
got = all_rows(w.admin, f"{INV}/transactions?product_id={q['id']}&transaction_from=2020-01-01&transaction_to=2020-01-02")
c.eq(got, [], "a past range is empty")
for x in led:
    c.ok(D(x["previous_current_quantity"]) + D(x["current_quantity_delta"]) == D(x["new_current_quantity"]), "each ledger row adds up", x["id"])
c.done()
