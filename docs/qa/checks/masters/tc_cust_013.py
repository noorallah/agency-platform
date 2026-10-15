"""TC-CUST-013: the customer account as a table (API half: GET /account rows, a receipt added through /receipts, over-allocation refused, on-account row, statement closing equals the last balance, a user without RECEIPT_CREATE can read the account but not add a receipt; the table row control is screen-only)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal

c = Check("tc_cust_013")
a = api()
sc = Scene(a, stock="100")
cu = sc.new_customer()
with counter(a):
    bills = []
    for q in ("1", "2"):
        b = must(a.post(SI, sc.bill_body(q, customer=cu)), "bill")
        bills.append(must(a.post(f"{SI}/{b['id']}/approve", {}), "approve"))
acc = must(a.get(f"{CU}/{cu['id']}/account"), "account")
c.eq([(l["transaction_type"], D(l["debit"]), D(l["balance"])) for l in acc["lines"]], [("INVOICE", D(118), D(118)), ("INVOICE", D(236), D(354))], "two bills as rows, oldest first, each with its balance")
c.eq((acc["total_entries"], D(acc["opening_balance"])), (2, D(0)), "all 2 entries, no opening balance")
r1 = receipt(a, cu, "118", [(bills[0], "118")])
c.eq(r1[0], 201, f"receipt against the first bill ({message(r1[1])})")
acc = must(a.get(f"{CU}/{cu['id']}/account"), "account")
last = acc["lines"][-1]
c.eq((last["transaction_type"], D(last["credit"]), D(last["balance"])), ("RECEIPT", D(118), D(236)), "receipt is the last row: 118 credit, balance 236")
offered = [r["invoice_id"] for r in rows_of(a.get(f"{RC}/outstanding?customer_id={cu['id']}"))]
c.eq(offered, [bills[1]["id"]], "the first bill is no longer offered under Against")
rid = data(r1[1])["id"]
c.eq(sorted(D(x["amount"]) for x in data(r1[1]).get("allocations", [])), [D(118)], "receipt is listed against the first bill")
over = receipt(a, cu, "300", [(bills[1], "300")])
c.ok(over[0] == 422 and "236.00 outstanding" in message(over[1]), "an amount over what the bill owes is refused naming the balance", f"{over[0]} {message(over[1])}")
onacc = receipt(a, cu, "50", [])
c.eq(onacc[0], 201, "on-account receipt of 50")
acc = must(a.get(f"{CU}/{cu['id']}/account"), "account")
c.eq((len(acc["lines"]), D(acc["lines"][-1]["credit"])), (4, D(50)), "one more row, 50 under Credit")
c.eq(D(owing_ := next(D(r["outstanding_amount"]) for r in rows_of(a.get(f"{RC}/outstanding?customer_id={cu['id']}")) if r["invoice_id"] == bills[1]["id"])), D(236), "second bill still owes 236")
day = today().isoformat()
st = must(a.get(f"{CU}/{cu['id']}/statement?from_date={day}&to_date={day}"), "statement")
c.eq(D(st["closing_balance"]), D(acc["lines"][-1]["balance"]), "statement closing equals the last balance of the table")
seller = api("seller")
c.eq(seller.get(f"{CU}/{cu['id']}/account")[0], 200, "a user without RECEIPT_CREATE still reads the account")
c.eq(seller.post(RC, {"party_id": cu["id"], "settlement_date": day, "amount": "5", "method": "CASH", "allocations": []})[0], 403, "and cannot add a receipt")
c.done()
