"""TC-MAST-029: what a business profile no longer does."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, state, suffix
from _lib import audit_actions, clear_tracked_products, must, product

c = Check("tc_mast_029")
tag = suffix()
admin, manager = client("generic_admin"), client("generic_manager")
platform = client("generic_platform")
generic = state()["own_firms"]["generic"]["id"]
BF = "/api/v1/business-framework"

# platform: the feature list and the Generic profile
s, b = platform.get(f"{BF}/features?page_size=100")
c.eq(sorted(r["code"] for r in data(b)),
     sorted(["ATTACHMENTS", "VEHICLE_TRACKING", "DRUG_LICENSE", "COMMISSION", "BATCH_PTR_PTS"]),
     "the feature list holds the five firm features and none of the old tracking ones")
s, b = platform.get(f"{BF}/profiles?page_size=100")
gp = next(p for p in data(b) if p["code"] == "GENERIC")
s, b = platform.get(f"{BF}/profiles/{gp['id']}/configuration")
feats = {f["id"]: f["code"] for f in data(platform.get(f"{BF}/features?page_size=100")[1])}
c.eq([feats[i] for i in data(b)["feature_ids"]], ["ATTACHMENTS"], "the Generic profile lists Attachments only")

# (a) a product with a barcode and a QR code
a = product(admin, f"BQ-{tag}", barcode=f"89{tag}0001", qr_code=f"QR-{tag}")
c.eq(a[0], 201, "(a) a product with a barcode and a QR code on the Generic profile")
if a[0] == 201:
    c.eq((data(a[1]).get("barcode"), data(a[1]).get("qr_code")), (f"89{tag}0001", f"QR-{tag}"),
         "(a) both read back")
# (b) a serial with warranty dates
ser = must(product(admin, f"SW-{tag}", track_serial=True, track_warranty=True), "serial product")
b1 = admin.post("/api/v1/batch-serial/serials", {
    "product_id": ser["id"], "serial_number": f"S{tag}",
    "warranty_start": "2026-10-01", "warranty_end": "2027-10-01"})
c.eq(b1[0], 201, "(b) a serial number with warranty dates on the Generic profile")
# (c) a batch with an expiry date
exp = must(product(admin, f"EX-{tag}", track_batch=True, track_expiry=True), "expiry product")
c1 = admin.post("/api/v1/batch-serial/batches", {
    "product_id": exp["id"], "batch_number": f"B{tag}", "expiry_date": "2028-01-01"})
c.eq(c1[0], 201, "(c) a batch with an expiry date on the Generic profile")
# (d) a route
base = "/api/v1/sales-territories"
cur = admin.get(f"{base}/hierarchy-levels")
if cur[0] == 200:
    lv = data(cur[1])
    keep = ("level_order", "level_code", "display_name", "is_mandatory")
    # the levels are a one-off set-up the platform administrator saves (a firm admin gets 403)
    saved = platform.put(f"{base}/hierarchy-levels", {
        "max_levels": lv["max_levels"], "levels": [{k: x[k] for k in keep} for x in lv["levels"]]})
    levels = {x["level_code"]: x["id"] for x in data(saved[1])["levels"]} if saved[0] == 200 else {}
    rt = admin.get(f"{base}/route-types")
    types = data(rt[1]) if rt[0] == 200 else []
    if not types:
        types = [must(admin.post(f"{base}/route-types", {"code": "SALES", "name": "Sales Route"}), "route type")]
    try:
        region = must(admin.post(base, {"code": f"RG{tag}", "name": f"Region {tag}",
                                        "hierarchy_level_id": levels["REGION"], "parent_id": None}), "region")
        zone = must(admin.post(base, {"code": f"ZN{tag}", "name": f"Zone {tag}",
                                      "hierarchy_level_id": levels["TERRITORY"], "parent_id": region["id"]}), "zone")
        d = admin.post(base, {"code": f"RT{tag}", "name": f"Route {tag}",
                              "hierarchy_level_id": levels["ROUTE"], "parent_id": zone["id"],
                              "route_profile": {"route_type_id": types[0]["id"], "visit_frequency": "WEEKLY",
                                                "working_days": [1, 3]}})
        c.eq(d[0], 201, "(d) a route on the Generic profile")
    except (SystemExit, KeyError) as error:
        c.ok(False, f"(d) the territory set-up could not be made: {error}")
else:
    c.ok(False, "(d) could not read the hierarchy levels")
# (e) a second warehouse
s, b = admin.get("/api/v1/branches")
e = admin.post("/api/v1/warehouses", {"branch_id": data(b)[0]["id"], "code": f"W{tag}", "name": f"Second {tag}"})
c.eq(e[0], 201, "(e) a warehouse on the Generic profile")
# (f) vehicle on a delivery note: the firm feature is not mapped to Generic
import uuid
LINES = [{"sales_order_line_id": str(uuid.uuid4()), "line_number": 1, "current_delivery_quantity": "1"}]
f = admin.post("/api/v1/delivery-notes", {"sales_order_id": str(uuid.uuid4()),
                                          "delivery_date": "2026-10-08", "vehicle": "MH12AB1234",
                                          "lines": LINES})
c.refused(f, 403, "VEHICLE_TRACKING", "(f) a vehicle number on a delivery note, Generic firm")
# (g) the attachments feature is mapped: the gate lets the field through (the order is then not found)
g = admin.post("/api/v1/delivery-notes", {"sales_order_id": str(uuid.uuid4()),
                                          "delivery_date": "2026-10-08", "lines": LINES,
                                          "attachments": [{"file_name": "a.pdf", "file_path": "x/a.pdf"}]})
c.ok(g[0] != 403 and "ATTACHMENTS" not in message(g[1]),
     "(g) attachments pass the profile gate (the unknown order is what is then refused)", (g[0], message(g[1])))

# the firm manager repeats (c)
m = manager.post("/api/v1/batch-serial/batches", {
    "product_id": exp["id"], "batch_number": f"M{tag}", "expiry_date": "2028-01-01"})
c.ok(m[0] in (201, 403), "firm manager: created or refused for permission only", (m[0], message(m[1])))
if m[0] == 403:
    c.ok("profile" not in message(m[1]).lower() and "feature" not in message(m[1]).lower(),
         "the manager's refusal is about permission, not the profile", message(m[1]))

# the round trip of profiles
s, b = platform.get(f"{BF}/firms/{generic}/profiles")
ids = {p["code"]: p["id"] for p in data(b)}
before = [r["code"] for r in data(admin.get("/api/v1/products/goods-types")[1]) if r["in_use"]]
try:
    r1 = platform.put(f"{BF}/firms/{generic}/profile-assignment",
                      {"business_profile_id": ids["PHARMACY"], "is_active": True})
    c.eq(r1[0], 200, "Pharmacy is assigned to the Generic firm")
    after = [r["code"] for r in data(admin.get("/api/v1/products/goods-types")[1]) if r["in_use"]]
    # CASE TEXT: the case says assigning Pharmacy puts Medicine in use. The code hands a profile's
    # goods types out only with a firm's FIRST profile (framework_service.assign_profile_to_firm,
    # the created branch), as TC-MAST-019 and BACKLOG 89 say: a later change hands out nothing.
    c.eq(after, before, "assigning Pharmacy to a firm that already has a profile hands out no goods type")
    c.eq(len(audit_actions(platform, generic, "goods_type.starting_set")), 0,
         "and writes no goods_type.starting_set row")
finally:
    r2 = platform.put(f"{BF}/firms/{generic}/profile-assignment",
                      {"business_profile_id": ids["GENERIC"], "is_active": True})
c.eq(r2[0], 200, "Generic is assigned back")
c.eq([r["code"] for r in data(admin.get("/api/v1/products/goods-types")[1]) if r["in_use"]], before,
     "the goods types are unchanged by the round trip")
# leave the firm without tracked goods, as TC-MAST-026 needs
clear_tracked_products(admin)
c.done()
