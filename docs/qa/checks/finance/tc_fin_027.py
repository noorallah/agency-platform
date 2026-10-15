"""TC-FIN-027: a supplier switched off for TDS is deducted nothing; a figure typed on one bill changes that bill only; TCS flag; TDS on a receipt."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_027")
a = admin()
bs = buy.Scene(a)
vendor = bs.new_vendor(pan="AAACT1234A", default_tds_section="194C", tds_applicable=True, gst_registration=False)
bs.vendor = vendor
VU = f"/api/v1/vendors/{vendor['id']}"
PI = buy.PI
c.eq(vendor["tds_applicable"], True, "step 1: Deduct TDS from this supplier is ticked")


def bill() -> dict:
    """Raise a bill of 40,000.00 before tax (400 x 100.00) from the supplier."""
    order = bs.order(qty="400")
    return must(a.post(PI, bs.bill_body(bs.receive(order, "400"))), "bill")


def owed(doc: dict) -> Decimal:
    """What the supplier is still owed on a bill."""
    return D(must(a.get(f"{PI}/{doc['id']}"), "bill")["amount_owed"])


b1 = bill()
c.eq(D(b1["grand_total"]), D("47200.00"), "a 40,000.00 bill is 47,200.00 with 18% GST")
prop = data(a.get(f"{PI}/{b1['id']}/tds-proposal")[1])
c.eq((prop["section"], D(prop["proposed"]), prop["switched_off"]), ("194C", D("800.00"), False), "step 1: the dialog proposes 800.00 under 194C")
must(a.post(f"{PI}/{b1['id']}/approve", {}), "approve 1")
r1 = must(a.get(f"{PI}/{b1['id']}"), "b1")
c.eq((D(r1["tds_amount"]), owed(b1)), (D("800.00"), D("46400.00")), "the bill deducts 800.00 and the supplier is owed 47,200.00 less 800.00 = 46,400.00")
t = tb(a)
c.ok(closing(t, "2700") <= D("-800.00"), "TDS Payable holds the 800.00 (a credit)", closing(t, "2700"))

# step 2: switch it off, then change only the name
st, ans = a.put(VU, {"code": vendor["code"], "name": vendor["name"], "tds_applicable": False})
c.eq(st, 200, "step 2: unticked and saved")
st, ans = a.put(VU, {"code": vendor["code"], "name": vendor["name"] + " renamed"})
c.eq(st, 200, "saved again with only the name changed")
v = must(a.get(VU), "vendor")
c.eq((v["tds_applicable"], v["default_tds_section"], v["name"].endswith("renamed")), (False, "194C", True), "after the second save the box is still unticked and the section still 194C")

b2 = bill()
prop = data(a.get(f"{PI}/{b2['id']}/tds-proposal")[1])
c.eq(prop["switched_off"], True, "step 3: the proposal says TDS is switched off for this supplier")
must(a.post(f"{PI}/{b2['id']}/approve", {}), "approve 2")
c.eq((D(must(a.get(f"{PI}/{b2['id']}"), "b2")["tds_amount"]), owed(b2)), (D("0.00"), D("47200.00")), "nothing deducted, the supplier is owed the whole bill")

b3 = bill()
must(a.post(f"{PI}/{b3['id']}/approve", {"tds_amount": "500.00"}), "approve 3")
r3 = must(a.get(f"{PI}/{b3['id']}"), "b3")
c.eq((D(r3["tds_amount"]), owed(b3)), (D("500.00"), D("46700.00")), "step 4: a typed 500.00 is deducted on this bill and the supplier is owed 46,700.00")

b4 = bill()
must(a.post(f"{PI}/{b4['id']}/approve", {}), "approve 4")
c.eq((D(must(a.get(f"{PI}/{b4['id']}"), "b4")["tds_amount"]), owed(b4)), (D("0.00"), D("47200.00")), "step 5: the next bill deducts nothing: the 500.00 was that bill's alone")
c.eq(must(a.get(VU), "vendor")["tds_applicable"], False, "and the supplier is still switched off")
c.eq(a.post(f"{PI}/{bill()['id']}/approve", {"tds_amount": "-5"})[0], 422, "a negative typed figure is refused")

# step 6: a customer's TCS flag survives a save
sc = Scene(a)
cust = sc.customer(tcs_applicable=True)
c.eq(cust["tcs_applicable"], True, "step 6: Collect TCS from this customer is ticked")
full = {"code": cust["code"], "name": cust["name"], "customer_type": cust["customer_type"], "currency_code": "INR"}
c.eq(a.put(f"{CU}/{cust['id']}", {**full, "tcs_applicable": False})[0], 200, "unticked and saved")
c.eq(must(a.get(f"{CU}/{cust['id']}"), "customer")["tcs_applicable"], False, "it is unticked when the customer is opened again")
c.eq(a.put(f"{CU}/{cust['id']}", {**full, "name": cust["name"] + " x"})[0], 200, "a save that changes only the name")
c.eq(must(a.get(f"{CU}/{cust['id']}"), "customer")["tcs_applicable"], False, "leaves it unticked")

# step 7: a receipt for the whole bill with 1% TDS under 194Q
with counter(a):
    sale = sc.bill(cust, "10")  # 1,180.00
before = tb(a)
st, ans = receipt(a, cust, "1180.00", [(sale, "1180.00")], method="BANK", tds_amount="11.80", tds_section="194Q")
c.eq(st, 201, "step 7: the receipt with 11.80 TDS under 194Q is recorded")
rcp = data(ans)
c.eq((D(rcp["amount"]), D(rcp["tds_amount"]), D(rcp["cash_amount"])), (D("1180.00"), D("11.80"), D("1168.20")), "the bill is settled 1,180.00; the bank receives 1,168.20")
after = tb(a)
c.eq((closing(after, "1010") - closing(before, "1010"), closing(after, "1100") - closing(before, "1100"), closing(after, "1400") - closing(before, "1400")), (D("1168.20"), D("-1180.00"), D("11.80")), "books: Dr Bank 1,168.20 / Dr TDS Receivable 11.80 / Cr Receivables 1,180.00")
c.eq(position(a, cust), (D("0.00"), D("0.00")), "the customer owes nothing on it")
c.done()
