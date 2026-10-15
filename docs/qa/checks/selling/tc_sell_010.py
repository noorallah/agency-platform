"""TC-SELL-010: a delivery ships the deal the order struck."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_010")
a = admin()
sc = Scene(a, stock="100")
order = new_order(sc, "12", approve=True, line={"unit_price": "84", "discount_percent": "2.5"})
ol = must(a.get(f"{SO}/{order['id']}"), "order")["lines"][0]
c.eq((D(ol["unit_price"]), D(ol["discount_percent"])), (D(84), D("2.5")), "the order struck 84 less 2.5%")
# the customer's standing rate changes after the order: the note must not follow
must(a.put(f"/api/v1/customers/{sc.customer['id']}", {
    "code": sc.customer["code"], "name": sc.customer["name"],
    "customer_type": sc.customer["customer_type"], "currency_code": "INR",
    "default_discount_percent": "10"}), "customer standing discount")
note = new_note(sc, order, "5", dispatch=True)
nl = must(a.get(f"{DN}/{note['id']}"), "note")["lines"][0]
c.eq((D(nl["unit_price"]), D(nl["discount_percent"])), (D(84), D("2.5")), "the note carries the order's deal")
bill = bill_note(sc, note, "5")
c.eq(D(bill["grand_total"]), D("483.21"), "and the bill totals 483.21")
c.done()
