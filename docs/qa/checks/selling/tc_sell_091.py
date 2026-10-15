"""TC-SELL-091: cancelling a draft counter bill withdraws its order and note and frees its stock."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_091")
a = admin()
sc = Scene(a, stock="100")
pid = sc.product["id"]


def chain_of(customer: dict) -> tuple[list, list]:
    """Return the customer's orders and notes."""
    cid = customer["id"]
    return (rows_of(a.get(f"{SO}?customer_id={cid}&page_size=50")),
            rows_of(a.get(f"{DN}?customer_id={cid}&page_size=50")))


with counter(a):
    bill = must(a.post(SI, sc.bill_body("7")), "counter bill")
    c.eq(stock(a, pid), (D(100), D(7)), "the draft reserves 7")
    other = new_order(sc, "3", approve=True)
    c.eq(stock(a, pid)[1], D(10), "another order reserves its own 3")
    gone = a.post(f"{SI}/{bill['id']}/cancel", {"reason": "customer left"})
    c.eq(gone[0], 200, f"cancel accepted ({message(gone[1])})")
    c.eq(stock(a, pid), (D(100), D(3)), "7 freed, the other order's 3 stays reserved")
    orders, notes = chain_of(sc.customer)
    mine = [o for o in orders if o["id"] != other["id"]]
    c.ok(mine and all(o["status"] == "CANCELLED" for o in mine), "the bill's order reads CANCELLED", [o["status"] for o in mine])
    c.ok(notes and all(n["status"] == "CANCELLED" for n in notes), "its note reads CANCELLED", [n["status"] for n in notes])
    kinds = [r["transaction_type"] for r in ledger(a, pid) if r["reference_number"] == (mine[0]["order_number"] if mine else "")]
    c.eq(kinds[:2], ["RESERVE", "UNRESERVE"], "the ledger shows RESERVE then UNRESERVE against the order")
    held = must(a.post(SI, sc.bill_body("7")), "second bill")
    c.eq(a.post(f"{SI}/{held['id']}/hold", {"note": "wait"})[0], 200, "held")
    c.eq(stock(a, pid)[1], D(10), "the held bill keeps its 7")
    c.eq(a.post(f"{SI}/{held['id']}/cancel", {"reason": "dropped while held"})[0], 200, "cancel while held")
    c.eq(stock(a, pid)[1], D(3), "freed again")
    c.eq(must(a.get(f"{SI}/{held['id']}"), "bill")["status"], "CANCELLED", "cancelled")
c.done()
