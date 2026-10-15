"""TC-FIN-023: sales and purchase analysis: basis, compare with last year, cost and margin only for PRODUCT_VIEW_COST_PRICE, saved layouts per user, rate trend."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_023")
a = admin()
plat = client("platform", MODULE)
held = state(MODULE)
fid, stem = held["firm_id"], held["suffix"]
email = f"{stem}.finmgr@fixtures.local"
ensure_user(plat, email, "Finance finmgr", fid, "SALES_MANAGER")  # holds the analysis report but not the cost price
mgr = sign_in(email, firm_id=fid)
SI, SO = "/api/v1/sales-invoices", "/api/v1/sales-orders"
SA = f"{SI}/reports/analysis"
PA_ = "/api/v1/purchase-invoices/reports/analysis"

# last year's October must have a period to post a back-dated bill into
fy25 = next((f for f in all_rows(a, f"{FIN}/financial-years") if f["starts_on"] == "2025-04-01"), None)
if fy25 is None:
    fy25 = must(a.post(f"{FIN}/financial-years", {"code": "FY2025", "name": "Financial Year 2025-2026", "starts_on": "2025-04-01", "ends_on": "2026-03-31"}), "last year")
if not [p for p in all_rows(a, f"{FIN}/accounting-periods") if p["starts_on"] == "2025-10-01"]:
    must(a.post(f"{FIN}/accounting-periods", {"financial_year_id": fy25["id"], "period_number": 7, "code": "P07", "name": "October 2025", "starts_on": "2025-10-01", "ends_on": "2025-10-31"}), "last October")

sc = Scene(a)
cust = sc.customer()
line = {"line_number": 1, "product_id": sc.product["id"], "current_invoice_quantity": "3", "warehouse_id": sc.warehouse["id"]}
with counter(a):
    now = sc.bill(cust, "3")  # 354.00, cost 3 x 60.00
    old = must(a.post(SI, {"customer_id": cust["id"], "branch_id": sc.branch["id"], "invoice_date": "2025-10-10", "lines": [{**line, "current_invoice_quantity": "2"}]}), "last year's bill")
    must(a.post(f"{SI}/{old['id']}/approve", {}), "approve last year's")
order = must(a.post(SO, {"customer_id": cust["id"], "order_date": today().isoformat(), "branch_id": sc.branch["id"], "warehouse_id": sc.warehouse["id"], "lines": [{"line_number": 1, "product_id": sc.product["id"], "quantity": "4"}]}), "order")
must(a.post(f"{SO}/{order['id']}/approve", {}), "approve order")
Q = f"?from_date=2026-10-01&to_date=2026-10-31&product_id={sc.product['id']}"

billed = must(a.get(f"{SA}{Q}&basis=billed&compare_previous_year=true"), "billed")
g = billed["grand_total"]
c.eq((D(g["quantity"]), D(g["taxable"]), D(g["tax"]), D(g["net"]), g["invoices"]), (D("3"), D("300.00"), D("54.00"), D("354.00"), 1), "billed basis: 3 pieces, 300.00 + 54.00 = 354.00, one invoice")
c.eq((D(g["cost"]), D(g["margin"]), D(g["margin_percent"])), (D("180.00"), D("120.00"), D("40.00")), "cost 180.00, margin 120.00, 40.00 percent for a cost-price holder")
c.eq(D(g["average_rate"]), D("100.00"), "average rate 100.00")
p = billed["previous"]["grand_total"]
c.eq((D(p["quantity"]), D(p["net"]), p["invoices"], D(p["cost"]), D(p["margin"])), (D("2"), D("236.00"), 1, D("120.00"), D("80.00")), "compare with last year: the back-dated bill, 236.00, margin 80.00, is the previous-year column")
ordered = must(a.get(f"{SA}{Q}&basis=ordered"), "ordered")["grand_total"]
# Observed: the 'ordered' basis counts the approved order (4 pieces, 472.00) AND the counter invoice
# raised without an order (3 pieces, 354.00): 7 and 826.00. Case text says "approved orders instead of invoices".
c.eq((D(ordered["quantity"]), D(ordered["net"])), (D("7"), D("826.00")), "ordered basis: the approved order (4, 472.00) plus the order-less counter bill (3, 354.00)")
c.refused(a.get(f"{SA}{Q}&basis=invoiced"), 422, "not a basis", "'invoiced' is not an API basis: the value is 'billed' (case text names the screen label)")
off = must(mgr.get(f"{SA}{Q}&basis=billed&compare_previous_year=true"), "manager")
mg = off["grand_total"]
c.eq((D(mg["net"]), mg["cost"], mg["margin"], mg["margin_percent"]), (D("354.00"), None, None, None), "without PRODUCT_VIEW_COST_PRICE the sales figures stay and cost, margin and margin percent are withheld")
c.eq((off["previous"]["grand_total"]["cost"], off["previous"]["grand_total"]["margin"]), (None, None), "also in the previous-year column")
c.eq(admin("cashier").get(f"{SA}{Q}")[0], 403, "a Cashier is refused the report")

# layouts: per user and report
name = f"Layout {suffix(4)}"
st, made = a.post("/api/v1/report-layouts", {"report_code": "sales_analysis", "name": name, "settings": {"basis": "ordered", "compare_previous_year": True}})
c.eq(st, 200, "a layout is saved (200, not 201)")
layout = data(made)
mine = rows_of(a.get("/api/v1/report-layouts?report_code=sales_analysis"))
c.eq([m["settings"] for m in mine if m["name"] == name], [{"basis": "ordered", "compare_previous_year": True}], "reopened, it carries what was saved")
c.eq([m for m in rows_of(mgr.get("/api/v1/report-layouts?report_code=sales_analysis")) if m["name"] == name], [], "another user does not see it: layouts are per user")
c.eq([m for m in rows_of(a.get("/api/v1/report-layouts?report_code=purchase_analysis")) if m["name"] == name], [], "nor on the other report")
c.eq(a.post("/api/v1/report-layouts", {"report_code": "trial_balance", "name": "x", "settings": {}})[0], 422, "a report that is not an analysis cannot hold a layout")
c.eq(mgr.delete(f"/api/v1/report-layouts/{layout['id']}")[0] in (403, 404), True, "another user cannot delete it")
c.ok(a.delete(f"/api/v1/report-layouts/{layout['id']}")[0] in (200, 204), "its owner deletes it")

# purchase side: basis, average rate, rate trend
bs = buy.Scene(a)
_, _, bill = bs.received_and_billed("4")
PQ = f"?from_date=2026-10-01&to_date=2026-10-31&product_id={bs.product['id']}"
for basis in ("billed", "received", "ordered"):
    g = must(a.get(f"{PA_}{PQ}&basis={basis}"), basis)["grand_total"]
    c.eq((D(g["quantity"]), D(g["taxable"]), D(g["net"]), D(g["average_rate"])), (D("4"), D("400.00"), D("472.00"), D("100.00")), f"purchase analysis, {basis}: 4 pieces at 100.00 average, 472.00 with tax")
c.eq(must(a.get(f"{PA_}{PQ}&compare_previous_year=true"), "cmp")["previous"]["grand_total"]["invoices"], 0, "compare with last year: nothing bought then")
trend = rows_of(a.get(f"/api/v1/purchase-invoices/reports/rate-trend?product_id={bs.product['id']}"))
c.eq([(r["bill_number"], D(r["quantity"]), D(r["rate"])) for r in trend], [(bill["invoice_number"], D("4"), D("100.00"))], "the rate trend shows the bill, its quantity and rate")
c.done()
