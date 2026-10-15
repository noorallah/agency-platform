"""TC-OFR-011: the saved rows on a read, and an edit that keeps or clears a choice."""

from _offer import SO, Check, D, Scene, admin, doc_line, message, mode, must, offer_rows

START = sorted(
    [
        ("TEA5", "APPLIED", False, D(55), D(0), False),
        ("TEA11", "APPLIED", False, D(0), D(1), False),
    ]
)
CHOSEN = sorted(
    [
        ("TEA11", "APPLIED", True, D(0), D(1), False),
        ("price_list", "APPLIED", True, D(44), D(0), False),
        ("TEA5", "REFUSED", False, D(55), D(0), False),
    ]
)

c = Check("tc_ofr_011")
api = admin()
with mode(api, "COMBINE"):
    s = Scene(api).tea()
    choice = {"discount_from": s.city["id"], "offers": [s.key("TEA11")]}
    order = must(s.save([s.line("11", offer_choice=choice)]), "order with a choice")
    read = must(api.get(f"{SO}/{order['id']}"), "order read")
    c.eq(
        sorted(offer_rows(doc_line(read))),
        CHOSEN,
        "(1) a read carries the rows: chosen, applied and passed over",
    )
    # (2) an edit that leaves the choice out keeps it.
    status, body = api.put(
        f"{SO}/{order['id']}", s.order_body([s.line("11", remarks="edited")])
    )
    c.eq(
        status,
        200,
        f"(2) an edit without offer_choice is saved ({message(body)[:160]})",
    )
    read = must(api.get(f"{SO}/{order['id']}"), "order read")
    c.eq(sorted(offer_rows(doc_line(read))), CHOSEN, "(2) and keeps the choice")
    c.eq(
        D(doc_line(read)["discount_amount"]),
        D(44),
        "(2) the line still takes CITY 44.00",
    )
    # (3) an explicit null clears it: the line follows the server again.
    status, body = api.put(
        f"{SO}/{order['id']}", s.order_body([s.line("11", offer_choice=None)])
    )
    c.eq(
        status,
        200,
        f"(3) an edit with offer_choice null is saved ({message(body)[:160]})",
    )
    read = must(api.get(f"{SO}/{order['id']}"), "order read")
    c.eq(
        sorted(offer_rows(doc_line(read))),
        START,
        "(3) the rows are the start's: TEA-5 and TEA-11, none chosen",
    )
    c.eq(
        (D(doc_line(read)["discount_amount"]), doc_line(read)["discount_source"]),
        (D(55), "promotion"),
        "(3) the line is back on TEA-5's 55.00",
    )
c.done()
