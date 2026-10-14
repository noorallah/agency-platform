"""TC-LOT-003: a receipt makes a lot for each line; a moved lot stops its cancel."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_003")
api = lot_admin(); c = Ctx(api)
p, q = c.product("B"), c.product("P", batch=False)
e_a, e_b = today() + timedelta(days=200), today() + timedelta(days=180)
g = c.receive([{"product": p, "qty": 10, "rate": 40, "batch": "LOTA", "expiry": e_a, "mrp": 150},
               {"product": p, "qty": 5, "rate": 42, "batch": "LOTB", "expiry": e_b, "mrp": 150}])
grn = g["grn_number"]
rows = lotmap(c, p)
c0.eq(sorted(rows), ["LOTA", "LOTB"], "one lot row per receipt line")
for key, qty, rate, exp in (("LOTA", "10.0000", "40.000000", e_a), ("LOTB", "5.0000", "42.000000", e_b)):
    r = rows.get(key, {})
    c0.eq((r.get("quantity"), r.get("rate"), r.get("expiry_date"), D(r.get("mrp"))),
          (qty, rate, exp.isoformat(), D(150)), f"{key} quantity, cost, expiry, MRP")
    c0.ok(str(r.get("lot_reference", "")).startswith("LOT-"), f"{key} carries a LOT reference", r.get("lot_reference"))
c0.eq(len({r.get("lot_reference") for r in rows.values()}), 2, "two different LOT references")
a = batch_of(c, p, "LOTA")
s, t = trail(api, a["id"])
t = data(t) if s == 200 else {}
first = (t.get("events") or [{}])[0]
c0.eq((first.get("document_type"), first.get("document_number"), first.get("document_date")),
      ("GOODS_RECEIPT", grn, today().isoformat()), "the lot's source is the receipt's number and date")
c0.eq(t.get("source_type"), "GOODS_RECEIPT", "lot source type")

# (2) an unbatched untracked product: one lot, a reference, no printed batch.
c.receive([{"product": q, "qty": 8, "rate": 30}])
qrows = c.lots(q)
c0.eq(len(qrows), 1, "untracked receipt makes one lot")
if qrows:
    c0.ok(str(qrows[0]["lot_reference"]).startswith("LOT-"), "untracked lot has a LOT reference", qrows[0]["lot_reference"])
    c0.ok(not qrows[0]["batch_number"], "no printed batch on the untracked lot", qrows[0]["batch_number"])
    c0.eq((qrows[0]["quantity"], qrows[0]["rate"]), ("8.0000", "30.000000"), "untracked lot qty and cost")
qb = c.batches(q)
c0.eq(len(qb), 1, "one batch row behind the untracked lot")
if qb:
    qt = data(trail(api, qb[0]["id"])[1])
    c0.eq(qt.get("has_printed_batch"), False, "trail says no printed batch")

# (4) sell 1 from LOTA; cancelling the receipt is refused; an untouched receipt cancels.
c.sell([{"product": p, "qty": 1, "picks": [(a["id"], 1)]}])
refusal = api.post(f"/api/v1/goods-receipts/{g['id']}/cancel", {"reason": "check"})
c0.ok(refusal[0] == 422 and "moved" in message(refusal[1]).lower(), "cancel of a receipt whose lot moved is refused", refusal)
c0.ok("LOT-" in message(refusal[1]) and grn in message(refusal[1]), "the refusal names the receipt and a lot", message(refusal[1]))
named = message(refusal[1])
c0.ok(rows["LOTA"]["lot_reference"] in named,
      f"the refusal names the lot that moved ({rows['LOTA']['lot_reference']}, LOTA), not another", named[:200])
g2 = c.receive([{"product": q, "qty": 3, "rate": 31}])
ok = api.post(f"/api/v1/goods-receipts/{g2['id']}/cancel", {"reason": "check"})
c0.eq(ok[0], 200, "an untouched receipt cancels")
c0.eq(c.stock(q), D(8), "the cancelled receipt's lot went with it (stock back to 8)")
c0.done()
