"""TC-MAST-020: a new product starts with its goods type's switches, HSN and tax group."""
import datetime
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("tc_mast_020")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)
piece = units["PIECE"]
med = ensure_use(admin, "MEDICINE", hsn="3004", group="GST_12_LOCAL")
elec = ensure_use(admin, "ELECTRONICS", hsn=None, group=None)
tablets = cat(admin, tag, "TABLETS", goods_type_id=med["id"])
phones = cat(admin, tag, "PHONES", goods_type_id=elec["id"])
sundries = cat(admin, tag, "SUNDRIES")
U = {"base_uom_id": piece, "inventory_uom_id": piece, "sales_uom_id": piece, "purchase_uom_id": piece}

def made(name, **kw):
    status, body = prod(admin, tag, name, **kw)
    c.eq(status, 201, f"{name} created ({message(body)})")
    return get_product(admin, data(body)["id"]) if status == 201 else {}

def flags(row, *names):
    return {n: row.get(n) for n in names}

p1 = made("P1", category_id=tablets["id"], **U)
c.eq(flags(p1, "track_batch", "track_expiry", "track_manufacturing_date", "require_batch_on_receipt",
           "require_batch_on_issue", "track_serial", "track_warranty"),
     {"track_batch": True, "track_expiry": True, "track_manufacturing_date": True, "require_batch_on_receipt": True,
      "require_batch_on_issue": True, "track_serial": False, "track_warranty": False}, "P1 switches from Medicine")
c.eq((p1.get("hsn_sac"), p1.get("tax_profile_group_code")), ("3004", "GST_12_LOCAL"), "P1 HSN and tax group from defaults")

p2 = made("P2", category_id=tablets["id"], track_batch=False)
c.eq(flags(p2, "track_batch", "require_batch_on_receipt", "require_batch_on_issue", "track_expiry"),
     {"track_batch": False, "require_batch_on_receipt": False, "require_batch_on_issue": False, "track_expiry": True},
     "P2 batch off: both require_batch off, expiry still on")

p3 = made("P3", category_id=tablets["id"], hsn_sac="3003", tax_profile_group_code="GST_18_LOCAL")
c.eq((p3.get("hsn_sac"), p3.get("tax_profile_group_code")), ("3003", "GST_18_LOCAL"), "P3 keeps its own HSN and tax group")

p4 = made("P4", category_id=phones["id"])
c.eq(flags(p4, "track_serial", "track_warranty", "require_serial_on_receipt", "require_serial_on_issue", "track_batch"),
     {"track_serial": True, "track_warranty": True, "require_serial_on_receipt": True,
      "require_serial_on_issue": True, "track_batch": False}, "P4 serial switches from Electronics")

p5 = made("P5", category_id=sundries["id"])
c.eq(flags(p5, "track_batch", "track_expiry", "track_manufacturing_date", "track_serial", "track_warranty",
           "require_batch_on_receipt", "require_batch_on_issue", "require_serial_on_receipt", "require_serial_on_issue"),
     {k: False for k in ("track_batch", "track_expiry", "track_manufacturing_date", "track_serial", "track_warranty",
                        "require_batch_on_receipt", "require_batch_on_issue", "require_serial_on_receipt",
                        "require_serial_on_issue")}, "P5 General tracks nothing")
c.eq(p5.get("hsn_sac"), None, "P5 has no HSN")

p6 = made("P6", category_id=sundries["id"], barcode=f"BC{tag}", qr_code=f"QR{tag}", track_warranty=True, shelf_life_days=365)
c.eq((p6.get("barcode"), p6.get("qr_code"), p6.get("track_warranty"), p6.get("shelf_life_days")),
     (f"BC{tag}", f"QR{tag}", True, 365), "P6 barcode, QR, warranty, shelf life saved")

# Metadata.
status, body = admin.get(f"{PRODUCTS}/metadata?category_id={tablets['id']}")
c.eq(status, 200, "metadata read")
meta = data(body) if status == 200 else {}
c.eq(meta.get("goods_type_id"), med["id"], "metadata names Medicine for Tablets")
options = {o["code"]: o for o in meta.get("goods_types", [])}
c.ok(options and all(len(o["switches"]) == 9 for o in options.values()), "each type lists nine switches",
     {k: len(v["switches"]) for k, v in options.items()})
c.eq(options.get("MEDICINE", {}).get("default_hsn_sac"), "3004", "metadata carries the HSN default")
c.eq(meta.get("unit_sets") is not None, True, "metadata carries unit_sets")

# Move P5 to Tablets via PUT.
put = {"code": p5["code"], "name": p5["name"], "product_type": "STOCK_ITEM", "category_id": tablets["id"]}
status, body = admin.put(f"{PRODUCTS}/{p5['id']}", put)
c.eq(status, 200, f"P5 moved ({message(body)})")
p5b = get_product(admin, p5["id"])
c.eq(p5b.get("goods_type_id"), med["id"], "P5 carries Medicine after the move")
c.eq((p5b.get("track_batch"), p5b.get("track_expiry"), p5b.get("require_batch_on_receipt")), (False, False, False),
     "P5 switches unchanged by the move")

# Duplicate P1.
status, body = admin.post(f"{PRODUCTS}/{p1['id']}/duplicate")
c.eq(status, 201, f"P1 duplicated ({message(body)})")
if status == 201:
    dup = get_product(admin, data(body)["id"])
    names = ("track_batch", "track_expiry", "track_manufacturing_date", "require_batch_on_receipt",
             "require_batch_on_issue", "track_serial", "track_warranty", "goods_type_id", "hsn_sac", "tax_profile_group_code")
    c.eq(flags(dup, *names), flags(p1, *names), "the copy carries P1's switches")

# Receipt of P1.
warehouse = next(w for w in data(admin.get("/api/v1/warehouses?page_size=50")[1]) if w["code"] == "MAIN")
branch = next(b for b in data(admin.get("/api/v1/branches?page_size=50")[1]) if b["code"] == "HO")
status, body = admin.post("/api/v1/vendors", {"code": f"{tag}-V", "name": f"Supplier {tag}"})
c.eq(status, 201, f"vendor ({message(body)})")
vendor = data(body)
today = datetime.date.today().isoformat()
status, body = admin.post("/api/v1/purchases", {
    "branch_id": branch["id"], "warehouse_id": warehouse["id"], "vendor_id": vendor["id"], "purchase_date": today,
    "lines": [{"product_id": p1["id"], "ordered_quantity": "10", "unit_price": "100",
               "purchase_uom_id": piece, "inventory_uom_id": piece}]})
c.eq(status, 201, f"purchase order ({message(body)})")
if status != 201:
    c.done()
order = data(body)
admin.post(f"/api/v1/purchases/{order['id']}/submit")
status, body = admin.post(f"/api/v1/purchases/{order['id']}/approve")
c.eq(status, 200, f"order approved ({message(body)})")
line = data(admin.get(f"/api/v1/purchases/{order['id']}")[1])["lines"][0]

def receipt(**extra):
    status, body = admin.post("/api/v1/goods-receipts", {
        "purchase_order_id": order["id"], "receipt_date": today,
        "lines": [{"purchase_order_line_id": line["id"], "line_number": 1, "current_receipt_quantity": "3",
                   "warehouse_id": warehouse["id"], **extra}]})
    if status != 201:
        return status, body
    return admin.post(f"/api/v1/goods-receipts/{data(body)['id']}/complete")

c.refused(receipt(), 422, "must be received with a batch number", "receipt with no batch")
expiry = (datetime.date.today() + datetime.timedelta(days=400)).isoformat()
mfg = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
status, body = receipt(batch_number=f"B{tag}", expiry_date=expiry, manufacturing_date=mfg)
c.eq(status, 200, f"receipt with a batch accepted ({message(body)})")
status, body = admin.put(f"{PRODUCTS}/{p1['id']}", {"code": p1["code"], "name": p1["name"], "product_type": "STOCK_ITEM", "track_batch": False})
c.refused((status, body), 422, "cannot be changed", "switching batch tracking off while it holds stock")
c.done()
