"""TC-MAST-023: a batch, a serial and their dates follow the product's switches."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, suffix
from _lib import must, product

c = Check("tc_mast_023")
tag = suffix()
admin = client("admin")
sales = client("sales")

med = must(product(admin, f"TR-MED-{tag}", track_batch=True, track_expiry=True,
                   track_manufacturing_date=True), "TR-MED")
paint = must(product(admin, f"TR-PAINT-{tag}", track_batch=True), "TR-PAINT")
phone = must(product(admin, f"TR-PHONE-{tag}", track_serial=True, track_warranty=True),
             "TR-PHONE")

# (a) a medicine batch with an expiry date
a = admin.post("/api/v1/batch-serial/batches", {
    "product_id": med["id"], "batch_number": f"M{tag}",
    "manufacturing_date": "2026-01-01", "expiry_date": "2028-01-01"})
c.eq(a[0], 201, "(a) a batch with an expiry for a product tracking expiry")

# (b) paint: expiry refused, then the same batch without it accepted
b1 = admin.post("/api/v1/batch-serial/batches", {
    "product_id": paint["id"], "batch_number": f"P{tag}", "expiry_date": "2028-01-01"})
c.refused(b1, 422, "does not track expiry dates", "(b) expiry on a product that does not track it")
c.ok(f"TR-PAINT-{tag}" in message(b1[1]) and "expiry_date cannot be set" in message(b1[1]),
     "(b) the refusal names the product and the field", message(b1[1]))
b2 = admin.post("/api/v1/batch-serial/batches", {
    "product_id": paint["id"], "batch_number": f"P{tag}"})
c.eq(b2[0], 201, "(b) the same batch without the expiry")

# (c) a batch for a serial-only product
c.refused(admin.post("/api/v1/batch-serial/batches", {
    "product_id": phone["id"], "batch_number": f"X{tag}"}),
    422, "is not tracked by batch", "(c) batch for a product not tracked by batch")

# (d) serial with warranty for the phone; serial for the paint refused
d1 = admin.post("/api/v1/batch-serial/serials", {
    "product_id": phone["id"], "serial_number": f"SN{tag}",
    "warranty_start": "2026-10-01", "warranty_end": "2027-10-01"})
c.eq(d1[0], 201, "(d) serial with warranty dates for a product tracking both")
c.refused(admin.post("/api/v1/batch-serial/serials", {
    "product_id": paint["id"], "serial_number": f"SNP{tag}"}),
    422, "is not tracked by serial number", "(d) serial for a product not tracked by serial")

# (e) a batch can be held after the switch went off
if b2[0] == 201:
    off = admin.put(f"/api/v1/products/{paint['id']}", {
        "code": paint["code"], "name": paint["name"], "product_type": "STOCK_ITEM",
        "track_batch": False})
    c.ok(off[0] == 200, "(e) precondition: the paint's batch switch can go off", message(off[1]))
    batch_id = data(b2[1])["id"]
    e = admin.put(f"/api/v1/batch-serial/batches/{batch_id}", {"status": "QUARANTINE"})
    c.eq(e[0], 200, "(e) an existing batch can be held although the switch is off")
else:
    c.ok(False, "(e) skipped: the paint batch of (b) was not made")

# (f) a customer with a minimum shelf life
f = admin.post("/api/v1/customers", {
    "code": f"SH{tag}", "name": f"Shelf {tag}", "customer_type": "BUSINESS",
    "currency_code": "INR", "minimum_shelf_life_days": 90})
c.eq(f[0], 201, "(f) a customer with a minimum shelf life of 90 days")
if f[0] == 201:
    c.eq(data(f[1]).get("minimum_shelf_life_days"), 90, "(f) the figure reads back")

# (g) a seller without BATCH_CREATE
g = sales.post("/api/v1/batch-serial/batches", {
    "product_id": med["id"], "batch_number": f"G{tag}"})
c.eq(g[0], 403, "(g) a user without BATCH_CREATE is refused")
s, body = admin.get(f"/api/v1/batch-serial/batches?search=G{tag}&page_size=10")
c.eq([r for r in data(body) if r["batch_number"] == f"G{tag}"], [], "(g) no batch is written")
c.done()
