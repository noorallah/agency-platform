"""TC-BUY-022: a supplier bill outside tolerance, and an order over budget."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_022")
a = admin()
approver = custom_approver()
sc = Scene(a)
# --- bill matching: price tolerance 2%, amount tolerance 50
with settings(a, bill_price_tolerance_percent="2", bill_tolerance_amount="50"):
    order = sc.order()
    r6 = sc.receive(order, "6")
    bill = sc.bill(r6, price="110", approve=False)
    c.eq(bill["status"], "DRAFT", "the bill 10% over the order saves as a draft")
    c.refused(approver.post(f"{PI}/{bill['id']}/approve", {}), 403, "PURCHASE_APPROVE_OVER_TOLERANCE", "single approve without the over-tolerance right")
    c.eq(must(a.get(f"{PI}/{bill['id']}"), "read")["status"], "DRAFT", "the refused bill is still a draft")
    bulk = approver.post(f"{PI}/bulk-approve", {"items": [{"id": bill["id"]}]})
    got = data(bulk[1]) if bulk[0] == 200 else None
    c.ok(bulk[0] in (200, 403) and "TOLERANCE" in str(bulk[1]).upper() + str(got).upper(), "bulk approve refuses it too, naming the tolerance", (bulk[0], str(bulk[1])[:200]))
    c.eq(must(a.get(f"{PI}/{bill['id']}"), "read")["status"], "DRAFT", "still a draft after the bulk try")
    c.eq(a.post(f"{PI}/{bill['id']}/approve", {})[0], 200, "the administrator may approve it")
# --- budget: a month, one category, 500
cat = must(a.post("/api/v1/products/categories", {"code": f"BC{sc.tag}", "name": f"Buy check cat {sc.tag}"}), "category")
budgeted = sc.new_product("G", category_id=cat["id"])
month = today().replace(day=1).isoformat()
budget = must(a.post(f"{PO}/budgets", {"budget_month": month, "product_category_id": cat["id"], "amount": "500"}), "budget")
try:
    with settings(a, budget_policy="WARN"):
        o = sc.order(approve=False, product=budgeted, qty="10")
        must(a.post(f"{PO}/{o['id']}/submit", {}), "submit")
        done = approver.post(f"{PO}/{o['id']}/approve", {})
        c.eq(done[0], 200, "under Warn the approval proceeds")
        panel = a.get(f"{PO}/{o['id']}/budget")
        c.eq(panel[0], 200, "the order's budget panel answers")
        text = str(panel[1])
        c.ok("500" in text and "1000" in text, "the panel shows the budget 500 and what the order adds, 1000", text[:300])
    with settings(a, budget_policy="NEEDS_APPROVAL"):
        o2 = sc.order(approve=False, product=budgeted, qty="10")
        must(a.post(f"{PO}/{o2['id']}/submit", {}), "submit")
        c.refused(approver.post(f"{PO}/{o2['id']}/approve", {}), 403, "PURCHASE_APPROVE_OVER_BUDGET", "under Needs approval, without the over-budget right")
        c.eq(a.post(f"{PO}/{o2['id']}/approve", {})[0], 200, "the administrator may approve")
finally:
    a.delete(f"{PO}/budgets/{budget['id']}")
c.done()
