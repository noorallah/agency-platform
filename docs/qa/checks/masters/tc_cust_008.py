"""TC-CUST-008: an opening balance typed on the customer is collected as a bill."""
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

c = Check("tc_cust_008")
a = api()
t = tag()
code = f"OB1{t}"
cu = must(a.post(CU, {"code": code, "name": f"Opening {t}", "customer_type": "BUSINESS", "currency_code": "INR", "opening_balance": "1500", "payment_terms_days": 30}), "customer")
bills = rows_of(a.get(OB(cu["id"])))
c.eq([(D(b["amount"]), b["covers_master_balance"]) for b in bills], [(D(1500), True)], "one opening bill of 1,500 standing for the figure typed")
c.eq(D(must(a.get(f"{CU}/{cu['id']}"), "c")["current_outstanding"]), D(1500), "outstanding 1,500")
je = journal(a, f"{code}-OB")
c.eq(len(je), 1, "one journal, reference <code>-OB")
if je:
    e = must(a.get(f"/api/v1/finance/journal-entries/{je[0]['id']}"), "entry")
    c.eq(net(e), [("Cr", "1500.00"), ("Dr", "1500.00")], "Dr receivables / Cr opening balance equity 1,500.00")
out = rows_of(a.get(f"{RC}/outstanding?customer_id={cu['id']}"))
c.eq([(r["invoice_number"] if "invoice_number" in r else None, D(r["outstanding_amount"])) for r in out][0][1], D(1500), "Record Receipt offers one row of 1,500")
c.eq(len(out), 1, "exactly one row")
due = out[0].get("due_date")
c.eq(due, (today() + timedelta(days=30)).isoformat(), "due the day it was entered plus 30 days")
age = next((r for r in rows_of(a.get(f"{CU}/ageing")) if r["customer_id"] == cu["id"]), None)
c.eq(D(age["total_outstanding"]) if age else None, D(1500), "the ageing lists the row")
day = today().isoformat()
st = must(a.get(f"{CU}/{cu['id']}/statement?from_date={day}&to_date={day}"), "statement")
c.eq(len(st["lines"]), 1, "the statement shows the opening balance once, not twice")
over = receipt(a, cu, "2000", [({"id": out[0]["invoice_id"]}, "2000")])
c.ok(over[0] == 422 and "1500.00 outstanding" in message(over[1]) and "2000.00 cannot be allocated" in message(over[1]), "2,000 against the row is refused naming the balance", f"{over[0]} {message(over[1])}")
ok = receipt(a, cu, "600", [({"id": out[0]["invoice_id"]}, "600")], method="CASH")
c.eq(ok[0], 201, f"600 cash is taken ({message(ok[1])})")
out = rows_of(a.get(f"{RC}/outstanding?customer_id={cu['id']}"))
c.eq([D(r["outstanding_amount"]) for r in out], [D(900)], "the row reads 900.00 on Record Receipt")
c.eq(D(must(a.get(f"{CU}/{cu['id']}"), "c")["current_outstanding"]), D(900), "outstanding 900")
age = next((r for r in rows_of(a.get(f"{CU}/ageing")) if r["customer_id"] == cu["id"]), None)
c.eq(D(age["total_outstanding"]) if age else None, D(900), "the ageing reads 900.00")
bill = rows_of(a.get(OB(cu["id"])))[0]
r = a.post(f"/api/v1/customers/opening-bills/{bill['id']}/cancel", {"reason": "try"})
c.ok(r[0] in (409, 422) and "opening balance entered on the customer" in message(r[1]), "cancelling the bill that stands for the typed figure is refused", f"{r[0]} {message(r[1])}")
r = a.post(OB(cu["id"]), {"reference_number": "X1", "bill_date": today().isoformat(), "amount": "250"})
c.ok(r[0] in (409, 422) and "either as one figure on the customer or bill by bill" in message(r[1]), "adding a bill beside the figure is refused", f"{r[0]} {message(r[1])}")
neg = must(a.post(CU, {"code": f"OB2{t}", "name": f"Owed {t}", "customer_type": "BUSINESS", "currency_code": "INR", "opening_balance": "-300"}), "negative")
c.eq(rows_of(a.get(OB(neg["id"]))), [], "a negative opening balance makes no bill")
c.done()
