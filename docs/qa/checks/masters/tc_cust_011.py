"""TC-CUST-011: the two credit modes on an order and on a bill (API half: figures from credit-status, then approvals under WARN and BLOCK). Changes the TEST01 credit policy and puts it back."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *

c = Check("tc_cust_011")
a = api()
sc = Scene(a, stock="100")
cust = sc.new_customer(credit_limit="1000")
def status(amount: str) -> dict:
    return data(a.get(f"{CU}/{cust['id']}/credit-status?amount={amount}")[1])
with counter(a):
    with credit_policy(a, enforcement="WARN", warn_at_percent="80", block_at_percent="100"):
        c.eq(status("590")["status"], "OK", "5 pieces (590) ask nothing")
        s7, s10 = status("826"), status("1180")
        c.eq((s7["status"], D(s7["used_percent"]).quantize(D("0.1"))), ("WARNING", D("82.6")), "7 pieces: 82.6%")
        c.ok("174.00 available" in str(s7["message"]), "7 pieces: leaving 174.00 available", s7["message"])
        c.ok("118.0%" in str(s10["message"]) and "180.00 over it" in str(s10["message"]), "10 pieces: 118.0%, 180.00 over it", s10["message"])
        for q in ("5", "7", "10"):
            o = new_order(sc, q, customer=cust)
            c.eq(a.post(f"{SO}/{o['id']}/approve", {})[0], 200, f"WARN: order of {q} approves")
    with credit_policy(a, enforcement="BLOCK", warn_at_percent="80", block_at_percent="100"):
        o7 = new_order(sc, "7", customer=cust)
        c.eq(a.post(f"{SO}/{o7['id']}/approve", {})[0], 200, "BLOCK: order of 7 approves (exposure is what is owed plus this document)")
        o10 = new_order(sc, "10", customer=cust)
        r = a.post(f"{SO}/{o10['id']}/approve", {})
        c.ok(r[0] in (409, 422) and "118.0%" in message(r[1]) and "Collect payment or raise the limit" in message(r[1]), "BLOCK: order of 10 refused at 118.0%", f"{r[0]} {message(r[1])}")
        c.eq(data(a.get(f"{SO}/{o10['id']}")[1])["status"], "DRAFT", "refused order stays a draft")
        b1 = a.post(SI, sc.bill_body("7", customer=cust))
        c.eq(b1[0], 201, f"bill of 7 saved ({message(b1[1])})")
        c.eq(a.post(f"{SI}/{data(b1[1])['id']}/approve", {})[0], 200, "BLOCK: first bill (82.6%) approves")
        c.eq(owed(a, cust["id"]), D(826), "826 owed")
        b2 = a.post(SI, sc.bill_body("5", customer=cust))
        c.ok(b2[0] in (409, 422) and "141.6%" in message(b2[1]), "BLOCK: a second bill that takes the account to 141.6% is refused already when typed (the case says it stays a draft)", f"{b2[0]} {message(b2[1])}")
    with credit_policy(a, enforcement="WARN", warn_at_percent="80", block_at_percent="100"):
        b3 = must(a.post(SI, sc.bill_body("5", customer=cust)), "draft bill under WARN")
    with credit_policy(a, enforcement="BLOCK", warn_at_percent="80", block_at_percent="100"):
        r = a.post(f"{SI}/{b3['id']}/approve", {})
        c.ok(r[0] in (409, 422) and "141.6%" in message(r[1]), "BLOCK: approving that draft is refused at 141.6%", f"{r[0]} {message(r[1])}")
        c.eq(data(a.get(f"{SI}/{b3['id']}")[1])["status"], "DRAFT", "and it stays a draft")
    with credit_policy(a, enforcement="WARN", warn_at_percent="80", block_at_percent="100"):
        ok = a.post(f"{SI}/{b3['id']}/approve", {})
        c.eq(ok[0], 200, f"WARN: the same bill now approves ({message(ok[1])})")
        c.eq(owed(a, cust["id"]), D(1416), "1,416 owed")
c.done()
