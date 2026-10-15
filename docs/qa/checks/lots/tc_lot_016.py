"""TC-LOT-016: a receipt line works its prices from the margins (HTTP steps 1-3; no screen step)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_016")
api = lot_admin(); c = Ctx(api); p = margin_product(api)
g = c.receive([{"product": p, "qty": 10, "rate": 80}])
ln = receipt_line(api, g); lot = lot_of_receipt(api, p, ln)
for what, row in (("line", ln), ("lot", lot)):
    c0.eq((D(row["ptr"]), D(row["pts"]), D(row["retail_margin_percent"]), D(row["wholesale_margin_percent"])),
          (D("100.00"), D("90.00"), D(25), D("12.5")), f"(1) the {what} carries PTR 100, PTS 90, margins 25 and 12.5")
g = c.receive([{"product": p, "qty": 10, "rate": 80, "mrp": 130, "retail_margin_percent": 40}])
ln = receipt_line(api, g); lot = lot_of_receipt(api, p, ln)
for what, row in (("line", ln), ("lot", lot)):
    c0.eq((D(row["ptr"]), D(row["pts"]), D(row["retail_margin_percent"]), D(row["wholesale_margin_percent"])),
          (D("112.00"), D("90.00"), D(40), D("12.5")), f"(2) the {what} carries PTR 112, PTS 90, margins 40 and 12.5")
c0.done()
