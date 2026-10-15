"""TC-CUST-004: a credit limit warns and does not block (API half: credit-status warns, approval over the limit succeeds under WARN; the Approve anyway question is screen-only)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *

c = Check("tc_cust_004")
a = api()
with credit_policy(a, enforcement="WARN", warn_at_percent="80", block_at_percent="100"):
    sc = Scene(a, stock="50")
    cust = sc.new_customer(credit_limit="1")
    st, body = a.get(f"{CU}/{cust['id']}/credit-status?amount=236")
    s = data(body)
    c.eq((st, s["status"], s["would_block"]), (200, "WARNING", False), "status warns and would not block")
    c.ok("credit limit" in str(s["message"]) and "over it" in str(s["message"]), "message names the exposure and 'over it'", s["message"])
    order = new_order(sc, "2", customer=cust)
    st, ap = a.post(f"{SO}/{order['id']}/approve", {})
    c.eq(st, 200, f"approval is not blocked in WARN ({message(ap)})")
    c.eq(data(ap)["status"], "APPROVED", "the order is approved")
c.done()
