"""TC-MAST-012: a duplicate warning, and merging two customers (and two vendors). The closed-financial-year refusal is not driven here: it needs a closed year and the shared test firm must not have one closed."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_012")
a, s = api(), api("seller")
t = tag()
phone = "+9198" + str(abs(hash(t)) % 100000000).zfill(8)
surv = must(a.post(CU, {"code": f"MS{t}", "name": f"Master Check {t}", "customer_type": "BUSINESS", "currency_code": "INR", "phone": phone}), "survivor")
dup = must(a.post(CU, {"code": f"MD{t}", "name": f"Master Check Stores {t}", "customer_type": "BUSINESS", "currency_code": "INR", "phone": phone}), "duplicate")
warn = must(a.get(f"{CU}/duplicates?name=M%2Fs%20Master%20Check%20Traders%20{t}&phone={phone.replace('+', '%2B')}"), "warn")
codes = sorted(r["code"] for r in warn)
c.ok({f"MS{t}", f"MD{t}"} <= set(codes), "typing the name and the phone warns of both customers", codes)
sc = Scene(a, stock="20")
with counter(a):
    b = must(a.post(SI, sc.bill_body("2", customer=dup)), "bill")
    b = must(a.post(f"{SI}/{b['id']}/approve", {}), "approve")
c.eq(receipt(a, dup, "100", [(b, "100")])[0], 201, "a receipt on the duplicate")
owed_before = D(must(a.get(f"{CU}/{dup['id']}"), "dup")["current_outstanding"])
c.eq(owed_before, D(136), "the duplicate owes 236 less 100")
body = {"duplicate_id": dup["id"], "reason": "same shop, typed twice"}
c.eq(s.post(f"{CU}/{surv['id']}/merge", body)[0], 403, "without CUSTOMER_DELETE the merge is refused")
m = a.post(f"{CU}/{surv['id']}/merge", body)
c.eq(m[0], 200, f"the merge runs ({message(m[1])})")
if m[0] == 200:
    c.ok(data(m[1])["rows_moved"] > 0, "it moved rows", data(m[1]))
sv = must(a.get(f"{CU}/{surv['id']}"), "survivor")
c.eq(D(sv["current_outstanding"]), owed_before, "the survivor now owes what the duplicate owed (balances summed)")
gone = a.get(f"{CU}/{dup['id']}")
c.ok(gone[0] == 404 or data(gone[1]).get("is_deleted"), "the duplicate is soft-deleted", gone[0])
inv = must(a.get(f"{SI}/{b['id']}"), "bill")
c.eq(inv["customer_id"], surv["id"], "the invoice is re-pointed to the survivor")
day = today().isoformat()
st = must(a.get(f"{CU}/{surv['id']}/statement?from_date={day}&to_date={day}"), "statement")
c.eq(D(st["closing_balance"]), owed_before, "the survivor's statement closes at the merged balance")
v1 = vendor(a, name=f"Supply Check {t}", phone=phone)
v2 = vendor(a, name=f"Supply Check Stores {t}", phone=phone)
vw = must(a.get(f"{VE}/duplicates?name=Supply%20Check%20Traders%20{t}&phone={phone.replace('+', '%2B')}"), "vendor warn")
c.ok({v1["code"], v2["code"]} <= {r["code"] for r in vw}, "the same warning for vendors", [r["code"] for r in vw])
vm = a.post(f"{VE}/{v1['id']}/merge", {"duplicate_id": v2["id"], "reason": "typed twice"})
c.eq(vm[0], 200, f"vendors merge too ({message(vm[1])})")
c.eq(s.post(f"{VE}/{v1['id']}/merge", {"duplicate_id": v2["id"], "reason": "x"})[0], 403, "and the seller is refused for vendors")
c.done()
