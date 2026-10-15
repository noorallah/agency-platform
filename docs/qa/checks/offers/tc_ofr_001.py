"""TC-OFR-001: a line's candidates and reasons in the order preview.

Steps 1 and 2 of the worked example (design section 1), under COMBINE.
"""

from _offer import Check, D, Scene, admin, cand, doc_line, mode, orders_of, taxable

c = Check("tc_ofr_001")
api = admin()
with mode(api, "COMBINE"):
    s = Scene(api).tea()
    pv = s.preview([s.line("9")])
    tea5, tea11 = cand(pv, s.code("TEA5")), cand(pv, s.code("TEA11"))
    city, standing = cand(pv, "price_list"), cand(pv, "customer")
    c.ok(
        tea5 and tea11 and city and standing,
        "(1) TEA-5, TEA-11, CITY and the standing rate are listed",
        pv["lines"],
    )
    if tea5 and tea11 and city and standing:
        c.eq(
            (tea5["key"], tea5["applied"], D(tea5["worth"]), tea5["gives"]["sentence"]),
            (s.key("TEA5"), True, D(45), "5% off"),
            "(1) TEA-5: keyed by its group, applied, 45.00, '5% off'",
        )
        c.eq(
            (tea11["applied"], tea11["gives"]["sentence"], tea11["combines"]),
            (False, "11 + 1 free", True),
            "(1) TEA-11: not applied, '11 + 1 free', combines",
        )
        c.eq(
            (city["key"], city["applied"], D(city["worth"]), city["reason"]),
            (s.city["id"], False, D(36), "An offer gives this line its discount."),
            "(1) CITY: the list's id, not applied, 36.00, an offer gives it",
        )
        c.eq(
            (
                standing["key"],
                standing["applied"],
                D(standing["worth"]),
                standing["reason"],
            ),
            ("CUSTOMER", False, D(18), "An offer gives this line its discount."),
            "(1) the standing rate: CUSTOMER, not applied, 18.00, same reason",
        )
    welcome = cand(pv, "WELCOME")
    c.ok(
        welcome is not None
        and not welcome["available"]
        and "coupon" in (welcome["reason"] or ""),
        "(1) a coupon offer is listed unavailable, saying it needs a coupon",
        welcome,
    )
    line = doc_line(pv["order"])
    c.eq(
        (
            D(line["discount_amount"]),
            line["discount_source"],
            taxable(line),
            D(line["tax_amount"]),
            D(line["net_amount"]),
            D(line["free_quantity"]),
        ),
        (D(45), "promotion", D(855), D("102.60"), D("957.60"), D(0)),
        "(1) the line: 45.00 off, taxable 855.00, GST 102.60, 957.60, none free",
    )
    c.eq(pv["lines"][0]["choice_refused"], None, "(1) no choice refused")
    pv = s.preview([s.line("11")])
    tea5, tea11 = cand(pv, s.code("TEA5")), cand(pv, s.code("TEA11"))
    c.eq(
        (
            (tea5 or {}).get("applied"),
            D((tea5 or {}).get("worth")),
            (tea11 or {}).get("applied"),
        ),
        (True, D(55), True),
        "(2) at 11: TEA-5 applied at 55.00 and TEA-11 applied",
    )
    line = doc_line(pv["order"])
    c.eq(
        (
            D(line["discount_amount"]),
            D(line["free_quantity"]),
            taxable(line),
            D(line["tax_amount"]),
            D(line["net_amount"]),
        ),
        (D(55), D(1), D(1045), D("125.40"), D("1170.40")),
        "(2) the line: 55.00 off, 1 free, taxable 1,045.00, GST 125.40, 1,170.40",
    )
    # (3) a preview leaves nothing behind.
    listed = orders_of(s)
    c.eq(len(listed), 0, "(3) no order was saved for the customer by two previews")
c.done()
