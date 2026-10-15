"""TC-OFR-012: the discount report's choice columns; discount by offer and product."""

from _offer import (
    SI,
    Check,
    D,
    Scene,
    admin,
    all_rows,
    counter_billing,
    message,
    mode,
    must,
    today,
)

c = Check("tc_ofr_012")
api = admin()
s = Scene(api, stock="50").tea()
choice = {"discount_from": s.city["id"], "offers": [s.key("TEA11")]}
with mode(api, "COMBINE"), counter_billing(api):
    for lines in ([s.line("11", offer_choice=choice)], [s.line("11")]):
        bill = must(api.post(SI, s.bill_body(lines)), "counter bill")
        done = api.post(f"{SI}/{bill['id']}/approve", {})
        c.eq(done[0], 200, f"a counter bill is approved ({message(done[1])[:160]})")
window = f"from_date={today().isoformat()}&to_date={today().isoformat()}"
mine = [
    r
    for r in all_rows(api, f"{SI}/reports/discount-by-product?{window}")
    if r["key_id"] == s.product["id"]
]
c.eq(len(mine), 1, "(1) one row for the item in Discount given by product")
if mine:
    row = mine[0]
    c.eq(
        (
            row["lines"],
            D(row["gross_amount"]),
            D(row["arranged_discount"]),
            D(row["promotion_discount"]),
        ),
        (2, D(2200), D(44), D(55)),
        "(1) 2 lines, 2,200.00 gross, CITY 44.00 arranged, TEA-5 55.00 by offer",
    )
    c.eq(
        (
            row["chosen_lines"],
            D(row["chosen_discount"]),
            row["passed_over"],
            D(row["passed_over_amount"]),
        ),
        (1, D(44), 1, D(55)),
        "(1) chosen: 1 line, 44.00; passed over: 1 arrangement (TEA-5), worth 55.00",
    )
got = sorted(
    (
        r["code"].rsplit("-", 1)[0],
        r["lines"],
        D(r["discount_amount"]),
        D(r["free_quantity"]),
    )
    for r in all_rows(api, f"{SI}/reports/discount-by-offer-product?{window}")
    if r["product_id"] == s.product["id"]
)
c.eq(
    got,
    [("TEA11", 2, D(0), D(2)), ("TEA5", 1, D(55), D(0))],
    "(2) by offer and product: TEA-11 on 2 lines, 2 free; TEA-5 on 1 line, 55.00",
)
c.done()
