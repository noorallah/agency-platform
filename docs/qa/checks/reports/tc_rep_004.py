"""D-FIN-35: orders booked leaves out the orders bills raised for themselves.

The order register lists every order, including the one the sales chain raises
behind a counter bill; ``analysis?basis=ordered`` counts only orders somebody
booked. So the analysis must come to no more than the register, and on TEST01,
which bills at the counter, to strictly less. The exact rule is pinned by
``tests/unit/test_sales_analysis_rest.py``.
"""

from decimal import Decimal

from _rep import FROM, TO, Check, admin, data, message

c = Check("tc_rep_004")
api = admin()
q = f"from_date={FROM}&to_date={TO}"
s1, a = api.get(f"/api/v1/sales-invoices/reports/analysis?rows=customer&basis=ordered&{q}")
c.eq(s1, 200, f"analysis ordered {message(a)[:150]}")
registered = Decimal(0)
counted = 0
statuses = {}
page = 1
while True:
    s2, b = api.get(f"/api/v1/sales-orders/reports/register?{q}&page={page}&page_size=100")
    c.eq(s2, 200, f"order register page {page} {message(b)[:150]}")
    if s2 != 200:
        break
    for r in data(b):
        statuses[r.get('status')] = statuses.get(r.get('status'), 0) + 1
    counted += sum(1 for r in data(b) if r.get('status') not in ('CANCELLED', 'DRAFT'))
    registered += sum(
        Decimal(str(r["grand_total"])) for r in data(b) if r.get("status") not in ("CANCELLED", "DRAFT")
    )
    if page >= int((b.get("pagination") or {}).get("total_pages") or 1):
        break
    page += 1
if s1 == 200:
    grand = data(a)["grand_total"]
    net = Decimal(str(grand["net"]))
    print(f"analysis ordered grand_total {grand}; order register sum {registered}")
    print("register statuses:", statuses)
    c.ok(0 < grand["invoices"] < counted,
            f"booked orders {grand['invoices']} below the register's {counted}")
    c.ok(net < registered, f"booked net {net} below the register's {registered}")
c.done()
