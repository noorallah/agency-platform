"""TC-CUST-015: the Account view paged: newest N, from the start, skip, the totals (API half; the Download sheet and the remembered Show choice are screen-only; the case needs 100+ entries, this drives the same paging on 8)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal

c = Check("tc_cust_015")
a = api()
sc = Scene(a, stock="100")
cu = sc.new_customer()
with counter(a):
    for i in range(4):
        b = must(a.post(SI, sc.bill_body("1", customer=cu)), "bill")
        b = must(a.post(f"{SI}/{b['id']}/approve", {}), "approve")
        c.eq(receipt(a, cu, "18", [(b, "18")])[0], 201, f"receipt {i + 1}")
def page(**q: object) -> dict:
    qs = "&".join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in q.items())
    return must(a.get(f"{CU}/{cu['id']}/account?{qs}"), "account page")
whole = page(last=20)
c.eq(whole["total_entries"], 8, "8 entries in all")
c.eq(len(whole["lines"]), 8, "the last 20 holds all 8")
day = today().isoformat()
closing_bal = D(must(a.get(f"{CU}/{cu['id']}/statement?from_date={day}&to_date={day}"), "statement")["closing_balance"])
c.eq(D(whole["lines"][-1]["balance"]), closing_bal, "last balance equals the statement closing")
tail = page(last=3)
c.eq([l["reference_number"] for l in tail["lines"]], [l["reference_number"] for l in whole["lines"][-3:]], "last=3 is the newest three, oldest first")
c.eq(D(tail["opening_balance"]), D(whole["lines"][-4]["balance"]), "opening balance is everything before the first shown")
head = page(last=3, from_start=True)
c.eq([l["reference_number"] for l in head["lines"]], [l["reference_number"] for l in whole["lines"][:3]], "from_start reads forward from the first entry")
c.eq(D(head["opening_balance"]), D(0), "from the start there is no opening balance")
seen = []
skip = 0
while True:
    got = page(last=3, from_start=True, skip=skip)["lines"]
    if not got:
        break
    seen += [l["reference_number"] for l in got]
    skip += len(got)
    if skip > 20:
        break
c.eq(seen, [l["reference_number"] for l in whole["lines"]], "paging 3 at a time with skip reads every entry once, in order")
c.eq(a.get(f"{CU}/{cu['id']}/account?last=0")[0], 422, "last=0 refused")
c.done()
