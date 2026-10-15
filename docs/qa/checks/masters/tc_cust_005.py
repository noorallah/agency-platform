"""TC-CUST-005: statement and ageing agree with the account (bill 590, receipt 200, closing 390)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal

c = Check("tc_cust_005")
a = api()
sc = Scene(a, stock="100")
cu = sc.new_customer()
with counter(a):
    bill = sc.bill_body("5", customer=cu)
    bill = must(a.post(SI, bill), "bill")
    bill = must(a.post(f"{SI}/{bill['id']}/approve", {}), "approve")
c.eq(D(bill["grand_total"]), D(590), "precondition: bill is 590")
c.eq(receipt(a, cu, "200", [(bill, "200")])[0], 201, "receipt of 200 applied")
day = today().isoformat()
st = must(a.get(f"{CU}/{cu['id']}/statement?from_date={day}&to_date={day}"), "statement")
c.eq(D(st["opening_balance"]), D(0), "opening 0.00")
c.eq([(l["transaction_type"], D(l["debit"]), D(l["credit"]), D(l["balance"])) for l in st["lines"]],
     [("INVOICE", D(590), D(0), D(590)), ("RECEIPT", D(0), D(200), D(390))], "invoice 590 then receipt 200, running balance 390")
c.eq(D(st["closing_balance"]), D(390), "closing 390")
c.eq(D(must(a.get(f"{CU}/{cu['id']}"), "customer")["current_outstanding"]), D(390), "equals the customer's balance")
age = next((r for r in rows_of(a.get(f"{CU}/ageing")) if r["customer_id"] == cu["id"]), None)
if c.ok(age is not None, "customer appears in the ageing"):
    c.eq(D(age["total_outstanding"]), D(390), "ageing total 390")
    c.eq([D(b["amount"]) for b in age["buckets"]], [D(390), D(0), D(0), D(0)], "all of it in 0-29 days")
    c.eq(sum(D(b["amount"]) for b in age["buckets"]), D(age["total_outstanding"]), "buckets sum to the total")
    c.eq((D(age["unapplied_credits"]), D(age["charges_not_billed"])), (D(0), D(0)), "nothing to reconcile")
    c.eq(D(age["account_balance"]), D(390), "reconciles to the account")
c.done()
