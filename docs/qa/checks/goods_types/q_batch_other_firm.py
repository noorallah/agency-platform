"""Probe: a batch, a serial or a batch move naming a product of another firm."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, suffix
from _lib import must, product

c = Check("q_batch_other_firm")
tag = suffix()
admin, other = client("admin"), client("test02_admin")
foreign = must(product(other, f"FOR-{tag}", track_batch=True, track_serial=True), "TEST02 product")
mine = must(product(admin, f"OWN-{tag}", track_batch=True), "TEST01 product")
B = "/api/v1/batch-serial"
c.eq(admin.post(f"{B}/batches", {"product_id": foreign["id"], "batch_number": f"F{tag}"})[0], 404,
     "a batch for a product of another firm is refused 404")
c.eq(admin.post(f"{B}/serials", {"product_id": foreign["id"], "serial_number": f"F{tag}"})[0], 404,
     "a serial for a product of another firm is refused 404")
made = must(admin.post(f"{B}/batches", {"product_id": mine["id"], "batch_number": f"O{tag}"}), "own batch")
moved = admin.put(f"{B}/batches/{made['id']}", {"product_id": foreign["id"]})
c.ok(moved[0] in (404, 422), "moving a batch onto another firm's product is refused", (moved[0], message(moved[1])))
plain = must(product(admin, f"PLN-{tag}"), "untracked product")
moved = admin.put(f"{B}/batches/{made['id']}", {"product_id": plain["id"]})
c.ok(moved[0] in (404, 422), "moving a batch onto a product that does not track batches is refused",
     (moved[0], message(moved[1])))
c.done()
