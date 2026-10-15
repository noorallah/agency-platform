"""TC-BUY-001: raising a purchase order; approval cannot be skipped."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_001")
a = admin()
sc = Scene(a)
made = sc.order(approve=False)
c.eq(made["status"], "DRAFT", "a new order is a draft")
c.ok(str(made["po_number"]).startswith("PO-"), "the number is a PO- number", made["po_number"])
line = made["lines"][0]
c.eq(D(line["ordered_quantity"]), D(10), "the line orders 10")
c.eq(D(line["unit_price"]), D(100), "at 100")
c.eq(line["product_id"], sc.product["id"], "the line names the product")
c.eq(D(made["grand_total"]), D(1180), "10 x 100 + 18% GST is 1,180.00")
c.refused(a.post(f"{PO}/{made['id']}/approve", {}), 422, "Only submitted purchase orders can be approved", "approve on a draft is refused")
c.eq(must(a.get(f"{PO}/{made['id']}"), "read")["status"], "DRAFT", "the refusal changed nothing")
sub = must(a.post(f"{PO}/{made['id']}/submit", {}), "submit")
c.eq(sub["status"], "SUBMITTED", "submitted")
c.eq(must(a.post(f"{PO}/{made['id']}/approve", {}), "approve")["status"], "APPROVED", "approved")
c.done()
