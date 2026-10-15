"""TC-OFR-007: the same line priced under BEST_OFFER, COMBINE and ASK."""

from _offer import (
    Check,
    D,
    Scene,
    admin,
    cand,
    data,
    doc_line,
    message,
    mode,
    offer_rows,
)


def priced(line: dict) -> tuple:
    """Return a line's (discount, source, free)."""
    return (
        D(line["discount_amount"]),
        line["discount_source"],
        D(line["free_quantity"]),
    )


c = Check("tc_ofr_007")
api = admin()
s = Scene(api).tea()
both = {"offers": [s.key("TEA5"), s.key("TEA11")]}
with mode(api, "COMBINE"):
    pv = s.preview([s.line("11")])
    c.eq(
        priced(doc_line(pv["order"])),
        (D(55), "promotion", D(1)),
        "(1) COMBINE: TEA-5 55.00 and TEA-11 1 free",
    )
with mode(api, "BEST_OFFER"):
    pv = s.preview([s.line("11")])
    c.eq(
        priced(doc_line(pv["order"])),
        (D(44), "price_list", D(1)),
        "(2) BEST_OFFER: TEA-11 alone (1 free, worth 100.00), CITY's 4% beside it",
    )
    tea5 = cand(pv, s.code("TEA5"))
    c.ok(
        tea5 is not None and not tea5["applied"] and tea5["reason"],
        "(2) TEA-5 is listed, not applied, with a reason",
        tea5,
    )
    c.refused(
        s.save([s.line("11", offer_choice=both)]),
        422,
        "the best one offer a line",
        "(3) BEST_OFFER: a second offer on a line is refused",
    )
    status, body = s.save([s.line("11", offer_choice={"offers": [s.key("TEA5")]})])
    c.eq(
        status,
        201,
        f"(4) BEST_OFFER: TEA-5 in TEA-11's place is taken ({message(body)[:160]})",
    )
    if status == 201:
        line = doc_line(data(body))
        c.eq(priced(line), (D(55), "promotion", D(0)), "(4) 55.00 off, nothing free")
        c.ok(
            ("TEA11", "REFUSED", False, D(0), D(1), False) in offer_rows(line),
            "(4) TEA-11 is kept as passed over, 1 free",
            offer_rows(line),
        )
with mode(api, "ASK"):
    pv = s.preview([s.line("11")])
    c.eq(
        priced(doc_line(pv["order"])),
        (D(44), "price_list", D(1)),
        "(5) ASK starts as best one only: TEA-11 and CITY",
    )
    status, body = s.save([s.line("11", offer_choice=both)])
    c.eq(
        status, 201, f"(6) ASK: ticking TEA-5 as well is taken ({message(body)[:160]})"
    )
    if status == 201:
        line = doc_line(data(body))
        c.eq(priced(line), (D(55), "promotion", D(1)), "(6) 55.00 off and 1 free")
        c.eq(
            sorted(r[:3] for r in offer_rows(line, "APPLIED")),
            [("TEA11", "APPLIED", True), ("TEA5", "APPLIED", True)],
            "(6) both offers applied and chosen",
        )
c.done()
