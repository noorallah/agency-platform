"""D-FIN-35: analysis basis=ordered must not count lines with no order."""

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
    c.eq(grand["invoices"], counted, "ordered document count: analysis vs order register (non-draft, non-cancelled)")
    c.eq(net.quantize(Decimal("0.01")), registered.quantize(Decimal("0.01")),
         "ordered net: analysis vs sum of order register grand_total (non-draft, non-cancelled)")
c.done()
