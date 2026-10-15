"""Probe (d): a receipt over-allocated beyond a bill's outstanding is refused, on every route."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("p_col_over_allocation")
a = admin()
sc = Scene(a)
cust = sc.customer()
with counter(a):
    bill = sc.bill(cust)  # 118.00
    other = sc.bill(cust)
day = today().isoformat()
mark, start = journal_count(a), position(a, cust)
c.refused(receipt(a, cust, "500.00", [(bill, "300.00")]), 422, "has 118.00 outstanding, so 300.00 cannot be allocated", "300.00 against a 118.00 bill is refused")
c.refused(receipt(a, cust, "50.00", [(bill, "100.00")]), 422, "more than the 50.00 that moved", "allocating more than the receipt is refused")
c.eq(receipt(a, cust, "200.00", [(bill, "100.00"), (bill, "100.00")])[0], 422, "the same bill twice in one receipt is refused")
c.eq(receipt(a, cust, "0.00")[0], 422, "a zero receipt is refused")
c.eq(receipt(a, cust, "-5.00")[0], 422, "a negative receipt is refused")
c.eq((journal_count(a), position(a, cust), owing(a, cust, bill)), (mark, start, D("118.00")), "none of them posted or moved anything")
# part-pay, then the remainder is all that may be allocated
c.eq(receipt(a, cust, "100.00", [(bill, "100.00")])[0], 201, "100.00 is allocated to the 118.00 bill")
c.refused(receipt(a, cust, "100.00", [(bill, "100.00")]), 422, "has 18.00 outstanding", "another 100.00 is refused: 18.00 is left")
c.eq(owing(a, cust, bill), D("18.00"), "the bill owes 18.00")
# applying an advance the same way
adv = data(receipt(a, cust, "300.00")[1])
c.refused(a.post(f"{RC}/{adv['id']}/allocate", {"invoice_id": bill["id"], "amount": "100.00"}), 422, "owes only 18.00", "applying 100.00 to a bill that owes 18.00 is refused")
c.refused(a.post(f"{RC}/{adv['id']}/allocate", {"invoice_id": other["id"], "amount": "400.00"}), 422, "", "applying more than the advance holds is refused")
c.eq(a.post(f"{RC}/{adv['id']}/allocate", {"invoice_id": bill["id"], "amount": "18.00"})[0], 200, "exactly the 18.00 owed is accepted")
c.eq(owing(a, cust, bill), D("0"), "the bill is closed")
c.eq(D(must(a.get(f"{RC}/{adv['id']}"), "read")["unallocated_amount"]), D("282.00"), "the advance holds 282.00")
c.eq(a.post(f"{RC}/{adv['id']}/allocate", {"invoice_id": bill["id"], "amount": "1.00"})[0], 422, "a closed bill takes nothing more")
c.eq(a.post(f"{RC}/{adv['id']}/allocate", {"invoice_id": other["id"], "amount": "-1.00"})[0], 422, "a negative application is refused")
# a customer's receipt cannot name another customer's bill unless it says so
stranger = sc.customer()
c.eq(receipt(a, stranger, "118.00", [(other, "118.00")])[0] in (404, 422), True, "another customer's bill is refused without Paid by")
c.eq(owing(a, cust, other), D("118.00"), "and the bill still owes 118.00")
c.done()
