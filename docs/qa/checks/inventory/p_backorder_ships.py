"""Probe: an order for more than is held ships what is on the shelf, alone and beside a later order."""
from _inv import *
from _flow import *
from _flow import _customer


def order(w, wh_id, product_id, qty):
    """Raise and approve a sales order of one line; return it as read back."""
    if not hasattr(w, "customer_id"):
        w.customer_id = _customer(w)
    so = must(
        w.admin.post(
            "/api/v1/sales-orders",
            {
                "customer_id": w.customer_id,
                "branch_id": w.branch_id,
                "warehouse_id": wh_id,
                "order_date": w.today,
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": product_id,
                        "quantity": str(qty),
                        "unit_price": "100",
                        "warehouse_id": wh_id,
                    }
                ],
            },
        ),
        "sales order",
    )
    must(w.admin.post(f"/api/v1/sales-orders/{so['id']}/approve", {}), "approve so")
    return must(w.admin.get(f"/api/v1/sales-orders/{so['id']}"), "read so")


def ship(w, so, wh_id, qty):
    """Raise, approve and dispatch a note for part of an order; return the last answer."""
    made = w.admin.post(
        "/api/v1/delivery-notes",
        {
            "sales_order_id": so["id"],
            "delivery_date": w.today,
            "lines": [
                {
                    "sales_order_line_id": so["lines"][0]["id"],
                    "line_number": 1,
                    "current_delivery_quantity": str(qty),
                    "warehouse_id": wh_id,
                }
            ],
        },
    )
    if made[0] not in (200, 201):
        return made
    note = data(made[1])
    approved = w.admin.post(f"/api/v1/delivery-notes/{note['id']}/approve", {})
    if approved[0] != 200:
        return approved
    return w.admin.post(f"/api/v1/delivery-notes/{note['id']}/dispatch", {})


c = Check("p_backorder_ships")
w = World()
wh = w.warehouse()

# One order for ten with four held: the four ship, six stay owed.
p = w.product()
w.stock_in(wh["id"], p["id"], 4)
a = order(w, wh["id"], p["id"], 10)
d = ship(w, a, wh["id"], 4)
c.eq(d[0], 200, "four of the ten ship while four are held: " + message(d[1]))
c.eq(w.qty(p["id"], wh["id"]), D(0), "nothing is left on the shelf")

# Goods arrive after a later order was taken: the earlier order ships what is
# held, and the later one does not ship from an empty shelf.
p2 = w.product()
w.stock_in(wh["id"], p2["id"], 4)
early = order(w, wh["id"], p2["id"], 10)
late = order(w, wh["id"], p2["id"], 2)
receive(w, wh["id"], p2["id"], 3)
d = ship(w, early, wh["id"], 7)
c.eq(d[0], 200, "the earlier order ships the seven now held: " + message(d[1]))
d = ship(w, late, wh["id"], 2)
c.ok(d[0] != 200, "the later order does not ship from an empty shelf", f"answered {d[0]}: {message(d[1])}")
c.done()
