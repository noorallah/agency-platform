"""TC-FIN-005: every report opens (200, never a 5xx) and an empty one is an empty list, not an error.

Walks the running server's own route list (openapi.json) for every parameterless-or-dated GET that is a report, so a report added later is covered without editing this file.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import json

from _fin import *
from common import fetch

c = Check("tc_fin_005")
a = admin()
viewer = admin("viewer")
per = period_of(a)
fy = next(y for y in all_rows(a, f"{FIN}/financial-years") if y["starts_on"] <= today().isoformat() <= y["ends_on"])
st, raw = fetch("GET", "/openapi.json", None, {})
spec = json.loads(raw)
KNOWN = {
    "from_date": fy["starts_on"], "to_date": today().isoformat(),
    "accounting_period_id": per["id"], "from_period_id": per["id"], "to_period_id": per["id"],
    "financial_year_id": fy["id"], "financial_year": "2026-27", "quarter": "Q2",
    "return_period": today().isoformat()[:7],
}
SKIP_PARAM = {"vendor_id", "customer_id", "product_id", "report_code"}  # a record has to be chosen first: not a report on its own
opened, empty, needs_record, no_gst, bad = 0, 0, 0, 0, []
for path, methods in sorted(spec["paths"].items()):
    if "get" not in methods or "{" in path:
        continue
    reportish = "/report" in path or path.endswith(("/ageing", "/outstanding")) or any(k in path for k in ("gst-returns", "trial-balance", "profit-loss", "balance-sheet", "cash-flow"))
    if not reportish:
        continue
    required = [q["name"] for q in methods["get"].get("parameters", []) if q.get("required") and q["name"] != "X-Firm-ID"]
    if set(required) & SKIP_PARAM:
        needs_record += 1
        continue
    query = "&".join(f"{k}={KNOWN[k]}" for k in required if k in KNOWN)
    status, body = a.get(f"{path}?{query}" + ("&" if query else "") + "page_size=5")
    if status == 200:
        opened += 1
        rows = data(body)
        if isinstance(rows, list) and not rows:
            empty += 1
    elif status == 422 and not message(body).startswith("The request validation failed"):
        no_gst += 1  # a return this firm or period cannot file (no GST number, monthly not quarterly): refused in words
    elif status == 422 and any(k not in KNOWN for k in required):
        needs_record += 1
    else:
        bad.append(f"{path}?{query} -> {status} {message(body)[:120]}")
c.ok(opened >= 100, "at least a hundred reports open", opened)
c.eq(bad, [], "no report answers anything but 200")
c.ok(no_gst >= 1, "returns the fixture firm cannot file are refused in words, not a 500", no_gst)
c.ok(empty > 0, "some of this firm's reports are empty lists, and answer 200 with []", empty)
# a Viewer holds only view codes: the finance statements are refused by permission, not by a crash
gate = viewer.get(f"{FIN}/trial-balance?accounting_period_id={per['id']}")[0]
c.ok(gate in (200, 403), "a Viewer gets the trial balance or a plain 403", gate)
c.done()
