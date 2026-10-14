"""TC-LOT-010: billing without stock: the confirmation, the report, settlement on purchase."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_010")
api = lot_admin(); c = Ctx(api)
q = c.product("P", batch=False, allow_negative_stock=True)
c.receive([{"product": q, "qty": 8, "rate": 30}])
lot_settings(api, True)
try:
    made = c.note([{"product": q, "qty": 10}])
    nid = made["note"]["id"]
    # (1) refused with the question.
    s, body = c.dispatch(nid)
    err = (body or {}).get("error", {}) if isinstance(body, dict) else {}
    c0.ok(s == 422 and (err.get("details") or {}).get("confirm") == "BILL_WITHOUT_STOCK",
          "dispatch without confirming is refused with details.confirm = BILL_WITHOUT_STOCK", (s, message(body)[:250]))
    # (2) confirmed.
    s, body = c.dispatch(nid, confirm=True)
    c0.eq(s, 200, f"confirmed dispatch accepted ({message(body)})")
    # (3) the report.
    shorts = [r for r in rows_of(api.get(f"{INV}/lot-shortfalls")) if r["product_id"] == q["id"]]
    c0.eq(len(shorts), 1, "one bill waiting for its cost")
    if shorts:
        r = shorts[0]
        c0.eq((D(r["quantity"]), D(r["quantity_waiting"]), D(r["unit_cost"])), (D(2), D(2), D(30)),
              "2 units waiting at the cost used, 30.00")
        c0.eq(r["warehouse_id"], c.warehouse["id"], "in the warehouse")
        c0.eq(r["delivery_note_id"], nid, "naming the note")
        c0.ok(r.get("confirmed_by"), "who confirmed is recorded", r)
    c0.eq(c.stock(q), D(0), "the 8 held have left the lot")
    # (4)-(5) receive 10 @35: the receipt covers the 2; a correction journal posts.
    g = c.receive([{"product": q, "qty": 10, "rate": 35}])
    shorts = [r for r in rows_of(api.get(f"{INV}/lot-shortfalls")) if r["product_id"] == q["id"]]
    c0.eq(shorts, [], "the report is empty once the receipt covered the units")
    c0.eq(c.stock(q), D(8), "the receipt's lot holds 10 less the 2 covered")
    rows = rows_of(api.get(f"/api/v1/finance/journal-entries?search={g['grn_number']}-LS&page_size=20"))
    mine = [e for e in rows if str(e.get("reference_number", "")).endswith("-LS") and g["grn_number"] in e["reference_number"]]
    c0.eq(len(mine), 1, f"a correction journal {g['grn_number']}-LS was posted")
    if mine:
        c0.eq(D(mine[0].get("total_debit", mine[0].get("total_amount"))), D(10), "for the lot's cost less cost used: 2 x (35 - 30) = 10")
finally:
    lot_settings(api, False)
c0.done()
