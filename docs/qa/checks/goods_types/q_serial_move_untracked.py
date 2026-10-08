"""Probe: a serial number moved onto a product that tracks no serials."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, message, suffix, data
from _lib import must, one_in_stock, product

c = Check("q_serial_move_untracked")
tag = suffix()
admin = client("admin")
tracked = must(product(admin, f"MT-{tag}", track_serial=True), "tracked")
plain = must(product(admin, f"MP-{tag}"), "plain")
S = "/api/v1/batch-serial/serials"
# a number is added only for a unit the firm holds (D-STK-50)
one_in_stock(admin, tracked["id"], tag)
made = must(admin.post(S, {"product_id": tracked["id"], "serial_number": f"M{tag}"}), "serial")
r = admin.put(f"{S}/{made['id']}", {"product_id": plain["id"]})
c.ok(r[0] in (404, 422), "moving a serial onto a product not tracked by serial is refused", (r[0], message(r[1])))
c.done()
