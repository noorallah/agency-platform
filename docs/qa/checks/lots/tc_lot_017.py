"""TC-LOT-017: a typed price wins and its margin is worked back (HTTP steps 1-3; no screen step)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_017")
api = lot_admin(); c = Ctx(api); p = margin_product(api)
for step, extra in (("(1) blank margin", {}), ("(2) margin 40 typed too", {"retail_margin_percent": 40})):
    g = c.receive([{"product": p, "qty": 10, "rate": 80, "ptr": 104, **extra}])
    ln = receipt_line(api, g); lot = lot_of_receipt(api, p, ln)
    for what, row in (("line", ln), ("lot", lot)):
        c0.eq((D(row["ptr"]), D(row["retail_margin_percent"]), D(row["pts"])),
              (D("104.00"), D("30"), D("90.00")), f"{step}: the {what} keeps PTR 104, margin 30, PTS 90")
c0.done()
