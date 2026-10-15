"""TC-OFR-003: a choice on an order line (step 3 of the worked example)."""

from _offer import (
    Check,
    D,
    Scene,
    admin,
    cand,
    client,
    data,
    doc_line,
    message,
    mode,
    offer_rows,
    state,
    taxable,
)

AUDIT = "/api/v1/audit-logs?action=sales_order.offer_chosen"

c = Check("tc_ofr_003")
api = admin()
clerk = client("clerk", "offers")
with mode(api, "COMBINE"):
    s = Scene(api).tea()
    choice = {"discount_from": s.city["id"], "offers": [s.key("TEA11")]}
    pv = s.preview([s.line("11", offer_choice=choice)], clerk)
    c.eq(pv["lines"][0]["choice_refused"], None, "(1) the preview takes the choice")
    city, tea5 = cand(pv, "price_list"), cand(pv, s.code("TEA5"))
    c.eq(
        (
            (city or {}).get("applied"),
            (city or {}).get("chosen"),
            D((city or {}).get("worth")),
        ),
        (True, True, D(44)),
        "(1) CITY is applied and chosen, 44.00",
    )
    c.eq(
        ((tea5 or {}).get("applied"), (tea5 or {}).get("chosen")),
        (False, False),
        "(1) TEA-5 is neither applied nor chosen",
    )
    line = doc_line(pv["order"])
    c.eq(
        (
            D(line["discount_amount"]),
            line["discount_source"],
            D(line["free_quantity"]),
            taxable(line),
            D(line["tax_amount"]),
            D(line["net_amount"]),
        ),
        (D(44), "price_list", D(1), D(1056), D("126.72"), D("1182.72")),
        "(1) 44.00 off by the list, 1 free, taxable 1,056.00, GST 126.72, 1,182.72",
    )
    status, body = s.save([s.line("11", offer_choice=choice)], clerk)
    c.eq(status, 201, f"(2) a Sales executive saves the order ({message(body)[:160]})")
    if status == 201:
        line = doc_line(data(body))
        c.eq(
            sorted(offer_rows(line)),
            sorted(
                [
                    ("TEA11", "APPLIED", True, D(0), D(1), False),
                    ("TEA5", "REFUSED", False, D(55), D(0), False),
                    ("price_list", "APPLIED", True, D(44), D(0), False),
                ]
            ),
            "(2) rows: CITY chosen 44.00, TEA-11 chosen 1 free, TEA-5 passed over",
        )
        c.eq(
            D(line["discount_amount"]),
            D(44),
            "(2) the discount box stays the server's 44.00",
        )
        trail = api.get(f"{AUDIT}&entity_id={data(body)['id']}")
        found = [
            (r["actor_email"]) for r in (data(trail[1]) if trail[0] == 200 else [])
        ]
        c.eq(
            found,
            [state("offers")["accounts"]["clerk"]["email"]],
            "(2) the choice is in the audit trail once, by the Sales executive",
        )
    # (3) a choice equal to the start is not a choice.
    same = {"discount_from": "offers", "offers": [s.key("TEA5"), s.key("TEA11")]}
    status, body = s.save([s.line("11", offer_choice=same)], clerk)
    c.eq(status, 201, f"(3) the start sent back is saved ({message(body)[:160]})")
    if status == 201:
        line = doc_line(data(body))
        c.eq(
            sorted(offer_rows(line)),
            sorted(
                [
                    ("TEA5", "APPLIED", False, D(55), D(0), False),
                    ("TEA11", "APPLIED", False, D(0), D(1), False),
                ]
            ),
            "(3) stored as the server's: both applied, none chosen, none passed over",
        )
        trail = api.get(f"{AUDIT}&entity_id={data(body)['id']}")
        c.eq(
            len(data(trail[1]) or []) if trail[0] == 200 else trail[0],
            0,
            "(3) and no choice is written to the audit trail",
        )
c.done()
