"""TC-SELL-107: a Draft sales return is edited (the box-unit quotation and offer steps are not driven)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_107")
a = admin()
v = admin("viewer")
sc = Scene(a, stock="100")
with counter(a):
    bill = sc.bill(qty="5")
body = return_body(sc, bill, "2", return_reason="damaged in transit", remarks="step 1")
made = must(a.post(SR, body), "step 1")
c.eq((made["status"], D(made["total_current_return_quantity"])), ("DRAFT", D(2)), "step 1: a Draft return of 2")
before = (made["return_number"], made["return_date"], made["grand_total"], len(made["lines"]))
same = a.put(f"{SR}/{made['id']}", body)
c.eq(same[0], 200, f"step 2: saving with nothing changed ({message(same[1])})")
if same[0] == 200:
    got = data(same[1])
    c.eq((got["return_number"], got["return_date"], got["grand_total"], len(got["lines"])), before, "step 2: number, date, totals and lines are what they were")
    c.eq(got["return_reason"], "damaged in transit", "step 2: the reason is kept")
    c.eq(got["version"] > made["version"] or got["version"] == made["version"], True, "version read")
three = {**body, "lines": [{**body["lines"][0], "current_return_quantity": "3", "restock_quantity": "3"}]}
edit = a.put(f"{SR}/{made['id']}", three)
c.eq(edit[0], 200, f"step 3: Returning 3 saves ({message(edit[1])})")
if edit[0] == 200:
    got = data(edit[1])
    c.eq(D(got["total_current_return_quantity"]), D(3), "step 3: the return reads 3")
    c.eq((got["return_number"], got["return_date"], got["return_reason"]), (made["return_number"], made["return_date"], "damaged in transit"), "step 3: reason, date and number unchanged")
    c.eq(D(got["grand_total"]), D(354), "step 3: the total follows (3 x 100 + 18%)")
other = must(a.post(SR, return_body(sc, bill, "1")), "a second draft")
c.eq(v.put(f"{SR}/{other['id']}", return_body(sc, bill, "1"))[0], 403, "step 5: a user without SALES_UPDATE cannot edit")
c.eq(must(a.post(f"{SR}/{made['id']}/approve", {}), "approve")["status"], "APPROVED", "step 4: approved")
late = a.put(f"{SR}/{made['id']}", three)
c.ok(late[0] in (409, 422), "step 4: an Approved return cannot be edited", f"{late[0]} {message(late[1])}")
c.done()
