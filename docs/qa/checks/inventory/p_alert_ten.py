"""Probe (round 5): Home's stock alerts at exactly ten of a kind, at eleven, and with ties (around D-STK-55).

Driven in the goods-types checks' own plain firm (state ``goods_types``, account ``plain_admin``), which holds no
other levels, so the counts are exact and not a difference. That firm has no control accounts, so nothing can be
stocked in it: the items are given a stock row with a reorder level and nothing held, which is *out of stock*. Ten
with levels 1 to 10: ten counted, ten listed, the largest level first. An eleventh with a level of nought is counted
and not listed. A twelfth as short as the worst is listed beside it, the product code settling which comes first, and
the one short by 1 drops off. Low stock and over-maximum at their limits are in ``tc_stock_019``. The levels are
taken off again at the end, and any a stopped run left behind are taken off at the start."""
from _inv import *


class PlainWorld(World):
    """The same helpers inside the plain fixture firm of the goods-types checks."""

    def __init__(self) -> None:
        held = state("goods_types")["accounts"]["plain_admin"]
        self.tag = suffix()
        self.admin = client("plain_admin", "goods_types")
        self.firm_id = held["firm_id"]
        self._uom = None
        self.branch_id = must(self.admin.get("/api/v1/branches"), "branches")[0]["id"]
        self.today = today(self.admin)


c = Check("p_alert_ten")
w = PlainWorld()


def levels_off() -> int:
    """Take every reorder, minimum and maximum level in the firm off; return how many rows carried one."""
    cleared = 0
    for r in all_rows(w.admin, f"{INV}?include_deleted=false"):
        if any(r.get(k) is not None for k in ("reorder_level", "minimum_level", "maximum_level")):
            st, b = w.admin.put(f"{INV}/{r['id']}", {"branch_id": r["branch_id"], "warehouse_id": r["warehouse_id"],
                                                    "product_id": r["product_id"], "reorder_level": None,
                                                    "minimum_level": None, "maximum_level": None})
            if st != 200:
                raise SystemExit(f"PRECONDITION levels off: {st} {message(b)}")
            cleared += 1
    return cleared


def alerts() -> dict:
    """The firm's alerts."""
    return must(w.admin.get(f"{INV}/alerts"), "alerts")


def of(kind: str, a: dict) -> list[tuple[str, Decimal, Decimal]]:
    """(code, quantity, level) of the rows of one kind, in the order given."""
    return [(r["product_code"], D(r["quantity"]), D(r["level"])) for r in a["rows"] if r["kind"] == kind]


levels_off()
start = alerts()
c.eq((start["low"], start["out"], start["over_maximum"]), (0, 0, 0), "the plain firm starts with no level alerts")


def row_with_level(product: dict, level: str) -> None:
    """Give an item a stock row holding nothing, with a reorder level."""
    must(w.admin.post(INV, {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": product["id"],
                            "reorder_level": level}), "stock row")


try:
    wh = w.warehouse("AL")
    ten = [w.product(f"L{n:02d}") for n in range(1, 11)]
    for n, p in enumerate(ten, start=1):
        row_with_level(p, str(n))
    a = alerts()
    out = of("OUT", a)
    c.eq((a["out"], a["low"]), (10, 0), "ten items with a level and nothing held: ten out of stock, none of them low as well")
    c.eq(len(out), 10, "and ten listed")
    c.eq([code for code, _, _ in out], [p["code"] for p in reversed(ten)], "worst first: a level of 10 down to a level of 1")
    c.eq(out[0][1:], (D(0), D(10)), "the first row reads nothing held against a level of 10")
    c.eq([r["kind"] for r in a["rows"]], ["OUT"] * 10, "no row of another kind")

    nought = w.product("L00")
    row_with_level(nought, "0")
    a = alerts()
    out = of("OUT", a)
    c.eq(a["out"], 11, "an eleventh, with a level of nought and nothing held, is counted")
    c.eq(len(out), 10, "ten are still listed")
    c.ok(nought["code"] not in [code for code, _, _ in out], "and the one short by nothing is the one left off")

    tie = w.product("L99")
    row_with_level(tie, "10")
    a = alerts()
    out = of("OUT", a)
    c.eq(a["out"], 12, "a twelfth as short as the worst is counted")
    c.eq([code for code, _, _ in out[:2]], sorted([ten[9]["code"], tie["code"]]),
         "the two with a level of 10 head the rows, the product code settling the tie")
    c.ok(ten[0]["code"] not in [code for code, _, _ in out], "the one short by 1 has dropped off the ten listed")

    # a row with no level at all is not an alert, however little it holds
    bare = w.product("L98")
    must(w.admin.post(INV, {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": bare["id"]}), "bare row")
    c.eq(alerts()["out"], 12, "an item with a stock row and no level is not counted")
finally:
    levels_off()
end = alerts()
c.eq((end["low"], end["out"], end["over_maximum"]), (0, 0, 0), "the levels taken off, the firm reads no alert again")
c.done()
