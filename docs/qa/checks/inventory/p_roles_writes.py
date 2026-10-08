"""Probe: every inventory write endpoint, attempted by manager, store, sales and read-only accounts.

Expected: 403 exactly when the route's permission code is not held by the account's seeded role; the read-only
account writes nothing.
"""
from _inv import *
from _flow import *
from _roles import role_codes

c = Check("p_roles_writes")
w = World()
ROLE = {"manager": "FIRM_MANAGER", "store": "INVENTORY_MANAGER", "sales": "SALES_MANAGER", "viewer": "VIEWER"}
codes = role_codes(client("platform"))
who = {name: client(name) for name in ROLE}
a, b2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
w.stock_in(a["id"], p["id"], 50)
row = w.rows(p["id"])[0]
batch_op = must(w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"RO{w.tag}", "posting_date": w.today,
                                                      "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "5"}]}), "draft opening")
trf = must(w.admin.post(f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": "1"}]}), "draft transfer")
cnt = must(w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": w.today}), "count")
reason = must(w.admin.post(f"{INV}/adjustment-reasons", {"code": f"R{w.tag}", "name": f"Reason {w.tag}"}), "reason")
kit = w.product("KIT", product_type="BUNDLE")
base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today}
wbase = {**base, "warehouse_id": a["id"]}
bt = {"product_id": p["id"], "batch_number": f"RB{w.tag}"}
cases = [
    ("POST /inventory", "POST", INV, {"branch_id": w.branch_id, "warehouse_id": b2["id"], "product_id": p["id"]}, "INVENTORY_ADJUST"),
    ("PUT /inventory/{id}", "PUT", f"{INV}/{row['id']}", {"branch_id": w.branch_id, "warehouse_id": a["id"], "product_id": p["id"], "reorder_level": "3"}, "INVENTORY_ADJUST"),
    ("POST adjustments", "POST", f"{INV}/adjustments", {**wbase, "quantity": "-1", "reference_number": "RA{n}"}, "INVENTORY_ADJUST"),
    ("POST transfers", "POST", f"{INV}/transfers", {**base, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": "1", "reference_number": "RT{n}"}, "INVENTORY_ADJUST"),
    ("POST write-offs", "POST", f"{INV}/write-offs", {**wbase, "quantity": "1", "reason": "DAMAGE", "reference_number": "RW{n}"}, "INVENTORY_ADJUST"),
    ("POST quarantine", "POST", f"{INV}/quarantine", {**wbase, "action": "HOLD", "quantity": "1", "reference_number": "RQ{n}"}, "INVENTORY_ADJUST"),
    ("POST opening-stock", "POST", f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": b2["id"], "reference_number": "RO{n}", "posting_date": w.today, "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "5"}]}, "OPENING_STOCK_CREATE"),
    ("PUT opening-stock/{id}", "PUT", f"{INV}/opening-stock/{batch_op['id']}", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": batch_op["reference_number"], "posting_date": w.today, "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "5"}]}, "OPENING_STOCK_UPDATE"),
    ("POST opening-stock/{id}/post", "POST", f"{INV}/opening-stock/{batch_op['id']}/post", {}, "OPENING_STOCK_CREATE"),
    ("POST opening-stock/import", "POST", f"{INV}/opening-stock/import", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": "RI{n}", "posting_date": w.today, "lines": []}, "INVENTORY_IMPORT"),
    ("PUT adjustment-limits", "PUT", f"{INV}/adjustment-limits", {"limits": []}, "INVENTORY_MANAGE_SETTINGS"),
    ("POST adjustment-reasons", "POST", f"{INV}/adjustment-reasons", {"code": "RR{n}", "name": "Reason {n}"}, "INVENTORY_MANAGE_REASONS"),
    ("PUT adjustment-reasons/{id}", "PUT", f"{INV}/adjustment-reasons/{reason['id']}", {"code": reason["code"], "name": "Renamed"}, "INVENTORY_MANAGE_REASONS"),
    ("POST adjustment-requests", "POST", f"{INV}/adjustment-requests", {"kind": "WRITE_OFF", "write_off": {**wbase, "quantity": "1", "reason": "DAMAGE", "reference_number": "RR{n}"}}, "INVENTORY_ADJUST"),
    ("POST repacks", "POST", f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"], "lines": [{"kind": "CONSUME", "product_id": p["id"], "quantity": "1"}, {"kind": "PRODUCE", "product_id": kit["id"], "quantity": "1"}]}, "INVENTORY_ADJUST"),
    ("POST stock-transfers", "POST", f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": "1"}]}, "INVENTORY_ADJUST"),
    ("PUT stock-transfers/{id}", "PUT", f"{INV}/stock-transfers/{trf['id']}", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": "2"}]}, "INVENTORY_ADJUST"),
    ("POST stock-transfers/{id}/cancel", "POST", f"{INV}/stock-transfers/{trf['id']}/cancel", {"reason": "probe"}, "INVENTORY_ADJUST"),
    ("POST count-plans", "POST", f"{INV}/count-plans", {"name": "Plan {n}", "branch_id": w.branch_id, "warehouse_id": a["id"], "frequency_days": 30}, "INVENTORY_ADJUST"),
    ("PUT counts/{id}", "PUT", f"{INV}/counts/{cnt['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": "49"}]}, "INVENTORY_ADJUST"),
    ("POST counts", "POST", f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": b2["id"], "count_date": w.today}, "INVENTORY_ADJUST"),
    ("POST counts/{id}/attachments", "POST", f"{INV}/counts/{cnt['id']}/attachments", {"attachments": [{"file_name": "f.pdf", "file_path": "e/f.pdf"}]}, "INVENTORY_ADJUST"),
    ("POST products/{id}/assemble", "POST", f"/api/v1/products/{kit['id']}/assemble", {"branch_id": w.branch_id, "warehouse_id": a["id"], "quantity": "1"}, "INVENTORY_ADJUST"),
    ("POST batches", "POST", "/api/v1/batch-serial/batches", {**bt, "batch_number": "RB{n}", "warehouse_id": a["id"]}, "BATCH_CREATE"),
    ("POST serials", "POST", "/api/v1/batch-serial/serials", {"product_id": p["id"], "serial_number": "RS{n}"}, "SERIAL_CREATE"),
    ("POST lots", "POST", "/api/v1/batch-serial/lots", {"product_id": p["id"], "lot_number": "RL{n}"}, "BATCH_CREATE"),
]
ledger_before = len(w.ledger(p["id"]))
viewer_attempts_moved = 0
for label, method, path, body, code in cases:
    for name, api in who.items():
        n = suffix(5)
        text = __import__("json").dumps(body).replace("{n}", n)
        payload = __import__("json").loads(text)
        st, b = api.call(method, path.replace("{n}", n), payload)
        allowed = code in codes[ROLE[name]]
        if allowed:
            c.ok(st != 403, f"{label} by {name} ({ROLE[name]} holds {code}) is not refused as forbidden", (st, message(b)))
        else:
            c.eq(st, 403, f"{label} by {name} ({ROLE[name]} lacks {code})")
c.done()
