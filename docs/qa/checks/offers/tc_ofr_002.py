"""TC-OFR-002: the "buy N more" hint on offers and on the price list's next break."""

from _offer import Check, D, Scene, admin, cand, cands, mode


def hint(item: dict | None) -> tuple:
    """Return a candidate's hint as (needs_more, then_gives)."""
    if item is None:
        return ("not listed",)
    more = item.get("needs_more")
    return (D(more) if more is not None else None, item.get("then_gives"))


c = Check("tc_ofr_002")
api = admin()
with mode(api, "COMBINE"):
    s = Scene(api, breaks=(("0", "4"), ("10", "6"))).tea()
    pv = s.preview([s.line("9")])
    c.eq(
        hint(cand(pv, s.code("TEA11"))),
        (D(2), "1 free"),
        "(1) at 9, TEA-11 hints 2 more for 1 free",
    )
    c.eq(
        hint(cand(pv, "price_list")),
        (D(1), "6% off"),
        "(1) at 9, CITY hints 1 more for its 6% break",
    )
    c.eq(
        hint(cand(pv, s.code("TEA5"))),
        (None, None),
        "(1) TEA-5, applied, carries no hint",
    )
    c.ok(
        sum(1 for x in cands(pv) if x.get("needs_more") is not None) <= 2,
        "(1) two hints a line at most",
    )
    pv = s.preview([s.line("3")])
    tea5 = cand(pv, s.code("TEA5"))
    c.eq(hint(tea5), (D(2), "5% off"), "(2) at 3, TEA-5 hints 2 more for 5% off")
    c.ok(
        tea5 is not None and tea5["available"] is False and not tea5["applied"],
        "(2) an offer short only on quantity is listed for the hint, not available",
        tea5,
    )
    c.eq(
        hint(cand(pv, s.code("TEA11"))),
        (None, None),
        "(2) at 3, TEA-11 (8 short, more than the 3 typed) carries no hint",
    )
    c.eq(
        hint(cand(pv, "price_list")),
        (None, None),
        "(2) at 3, CITY's break (7 short) carries no hint",
    )
    pv = s.preview([s.line("9", discount_percent="0")])
    c.eq(
        [x["code"] for x in cands(pv) if x.get("needs_more") is not None],
        [],
        "(3) a line with a discount typed carries no hint",
    )
    c.ok(
        all(x["reason"] == "A discount is typed on this line." for x in cands(pv)),
        "(3) and every candidate says a discount is typed",
        [x["reason"] for x in cands(pv)],
    )
c.done()
