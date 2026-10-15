"""TC-OFR-004: a choice refused on save, and reported (not raised) in a preview."""

import uuid

from _offer import Check, D, Scene, admin, doc_line, mode, orders_of

c = Check("tc_ofr_004")
api = admin()
with mode(api, "COMBINE"):
    s = Scene(api).tea()
    tea11 = {"discount_from": s.city["id"], "offers": [s.key("TEA11")]}
    # (1) a discount typed beside a choice: two answers on one line.
    c.refused(
        s.save([s.line("11", discount_percent="3", offer_choice=tea11)]),
        422,
        "two answers on one line",
        "(1) a typed 3% beside a choice is refused",
    )
    # (2) a stale key: TEA-5 chosen at 9, the quantity then changed to 3.
    stale = {"offers": [s.key("TEA5")]}
    says = f"Line 1: offer {s.code('TEA5')} does not apply to this line any more"
    c.refused(
        s.save([s.line("3", offer_choice=stale)]),
        422,
        says,
        "(2) TEA-5 chosen on a line of 3 is refused by name",
    )
    # (3) a key no candidate carries at all.
    c.refused(
        s.save([s.line("11", offer_choice={"offers": [str(uuid.uuid4())]})]),
        422,
        "does not apply to this line any more",
        "(3) an unknown offer key is refused",
    )
    c.refused(
        s.save([s.line("11", offer_choice={"discount_from": str(uuid.uuid4())})]),
        422,
        "does not apply to this line any more",
        "(3) an unknown arrangement key is refused",
    )
    c.eq(len(orders_of(s)), 0, "(4) nothing was saved by the four refusals")
    # (5) the preview is lenient: it names the refusal and prices from the start.
    pv = s.preview(
        [s.line("3", offer_choice=stale), s.line("11", 2, offer_choice=tea11)]
    )
    first, second = pv["lines"][0], pv["lines"][1]
    c.ok(
        first["choice_refused"] and says in first["choice_refused"],
        "(5) line 1's refusal is named in the preview",
        first["choice_refused"],
    )
    one = doc_line(pv["order"], 1)
    c.eq(
        (D(one["discount_amount"]), one["discount_source"]),
        (D(12), "price_list"),
        "(5) line 1 is priced from the start: CITY 4% of 300.00",
    )
    c.eq(second["choice_refused"], None, "(5) line 2's choice stands beside it")
    two = doc_line(pv["order"], 2)
    c.eq(
        (D(two["discount_amount"]), D(two["free_quantity"])),
        (D(44), D(1)),
        "(5) line 2 takes CITY 44.00 and 1 free",
    )
c.done()
