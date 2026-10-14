"""TC-LOT-002: the one-way switch (a firm of its own, made for this run)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_002")
platform = client("platform", "lots")
info = new_average_firm(platform, "B")
admin = firm_admin(info)
c = Ctx(admin)
p, q = c.product("B"), c.product("P", batch=False)
c.receive([{"product": p, "qty": 10, "rate": 40, "batch": "LOTA", "expiry": today() + timedelta(days=200), "mrp": 150},
           {"product": p, "qty": 6, "rate": 44, "batch": "LOTB", "expiry": today() + timedelta(days=300), "mrp": 150}])
c.receive([{"product": q, "qty": 8, "rate": 30}])
c.receive([{"product": q, "qty": 2, "rate": 36}])        # q's average becomes 31.2


def valuation():
    """Return ({code: (qty, rate, value)}, books value, difference, journal count)."""
    rows = rows_of(admin.get(f"{INV}/reports/stock-valuation?page_size=100"))
    items = {r["product_code"]: (D(r["quantity"]), D(r["rate"]), D(r["value"])) for r in rows if r["row_type"] == "ITEM"}
    books = next((D(r["value"]) for r in rows if r["row_type"] == "BOOKS"), None)
    diff = next((D(r["value"]) for r in rows if r["row_type"] == "DIFFERENCE"), None)
    s, b = admin.get("/api/v1/finance/journal-entries?page_size=1")
    return items, books, diff, (b.get("pagination") or {}).get("total_records") if s == 200 else None


v0, books0, diff0, journals0 = valuation()
c0.ok(p["code"] in v0 and q["code"] in v0, "(1) both items are valued before the switch", list(v0))
# (2) switch on the day the preview suggests.
pv = must(admin.get(f"{INV}/lot-settings/switch-preview"), "preview")
pv = must(admin.get(f"{INV}/lot-settings/switch-preview?on={today().isoformat()}"), "preview today")
c0.eq(pv["refusals"], [], "the preview of today has no refusal")
s, body = admin.post(f"{INV}/lot-settings/switch", {"on": pv["on"]})
c0.eq(s, 200, f"(2) the switch succeeds ({message(body)})")
# (3) reopen the screen.
st = must(admin.get(f"{INV}/lot-settings"), "settings")
c0.eq((st["costing_method"], st["switched_on"]), ("BY_LOT", pv["on"]), "(3) By lot, from the switch day")
c0.eq(st["allow_billing_without_stock"], False, "(3) billing without stock reads off")
# (4) each batch is a lot; unbatched stock is one new lot (Carried forward) at the average.
la = {r["batch_number"] or r["lot_reference"]: r for r in c.lots(p)}
c0.eq(sorted((k, D(r["quantity"]), D(r["rate"])) for k, r in la.items()), [("LOTA", D(10), D("41.5")), ("LOTB", D(6), D("41.5"))],
      "(4) each batch is a lot, at the item's average (41.5; Average kept no batch cost)")
lq = c.lots(q)
c0.eq(len(lq), 1, "(4) the unbatched stock is one new lot")
if lq:
    c0.eq((D(lq[0]["quantity"]), D(lq[0]["rate"]), D(lq[0]["value"])), (D(10), D("31.2"), D("312")), "(4) at the item's average (31.2)")
    c0.ok(lq[0]["lot_reference"].startswith("LOT-") and not lq[0]["batch_number"], "(4) with a LOT reference, no printed batch")
    qb = next((b for b in c.batches(q)), None)
    if qb:
        c0.eq(data(trail(admin, qb["id"])[1]).get("source_type"), "CARRIED_FORWARD", "(4) source Carried forward")
v1, books1, diff1, journals1 = valuation()
c0.eq(v1, v0, "(4) totals per item are exactly what they were")
c0.eq(books1, books0, "(4) the Inventory account is exactly what it was")
c0.eq(journals1, journals0, "(4) no journal was posted")
# (5) a second switch.
s, body = admin.post(f"{INV}/lot-settings/switch", {"on": pv["on"]})
c0.ok(s in (409, 422) and "lot" in message(body).lower(), "(5) a second switch is refused: already by lot", (s, message(body)[:200]))
# (6) an adjustment dated before the switch day.
day = date.fromisoformat(pv["on"]) - timedelta(days=1)
s, body = c.adjust(p, "1", batch_id=batch_of(c, p, "LOTA")["id"], transaction_date=day.isoformat())
c0.ok(s in (409, 422) and "costing by lot" in message(body).lower(), "(6) an adjustment dated before the switch is refused", (s, message(body)[:200]))
s, body = c.adjust(q, "1", transaction_date=day.isoformat())
c0.ok(s in (409, 422) and "costing by lot" in message(body).lower(), "(6) the same for an untracked item", (s, message(body)[:200]))
c0.done()
