"""Probe (round 12): a text the record needs is not satisfied by spaces.

Every inventory request that asks for a reason, a reference or a batch
number is sent one made only of spaces, and one sent as a number; each is
a 422 that leaves the record as it was, never a 500 and never a save.
"""
from _inv import *

c = Check("p_blank_text")
w = World()
store = client("store")
a, b2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
med = w.product("M", goods_type="MEDICINE")
w.stock_in(a["id"], p["id"], 100, 10)
base = {"branch_id": w.branch_id, "warehouse_id": a["id"], "product_id": p["id"], "transaction_date": w.today}
ST = f"{INV}/stock-transfers"
RP = f"{INV}/repacks"
REQ = f"{INV}/adjustment-requests"
BLANK = "   "


def refused(label: str, answer: tuple[int, object]) -> None:
    """Must be a 422."""
    c.ok(answer[0] == 422, f"{label} is refused", (answer[0], message(answer[1])))


# ---- a transfer document withdrawn for no reason ------------------------
t = must(w.admin.post(ST, {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"],
                           "lines": [{"product_id": p["id"], "quantity": "5"}]}), "transfer")
refused("cancelling a transfer with a reason of spaces", w.admin.post(f"{ST}/{t['id']}/cancel", {"reason": BLANK}))
refused("cancelling a transfer with a reason that is a number", w.admin.post(f"{ST}/{t['id']}/cancel", {"reason": 7}))
refused("cancelling a transfer with no reason", w.admin.post(f"{ST}/{t['id']}/cancel", {}))
st, b = w.admin.get(f"{ST}/{t['id']}")
c.eq(data(b)["status"], "DRAFT", "the transfer is still a draft")
st, b = w.admin.post(f"{ST}/{t['id']}/cancel", {"reason": "  wrong warehouse  "})
c.eq(st, 200, "a real reason withdraws it")
c.eq(data(b)["cancel_reason"], "wrong warehouse", "and is kept without the spaces around it")

# ---- a repack reversed for no reason, a batch named with spaces -----------
r = must(w.admin.post(RP, {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"], "lines": [
    {"kind": "CONSUME", "product_id": p["id"], "quantity": "2"},
    {"kind": "PRODUCE", "product_id": p["id"], "quantity": "2"}]}), "repack")
refused("reversing a repack with a reason of spaces", w.admin.post(f"{RP}/{r['id']}/cancel", {"reason": BLANK}))
refused("reversing a repack with a reason that is a number", w.admin.post(f"{RP}/{r['id']}/cancel", {"reason": 7}))
st, b = w.admin.get(RP)
c.eq(next(row for row in data(b) if row["id"] == r["id"])["status"], "POSTED", "the repack still stands")
st, b = w.admin.post(f"{RP}/{r['id']}/cancel", {"reason": " miscounted "})
c.eq(st, 200, "a real reason reverses it")
c.eq(data(b)["cancel_reason"], "miscounted", "and is kept without the spaces around it")
answer = w.admin.post(RP, {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"], "lines": [
    {"kind": "CONSUME", "product_id": p["id"], "quantity": "1"},
    {"kind": "PRODUCE", "product_id": med["id"], "quantity": "1", "batch_number": BLANK, "expiry_date": "2031-01-31"}]})
refused("producing into a batch named with spaces", answer)
st, b = w.admin.get(f"/api/v1/batch-serial/batches?product_id={med['id']}")
c.ok(st != 200 or not [row for row in data(b) if not str(row.get("batch_number", "x")).strip()], "no batch with an empty number was opened", data(b) if st == 200 else st)
c.eq(w.qty(p["id"], a["id"]), D(100), "and nothing was consumed")

# ---- a request turned down for no reason ---------------------------------
held = must(store.post(REQ, {"kind": "WRITE_OFF", "write_off": {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": f"BT{w.tag}"}}), "request")
refused("rejecting a request with a reason of spaces", w.admin.post(f"{REQ}/{held['id']}/reject", {"reason": BLANK}))
refused("rejecting a request with a reason that is a number", w.admin.post(f"{REQ}/{held['id']}/reject", {"reason": 7}))
st, b = w.admin.get(f"{REQ}?status=PENDING")
c.ok(any(row["id"] == held["id"] for row in data(b)), "the request still waits")
c.eq(w.admin.post(f"{REQ}/{held['id']}/reject", {"reason": "not damaged"})[0], 200, "a real reason turns it down")

# ---- references and reasons on the stock writes --------------------------
for label, path, body in (
    ("a write-off with a reason of spaces", "write-offs", {**base, "quantity": "1", "reason": BLANK, "reference_number": f"BW{w.tag}"}),
    ("an adjustment with a reason code of spaces", "adjustments", {**base, "quantity": "1", "reason_code": BLANK, "reference_number": f"BA{w.tag}"}),
    ("opening stock with a reference of spaces", "opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": BLANK,
                                                                 "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "10"}]}),
    ("opening stock with a reference of one letter and spaces", "opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": " X ",
                                                                                "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "10"}]}),
):
    refused(label, w.admin.post(f"{INV}/{path}", body))
import json  # noqa: E402

refused("an opening-stock import with a reference of spaces", w.admin.upload(f"{INV}/opening-stock/import", "os.json", b"{}", fields={"format": "json", "payload": json.dumps({
    "branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": BLANK,
    "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "10"}]})}))
c.eq(w.qty(p["id"], a["id"]), D(100), "none of them moved stock")

# a movement's reference is optional: spaces are nothing typed, and it is numbered from its series
for label, path, body in (
    ("a write-off", "write-offs", {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": BLANK}),
    ("an adjustment", "adjustments", {**base, "quantity": "1", "reference_number": BLANK}),
    ("a quarantine hold", "quarantine", {**base, "quantity": "1", "action": "HOLD", "reference_number": BLANK}),
    ("a transfer", "transfers", {"branch_id": w.branch_id, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "product_id": p["id"],
                                 "quantity": "1", "transaction_date": w.today, "reference_number": BLANK}),
):
    st, b = w.admin.post(f"{INV}/{path}", body)
    c.ok(st == 201, f"{label} with a reference of spaces is taken as one with none", (st, message(b)))
blank_refs = [row for row in w.ledger(p["id"]) if not str(row.get("reference_number") or "").strip()]
c.eq(len(blank_refs), 0, "and every movement carries a number from its series")

# a batch number of spaces on an opening line is no batch at all
st, b = w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": f" bo{w.tag} ",
                                              "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "10", "batch_number": BLANK}]})
c.eq(st, 201, "an opening line whose batch is spaces is saved")
c.eq(data(b)["reference_number"], f"BO{w.tag}", "under its reference without the spaces around it")
c.eq(data(b)["lines"][0]["batch_number"], None, "and names no batch")
c.done()
