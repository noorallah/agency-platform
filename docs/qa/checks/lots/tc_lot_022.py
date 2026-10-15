"""TC-LOT-022: a bill line over lots at two prices is refused unless a rate is typed (HTTP steps 3-4).

Not driven: steps 1-2 (the counter screen splitting the line after a second). Uses two lots of
its own (PTR 100.00 and 112.00) instead of TEST03-M1/M2 so the shared stock is not spent.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_022")
api = lot_admin(); c = Ctx(api); p = margin_product(api)
c.receive([{"product": p, "qty": 10, "rate": 80}])
la = lot_of_receipt(api, p, {})
c.receive([{"product": p, "qty": 10, "rate": 80, "retail_margin_percent": 40}])
lb = lot_of_receipt(api, p, {})
c0.eq((D(la["ptr"]), D(lb["ptr"])), (D(100), D(112)), "the two lots carry PTR 100.00 and 112.00")
customer = by_code(api, "/api/v1/customers", "LOT-R")


def bill(rate: str | None) -> tuple[int, object]:
    """Post a bare bill line of 15 over both lots, with or without a typed rate."""
    line = {"line_number": 1, "product_id": p["id"], "current_invoice_quantity": "15",
            "batches": [{"batch_id": la["id"], "quantity": "10"}, {"batch_id": lb["id"], "quantity": "5"}]}
    if rate is not None:
        line["unit_price"] = rate
    return api.post("/api/v1/sales-invoices", {
        "customer_id": customer["id"], "branch_id": c.branch["id"],
        "invoice_date": today().isoformat(), "lines": [line]})


SETTINGS = "/api/v1/sales-orders/workflow-settings"
was = must(api.get(SETTINGS), "settings")
keep = {k: was[k] for k in ("quotation_stage", "sales_order_stage", "delivery_note_stage",
                            "default_branch_id", "default_warehouse_id")}
# A counter bill: the firm types no order and no delivery note.
must(api.put(SETTINGS, {"quotation_stage": False, "sales_order_stage": False, "delivery_note_stage": False,
                        "default_branch_id": c.branch["id"], "default_warehouse_id": c.warehouse["id"]}),
     "counter settings")
try:
    s, b = bill(None)
    c0.ok(s == 422 and "100.00" in message(b) and "112.00" in message(b),
          "(3) no typed price over two lots is refused naming 100.00 and 112.00", (s, message(b)))
    before = (c.stock(p))
    s, b = bill("105.00")
    c0.eq(s, 201, f"(4) a typed rate is accepted ({message(b)})")
    if s == 201:
        inv = data(b)
        c0.eq({D(ln["unit_price"]) for ln in inv["lines"]}, {D("105")}, "(4) the typed rate stands on every part")
        c0.eq(c.stock(p), before, "(4) a draft bill takes nothing from the lots")
finally:
    api.put(SETTINGS, keep)
c0.done()
