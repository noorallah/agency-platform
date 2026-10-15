"""TC-FIN-016: checks before closing a month (WARN lists, BLOCK refuses), the firm's ageing bands on both ageing reports, and the due lists."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from datetime import timedelta

from _fin import *

c = Check("tc_fin_016")
a = admin()
viewer = admin("viewer")
SI = "/api/v1/sales-invoices"
PI = "/api/v1/purchase-invoices"
held_close = data(a.get(f"{FIN}/period-close-settings")[1])["close_check"]
held_bands = data(a.get(f"{FIN}/ageing-settings")[1])["bucket_days"]

# ---- close checks, on a month older than anything else so it can be closed
oldest = min(int(p["starts_on"][:4]) for p in all_rows(a, f"{FIN}/accounting-periods"))
y = oldest - 1
fy = must(a.post(f"{FIN}/financial-years", {"code": f"FY{y}", "name": f"Check year {y}", "starts_on": f"{y}-04-01", "ends_on": f"{y + 1}-03-31"}), "year")
p1 = must(a.post(f"{FIN}/accounting-periods", {"financial_year_id": fy["id"], "period_number": 1, "code": "P01", "name": "April", "starts_on": f"{y}-04-01", "ends_on": f"{y}-04-30"}), "period")
draft = must(a.post(JE, draft_body(a, [("5000", "4.00", "0"), ("1000", "0", "4.00")], day=f"{y}-04-09", period=p1)), "draft")
CHECKS = f"{FIN}/accounting-periods/{p1['id']}/close-checks"
try:
    c.eq(a.put(f"{FIN}/period-close-settings", {"close_check": "WARN"})[0], 200, "the firm is set to WARN")
    got = must(a.get(CHECKS), "checks")
    items = {i["code"]: i for i in got["items"]}
    c.ok("DRAFT_JOURNALS" in items, "the checklist lists the draft journal dated in the month", sorted(items))
    c.eq((items["DRAFT_JOURNALS"]["count"], draft["reference_number"] in items["DRAFT_JOURNALS"]["examples"]), (1, True), "count 1 and it names the draft")
    c.eq(got["refuses"], False, "under WARN the list refuses nothing")
    c.eq(a.put(f"{FIN}/period-close-settings", {"close_check": "BLOCK"})[0], 200, "the firm changes the setting to BLOCK")
    got = must(a.get(CHECKS), "checks")
    c.eq((got["close_check"], got["refuses"]), ("BLOCK", True), "under BLOCK the same list now refuses")
    st, ans = a.call("PATCH", f"{FIN}/accounting-periods/{p1['id']}", {"status": "CLOSED"})
    c.ok(st in (409, 422), "and closing the month is refused", (st, message(ans)))
    c.ok(draft["reference_number"] in message(ans) or "draft" in message(ans).lower(), "naming the draft", message(ans))
    c.eq(a.put(f"{FIN}/period-close-settings", {"close_check": "WARN"})[0], 200, "back to WARN")
    c.eq(a.call("PATCH", f"{FIN}/accounting-periods/{p1['id']}", {"status": "CLOSED"})[0], 200, "under WARN the month closes with the draft in it")
    c.eq(a.put(f"{FIN}/period-close-settings", {"close_check": "SOMETIMES"})[0], 422, "a setting other than WARN / BLOCK is refused")
    c.eq(viewer.put(f"{FIN}/period-close-settings", {"close_check": "BLOCK"})[0], 403, "a Viewer cannot change the setting")
finally:
    a.put(f"{FIN}/period-close-settings", {"close_check": held_close})

# ---- ageing bands
sc = Scene(a)
cust = sc.customer()
old = (today() - timedelta(days=50)).isoformat()
body = {"customer_id": cust["id"], "branch_id": sc.branch["id"], "invoice_date": old, "due_date": old, "lines": [{"line_number": 1, "product_id": sc.product["id"], "current_invoice_quantity": "1", "warehouse_id": sc.warehouse["id"]}]}
bs = buy.Scene(a)
o = bs.order(qty="3")
rc = bs.receive(o, "3")
vb = bs.bill_body(rc)
d20 = (today() - timedelta(days=20)).isoformat()
vb.update({"invoice_date": d20, "supplier_invoice_date": d20, "due_date": d20})
try:
    with counter(a):
        st, made = a.post(SI, body)
        c.eq(st, 201, "an invoice due 50 days ago is typed")
        c.eq(a.post(f"{SI}/{data(made)['id']}/approve", {})[0], 200, "and approved")
    st, made = a.post(PI, vb)
    c.eq(st, 201, "a supplier bill due 20 days ago is typed")
    c.eq(a.post(f"{PI}/{data(made)['id']}/approve", {})[0], 200, "and approved")
    st, ans = a.put(f"{FIN}/ageing-settings", {"bucket_days": [15, 45, 90]})
    c.eq(st, 200, "the bands are set to 15 / 45 / 90")
    c.eq([b["label"] for b in data(ans)["bands"]], ["0-14", "15-44", "45-89", "90+"], "they read 0-14, 15-44, 45-89, 90+")
    cage = data(a.get(f"/api/v1/customers/ageing?customer_id={cust['id']}")[1])[0]
    c.eq([(b["from_days"], b["to_days"], D(b["amount"])) for b in cage["buckets"]], [(0, 14, D("0")), (15, 44, D("0")), (45, 89, D("118.00")), (90, None, D("0"))], "customer ageing puts the 50-day bill (118.00) in 45-89")
    vage = [v for v in all_rows(a, f"{PI}/reports/vendor-ageing") if v["vendor_id"] == bs.vendor["id"]][0]
    c.eq([b["label"] for b in vage["buckets"]], ["0-14", "15-44", "45-89", "90+"], "vendor ageing carries a buckets list with the same bands")
    c.eq([D(b["amount"]) for b in vage["buckets"]], [D("0"), D("354.00"), D("0"), D("0")], "the 20-day supplier bill (354.00) sits in 15-44")
    c.eq(D(vage["total_outstanding"]), D("354.00"), "vendor total is the bill")
    c.eq(a.put(f"{FIN}/ageing-settings", {"bucket_days": [30, 60, 90]})[0], 200, "bands put back")
    c.eq([(b["from_days"], D(b["amount"])) for b in data(a.get(f"/api/v1/customers/ageing?customer_id={cust['id']}")[1])[0]["buckets"]][1], (30, D("118.00")), "and the same bill reads 30-59 again")
finally:
    a.put(f"{FIN}/ageing-settings", {"bucket_days": held_bands})

# ---- due lists
due_bs = buy.Scene(a)
o2 = due_bs.order(qty="2")
rc2 = due_bs.receive(o2, "2")
b2 = due_bs.bill_body(rc2)
b2["due_date"] = (today() + timedelta(days=5)).isoformat()
st, made = a.post(PI, b2)
a.post(f"{PI}/{data(made)['id']}/approve", {})
supplier_bill = data(a.get(f"{PI}/{data(made)['id']}")[1])["invoice_number"]
today_list = {r["invoice_number"] for r in all_rows(a, f"{PI}/reports/due?days=0")}
week_list = {r["invoice_number"] for r in all_rows(a, f"{PI}/reports/due?days=7")}
c.ok(supplier_bill not in today_list, "a supplier bill due in 5 days is not on today's list")
c.ok(supplier_bill in week_list, "but is on the next-7-days list")
sale = sc.customer()
with counter(a):
    sb = sc.bill(sale, "1")
sales_today = {r["invoice_number"] for r in all_rows(a, f"{SI}/reports/due?days=0")}
c.ok(sb["invoice_number"] in sales_today, "a sales invoice due today is on the due-today list")
c.done()
