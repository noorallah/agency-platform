"""TC-OFR-010: a quotation's choice, and the order it is converted into."""

from _offer import (
    QT,
    SO,
    Check,
    D,
    Scene,
    admin,
    cand,
    data,
    doc_line,
    message,
    mode,
    must,
    offer_rows,
)

c = Check("tc_ofr_010")
api = admin()
with mode(api, "COMBINE"):
    s = Scene(api).tea()
    choice = {"discount_from": s.city["id"], "offers": [s.key("TEA11")]}
    pv = must(
        api.post(f"{QT}/preview", s.quote_body([s.line("11", offer_choice=choice)])),
        "quote preview",
    )
    city = cand(pv, "price_list")
    c.ok(
        city and city["applied"] and city["chosen"],
        "(1) the quotation preview lists and takes the choice",
        pv["lines"][0],
    )
    status, body = api.post(QT, s.quote_body([s.line("11", offer_choice=choice)]))
    c.eq(status, 201, f"(2) the quotation is saved ({message(body)[:160]})")
    if status == 201:
        quote = data(body)
        line = doc_line(quote)
        rows = sorted(
            [
                ("TEA11", "APPLIED", True, D(0), D(1), False),
                ("price_list", "APPLIED", True, D(44), D(0), False),
                ("TEA5", "REFUSED", False, D(55), D(0), False),
            ]
        )
        c.eq(
            (D(line["discount_amount"]), D(line["free_quantity"])),
            (D(44), D(1)),
            "(2) the quotation line: CITY 44.00 and 1 free",
        )
        c.eq(
            sorted(offer_rows(line)),
            rows,
            "(2) its rows: CITY and TEA-11 chosen, TEA-5 passed over",
        )
        for step in ("send", "accept"):
            must(api.post(f"{QT}/{quote['id']}/{step}", {}), step)
        status, body = api.post(f"{QT}/{quote['id']}/convert", {})
        c.eq(status, 201, f"(3) the quotation is converted ({message(body)[:160]})")
        if status == 201:
            order = must(api.get(f"{SO}/{body['order']['id']}"), "order")
            line = doc_line(order)
            c.eq(
                (
                    D(line["discount_amount"]),
                    line["discount_source"],
                    D(line["free_quantity"]),
                ),
                (D(44), "price_list", D(1)),
                "(3) the order line keeps CITY 44.00 and 1 free",
            )
            c.eq(
                sorted(offer_rows(line)),
                rows,
                "(3) and the choice handed over: the same rows",
            )
c.done()
