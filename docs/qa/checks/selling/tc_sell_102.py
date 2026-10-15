"""TC-SELL-102: billing and shipping address: what each document takes and what each print shows."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_102")
a = admin()
sc = Scene(a, stock="300")
T = sc.tag


def addr(kind: str, city: str, billing: bool = False, shipping: bool = False) -> dict:
    """Return one address input."""
    return {"address_type": kind, "address_line1": f"{city} line {T}", "city": f"{city}{T}",
            "state": "Karnataka", "country": "IN", "postal_code": "560001",
            "is_default_billing": billing, "is_default_shipping": shipping}


def customer(label: str, addresses: list[dict]) -> dict:
    """Make a customer with addresses; return it read back with its address ids."""
    made = sc.new_customer(addresses=addresses)
    got = must(a.get(f"/api/v1/customers/{made['id']}"), "customer read")
    got["by_city"] = {x["city"]: x["id"] for x in got["addresses"]}
    return got


def chain(cust: dict, ship_order: str | None = None, ship_note: str | None = None,
          ship_bill: str | None = None, qty: str = "1") -> tuple[dict, dict, dict]:
    """Raise, approve, deliver and bill one sale of the customer; return the three documents read back."""
    extra = {"shipping_address_id": ship_order} if ship_order else {}
    order = new_order(sc, qty, customer=cust, approve=True, **extra)
    note = new_note(sc, order, qty, dispatch=True, **({"shipping_address_id": ship_note} if ship_note else {}))
    line = must(a.get(f"{DN}/{note['id']}"), "note")["lines"][0]
    bill = must(a.post(SI, {
        "customer_id": cust["id"], "branch_id": sc.branch["id"], "invoice_date": today().isoformat(),
        **({"shipping_address_id": ship_bill} if ship_bill else {}),
        "source_documents": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"]}],
        "lines": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"],
                   "source_document_line_id": line["id"], "line_number": 1, "current_invoice_quantity": qty}]}), "bill")
    bill = must(a.post(f"{SI}/{bill['id']}/approve", {}), "bill approve")
    return (must(a.get(f"{SO}/{order['id']}"), "o"), must(a.get(f"{DN}/{note['id']}"), "n"),
            must(a.get(f"{SI}/{bill['id']}"), "b"))


def text(path: str, doc: dict) -> str:
    """Return a document's printed text."""
    status, raw = a.raw(f"{path}/{doc['id']}/print")
    if status != 200:
        raise SystemExit(f"PRECONDITION print {path}: {status}")
    return pdf_text(raw)


A = customer("A", [addr("BILLING", "Alphapur", billing=True), addr("SHIPPING", "Betanagar", shipping=True), addr("SHIPPING", "Gammabad")])
B = customer("B", [addr("BILLING", "Deltapur")])
C = customer("C", [addr("BILLING", "Epsilonpet"), addr("BILLING", "Zetaguda", billing=True)])
ids = A["by_city"]
alpha, beta, gamma = (ids[f"{n}{T}"] for n in ("Alphapur", "Betanagar", "Gammabad"))

o, n, b = chain(A)
c.eq((o["shipping_address_id"], n["shipping_address_id"], b["shipping_address_id"]), (beta, beta, beta), "step 1: all three ship to Betanagar")
o, n, b = chain(A, ship_order=gamma)
c.eq((o["shipping_address_id"], n["shipping_address_id"], b["shipping_address_id"]), (gamma, gamma, gamma), "step 2: all three ship to Gammabad")
for what, path, doc in (("order", SO, o), ("challan", DN, n), ("bill", SI, b)):
    t = text(path, doc)
    c.ok(f"Gammabad{T}" in t, f"step 2: the {what} print shows Gammabad")
    c.ok(f"Betanagar{T}" not in t, f"step 2: the {what} print does not show Betanagar")
    c.ok(f"Alphapur{T}" in t, f"step 2: the {what} print shows the Alphapur billing address")
o, n, b = chain(A, ship_order=gamma, ship_note=beta)
c.eq(b["shipping_address_id"], beta, "step 3: the bill follows the note, not the order")
o, n, b = chain(A, ship_bill=gamma)
c.eq(b["shipping_address_id"], gamma, "step 4: the bill's own choice holds")
c.ok(f"Gammabad{T}" in text(SI, b), "step 4: and prints")
o, n, b = chain(B)
t = text(SI, b)
c.ok(t.count(f"Deltapur{T}") >= 2, "step 5: both blocks of the bill show Deltapur", t.count(f"Deltapur{T}"))
c.ok(f"Deltapur{T}" in text(DN, n), "step 5: so does the challan")
o, n, b = chain(C)
for what, path, doc in (("order", SO, o), ("challan", DN, n), ("bill", SI, b)):
    t = text(path, doc)
    c.ok(f"Zetaguda{T}" in t and f"Epsilonpet{T}" not in t, f"step 6: the {what} print shows Zetaguda and not Epsilonpet")
# another customer's address is refused
foreign = a.post(SO, {"customer_id": B["id"], "order_date": today().isoformat(), "branch_id": sc.branch["id"],
                      "warehouse_id": sc.warehouse["id"], "shipping_address_id": gamma,
                      "lines": [{"line_number": 1, "product_id": sc.product["id"], "quantity": "1"}]})
c.refused(foreign, 422, "ship-to address must be one of the customer's own", "an address of another customer is refused")
c.done()
