"""Probe (e): a Viewer, another firm's user and an outsider are refused on the collection documents."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("p_col_other_firm_and_viewer")
a = admin()
viewer = admin("viewer")
other = admin("admin2")
c1, _ = collector_ids()
firm1 = state("collections")["firm_id"]
sc = Scene(a)
cust = sc.customer()
with counter(a):
    bill = sc.bill(cust)
paid = data(receipt(a, cust, "500.00", [(bill, "118.00")])[1])
day = today().isoformat()
mark, start = journal_count(a), position(a, cust)
# a Viewer reads, and cannot write
c.eq(viewer.get(f"{RC}/{paid['id']}")[0], 200, "a Viewer can read the receipt")
c.eq(receipt(viewer, cust, "10.00", method="CASH")[0], 403, "a Viewer cannot record a receipt")
c.eq(viewer.post(f"{RC}/{paid['id']}/reverse", {"reason": "x"})[0], 403, "cannot reverse one")
c.eq(viewer.post(f"{RC}/{paid['id']}/allocate", {"invoice_id": bill["id"], "amount": "1"})[0], 403, "cannot apply one")
c.eq(viewer.post(RF, {"party_id": cust["id"], "settlement_date": day, "amount": "10", "method": "BANK"})[0], 403, "cannot record a refund")
c.eq(viewer.post(f"{PDC}/received", {"party_id": cust["id"], "cheque_number": "VV1", "cheque_date": day, "amount": "10", "received_on": day})[0], 403, "cannot take a cheque")
c.eq(viewer.post(f"{PDC}/issued/write", {"bank_account_id": cust["id"], "account_id": cust["id"], "amount": "10", "cheque_number": "VV2", "cheque_date": day})[0], 403, "cannot write a cheque")
c.eq(hand(viewer, [bill["id"]], c1)[0], 403, "cannot hand a bill to a collector")
c.eq(viewer.post(f"{COL}/promises", {"customer_id": cust["id"], "sales_invoice_id": bill["id"], "promised_on": day, "amount": "10"})[0], 403, "cannot record a promise")
c.eq(viewer.post(f"{PA}/settings", {})[0] in (403, 405), True, "cannot change the adjustment limits")
# another firm's administrator
for what, status in (
    ("read the receipt", other.get(f"{RC}/{paid['id']}")[0]),
    ("reverse it", other.post(f"{RC}/{paid['id']}/reverse", {"reason": "x"})[0]),
    ("record one against the customer", receipt(other, cust, "10.00", method="CASH")[0]),
    ("read the customer's statement", other.get(f"{CU}/{cust['id']}/statement?{day_range()}")[0]),
):
    c.ok(status in (403, 404), f"another firm's administrator cannot {what}", status)
named = other.inside(firm1)
c.eq(named.get(f"{RC}/{paid['id']}")[0], 403, "naming this firm in X-Firm-ID is refused")
c.eq(receipt(named, cust, "10.00", method="CASH")[0], 403, "...also for recording a receipt")
c.eq(named.post(f"{RC}/{paid['id']}/reverse", {"reason": "x"})[0], 403, "...and for reversing one")
anon = Api(None, firm1)
c.eq(anon.get(f"{RC}/{paid['id']}")[0], 401, "no sign-in is 401")
c.eq(receipt(anon, cust, "10.00", method="CASH")[0], 401, "...for recording a receipt too")
ids = {r["id"] for r in all_rows(other, RC)}
c.ok(paid["id"] not in ids, "his own list does not hold this firm's receipt")
c.eq((journal_count(a), position(a, cust), D(must(a.get(f"{RC}/{paid['id']}"), "read")["unallocated_amount"]), must(a.get(f"{RC}/{paid['id']}"), "read")["status"]), (mark, start, D("382.00"), "POSTED"), "after all the refusals nothing moved")
c.done()
