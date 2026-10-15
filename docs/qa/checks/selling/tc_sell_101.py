"""TC-SELL-101: the bill starts at the customer's price level, and one switch reprices it."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_101")
a = admin()
sc = Scene(a, stock="100")
tag = sc.tag
retail = must(a.post("/api/v1/price-levels", {"code": f"RT{tag}", "name": f"Retail {tag}"}), "retail level")
whole = must(a.post("/api/v1/price-levels", {"code": f"WS{tag}", "name": f"Wholesale {tag}"}), "wholesale level")
soap = sc.new_product("SO", "100", "100", "GST_18_LOCAL")
oil = sc.new_product("OI", "200", "100", "GST_18_LOCAL")
salt = sc.new_product("SA", "40", "100", "GST_18_LOCAL")
for prod, r, w in ((soap, "95", "80"), (oil, "190", "150")):
    must(a.put(f"/api/v1/price-levels/products/{prod['id']}", {"rates": [
        {"price_level_id": retail["id"], "rate": r}, {"price_level_id": whole["id"], "rate": w}]}), "rates")
must(a.put(f"/api/v1/price-levels/products/{salt['id']}", {"rates": [{"price_level_id": retail["id"], "rate": "38"}]}), "salt rates")
t = sc.new_customer(price_level_id=whole["id"])
sc.customer = sc.new_customer()   # S: no level
s_cust = sc.customer


def order(customer: dict, **extra: object) -> dict:
    """Raise an order of the three items, two each; return the read-back."""
    body = {"customer_id": customer["id"], "order_date": today().isoformat(),
            "branch_id": sc.branch["id"], "warehouse_id": sc.warehouse["id"],
            "lines": [{"line_number": n, "product_id": p["id"], "quantity": "2"} for n, p in enumerate((soap, oil, salt), 1)],
            **extra}
    made = must(a.post(SO, body), "order")
    return must(a.get(f"{SO}/{made['id']}"), "order read")


def rates(doc: dict) -> list[Decimal]:
    """Return the lines' rates."""
    return [D(l["unit_price"]) for l in doc["lines"]]


c.eq(rates(order(t)), [D(80), D(150), D(40)], "step 1: T's usual is Wholesale; Salt has no wholesale rate so its own price")
c.eq(rates(order(t, price_level_id=retail["id"])), [D(95), D(190), D(38)], "step 2: Retail reprices all three")
typed = {"customer_id": t["id"], "order_date": today().isoformat(), "branch_id": sc.branch["id"],
         "warehouse_id": sc.warehouse["id"], "price_level_id": retail["id"],
         "lines": [{"line_number": 1, "product_id": soap["id"], "quantity": "2", "unit_price": "91"},
                   {"line_number": 2, "product_id": oil["id"], "quantity": "2"},
                   {"line_number": 3, "product_id": salt["id"], "quantity": "2"}]}
made = must(a.post(SO, typed), "typed")
got = must(a.get(f"{SO}/{made['id']}"), "typed read")
c.eq(rates(got), [D(91), D(190), D(38)], "step 3: a typed rate holds beside the level")
c.eq(got["price_level_id"], retail["id"], "step 3: the order reopens with Retail")
c.eq(rates(order(s_cust)), [D(100), D(200), D(40)], "step 6: a customer with no level gets the product price")
c.eq(rates(order(s_cust, price_level_id=whole["id"])), [D(80), D(150), D(40)], "step 6: after the switch to Wholesale")
usual = order(t)
c.ok(usual.get("price_level_id") is None, "step 5: an order of the usual level names no level of its own", usual.get("price_level_id"))
ghost = a.post(SO, {**typed, "price_level_id": "00000000-0000-4000-8000-000000000000"})
c.ok(ghost[0] in (404, 422), "a level that is not the firm's is refused", f"{ghost[0]} {message(ghost[1])}")
c.ok(ghost[0] != 201 and message(ghost[1]) != "", "and in words", message(ghost[1]))
off = must(a.put(f"/api/v1/price-levels/{whole['id']}", {"code": whole["code"], "name": whole["name"], "is_active": False}), "switch off")
dead = a.post(SO, {**typed, "price_level_id": whole["id"]})
c.ok(dead[0] in (404, 422), "a level switched off is refused", f"{dead[0]} {message(dead[1])}")
must(a.put(f"/api/v1/price-levels/{whole['id']}", {"code": whole["code"], "name": whole["name"], "is_active": True}), "switch on")
# step 8: a bill typed directly
with counter(a):
    sc.customer = t
    sc.product = soap
    bill = must(a.post(SI, sc.bill_body("1", customer=t)), "direct bill, usual level")
    got = must(a.get(f"{SI}/{bill['id']}"), "bill read")
    c.eq(D(got["lines"][0]["unit_price"]), D(80), "step 8: the bill starts at 80.00")
    bill = must(a.post(SI, sc.bill_body("1", customer=t, price_level_id=retail["id"])), "direct bill, retail")
    got = must(a.get(f"{SI}/{bill['id']}"), "bill read")
    c.eq(D(got["lines"][0]["unit_price"]), D(95), "step 8: after the switch 95.00")
# a bill of delivery notes that names a level
sc.customer = t
o = must(a.post(SO, {**typed, "customer_id": t["id"], "price_level_id": None}), "order for the note")
must(a.post(f"{SO}/{o['id']}/approve", {}), "approve")
note = new_note(sc, o, "2", dispatch=True)
nl = must(a.get(f"{DN}/{note['id']}"), "note")["lines"][0]
refused = a.post(SI, {
    "customer_id": t["id"], "branch_id": sc.branch["id"], "invoice_date": today().isoformat(),
    "price_level_id": retail["id"],
    "source_documents": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"]}],
    "lines": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"],
               "source_document_line_id": nl["id"], "line_number": 1, "current_invoice_quantity": "2"}]})
c.refused(refused, 422, "takes its prices from the documents", "a bill of notes that names a level is refused")
c.done()
