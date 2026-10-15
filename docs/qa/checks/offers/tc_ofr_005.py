"""TC-OFR-005: an offer that does not combine, chosen beside one after it.

An offer with ``allow_stacking`` off ends the stack where it applies, so the
offers after it are passed over with "Does not combine with ..." (design
3.2, 3.3 rule 2).
"""

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

c = Check("tc_ofr_005")
api = admin()
with mode(api, "COMBINE"):
    s = Scene(api)
    s.offer(
        "SOLO3",
        {"action_type": "LINE_DISCOUNT_PERCENT", "percent": "3"},
        5,
        "5",
        allow_stacking=False,
    )
    s.offer("TEA5", {"action_type": "LINE_DISCOUNT_PERCENT", "percent": "5"}, 10, "5")
    pv = s.preview([s.line("9")])
    solo, tea5 = cand(pv, s.code("SOLO3")), cand(pv, s.code("TEA5"))
    c.ok(
        solo is not None and solo["applied"] and solo["combines"] is False,
        "(1) SOLO-3 (first, does not combine) is applied",
        solo,
    )
    c.ok(
        tea5 is not None
        and not tea5["applied"]
        and (tea5["reason"] or "").startswith(
            f"Does not combine with {s.code('SOLO3')}"
        ),
        "(1) TEA-5 after it is not applied, saying it does not combine with SOLO-3",
        tea5,
    )
    c.eq(
        D(doc_line(pv["order"])["discount_amount"]),
        D(27),
        "(1) the start is SOLO-3 alone: 27.00",
    )
    both = {"offers": [s.key("SOLO3"), s.key("TEA5")]}
    c.refused(
        s.save([s.line("9", offer_choice=both)]),
        422,
        f"{s.code('TEA5')} does not combine with {s.code('SOLO3')}",
        "(2) SOLO-3 and TEA-5 together are refused by name",
    )
    alone = {"offers": [s.key("TEA5")]}
    status, body = s.save([s.line("9", offer_choice=alone)])
    c.eq(status, 201, f"(3) TEA-5 alone is taken ({message(body)[:160]})")
    if status == 201:
        line = doc_line(data(body))
        c.eq(
            (D(line["discount_amount"]), line["discount_source"]),
            (D(45), "promotion"),
            "(3) the line takes 5% of 900.00: 45.00",
        )
        c.eq(
            sorted(offer_rows(line)),
            sorted(
                [
                    ("TEA5", "APPLIED", True, D(45), D(0), False),
                    ("SOLO3", "REFUSED", False, D(27), D(0), False),
                ]
            ),
            "(3) rows: TEA-5 applied and chosen, SOLO-3 passed over at 27.00",
        )
c.done()
