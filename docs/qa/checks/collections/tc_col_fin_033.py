"""TC-FIN-033: one receipt from a parent closes bills of three shops."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_fin_033")
a = admin()
sc = Scene(a)
parent = sc.customer()
shops = [sc.customer(parent_customer_id=parent["id"]) for _ in range(3)]
with counter(a):
    bills = [sc.bill(shops[0], "1"), sc.bill(shops[1], "2"), sc.bill(shops[2], "3")]  # 118, 236, 354
amounts = [D("118.00"), D("236.00"), D("354.00")]
c.eq([D(b["grand_total"]) for b in bills], amounts, "set-up: shop bills of 118.00, 236.00 and 354.00")
day = today().isoformat()


def statement(customer: dict) -> list[dict]:
    """Return today's statement lines of a customer."""
    return must(a.get(f"{CU}/{customer['id']}/statement?from_date={day}&to_date={day}"), "statement")["lines"]


def receipt_lines(customer: dict, number: str) -> list[dict]:
    """Return the statement lines carrying one receipt number."""
    return [x for x in statement(customer) if x["reference_number"] == number]


# 1, 3
c.eq([position(a, s) for s in shops], [(x, D("0")) for x in amounts], "step 1: each shop owes its own bill")
listed = rows_of(a.get(f"{RC}/outstanding?customer_id={parent['id']}&with_shops=true"))
c.eq({r["invoice_id"] for r in listed}, {b["id"] for b in bills}, "step 3: the three shops' bills are listed under the parent")
c.eq({r["party_code"] for r in listed}, {s["code"] for s in shops}, "each with its shop's code")
c.eq(rows_of(a.get(f"{RC}/outstanding?customer_id={parent['id']}")), [], "without the shops flag the parent's own list is empty")
# 4
st, body = receipt(a, parent, "1000.00", list(zip(bills, ["118.00", "236.00", "354.00"])))
c.eq(st, 201, "step 4: one receipt in the parent's name")
r = data(body)
c.eq((D(r["amount"]), D(r["allocated_amount"]), D(r["unallocated_amount"])), (D("1000.00"), D("708.00"), D("292.00")), "1,000.00 of which 708.00 set against bills and 292.00 not")
c.eq(r["party_id"], parent["id"], "in the parent's name")
# 5
for shop, bill, amount in zip(shops, bills, amounts):
    c.eq(position(a, shop), (D("0"), D("0")), f"step 5: shop {shop['code']} owes nothing")
    lines = receipt_lines(shop, r["settlement_number"])
    c.eq(len(lines), 1, f"its statement has one line for the parent's receipt")
    if lines:
        c.eq(D(lines[0]["credit"]), amount, "for its own bill's amount")
        c.ok(parent["name"] in str(lines[0]["remarks"]) or parent["code"] in str(lines[0]["remarks"]), "saying Paid by the parent", lines[0]["remarks"])
c.eq(position(a, parent), (D("0"), D("292.00")), "the parent holds 292.00 on account")
plines = receipt_lines(parent, r["settlement_number"])
c.eq(len(plines), 1, "the parent's statement has one line for the receipt")
if plines:
    # case text: the statement moves only the balance owed, so an on-account line is 0.00 / 0.00
    c.eq((D(plines[0]["debit"]), D(plines[0]["credit"])), (D("0"), D("0")), "the on-account line moves no balance (case text says 250.00)")
    c.eq(D(must(a.get(f"{CU}/{parent['id']}/statement?from_date={day}&to_date={day}"), "statement")["unapplied_advance"]), D("292.00"), "the statement header carries the 292.00 held on account")
# 6
c.eq({x["party_code"] for x in must(a.get(f"{RC}/{r['id']}"), "read")["allocations"]}, {s["code"] for s in shops}, "step 6: each allocation names its shop")
# 7
with counter(a):
    extra = sc.bill(shops[0], "1")  # 118.00 on the first shop
st, body = a.post(f"{RC}/{r['id']}/allocate", {"invoice_id": extra["id"], "amount": "118.00", "paid_for_customer_id": shops[0]["id"]})
c.eq(st, 200, "step 7: the left-over is applied to a new bill of the first shop")
if st == 200:
    c.eq(D(data(body)["unallocated_amount"]), D("174.00"), "174.00 left not set against a bill")
else:
    c.ok(False, "apply refused", message(body))
# 8
c.eq(position(a, shops[0]), (D("0"), D("0")), "step 8: the first shop owes nothing again")
c.eq(position(a, parent), (D("0"), D("174.00")), "the parent holds 174.00 on account")
# 9
with counter(a):
    parent_bill = sc.bill(parent, "1")
    second = sc.bill(shops[1], "1")
own = rows_of(a.get(f"{RC}/outstanding?customer_id={shops[1]['id']}&with_shops=true"))
c.eq({x["invoice_id"] for x in own}, {second["id"]}, "step 9: a shop's own receipt lists only that shop's bills")
c.ok(parent_bill["id"] not in {x["invoice_id"] for x in own}, "not the parent's")
# 10
st, body = a.post(f"{RC}/{r['id']}/reverse", {"reason": "check"})
c.eq(st, 200, "step 10: the parent's receipt is reversed")
c.eq(data(body)["status"], "REVERSED", "it reads Reversed")
c.eq(
    [position(a, s) for s in shops],
    [(D("236.00"), D("0")), (D("354.00"), D("0")), (D("354.00"), D("0"))],
    "every shop owes its bills again in full (the first and second also hold the new 118.00 bills)",
)
c.eq(position(a, parent)[0], D("118.00"), "the parent owes only its own new bill")
c.eq(position(a, parent)[1], D("0"), "the parent holds nothing on account")
c.done()
