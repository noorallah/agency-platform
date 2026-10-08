"""Probe: a batch that expires before it was made."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, message, suffix
from _lib import must, product

c = Check("q_expiry_before_manufacturing")
tag = suffix()
admin = client("admin")
med = must(product(admin, f"QEX-{tag}", track_batch=True, track_expiry=True,
                   track_manufacturing_date=True), "product")
r = admin.post("/api/v1/batch-serial/batches", {
    "product_id": med["id"], "batch_number": f"E{tag}",
    "manufacturing_date": "2027-06-01", "expiry_date": "2026-06-01"})
c.ok(r[0] in (400, 422), "an expiry date before the manufacturing date is refused", (r[0], message(r[1])))
c.done()
