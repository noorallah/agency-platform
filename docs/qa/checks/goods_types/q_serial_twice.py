"""Probe: the same serial number twice, and a serial on a deleted product."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, suffix
from _lib import must, product

c = Check("q_serial_twice")
tag = suffix()
admin = client("admin")
p1 = must(product(admin, f"SA-{tag}", track_serial=True), "p1")
p2 = must(product(admin, f"SB-{tag}", track_serial=True), "p2")
S = "/api/v1/batch-serial/serials"
c.eq(admin.post(S, {"product_id": p1["id"], "serial_number": f"X{tag}"})[0], 201, "first serial")
c.refused(admin.post(S, {"product_id": p1["id"], "serial_number": f"X{tag}"}), 409, "already",
          "the same serial twice on one product")
c.refused(admin.post(S, {"product_id": p2["id"], "serial_number": f"X{tag}"}), 409, "already",
          "the same serial on another product of the firm")
c.refused(admin.post(S, {"product_id": p1["id"], "serial_number": f"  X{tag}  "}), 409, "already",
          "the same serial with spaces round it")
c.done()
