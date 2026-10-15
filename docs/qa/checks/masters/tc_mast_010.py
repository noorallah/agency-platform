"""TC-MAST-010: mapping another software's export on import (preview suggestion, required Code unmapped, a mapping applied, a saved mapping)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_010")
a = api()
t = tag()
rows = [["Account No", "Ledger Name", "GSTIN/UIN", "Remarks"],
        [f"TL{t}1", f"Tally ledger one {t}", "", "r1"], [f"TL{t}2", f"Tally ledger two {t}", "", "r2"]]
f = csv_bytes(rows)
pv = must(a.upload(f"{IMP}/customers/preview", "tally.csv", f), "preview")
c.eq(pv["file_headings"], rows[0], "the file's own headings are listed")
c.eq((pv["suggested"]["Ledger Name"], pv["suggested"]["GSTIN/UIN"], pv["suggested"]["Account No"]), ("Name", "GSTIN", None), "Ledger Name already maps to Name, GSTIN/UIN to GSTIN, Account No to nothing")
c.eq(len(pv["sample_rows"]), 2, "sample rows come with it")
r = a.upload(f"{CU}/import-file", "tally.csv", f, {"existing": "refuse", "apply": "false"})
issues = data(r[1])["issues"] if r[0] == 200 else []
c.ok(any("no Code column" in i["message"] for i in issues), "with Code unmapped the check says the heading row has no Code column", f"{r[0]} {issues[:2] if issues else message(r[1])}")
mp = json.dumps({"Account No": "Code", "Ledger Name": "Name", "GSTIN/UIN": "GSTIN", "Remarks": None})
ck = a.upload(f"{CU}/import-file", "tally.csv", f, {"existing": "refuse", "apply": "false", "mapping": mp})
c.eq((ck[0], data(ck[1])["issues"] if ck[0] == 200 else message(ck[1])), (200, []), "mapped, the check is clean")
c.eq(rows_of(a.get(f"{CU}?search=TL{t}")), [], "a check writes nothing")
ap = a.upload(f"{CU}/import-file", "tally.csv", f, {"existing": "refuse", "apply": "true", "mapping": mp})
c.eq((ap[0], data(ap[1])["imported"] if ap[0] == 200 else message(ap[1])), (200, True), "the import runs")
c.eq(sorted(r["code"] for r in rows_of(a.get(f"{CU}?search=TL{t}"))), [f"TL{t}1", f"TL{t}2"], "both customers exist")
name = f"Tally ledgers {t}"
sv = a.post(f"{IMP}/customers/mappings", {"name": name, "mapping": json.loads(mp)})
c.ok(sv[0] in (200, 201), f"mapping saved ({message(sv[1])})")
got = [m for m in rows_of(a.get(f"{IMP}/customers/mappings")) if m["name"] == name]
c.eq([m["mapping"] for m in got], [json.loads(mp)], "the saved mapping reads back the same")
if got:
    a.delete(f"{IMP}/mappings/{got[0]['id']}")
c.done()
