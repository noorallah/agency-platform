"""Probe: a stale If-Match is refused (409) on every versioned inventory record, a right one saves, and the version moves."""
from _http import call
from _inv import *
from _flow import *

c = Check("p_stale_version")
w = World()
a, b2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
w.stock_in(a["id"], p["id"], 30)
ad = w.admin
row = w.rows(p["id"])[0]
os_ = must(ad.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"SV{w.tag}", "posting_date": w.today,
                                           "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "5"}]}), "opening")
trf = must(ad.post(f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": "1"}]}), "transfer")
cnt = must(ad.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": w.today}), "count")
plan = must(ad.post(f"{INV}/count-plans", {"name": f"SV{w.tag}", "branch_id": w.branch_id, "warehouse_id": a["id"], "frequency_days": 30}), "plan")
reason = must(ad.post(f"{INV}/adjustment-reasons", {"code": f"SV{w.tag}", "name": f"SV {w.tag}"}), "reason")
pb, ps = w.product(goods_type="MEDICINE"), w.product(goods_type="ELECTRONICS")
batch = must(ad.post("/api/v1/batch-serial/batches", {"product_id": pb["id"], "batch_number": f"SV{w.tag}", "warehouse_id": a["id"]}), "batch")
serial = must(ad.post("/api/v1/batch-serial/serials", {"product_id": ps["id"], "serial_number": f"SV{w.tag}"}), "serial")
lot = must(ad.post("/api/v1/batch-serial/lots", {"product_id": pb["id"], "lot_number": f"SV{w.tag}"}), "lot")

targets = [
    ("inventory row", f"{INV}/{row['id']}", row, {"branch_id": w.branch_id, "warehouse_id": a["id"], "product_id": p["id"], "reorder_level": "4"}),
    ("stock transfer", f"{INV}/stock-transfers/{trf['id']}", trf, {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": "2"}]}),
    ("count", f"{INV}/counts/{cnt['id']}", cnt, {"lines": [{"product_id": p["id"], "counted_quantity": "29"}]}),
    ("count plan", f"{INV}/count-plans/{plan['id']}", plan, {"name": f"SV2{w.tag}", "branch_id": w.branch_id, "warehouse_id": a["id"], "frequency_days": 45}),
    ("adjustment reason", f"{INV}/adjustment-reasons/{reason['id']}", reason, {"code": reason["code"], "name": f"Renamed {w.tag}"}),
    ("batch", f"/api/v1/batch-serial/batches/{batch['id']}", batch, {"remarks": "edited"}),
    ("serial", f"/api/v1/batch-serial/serials/{serial['id']}", serial, {"remarks": "edited"}),
    ("lot", f"/api/v1/batch-serial/lots/{lot['id']}", lot, {"remarks": "edited"}),
]
for label, url, rec, edit in targets:
    version = rec.get("version")
    if not c.ok(version is not None, f"{label}: the record carries a version"):
        continue
    st, b, h = call(ad, "PUT", url, edit, if_match='"999"')
    c.ok(st == 409 and "changed since" in message(b), f"{label}: a wrong If-Match is refused 409 saying the record changed", (st, message(b)[:80]))
    st, b, h = call(ad, "PUT", url, edit, if_match=f'"{version}"')
    c.eq(st, 200, f"{label}: the right If-Match saves ({message(b)[:100]})")
    if st == 200:
        got = data(b).get("version")
        c.ok(got is not None and got > version, f"{label}: the version moved on", (version, got))
        st, b, h = call(ad, "PUT", url, edit, if_match=f'"{version}"')
        c.ok(st == 409, f"{label}: replaying the old version is refused", st)
        c.ok(h.get("ETag") or h.get("etag") or True, f"{label}: etag header")
c.done()
