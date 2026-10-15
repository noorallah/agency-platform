"""TC-OFR-006: a person without SALES_OFFER_CHOOSE sees the list but cannot choose."""

from _offer import (
    Check,
    D,
    Scene,
    admin,
    cand,
    client,
    doc_line,
    message,
    mode,
    orders_of,
)

c = Check("tc_ofr_006")
api = admin()
nochoose = client("nochoose", "offers")
clerk = client("clerk", "offers")
with mode(api, "COMBINE"):
    s = Scene(api).tea()
    pv = s.preview([s.line("11")], nochoose)
    c.ok(
        cand(pv, s.code("TEA5")) and cand(pv, "price_list"),
        "(1) the list is shown to a person without the permission",
        pv["lines"][0]["candidates"],
    )
    choice = {"discount_from": s.city["id"], "offers": [s.key("TEA11")]}
    pv = s.preview([s.line("11", offer_choice=choice)], nochoose)
    c.ok(
        "SALES_OFFER_CHOOSE" in (pv["lines"][0]["choice_refused"] or ""),
        "(2) the preview reports the choice refused, naming the permission",
        pv["lines"][0]["choice_refused"],
    )
    c.eq(
        D(doc_line(pv["order"])["discount_amount"]),
        D(55),
        "(2) and prices the start: 55.00",
    )
    c.refused(
        s.save([s.line("11", offer_choice=choice)], nochoose),
        403,
        "SALES_OFFER_CHOOSE",
        "(3) the save is refused naming the permission",
    )
    c.eq(len(orders_of(s)), 0, "(3) nothing saved")
    same = {"discount_from": "offers", "offers": [s.key("TEA5"), s.key("TEA11")]}
    status, body = s.save([s.line("11", offer_choice=same)], nochoose)
    c.eq(
        status, 201, f"(4) the start sent back by him is saved ({message(body)[:160]})"
    )
    status, body = s.save([s.line("11", offer_choice=choice)], clerk)
    c.eq(
        status,
        201,
        f"(5) the same choice by a Sales executive is saved ({message(body)[:160]})",
    )
c.done()
