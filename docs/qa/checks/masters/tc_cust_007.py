"""TC-CUST-007: a customer's money terms need CUSTOMER_MANAGE_SETTINGS (Seller creates, Sales Manager edits and imports; Firm admin may). The Firm Manager step is not driven: no Firm Manager account in the set-up."""
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

c = Check("tc_cust_007")
a, s, m = api(), api("seller"), api("manager")
t = tag()
terms = {"credit limit": {"credit_limit": "50000"}, "an opening balance": {"opening_balance": "1500"},
         "credit days": {"payment_terms_days": 30}, "cash-discount terms": {"cash_discount_percent": "2", "cash_discount_days": 10},
         "a standing discount": {"default_discount_percent": "12.5"}}
def mk(who, code, **x):
    return who.post(CU, {"code": code, "name": f"Terms {code}", "customer_type": "BUSINESS", "currency_code": "INR", **x})
c.eq(mk(s, f"T0{t}")[0], 201, "seller saves a customer with no terms")
for i, (what, extra) in enumerate(terms.items()):
    r = mk(s, f"T{i + 1}{t}", **extra)
    c.ok(r[0] == 403 and what in message(r[1]) and "CUSTOMER_MANAGE_SETTINGS" in message(r[1]), f"seller sending {what}: 403 naming the permission", f"{r[0]} {message(r[1])}")
    c.eq(rows_of(a.get(f"{CU}?search=T{i + 1}{t}")), [], f"{what}: nothing created")
zero = mk(s, f"TZ{t}", credit_limit="0", opening_balance="0", payment_terms_days=0, cash_discount_percent="0", cash_discount_days=0, default_discount_percent="0")
c.eq(zero[0], 201, f"every term sent as zero is not a term ({message(zero[1])})")
d = described(a)
for label, change in (("credit days", {"payment_terms_days": 45}), ("credit limit", {"credit_limit": "60000"}), ("standing discount", {"default_discount_percent": "9"})):
    got = must(a.get(f"{CU}/{d['id']}"), "customer")
    r = m.put(f"{CU}/{d['id']}", echo("CustomerUpdate", got, {"addresses": "CustomerAddressInput", "contacts": "CustomerContactInput"}, **change))
    c.ok(r[0] == 403 and "CUSTOMER_MANAGE_SETTINGS" in message(r[1]), f"sales manager changing {label}: 403", f"{r[0]} {message(r[1])}")
got = must(a.get(f"{CU}/{d['id']}"), "customer")
r = m.put(f"{CU}/{d['id']}", echo("CustomerUpdate", got, {"addresses": "CustomerAddressInput", "contacts": "CustomerContactInput"}, payment_terms_days=0))
c.ok(r[0] == 403, "setting a term to 0 is a change and is refused", f"{r[0]} {message(r[1])}")
r = m.put(f"{CU}/{d['id']}", echo("CustomerUpdate", got, {"addresses": "CustomerAddressInput", "contacts": "CustomerContactInput"}, name="Renamed by manager " + t))
c.eq(r[0], 200, f"the same record with only the name changed saves ({message(r[1])})")
after = must(a.get(f"{CU}/{d['id']}"), "after")
c.eq((after["payment_terms_days"], D(after["credit_limit"]), D(after["default_discount_percent"])), (30, D(50000), D("7.5")), "the terms are as they were")
imp = m.post(f"{CU}/import", {"records": [{"code": f"TI{t}", "name": "Import terms", "customer_type": "BUSINESS", "currency_code": "INR", "credit_limit": "5000"}]})
c.ok(imp[0] == 403 or (imp[0] == 200 and "CUSTOMER_MANAGE_SETTINGS" in str(imp[1])), "batch import with a credit limit by the sales manager is refused", f"{imp[0]} {message(imp[1])}")
c.eq(rows_of(a.get(f"{CU}?search=TI{t}")), [], "and creates nothing")
r = a.put(f"{CU}/{d['id']}", echo("CustomerUpdate", after, {"addresses": "CustomerAddressInput", "contacts": "CustomerContactInput"}, payment_terms_days=45))
c.eq(r[0], 200, f"the Firm admin changes payment terms ({message(r[1])})")
c.done()
