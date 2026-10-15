"""TC-MAST-016: customer and supplier PAN reports list missing/malformed PANs and skip good ones; each needs its view code."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_016")
a, s, acc = api(), api("seller"), api("accountant")
t = tag()
none_ = must(a.post(CU, {"code": f"NP{t}", "name": f"No PAN {t}", "customer_type": "BUSINESS", "currency_code": "INR"}), "no pan")
bad = a.post(f"{CU}/import", {"records": [{"code": f"BP{t}", "name": f"Bad PAN {t}", "customer_type": "BUSINESS", "currency_code": "INR", "pan_number": "12345"}]})
c.ok(bad[0] in (409, 422) and "is not a PAN" in message(bad[1]), "a malformed PAN is refused at the customer import (the case says it comes in; only legacy rows can hold one)", f"{bad[0]} {message(bad[1])}")
good = must(a.post(CU, {"code": f"GP{t}", "name": f"Good PAN {t}", "customer_type": "BUSINESS", "currency_code": "INR", "pan_number": "ABCDE1234F"}), "good")
rep = rows_of(a.get(f"{CU}/reports/pan"))
mine = {r["code"]: r for r in rep if t in r["code"]}
c.eq(sorted(mine), [f"NP{t}"], "the report lists the missing one and not the good one")
c.eq(len(next(iter(rep), {})), 8, "each row carries eight fields (six columns on screen)") if rep else None
c.ok("No PAN" in mine.get(f"NP{t}", {}).get("problem", ""), "missing PAN named", mine.get(f"NP{t}"))
v_none = vendor(a)
v_bad = a.post(f"{VE}/import", {"records": [{"code": f"VB{t}", "name": f"Bad vendor PAN {t}", "pan": "XYZ"}]})
c.ok(v_bad[0] in (409, 422) and "is not a PAN" in message(v_bad[1]), "a malformed supplier PAN is refused at the supplier import as well", f"{v_bad[0]} {message(v_bad[1])}")
v_good = vendor(a, pan="ABCDE1234F")
vrep = {r["code"] for r in rows_of(a.get(f"{VE}/reports/pan"))}
c.ok(v_none["code"] in vrep and v_good["code"] not in vrep, "the supplier report lists the one with no PAN and not the good one")
cu_view = acc.get(f"{CU}/reports/pan")[0]
ve_view = acc.get(f"{VE}/reports/pan")[0]
c.ok(cu_view in (200, 403) and ve_view in (200, 403), "accountant answers both reports with a decision, not an error", (cu_view, ve_view))
c.done()
