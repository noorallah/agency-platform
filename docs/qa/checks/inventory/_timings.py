"""Time three read routes on the inventory fixture firm (not a check; prints milliseconds)."""
import time

from _inv import *

w = World()
routes = [
    ("stock-statement", f"{INV}/reports/stock-statement?from_date=2026-04-01&to_date={w.today}&page_size=100"),
    ("stock-valuation", f"{INV}/reports/stock-valuation?page_size=100"),
    ("invoice analysis", f"/api/v1/sales-invoices/reports/analysis/invoices?from_date=2026-04-01&to_date={w.today}"),
]
for name, path in routes:
    ms = []
    for _ in range(3):
        t = time.perf_counter()
        st, b = w.admin.get(path)
        ms.append(round((time.perf_counter() - t) * 1000))
    rows = len(data(b)) if isinstance(data(b), list) else "-"
    print(f"{name}: status {st} rows {rows} ms {ms}")
