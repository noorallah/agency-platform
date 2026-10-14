"""Probe: the whole by-lot firm's stock valuation equals the Inventory account, and the lots add up to it."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("p_books_agree")
api = lot_admin()
rows = rows_of(api.get(f"{INV}/reports/stock-valuation?page_size=100&include_zero=true"))
total = next(D(r["value"]) for r in rows if r["row_type"] == "TOTAL")
books = next(D(r["value"]) for r in rows if r["row_type"] == "BOOKS")
diff = next(D(r["value"]) for r in rows if r["row_type"] == "DIFFERENCE")
c0.eq((diff, total), (D(0), books), "valuation total equals the Inventory account")
lots = []
page = 1
while True:
    s, b = api.get(f"{INV}/reports/stock-valuation/lots?page={page}&page_size=100")
    got = data(b) if s == 200 else []
    lots += got
    if not got or page >= (b.get("pagination") or {}).get("total_pages", 1):
        break
    page += 1
owed = sum((D(r["value"]) for r in rows if r["row_type"] == "OWED"), Decimal(0))
c0.eq(sum((D(r["value"]) for r in lots), Decimal(0)) + owed, total, "the lot rows (plus units owed) add up to the grand total")
c0.done()
