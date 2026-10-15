"""TC-LOT-019: changing a price on the lot page works the margin back (HTTP steps 2-4; no screen).

Drives a lot of its own (cost 80, PTR 100, PTS 90), not TEST03-M1, so the shared lots keep
their prices. BATCH_PTR_PTS is a business feature, not a permission; the user without the
update permission is the fixture's Viewer. A holder of BATCH_UPDATE only is not driven.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_019")
api = lot_admin(); c = Ctx(api); p = margin_product(api)
g = c.receive([{"product": p, "qty": 10, "rate": 80}])
lot = lot_of_receipt(api, p, receipt_line(api, g))
c0.eq((D(lot["ptr"]), D(lot["pts"])), (D(100), D(90)), "(1) the lot shows PTR 100 and PTS 90")
path = f"/api/v1/batch-serial/batches/{lot['id']}"
s, b = api.put(path, {"ptr": "108.00"})
c0.eq(s, 200, f"(2) PTR 108 saved ({message(b)})")
now = must(api.get(path), "lot read")
c0.eq((D(now["ptr"]), D(now["retail_margin_percent"]), D(now["pts"]), D(now["wholesale_margin_percent"])),
      (D(108), D(35), D(90), D("12.5")), "(2) retail margin 35, wholesale unchanged")
s, b = api.put(path, {"ptr": "85.00"})
c0.ok(s == 422 and "90" in message(b), "(3) PTR 85 is refused naming the wholesale price 90.00", (s, message(b)))
s, b = client("viewer", "lots").put(path, {"ptr": "108.00"})
c0.eq(s, 403, "(4) the Viewer's save is refused")
c0.done()
