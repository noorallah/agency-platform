"""TC-CUST-010: recording, cancelling and importing opening bills needs CUSTOMER_MANAGE_SETTINGS (Sales Manager refused; Firm admin may). The Firm Manager and Customer Support steps are not driven: no such accounts in the set-up."""
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

c = Check("tc_cust_010")
a, m = api(), api("manager")
t = tag()
five = must(a.post(CU, {"code": f"OB5{t}", "name": f"Five {t}", "customer_type": "BUSINESS", "currency_code": "INR"}), "ob5")
six = must(a.post(CU, {"code": f"OB6{t}", "name": f"Six {t}", "customer_type": "BUSINESS", "currency_code": "INR"}), "ob6")
bill5 = must(a.post(OB(five["id"]), {"reference_number": "OLD-5", "bill_date": today().isoformat(), "amount": "5000"}), "bill 5000")
c.eq([D(b["amount"]) for b in rows_of(m.get(OB(five["id"])))], [D(5000)], "the sales manager reads the list of opening bills")
r = m.post(OB(six["id"]), {"reference_number": "OLD-6", "bill_date": today().isoformat(), "amount": "900"})
c.ok(r[0] == 403 and "Recording a customer's opening bill needs the manage customer settings permission" in message(r[1]), "record refused 403", f"{r[0]} {message(r[1])}")
r = m.post(f"{CU}/opening-bills/{bill5['id']}/cancel", {"reason": "x"})
c.ok(r[0] == 403 and "Cancelling a customer's opening bill" in message(r[1]), "cancel refused 403", f"{r[0]} {message(r[1])}")
r = m.post(f"{CU}/opening-bills/import", {"records": [{"customer_code": six["code"], "bill_date": today().isoformat(), "amount": "900"}]})
c.ok(r[0] == 403 and "Importing customers' opening bills" in message(r[1]), "batch import refused 403", f"{r[0]} {message(r[1])}")
csv = f"PartyCode,BillNumber,BillDate,DueDate,Amount,Narration\n{six['code']},OLD-7,{today().isoformat()},,900,\n".encode()
for apply in ("false", "true"):
    r = m.upload(f"{CU}/opening-bills/import-file", "ob.csv", csv, {"apply": apply})
    c.ok(r[0] == 403 and "Importing customers' opening bills" in message(r[1]), f"file import apply={apply} refused 403", f"{r[0]} {message(r[1])}")
c.eq(D(must(a.get(f"{CU}/{six['id']}"), "six")["current_outstanding"]), D(0), "OB6 still owes nothing")
c.eq(D(must(a.get(f"{CU}/{five['id']}"), "five")["current_outstanding"]), D(5000), "OB5 still owes 5,000")
c.eq(journal(a, f"OB6{t}"), [], "no journal written for OB6")
ok = a.post(OB(six["id"]), {"reference_number": "OLD-7", "bill_date": today().isoformat(), "amount": "900"})
c.eq(ok[0], 201, f"the Firm admin records a bill dated today ({message(ok[1])})")
tom = a.post(OB(six["id"]), {"reference_number": "OLD-8", "bill_date": (today() + timedelta(days=1)).isoformat(), "amount": "100"})
c.ok(tom[0] in (409, 422) and "cannot be after" in message(tom[1]), "dated tomorrow is refused", f"{tom[0]} {message(tom[1])}")
cn = a.post(f"{CU}/opening-bills/{data(ok[1])['id']}/cancel", {"reason": "typed twice"})
c.eq(cn[0], 200, f"cancel with a reason ({message(cn[1])})")
c.eq(D(must(a.get(f"{CU}/{six['id']}"), "six")["current_outstanding"]), D(0), "cancelling reverses the journal: OB6 owes nothing")
csv2 = f"PartyCode,BillNumber,BillDate,DueDate,Amount,Narration\n{six['code']},OLD-9,{today().isoformat()},,700,\n".encode()
chk = a.upload(f"{CU}/opening-bills/import-file", "ob.csv", csv2, {"apply": "false"})
c.eq(chk[0], 200, f"file check ({message(chk[1])})")
c.eq(D(must(a.get(f"{CU}/{six['id']}"), "six")["current_outstanding"]), D(0), "the check wrote nothing")
app = a.upload(f"{CU}/opening-bills/import-file", "ob.csv", csv2, {"apply": "true"})
c.eq(app[0], 200, f"file apply ({message(app[1])})")
c.eq(D(must(a.get(f"{CU}/{six['id']}"), "six")["current_outstanding"]), D(700), "apply posted the bill: OB6 owes 700")
c.done()
