"""Probe: opening stock by file: template, check with one bad row writes nothing, apply is all-or-nothing, rules per tracking."""
import csv
import io

from _inv import *
from _flow import *

c = Check("p_opening_import")
w = World()
a = w.warehouse()
IMP = f"{INV}/opening-stock/import-file"
st, raw = w.admin.raw(f"{INV}/opening-stock/import-template?format=csv")
c.eq(st, 200, "template downloads")
header = raw.decode().splitlines()[0].split(",")
c.eq(header, ["ProductCode", "Warehouse", "Quantity", "UnitCost", "Batch", "Expiry", "Unit", "Remarks"], "template columns")
st, raw2 = w.admin.raw(f"{INV}/opening-stock/import-template?format=xlsx")
c.ok(st == 200 and raw2[:2] == b"PK", "the xlsx template is a workbook", (st, raw2[:4]))
p1, p2, p3 = w.product(), w.product(), w.product()
pb, ps = w.product(goods_type="MEDICINE"), w.product(goods_type="ELECTRONICS")


def file(rows: list[list[str]]) -> bytes:
    """A CSV in the template layout."""
    out = io.StringIO()
    wr = csv.writer(out, lineterminator="\n")
    wr.writerow(header)
    wr.writerows(rows)
    return out.getvalue().encode()


def run(rows: list[list[str]], apply: bool) -> tuple[int, dict]:
    """Upload a file."""
    st, b = w.admin.upload(IMP, "os.csv", file(rows), fields={"apply": "true" if apply else "false", "posting_date": w.today})
    return st, (data(b) if isinstance(b, dict) and b.get("data") is not None else {"raw": b})


def issues(report: dict) -> str:
    """All issue texts."""
    return " | ".join(i.get("text", "") for i in report.get("issues", []))


def docs() -> int:
    """Opening-stock documents of the firm."""
    st, b = w.admin.get(f"{INV}/opening-stock?page=1&page_size=1")
    return int(b["pagination"]["total_records"])


good = [[p1["code"], a["code"], "10", "5.50", "", "", "", ""], [p2["code"], a["code"], "4", "7", "", "", "", ""]]
bad = [[p3["code"], a["code"], "3", "2", "", "", "", ""], ["NOSUCH" + w.tag, a["code"], "1", "1", "", "", "", ""]]
before = docs()
st, r = run(good + bad, apply=False)
c.eq(st, 200, "check answers 200")
c.ok(bool(r.get("issues")) and "NOSUCH" in issues(r), "the check names the unknown product by row", issues(r))
c.eq(docs(), before, "a check writes nothing")
st, r = run(good + bad, apply=True)
c.eq(r.get("imported"), False, "apply with one bad row imports nothing: " + issues(r)[:120])
c.eq((w.qty(p1["id"]), w.qty(p2["id"]), w.qty(p3["id"]), docs()), (D(0), D(0), D(0), before), "no stock, no document written by the refused apply")
st, r = run(good, apply=True)
c.eq(r.get("imported"), True, "a clean file applies: " + issues(r)[:120])
c.eq((w.qty(p1["id"]), w.qty(p2["id"])), (D(10), D(4)), "stock arrives")
val = {v["product_code"]: v for v in w.valuation() if v["row_type"] == "ITEM"}
c.eq((D(val[p1["code"]]["value"]), D(val[p2["code"]]["value"])), (D(55), D(28)), "valued at the typed cost (55, 28)")
st, r = run(good, apply=True)
c.eq(r.get("imported"), False, "the same file again is refused: " + issues(r)[:140])
c.eq(w.qty(p1["id"]), D(10), "and doubles nothing")
# rules by tracking
cases = [
    ("batch-tracked product without a batch", [pb["code"], a["code"], "3", "5", "", "", "", ""]),
    ("plain product with a batch", [p3["code"], a["code"], "3", "5", "B1", "", "", ""]),
    ("serial product", [ps["code"], a["code"], "3", "5", "", "", "", ""]),
    ("zero quantity", [p3["code"], a["code"], "0", "5", "", "", "", ""]),
    ("negative quantity", [p3["code"], a["code"], "-2", "5", "", "", "", ""]),
    ("text quantity", [p3["code"], a["code"], "ten", "5", "", "", "", ""]),
    ("negative cost", [p3["code"], a["code"], "2", "-5", "", "", "", ""]),
    ("unknown warehouse", [p3["code"], "NOWH" + w.tag, "2", "5", "", "", "", ""]),
    ("the same stock twice in the file", None),
]
for label, row in cases:
    rows = [row] if row else [[p3["code"], a["code"], "2", "5", "", "", "", ""]] * 2
    st, r = run(rows, apply=True)
    c.ok(st == 200 and r.get("imported") is False and r.get("issues"), f"{label} is refused by the import", (st, str(r)[:140]))
c.eq((w.qty(p3["id"]), w.qty(pb["id"]), w.qty(ps["id"])), (D(0), D(0), D(0)), "none of the refused rows stocked anything")
# a file with no rows, a binary file
st, r = run([], apply=True)
c.ok(st in (200, 422) and r.get("imported") is not True, "an empty file imports nothing", (st, str(r)[:100]))
st, b = w.admin.upload(IMP, "os.csv", b"\x00\x01\x02garbage", fields={"apply": "true"})
c.ok(st in (200, 422), "a garbage file is not a 500", (st, str(b)[:100]))
c.done()
