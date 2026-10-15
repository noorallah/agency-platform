"""TC-FIN-031: a bill collector sees only the bills handed to him."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_fin_031")
a = admin()
col1 = admin("collector1")
col2 = admin("collector2")
c1, c2 = collector_ids()
sc = Scene(a)
cu1, cu2 = sc.customer(), sc.customer()
with counter(a):
    b1, b2, b3 = (sc.bill(cu1, "10") for _ in range(3))  # 1,180.00 each
    d1 = sc.bill(cu2, "10")


def mine(api: Api) -> dict[str, dict]:
    """Return a collector's own list, restricted to this check's two customers."""
    got = all_rows(api, f"{COL}/my-bills", 50)
    return {r["invoice_id"]: r for r in got if r["customer_id"] in (cu1["id"], cu2["id"])}


# 1
c.eq(hand(a, [b1["id"]], c1)[0], 201, "step 1: the first bill goes to the first collector")
c.eq(hand(a, [b2["id"]], c2)[0], 201, "the second to the second collector")
# 3
got = mine(col1)
c.eq(set(got), {b1["id"], b2["id"], b3["id"]}, "step 3: three rows, all of the first customer; the second customer is not on the list")
c.eq(got[b1["id"]]["handed_to_me"], True, "the first bill is marked With me")
c.eq(got[b1["id"]]["handed_on"], today().isoformat(), "with the day it was handed over")
c.eq(got[b2["id"]]["handed_to_me"], False, "the second is Not handed to me")
c.eq(got[b3["id"]]["handed_to_me"], False, "so is the third")
c.eq((got[b2["id"]]["handover_id"], got[b2["id"]]["handed_on"]), (None, None), "the second bill does not say who carries it")
c.eq(D(got[b1["id"]]["outstanding"]), D("1180.00"), "the first bill owes 1,180.00")
# 4
got2 = mine(col2)
c.eq(set(got2), {b1["id"], b2["id"], b3["id"]}, "step 4: the second collector sees the same three rows")
c.eq(
    (got2[b1["id"]]["handed_to_me"], got2[b2["id"]]["handed_to_me"], got2[b3["id"]]["handed_to_me"]),
    (False, True, False),
    "with the second bill marked With me",
)
# 5
st, _ = receipt(a, cu1, "500.00", [(b1, "500.00")])
c.eq(st, 201, "step 5: the office records a part receipt")
c.eq(D(mine(col1)[b1["id"]]["outstanding"]), D("680.00"), "the first bill shows 680.00 still owing")
# 6
held = [h for h in all_rows(a, f"{COL}/handovers", 50) if h["invoice_id"] == b1["id"] and h["state"] == "OUT"]
c.eq(len(held), 1, "set-up for step 6: one handover is out")
c.eq(a.post(f"{COL}/handovers/take-back", {"handover_ids": [held[0]["id"]]})[0], 200, "step 6: the office takes the first bill back")
c.eq(mine(col1), {}, "his list holds none of those customers' bills")
# 7 the collector's reach
for what, status in (
    ("receipts", col1.get(RC)[0]),
    ("customers", col1.get(CU)[0]),
    ("the office's hand-over screen", col1.get(f"{COL}/handovers/bills")[0]),
):
    c.eq(status, 403, f"step 7: a Bill Collector is refused {what}")
c.eq(hand(col1, [b3["id"]], c1)[0], 403, "and cannot hand a bill to himself")
c.eq(col1.post(f"{COL}/handovers/take-back", {"handover_ids": [held[0]["id"]]})[0], 403, "or take one back")
c.done()
