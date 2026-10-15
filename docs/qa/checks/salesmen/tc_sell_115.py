"""TC-SELL-115: what the Salesman box starts on, and what a note and a bill take from the order."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_sell_115")
a = admin()
ex = admin("exec")
held = state()
sc = Scene(a, stock="200")
exec_uid = user_id_of(held["accounts"]["exec"]["email"])

# The executive's tie belongs to one entry at a time: clear any older tie first.
for row in all_rows(a, f"{SM}?search=Asha"):
    if row.get("user_id") == exec_uid:
        a.put(f"{SM}/{row['id']}", {"user_id": None, "is_active": False})
asha = sc.salesman(f"Asha {sc.tag}", user_id=exec_uid)
bala = sc.salesman(f"Bala {sc.tag}")
chitra = sc.salesman(f"Chitra {sc.tag}")
c1 = sc.new_customer(salesman_id=bala["id"])
c2 = sc.new_customer()
c3 = sc.new_customer()
c4 = sc.new_customer(salesman_id=bala["id"])
# Bala covers the round (not primary), so as account manager he is the start.
route = make_route(a, sc.tag + "R", [(chitra["id"], True), (bala["id"], False)])
must(a.put(f"{T}/{route['id']}/customers", {"customer_ids": [c1["id"], c2["id"]]}), "customers on the round")
# A round Bala does not cover: the account manager is passed over, as on save.
route2 = make_route(a, sc.tag + "Q", [(chitra["id"], True)])
must(a.put(f"{T}/{route2['id']}/customers", {"customer_ids": [c4["id"]]}), "customer on the second round")


def start(api: Api, customer: dict) -> tuple[str | None, str]:
    """Return the salesman and the source the box starts on."""
    status, body = api.get(f"{SM}/starting-choice?customer_id={customer['id']}")
    if status != 200:
        raise SystemExit(f"PRECONDITION starting-choice {status} {message(body)}")
    got = data(body)
    return got.get("salesman_id"), str(got.get("source"))


for label, cust in (("C01", c1), ("C02", c2), ("neither", c3)):
    c.eq(start(ex, cust)[0], asha["id"], f"as Asha's user the box starts on Asha for {label}")
c.eq(start(a, c1)[0], bala["id"], "untied user, account manager customer: Bala")
c.eq(start(a, c2)[0], chitra["id"], "untied user, customer on the round: Chitra")
c.eq(start(a, c3)[0], None, "untied user, customer with neither: blank")
c.eq(start(a, c4)[0], chitra["id"], "account manager not on the customer's round: the round's primary")

status, body = ex.post(SO, sc.order_body("1", customer=c1, salesman_id=chitra["id"]))
c.eq(status, 201, f"Chitra can be picked instead and saves ({message(body)[:150]})")
if status == 201:
    c.eq(data(body).get("salesman_id"), chitra["id"], "the order keeps Chitra")

# An order naming Chitra: the note and the bill take her and are not asked.
bill = sell(sc, chitra["id"], "2", "100", today(), customer=c1)
c.eq(bill.get("salesman_id"), chitra["id"], "the bill takes Chitra from the order")
note = must(a.get(f"{DN}/{bill['note_id']}"), "note")
c.eq(note.get("salesman_id"), chitra["id"], "the delivery note takes Chitra from the order")

# An inactive entry is never the starting choice.
must(a.put(f"{SM}/{asha['id']}", {"is_active": False}), "deactivate Asha")
c.ok(start(ex, c3)[0] != asha["id"], "an inactive entry is not the starting choice", start(ex, c3))
c.eq(start(ex, c1)[0], bala["id"], "with Asha inactive the box falls to the account manager")
c.done()
