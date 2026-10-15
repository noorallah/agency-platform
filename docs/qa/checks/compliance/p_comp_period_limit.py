"""Probe: GSTR-1 and GSTR-3B cover at most three calendar months; a longer period is refused naming the limit (firm one, read only)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("p_comp_period_limit")
a = api()
for r in ("gstr1", "gstr3b"):
    c.eq(a.get(f"{GST}/{r}?from_date=2026-08-01&to_date=2026-10-31")[0], 200, f"{r}: exactly three calendar months is allowed")
    c.refused(a.get(f"{GST}/{r}?from_date=2026-07-01&to_date=2026-10-31"), 422, "3 calendar months", f"{r}: four months is refused naming the limit")
    c.refused(a.get(f"{GST}/{r}?from_date=2025-04-01&to_date=2026-03-31"), 422, "3 calendar months", f"{r}: a whole year is refused")
    c.ok(a.get(f"{GST}/{r}?from_date=2026-10-31&to_date=2026-10-01")[0] in (400, 422), f"{r}: to before from is refused")
    c.eq(a.get(f"{GST}/{r}?from_date=2026-08-15&to_date=2026-10-31")[0], 200, f"{r}: a span inside three months is allowed")
    c.ok(a.get(f"{GST}/{r}?from_date=2026-08-01")[0] == 422, f"{r}: a missing date is refused")
c.done()
