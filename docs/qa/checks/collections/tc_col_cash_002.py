"""TC-CASH-002 (server half): a Cashier records a receipt, with a searchable party picker."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_cash_002")
a = admin()
cashier = admin("cashier")
sc = Scene(a)
till = sc.customer(name=f"Till Customer {sc.tag}")
# the old picker read GET /customers, which a Cashier may not
c.eq(cashier.get(f"{CU}?page_size=5")[0], 403, "a Cashier holds no CUSTOMER_VIEW (the reason the picker has its own route)")
st, body = cashier.get(f"{RC}/parties?search={till['code'][:6]}")
c.eq(st, 200, "step 1: the party picker answers for a Cashier")
c.ok(till["id"] in {r["id"] for r in data(body)}, "step 2: part of the code finds the customer", data(body))
st, body = cashier.get(f"{RC}/parties?search=Till%20Customer%20{sc.tag}")
c.ok(till["id"] in {r["id"] for r in data(body)}, "part of the name finds it too")
row = next((r for r in data(body) if r["id"] == till["id"]), {})
c.eq((row.get("code"), row.get("name")), (till["code"], till["name"]), "each option carries its code and name")
st, body = cashier.get(f"{RC}/parties?search=zzzz-nobody")
c.eq((st, data(body)), (200, []), "a search matching nobody gives an empty list")
st, body = receipt(cashier, till, "100.00", method="CASH")
c.eq(st, 201, "step 3: the receipt is recorded")
r = data(body)
c.eq((D(r["amount"]), r["method"], r["status"]), (D("100.00"), "CASH", "POSTED"), "100.00, cash, posted")
listed = all_rows(cashier, f"{RC}?customer_id={till['id']}")
c.eq([x["id"] for x in listed], [r["id"]], "and listed")
c.eq(position(a, till), (D("0"), D("100.00")), "the customer holds 100.00 on account")
c.done()
