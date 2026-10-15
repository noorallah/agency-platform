"""TC-COMP-007: TCS - nothing is collected from 1 April 2025 (firm one, read only)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_007")
a = api()
f = firm()
s = data(a.get(f"{TCS}/settings")[1])
for key in ("section_code", "is_enabled", "threshold_amount", "rate_percent", "rate_without_pan_percent", "preceding_year_turnover"):
    c.ok(key in s, f"settings carry {key}", list(s))
c.eq((D(s["rate_percent"]), D(s["rate_without_pan_percent"])), (D("0.1"), D("1")), "rates 0.1 and 1.0 without a PAN")
c.eq(a.get(f"{TCS}/collections")[0], 200, "the register opens")
c.eq(rows_of(a.get(f"{TCS}/collections?page_size=50")), [], "the register is empty: no receipt of this firm was charged")
cust = rows_of(a.get(f"{CU}?search=B2B&page_size=5"))[0]
p = data(a.get(f"{TCS}/preview?customer_id={cust['id']}&amount=100000000&on={today().isoformat()}")[1])
c.eq((p["applicable"], D(p["tcs_amount"])), (False, D(0)), "a huge receipt today attracts no TCS")
c.ok("2025" in p["reason"], "and says why (omitted 1 April 2025)", p["reason"])
c.eq(rows_of(a.get(f"/api/v1/finance/journal-entries?search=TCS-RC&page_size=50")), [], "no TCS-RC journal entry")
c.eq(a.get(f"{TCS}/reports/charged-versus-due")[0], 200, "the charged-versus-due report opens")
c.done()
