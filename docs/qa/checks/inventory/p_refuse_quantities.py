"""Probe: zero or negative quantities and same-warehouse transfers are refused on every stock write."""
from _inv import *
from _flow import *

c = Check("p_refuse_quantities")
w = World()
a, b2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
w.stock_in(a["id"], p["id"], 10)
base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today}


def never_2xx(label: str, answer: tuple[int, object]) -> None:
    """The write must be a 4xx (never 2xx, never 5xx)."""
    st, body = answer
    c.ok(400 <= st < 500, f"{label} refused with a 4xx", (st, message(body)))


for q in ("0", "-1"):
    never_2xx(f"transfer qty {q}", w.admin.post(f"{INV}/transfers", {**base, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": q, "reference_number": f"T{q}{w.tag}"}))
    never_2xx(f"write-off qty {q}", w.admin.post(f"{INV}/write-offs", {**base, "warehouse_id": a["id"], "quantity": q, "reason": "DAMAGE", "reference_number": f"W{q}{w.tag}"}))
    never_2xx(f"quarantine hold qty {q}", w.admin.post(f"{INV}/quarantine", {**base, "warehouse_id": a["id"], "action": "HOLD", "quantity": q, "reference_number": f"Q{q}{w.tag}"}))
    never_2xx(f"opening stock qty {q}", w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"O{q}{w.tag}", "posting_date": w.today, "lines": [{"product_id": p["id"], "quantity": q, "unit_cost": "5"}]}))
    never_2xx(f"stock-transfer line qty {q}", w.admin.post(f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": q}]}))
    never_2xx(f"repack consume qty {q}", w.admin.post(f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"], "lines": [{"kind": "CONSUME", "product_id": p["id"], "quantity": q}, {"kind": "PRODUCE", "product_id": p["id"], "quantity": "1"}]}))
never_2xx("adjustment qty 0", w.admin.post(f"{INV}/adjustments", {**base, "warehouse_id": a["id"], "quantity": "0", "reference_number": f"A0{w.tag}"}))
never_2xx("opening stock negative cost", w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"OC{w.tag}", "posting_date": w.today, "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "-5"}]}))
never_2xx("count with a negative counted quantity", w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": w.today, "lines": [{"product_id": p["id"], "counted_quantity": "-3"}]}))
# same warehouse
never_2xx("transfer to the same warehouse", w.admin.post(f"{INV}/transfers", {**base, "from_warehouse_id": a["id"], "to_warehouse_id": a["id"], "quantity": "1", "reference_number": f"S{w.tag}"}))
never_2xx("stock-transfer document to the same warehouse", w.admin.post(f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": a["id"], "lines": [{"product_id": p["id"], "quantity": "1"}]}))
# too many decimals / absurd sizes
never_2xx("quantity 'abc'", w.admin.post(f"{INV}/transfers", {**base, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": "abc", "reference_number": f"X{w.tag}"}))
never_2xx("quantity 1e30", w.admin.post(f"{INV}/write-offs", {**base, "warehouse_id": a["id"], "quantity": "1e30", "reason": "DAMAGE", "reference_number": f"X2{w.tag}"}))
c.eq(w.qty(p["id"]), D(10), "none of the refused writes moved stock")
c.done()
