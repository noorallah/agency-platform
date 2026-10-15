"""TC-CUST-009: correcting an opening balance after a reversed receipt, and after a cancelled invoice."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
from datetime import timedelta

OB = lambda cid: f"{CU}/{cid}/opening-bills"


def plain(d: dict, **changes: object) -> dict:
    """The smallest update body for a customer, with changes."""
    return {"code": d["code"], "customer_type": "BUSINESS", "name": d["name"], "currency_code": "INR", **changes}


def net(entry: dict) -> list[tuple[str, str]]:
    """(debit/credit, amount) pairs of an entry."""
    return sorted((("Dr" if D(l["debit_amount"]) else "Cr"), str(max(D(l["debit_amount"]), D(l["credit_amount"])))) for l in entry["lines"])

c = Check("tc_cust_009")
a = api()
t = tag()
def mkc(code, bal="1500"):
    return must(a.post(CU, {"code": code, "name": f"Correct {code}", "customer_type": "BUSINESS", "currency_code": "INR", "opening_balance": bal, "payment_terms_days": 30}), "customer")
def setbal(cu, bal):
    return a.put(f"{CU}/{cu['id']}", plain(cu, opening_balance=bal))
ob3 = mkc(f"OB3{t}")
row = rows_of(a.get(f"{RC}/outstanding?customer_id={ob3['id']}"))[0]
rc = receipt(a, ob3, "600", [({"id": row["invoice_id"]}, "600")], method="CASH")
c.eq(rc[0], 201, "precondition: receipt of 600")
for bal in ("400", "0", "2000"):
    r = setbal(ob3, bal)
    c.ok(r[0] in (409, 422) and "cannot be changed while other entries stand" in message(r[1]) and "RC-" in message(r[1]), f"opening balance {bal} refused naming the receipt", f"{r[0]} {message(r[1])}")
c.eq(D(must(a.get(f"{CU}/{ob3['id']}"), "c")["opening_balance"]), D(1500), "the figure stays 1,500")
rv = a.post(f"{RC}/{data(rc[1])['id']}/reverse", {"reason": "to correct the opening balance"})
c.eq(rv[0], 200, f"receipt reversed ({message(rv[1])})")
r = setbal(ob3, "400")
c.eq(r[0], 200, f"with the receipt reversed 400 saves ({message(r[1])})")
bills = rows_of(a.get(OB(ob3["id"])))
c.eq(sorted((b["status"], str(D(b["amount"]))) for b in bills), [("CANCELLED", "1500.00"), ("OPEN", "400.00")] if any(b["status"] == "OPEN" for b in bills) else sorted((b["status"], str(D(b["amount"]))) for b in bills), "the 1,500 bill is cancelled and one standing bill of 400.00 stands")
live = [b for b in bills if b["status"] != "CANCELLED"]
c.eq([D(b["amount"]) for b in live], [D(400)], "one live bill of 400.00")
c.ok(any("revised" in str(b.get("cancellation_reason")) for b in bills), "the cancelled bill says the opening balance was revised", [b.get("cancellation_reason") for b in bills])
c.eq([D(r["outstanding_amount"]) for r in rows_of(a.get(f"{RC}/outstanding?customer_id={ob3['id']}"))], [D(400)], "Record Receipt lists one row of 400.00")
c.ok(journal(a, f"OB3{t}-OB-REV") != [], "a -OB-REV journal mirrors the first")
c.ok(journal(a, f"OB3{t}-OB2") != [], "a -OB2 journal posts the 400")
r = setbal(ob3, "0")
c.eq(r[0], 200, f"0 saves ({message(r[1])})")
c.eq([b for b in rows_of(a.get(OB(ob3["id"]))) if b["status"] != "CANCELLED"], [], "no bill stands")
c.eq(a.delete(f"{CU}/{ob3['id']}")[0], 204, "the customer can then be deleted")
ob4 = mkc(f"OB4{t}", "0")
setbal(ob4, "1500")
sc = Scene(a, stock="20")
with counter(a):
    b = must(a.post(SI, sc.bill_body("1", customer=ob4)), "bill")
    b = must(a.post(f"{SI}/{b['id']}/approve", {}), "approve")
r = setbal(ob4, "400")
c.ok(r[0] in (409, 422) and b["invoice_number"] in message(r[1]), "with an approved invoice standing, the change is refused naming the invoice", f"{r[0]} {message(r[1])}")
cn = a.post(f"{SI}/{b['id']}/cancel", {"reason": "to correct the opening balance"})
c.eq(cn[0], 200, f"invoice cancelled ({message(cn[1])})")
r = setbal(ob4, "400")
c.eq(r[0], 200, f"once the invoice is cancelled the change saves ({message(r[1])})")
c.done()
