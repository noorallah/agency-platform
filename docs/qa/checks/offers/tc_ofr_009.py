"""TC-OFR-009: a counter bill carries the choice to its order.

A bill of documents already priced refuses one.
"""

from decimal import Decimal

from _offer import (
    SI,
    SO,
    Check,
    D,
    Scene,
    admin,
    cand,
    counter_billing,
    data,
    doc_line,
    message,
    mode,
    must,
    offer_rows,
    orders_of,
    today,
)


def claimed(scene: Scene, name: str) -> Decimal:
    """Return the free units an offer's approved claims have taken."""
    row = must(scene.api.get(f"/api/v1/promotions/{scene.offers[name]['id']}"), "offer")
    return D(row["free_quantity_claimed"])


c = Check("tc_ofr_009")
api = admin()
s = Scene(api, stock="50").tea()
choice = {"discount_from": s.city["id"], "offers": [s.key("TEA11")]}
expected_rows = sorted(
    [
        ("TEA11", "APPLIED", True, D(0), D(1), False),
        ("price_list", "APPLIED", True, D(44), D(0), False),
        ("TEA5", "REFUSED", False, D(55), D(0), False),
    ]
)
with mode(api, "COMBINE"), counter_billing(api):
    pv = must(
        api.post(f"{SI}/preview", s.bill_body([s.line("11", offer_choice=choice)])),
        "bill preview",
    )
    city = cand(pv, "price_list")
    c.ok(
        city
        and city["applied"]
        and city["chosen"]
        and pv["lines"][0]["choice_refused"] is None,
        "(1) the counter bill's preview lists the candidates and takes the choice",
        pv["lines"][0],
    )
    status, body = api.post(SI, s.bill_body([s.line("11", offer_choice=choice)]))
    c.eq(status, 201, f"(2) the counter bill is saved ({message(body)[:160]})")
    if status == 201:
        bill = data(body)
        line = doc_line(bill)
        c.eq(
            (D(line["discount_amount"]), D(line["free_quantity"])),
            (D(44), D(1)),
            "(2) the bill line: CITY 44.00 and 1 free",
        )
        c.eq(
            sorted(offer_rows(line)),
            expected_rows,
            "(2) the bill line carries its order line's rows",
        )
        orders = orders_of(s)
        c.eq(len(orders), 1, "(3) one order was raised behind the bill")
        if orders:
            order = must(api.get(f"{SO}/{orders[0]['id']}"), "order")
            c.eq(
                sorted(offer_rows(doc_line(order))),
                expected_rows,
                "(3) the order behind it holds the choice: the same rows",
            )
        c.eq(
            claimed(s, "TEA11"),
            D(0),
            "(4) nothing is claimed on TEA-11 before approval",
        )
        approved = api.post(f"{SI}/{bill['id']}/approve", {})
        c.eq(
            approved[0], 200, f"(4) the bill is approved ({message(approved[1])[:160]})"
        )
        c.eq(claimed(s, "TEA11"), D(1), "(4) approval claims TEA-11's 1 free unit")
# (5) a bill of documents already priced refuses a choice.
with mode(api, "COMBINE"):
    order = must(api.post(SO, s.order_body([s.line("2")])), "order")
    must(api.post(f"{SO}/{order['id']}/approve", {}), "approve order")
    order = must(api.get(f"{SO}/{order['id']}"), "order read")
    note = must(
        api.post(
            "/api/v1/delivery-notes",
            {
                "sales_order_id": order["id"],
                "delivery_date": today().isoformat(),
                "lines": [
                    {
                        "sales_order_line_id": order["lines"][0]["id"],
                        "line_number": 1,
                        "current_delivery_quantity": "2",
                    }
                ],
            },
        ),
        "delivery note",
    )
    must(api.post(f"/api/v1/delivery-notes/{note['id']}/approve", {}), "approve note")
    must(api.post(f"/api/v1/delivery-notes/{note['id']}/dispatch", {}), "dispatch")
    note = must(api.get(f"/api/v1/delivery-notes/{note['id']}"), "note read")
    body = {
        "customer_id": s.customer["id"],
        "branch_id": s.branch["id"],
        "invoice_date": today().isoformat(),
        "source_documents": [
            {"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"]}
        ],
        "lines": [
            {
                "source_document_type": "DELIVERY_NOTE",
                "source_document_id": note["id"],
                "source_document_line_id": note["lines"][0]["id"],
                "line_number": 1,
                "current_invoice_quantity": "2",
                "offer_choice": {"discount_from": s.city["id"]},
            }
        ],
    }
    c.refused(
        api.post(SI, body),
        422,
        "chosen where its price is set",
        "(5) a bill of a delivery note refuses a choice on its line",
    )
c.done()
