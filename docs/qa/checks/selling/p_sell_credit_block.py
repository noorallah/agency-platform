"""Probe (d): credit control set to block refuses a bill over the limit at approval; back to warn it passes."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("p_sell_credit_block")
a = admin()
sc = Scene(a, stock="100")
cust = sc.new_customer(credit_limit="1000")
with counter(a):
    with credit_policy(a, enforcement="BLOCK", warn_at_percent="80", block_at_percent="100"):
        over = a.post(SI, sc.bill_body("10", customer=cust))
        c.ok(over[0] in (409, 422) and "credit limit" in message(over[1]).lower(), "BLOCK: a bill over the limit (1,180 on 1,000) is refused in words, naming the limit", f"{over[0]} {message(over[1])}")
        c.eq(owed(a, cust["id"]), D(0), "BLOCK: nothing owed")
        small = must(a.post(SI, sc.bill_body("1", customer=cust)), "small draft")
        c.eq(must(a.post(f"{SI}/{small['id']}/approve", {}), "approve small")["status"], "APPROVED", "BLOCK: a bill inside the limit passes")
    with credit_policy(a, enforcement="WARN", warn_at_percent="80", block_at_percent="100"):
        draft = a.post(SI, sc.bill_body("10", customer=cust))
        c.eq(draft[0], 201, f"WARN: the over-limit draft is saved ({message(draft[1])})")
    if draft[0] == 201:
        draft = data(draft[1])
        with credit_policy(a, enforcement="BLOCK", warn_at_percent="80", block_at_percent="100"):
            stop = a.post(f"{SI}/{draft['id']}/approve", {})
            c.ok(stop[0] in (409, 422) and "credit limit" in message(stop[1]).lower(), "BLOCK: approving the over-limit draft is refused", f"{stop[0]} {message(stop[1])}")
            c.eq(must(a.get(f"{SI}/{draft['id']}"), "bill")["status"], "DRAFT", "BLOCK: it stays a draft")
        with credit_policy(a, enforcement="WARN", warn_at_percent="80", block_at_percent="100"):
            passed = a.post(f"{SI}/{draft['id']}/approve", {})
            c.eq(passed[0], 200, f"WARN: the same draft now approves ({message(passed[1])})")
    with credit_policy(a, enforcement="BLOCK", warn_at_percent="80", block_at_percent="100"):
        order = a.post(SO, {"customer_id": cust["id"], "order_date": today().isoformat(), "branch_id": sc.branch["id"],
                            "warehouse_id": sc.warehouse["id"],
                            "lines": [{"line_number": 1, "product_id": sc.product["id"], "quantity": "10"}]})
        c.eq(order[0], 201, f"BLOCK: an order is still saved as a draft ({message(order[1])})")
        if order[0] == 201:
            stop = a.post(f"{SO}/{data(order[1])['id']}/approve", {})
            c.ok(stop[0] in (409, 422) and "credit limit" in message(stop[1]).lower(), "BLOCK: and refused at approval over the limit", f"{stop[0]} {message(stop[1])}")
c.done()
