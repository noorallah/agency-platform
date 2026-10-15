"""TC-BUY-102: an order on the main office is received from a branch and billed by it.

Not driven: the screens, and the GST-state tax for the branch (the check vendors carry
no GST number, so the tax split by state is not exercised).
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_102")
a = admin()
sc = Scene(a)
main = sc.vendor
vid = main["id"]
br = sc.new_vendor(parent_vendor_id=vid)
br2 = sc.new_vendor(parent_vendor_id=vid)
c.eq(br["parent_vendor_id"], vid, "(1) the branch is saved under the main office")
fam = data(a.get(f"/api/v1/vendors/{vid}/family")[1])
c.eq(sorted(m["code"] for m in fam["members"]), sorted([main["code"], br["code"], br2["code"]]), "(2) the family lists the main office and both branches")
third = a.post("/api/v1/vendors", {"code": f"X{sc.tag}", "name": f"third {sc.tag}", "parent_vendor_id": br["id"]})
c.refused(third, 422, "is itself a branch of", "(3) choosing a branch as Branch of")
c.refused(a.delete(f"/api/v1/vendors/{vid}"), 409, "main office of 2 branch", "deleting the main office")
# 4-6: order on the main office, receipt from the branch
order = sc.order()
body = sc.receipt_body(order, "10")
body["vendor_id"] = br["id"]
gr = must(a.post(GR, body), "receipt")
gr = must(a.post(f"{GR}/{gr['id']}/complete", {}), "complete")
c.eq(gr["vendor_id"], br["id"], "(5) the receipt is saved in the branch's name")
after = sc.reload(order)
c.eq((after["vendor_id"], after["status"]), (vid, "RECEIVED"), "(6) the order is still on the main office and reads Received")
# 7: the bill in the branch's name
sc.vendor = br
bill = sc.bill(gr)
c.eq(bill["vendor_id"], br["id"], "(7) the bill is saved in the branch's name")
c.eq(D(bill["grand_total"]), D(1180), "1,180.00")
sc.vendor = main
# 8: Record Payment for the main office lists the branch's bill
rows = rows_of(a.get(f"{PAY}/outstanding?vendor_id={vid}&with_branches=true"))
c.eq([(r["invoice_id"], r["party_code"]) for r in rows], [(bill["id"], br["code"])], "(8) the branch's bill is listed with the branch's code")
c.eq(rows_of(a.get(f"{PAY}/outstanding?vendor_id={vid}")), [], "without with_branches the main office's own list is empty")
# 9: 1,500 in the main office's name, 1,180 set against the branch's bill
pay = must(a.post(PAY, {"party_id": vid, "settlement_date": today().isoformat(), "amount": "1500", "method": "BANK",
                        "allocations": [{"invoice_id": bill["id"], "amount": "1180"}]}), "payment")
c.eq(pay["party_id"], vid, "(9) one payment in the main office's name")
c.eq((D(pay["allocated_amount"]), D(pay["unallocated_amount"])), (D(1180), D(320)), "1,180 set against the bill, 320 stays on the main office's account")
# 10: statements
day = today().isoformat()


def lines_of(v: dict) -> list[dict]:
    """Return a vendor's statement lines for today."""
    return data(a.get(f"/api/v1/vendors/{v['id']}/statement?from_date={day}&to_date={day}")[1])["lines"]


def close(v: dict) -> Decimal:
    """Return a vendor's closing balance for today."""
    return D(data(a.get(f"/api/v1/vendors/{v['id']}/statement?from_date={day}&to_date={day}")[1])["closing_balance"])


bl = lines_of(br)
c.ok(any("Paid by the main office" in x["remarks"] and D(x["debit"]) == D(1180) for x in bl), "(10) the branch's statement carries 'Paid by the main office' 1,180.00", bl)
c.eq(close(br), D(0), "the branch closes at nothing")
ml = lines_of(main)
c.ok(any("Paid for a branch" in x["remarks"] for x in ml), "the main office's statement carries 'Paid for a branch'", ml)
c.eq(close(main), D(-320), "the main office closes at 320.00 paid ahead")
# 11: a second branch lists only its own bills
c.eq(rows_of(a.get(f"{PAY}/outstanding?vendor_id={br2['id']}&with_branches=true")), [], "(11) the second branch lists neither the first branch's nor the main office's bills")
# 12: reverse
rev = a.post(f"{PAY}/{pay['id']}/reverse", {"reason": "check"})
c.eq(rev[0], 200, "(12) the payment reverses")
c.eq(owing(a, br["id"], bill["id"]), D(1180), "the branch is owed its bill again")
c.eq((close(br), close(main)), (D(1180), D(0)), "the branch closes at 1,180.00 and the main office at nothing")
c.ok(any(x["transaction_type"] == "PAYMENT_TRANSFER_REVERSAL" for x in lines_of(br)) and any(x["transaction_type"] == "PAYMENT_TRANSFER_REVERSAL" for x in lines_of(main)),
     "both statements keep the earlier lines with a reversal line under each")
print("note: GST-state tax for the branch and the screens are not driven")
c.done()
