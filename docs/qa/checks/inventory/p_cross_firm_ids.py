"""Probe: another firm's product, warehouse, branch or batch id on any stock write is refused (4xx), never accepted or a 500."""
import json

from _inv import *
from _flow import *

c = Check("p_cross_firm_ids")
w = World()
other = client("other_admin")
fp = data(other.get("/api/v1/products?page_size=1")[1])[0]["id"]
fw = data(other.get("/api/v1/warehouses?page_size=1")[1])[0]["id"]
fb = data(other.get("/api/v1/branches")[1])[0]["id"]
fbatch = None
rows = data(other.get("/api/v1/batch-serial/batches?page_size=1")[1])
fbatch = rows[0]["id"] if rows else "00000000-0000-4000-8000-000000000001"
a = w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 20)
before = w.qty(p["id"])


def refused(label: str, method: str, path: str, body: dict) -> None:
    """The request must be a 4xx."""
    st, b = w.admin.call(method, path, body)
    c.ok(400 <= st < 500, f"{label}: refused with a 4xx", (st, message(b)))


n = suffix(4)
ok_base = {"branch_id": w.branch_id, "transaction_date": w.today}
refused("adjustment, foreign product", "POST", f"{INV}/adjustments", {**ok_base, "warehouse_id": a["id"], "product_id": fp, "quantity": "1", "reference_number": f"X1{n}"})
refused("adjustment, foreign warehouse", "POST", f"{INV}/adjustments", {**ok_base, "warehouse_id": fw, "product_id": p["id"], "quantity": "1", "reference_number": f"X2{n}"})
refused("adjustment, foreign branch", "POST", f"{INV}/adjustments", {"branch_id": fb, "transaction_date": w.today, "warehouse_id": a["id"], "product_id": p["id"], "quantity": "1", "reference_number": f"X3{n}"})
refused("adjustment, foreign batch", "POST", f"{INV}/adjustments", {**ok_base, "warehouse_id": a["id"], "product_id": p["id"], "batch_id": fbatch, "quantity": "1", "reference_number": f"X4{n}"})
refused("transfer to a foreign warehouse", "POST", f"{INV}/transfers", {**ok_base, "from_warehouse_id": a["id"], "to_warehouse_id": fw, "product_id": p["id"], "quantity": "1", "reference_number": f"X5{n}"})
refused("transfer from a foreign warehouse", "POST", f"{INV}/transfers", {**ok_base, "from_warehouse_id": fw, "to_warehouse_id": a["id"], "product_id": p["id"], "quantity": "1", "reference_number": f"X6{n}"})
refused("transfer with a foreign batch", "POST", f"{INV}/transfers", {**ok_base, "from_warehouse_id": a["id"], "to_warehouse_id": w.warehouse()["id"], "product_id": p["id"], "batch_id": fbatch, "quantity": "1", "reference_number": f"X7{n}"})
refused("write-off, foreign product", "POST", f"{INV}/write-offs", {**ok_base, "warehouse_id": a["id"], "product_id": fp, "quantity": "1", "reason": "DAMAGE", "reference_number": f"X8{n}"})
refused("write-off, foreign warehouse", "POST", f"{INV}/write-offs", {**ok_base, "warehouse_id": fw, "product_id": p["id"], "quantity": "1", "reason": "DAMAGE", "reference_number": f"X9{n}"})
refused("quarantine, foreign product", "POST", f"{INV}/quarantine", {**ok_base, "warehouse_id": a["id"], "product_id": fp, "action": "HOLD", "quantity": "1", "reference_number": f"XA{n}"})
refused("opening stock, foreign product", "POST", f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"XB{n}", "posting_date": w.today, "lines": [{"product_id": fp, "quantity": "1", "unit_cost": "1"}]})
refused("opening stock, foreign warehouse", "POST", f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": fw, "reference_number": f"XC{n}", "posting_date": w.today, "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "1"}]})
refused("stock-transfer, foreign warehouse", "POST", f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": fw, "lines": [{"product_id": p["id"], "quantity": "1"}]})
refused("stock-transfer, foreign product", "POST", f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": w.warehouse()["id"], "lines": [{"product_id": fp, "quantity": "1"}]})
refused("repack, foreign product", "POST", f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"], "lines": [{"kind": "CONSUME", "product_id": fp, "quantity": "1"}, {"kind": "PRODUCE", "product_id": p["id"], "quantity": "1"}]})
refused("count, foreign warehouse", "POST", f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": fw, "count_date": w.today})
refused("count line, foreign product", "POST", f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": w.today, "lines": [{"product_id": fp, "counted_quantity": "1"}]})
refused("count plan, foreign warehouse", "POST", f"{INV}/count-plans", {"name": f"P{n}", "branch_id": w.branch_id, "warehouse_id": fw, "frequency_days": 30})
refused("inventory row, foreign product", "POST", INV, {"branch_id": w.branch_id, "warehouse_id": a["id"], "product_id": fp})
refused("batch, foreign product", "POST", "/api/v1/batch-serial/batches", {"product_id": fp, "batch_number": f"XD{n}"})
refused("batch, foreign warehouse", "POST", "/api/v1/batch-serial/batches", {"product_id": p["id"], "batch_number": f"XE{n}", "warehouse_id": fw})
refused("serial, foreign product", "POST", "/api/v1/batch-serial/serials", {"product_id": fp, "serial_number": f"XF{n}"})
refused("serial, foreign batch", "POST", "/api/v1/batch-serial/serials", {"product_id": p["id"], "serial_number": f"XG{n}", "batch_id": fbatch})
refused("lot, foreign product", "POST", "/api/v1/batch-serial/lots", {"product_id": fp, "lot_number": f"XH{n}"})
kit = w.product("KIT", product_type="BUNDLE")
refused("kit component, foreign product", "PUT", f"/api/v1/products/{kit['id']}/components", {"components": [{"component_product_id": fp, "quantity": "1"}]})
refused("assemble in a foreign warehouse", "POST", f"/api/v1/products/{kit['id']}/assemble", {"branch_id": w.branch_id, "warehouse_id": fw, "quantity": "1"})
for path in (f"{INV}/{fp}", f"{INV}/stock-transfers/{fp}", f"{INV}/counts/{fp}", f"/api/v1/batch-serial/batches/{fbatch}"):
    st, b = w.admin.get(path)
    c.ok(st in (404, 422), f"GET {path.split('/api/v1/')[1][:40]} with an id of another firm is a 404", (st, message(b)))
c.eq(w.qty(p["id"]), before, "none of it moved stock")
c.done()
