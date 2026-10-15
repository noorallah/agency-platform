"""D-FIN-36 (not a defect): POST /report-layouts saves by name, 200 both times.

The route is an upsert: the same name again replaces the layout, so it answers
200 for a save as a PUT would, and the second save keeps the first one's id.
"""

from _rep import Check, admin, data, message
from common import suffix

c = Check("tc_rep_005")
api = admin()
body = {"report_code": "sales_analysis", "name": f"QA-LAYOUT-{suffix()}", "settings": {}}
status, ans = api.post("/api/v1/report-layouts", body)
c.eq(status, 200, f"first save: {message(ans)[:200]}")
first = data(ans) or {}
status, ans = api.post(
    "/api/v1/report-layouts", {**body, "settings": {"rows": "product"}}
)
c.eq(status, 200, f"second save: {message(ans)[:200]}")
second = data(ans) or {}
c.eq(second.get("id"), first.get("id"), "the same name replaces, never duplicates")
c.eq((second.get("settings") or {}).get("rows"), "product", "the new settings kept")
if first.get("id"):
    status, _ = api.delete(f"/api/v1/report-layouts/{first['id']}")
    c.eq(status, 204, "delete the layout")
c.done()
