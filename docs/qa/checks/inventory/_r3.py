"""Orders, notes and dates the round 3 probes share (not a check)."""
from datetime import date, timedelta

from _inv import *
from _flow import _customer

SERIALS = "/api/v1/batch-serial/serials"


def iso(w, days):
    """The firm's today moved by a number of days."""
    return (date.fromisoformat(w.today) + timedelta(days=days)).isoformat()


def order(w, wh_id, product_id, qty):
    """Raise and approve a sales order of one line; return it as read back."""
    if not hasattr(w, "customer_id"):
        w.customer_id = _customer(w)
    line = {"line_number": 1, "product_id": product_id, "quantity": str(qty), "unit_price": "100", "warehouse_id": wh_id}
    so = must(w.admin.post("/api/v1/sales-orders", {"customer_id": w.customer_id, "branch_id": w.branch_id, "warehouse_id": wh_id,
                                                    "order_date": w.today, "lines": [line]}), "sales order")
    must(w.admin.post(f"/api/v1/sales-orders/{so['id']}/approve", {}), "approve so")
    return must(w.admin.get(f"/api/v1/sales-orders/{so['id']}"), "read so")


def ship(w, so, wh_id, qty, **extra):
    """Raise, approve and dispatch a note for part of an order; return (status, message) of the step that ended it."""
    line = {"sales_order_line_id": so["lines"][0]["id"], "line_number": 1, "current_delivery_quantity": str(qty), "warehouse_id": wh_id, **extra}
    made = w.admin.post("/api/v1/delivery-notes", {"sales_order_id": so["id"], "delivery_date": w.today, "lines": [line]})
    if made[0] not in (200, 201):
        return made[0], "create: " + message(made[1])
    note = data(made[1])
    approved = w.admin.post(f"/api/v1/delivery-notes/{note['id']}/approve", {})
    if approved[0] != 200:
        return approved[0], "approve: " + message(approved[1])
    done = w.admin.post(f"/api/v1/delivery-notes/{note['id']}/dispatch", {})
    return done[0], message(done[1])


def by_batch(w, product_id, field="current_quantity"):
    """A quantity of a product per batch number (None for the row with no batch)."""
    return {r.get("batch_number"): D(r[field]) for r in w.rows(product_id)}


def units(w, product_id):
    """The serial units of a product: number -> row."""
    return {x["serial_number"]: x for x in all_rows(w.admin, f"{SERIALS}?product_id={product_id}")}
