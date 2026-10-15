"""TC-CUST-011 (second): shipping address the same as billing, or different (API half: the default flags; the bill print and the Ship to defaults are screen-only)."""
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

c = Check("tc_cust_011b")
a = api()
t = tag()
def addr(line: str, **flags: bool) -> dict:
    return {"address_type": "BILLING", "address_line1": line, "city": "Chennai", "state": "Tamil Nadu", "country": "IN", "postal_code": "600001", **flags}
cu = must(a.post(CU, {"code": f"SH{t}", "name": f"Ship {t}", "customer_type": "BUSINESS", "currency_code": "INR",
                      "addresses": [addr("1 Bill Road", is_default_billing=True, is_default_shipping=True)]}), "customer")
def flags(row):
    return sorted((x["address_line1"], x["is_default_billing"], x["is_default_shipping"]) for x in row["addresses"])
c.eq(flags(must(a.get(f"{CU}/{cu['id']}"), "c")), [("1 Bill Road", True, True)], "a lone address is billing and shipping")
whole = lambda row, **ch: echo("CustomerUpdate", row, {"addresses": "CustomerAddressInput", "contacts": "CustomerContactInput"}, **ch)
row = must(a.get(f"{CU}/{cu['id']}"), "c")
first = whole(row)["addresses"][0]
st, body = a.put(f"{CU}/{cu['id']}", whole(row, addresses=[{**first, "is_default_shipping": False}, addr("2 Ship Lane", is_default_shipping=True)]))
c.eq(st, 200, f"a second address ticked for shipping ({message(body)})")
row = must(a.get(f"{CU}/{cu['id']}"), "c")
c.eq(flags(row), [("1 Bill Road", True, False), ("2 Ship Lane", False, True)], "billing stays on the first, shipping moves to the second")
first = next(x for x in whole(row)["addresses"] if x["address_line1"] == "1 Bill Road")
second = next(x for x in whole(row)["addresses"] if x["address_line1"] == "2 Ship Lane")
st, body = a.put(f"{CU}/{cu['id']}", whole(row, addresses=[{**first, "is_default_shipping": True}, {**second, "is_default_shipping": False}]))
c.eq(st, 200, f"back to the same as billing ({message(body)})")
c.eq(flags(must(a.get(f"{CU}/{cu['id']}"), "c")), [("1 Bill Road", True, True), ("2 Ship Lane", False, False)], "the first is ticked for both, the second for neither")
two_ = whole(row, addresses=[{**first, "is_default_shipping": True}, {**second, "is_default_shipping": True}])
st, body = a.put(f"{CU}/{cu['id']}", two_)
c.ok(st in (409, 422) or sum(1 for x in must(a.get(f"{CU}/{cu['id']}"), "c")["addresses"] if x["is_default_shipping"]) == 1, "two default shipping addresses are refused or collapsed to one", f"{st} {message(body)}")
c.done()
