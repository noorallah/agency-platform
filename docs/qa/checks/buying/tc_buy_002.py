"""TC-BUY-002: editing an approved order withdraws the approval."""
import json
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_002")
a = admin()
sc = Scene(a)
order = sc.order()
c.eq(order["status"], "APPROVED", "the order starts approved")
body = sc.order_body()
body["remarks"] = "edited order remark"
body["lines"][0]["remarks"] = "edited line remark"
body["status"] = "APPROVED"  # an edit must not be able to decide the status
edited = a.put(f"{PO}/{order['id']}", body)
c.ok(edited[0] == 200, "the edit is saved", (edited[0], message(edited[1])))
if edited[0] == 200:
    c.eq(data(edited[1])["status"], "DRAFT", "an edit withdraws the approval; the body cannot write a status")
    again = sc.reload(order)
    c.eq(again["status"], "DRAFT", "reopened it is a draft")
    c.eq(again["remarks"], "edited order remark", "the order remark survives")
    c.eq(again["lines"][0]["remarks"], "edited line remark", "the line remark survives")
    status, hist = a.get(f"{PO}/{order['id']}/history")
    c.ok(status == 200 and "approval_withdrawn" in json.dumps(hist), "history shows purchase.approval_withdrawn", status)
    must(a.post(f"{PO}/{order['id']}/submit", {}), "submit")
    c.eq(must(a.post(f"{PO}/{order['id']}/approve", {}), "approve")["status"], "APPROVED", "approved again")
c.done()
