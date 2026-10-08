"""Probe: after a mix of movements the ledger balance, the inventory row, the summary and the valuation agree,
and the Inventory account moves by exactly what the valuation moves."""
from _inv import *
from _flow import *

c = Check("p_books_agree")
w = World()
a, b2 = w.warehouse("A"), w.warehouse("B")
p, q = w.product(), w.product("Q", purchase_price="10")


def totals() -> tuple[Decimal, Decimal]:
    """(valuation total, Inventory account balance) for the whole firm."""
    v = {r["row_type"]: D(r["value"]) for r in w.valuation() if r["row_type"] != "ITEM"}
    return v["TOTAL"], v["BOOKS"]


t0, b0 = totals()
receive(w, a["id"], p["id"], 10, "61.37")
receive(w, a["id"], p["id"], 7, "58.11")
base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today}
sell_and_dispatch(w, a["id"], p["id"], 4)
w.admin.post(f"{INV}/write-offs", {**base, "warehouse_id": a["id"], "quantity": "1", "reason": "DAMAGE", "reference_number": f"W{w.tag}"})
w.admin.post(f"{INV}/adjustments", {**base, "warehouse_id": a["id"], "quantity": "2", "reference_number": f"AD{w.tag}", "reason_code": "LOSS"})
w.admin.post(f"{INV}/transfers", {**base, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": "3", "reference_number": f"T{w.tag}"})
w.admin.post(f"{INV}/quarantine", {**base, "warehouse_id": b2["id"], "action": "HOLD", "quantity": "1", "reference_number": f"Q{w.tag}"})
cnt = must(w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": w.today}), "count")
line = next(l for l in cnt["lines"] if l["product_id"] == p["id"])
w.admin.put(f"{INV}/counts/{cnt['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": str(D(line["expected_quantity"]) - 1)}]})
w.admin.post(f"{INV}/counts/{cnt['id']}/post", {})
w.admin.post(f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"], "wastage_percent": "2",
                                "lines": [{"kind": "CONSUME", "product_id": p["id"], "quantity": "3"}, {"kind": "PRODUCE", "product_id": q["id"], "quantity": "9"}]})
for prod in (p, q):
    rows = w.rows(prod["id"])
    cur = sum(D(r["current_quantity"]) for r in rows)
    owned = cur + sum(D(r["quarantine_quantity"]) for r in rows) + sum(D(r["damaged_quantity"]) for r in rows)
    st, b = w.admin.get(f"{INV}/summary/by-product")
    summ = next(x for x in data(b) if x["scope_id"] == prod["id"])
    c.eq(D(summ["current_quantity"]), cur, f"{prod['code'][:3]}: by-product summary = sum of rows")
    led = w.ledger(prod["id"])
    by_inv: dict[str, Decimal] = {}
    for x in led:
        by_inv[x["inventory_id"]] = D(x["new_current_quantity"])
    c.eq(sum(by_inv.values()), cur, f"{prod['code'][:3]}: last ledger balance per row sums to the rows")
    c.eq(sum(D(x["current_quantity_delta"]) for x in led), cur, f"{prod['code'][:3]}: ledger deltas sum to the rows")
    val = next(v for v in w.valuation() if v["product_code"] == prod["code"] and v["row_type"] == "ITEM")
    c.eq(D(val["quantity"]), owned, f"{prod['code'][:3]}: valuation quantity = held + quarantined + damaged")
    c.ok(abs(D(val["value"]) - D(val["quantity"]) * D(val["rate"])) <= D("0.01"), f"{prod['code'][:3]}: value = quantity x rate",
         (val["value"], val["quantity"], val["rate"]))
t1, b1 = totals()
c.ok(abs((b1 - b0) - (t1 - t0)) <= D("0.05"), "the Inventory account moved by what the valuation moved (a paisa or two of rounding is D-STK-20, pinned in d_stk_20)", (b1 - b0, t1 - t0))
c.done()
