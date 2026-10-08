"""D-STK-19: opening stock for a serial-tracked product gives units with no serial number.

The file import refuses serial-numbered stock because a line carries no serials; the form path
(create + post) does not, and the 4 units can then not be dispatched (a dispatch needs serial ids).
The 403 naming SERIAL_NUMBER that the register describes no longer reproduces (a pharmacy firm now records the serial).
"""
from _inv import *
from _flow import *

c = Check("d_stk_19")
w = World()
wh = w.warehouse()
ps = w.product(goods_type="ELECTRONICS")
st, b = w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "reference_number": f"S{w.tag}", "posting_date": w.today,
                                              "lines": [{"product_id": ps["id"], "quantity": "4", "unit_cost": "10"}]})
posted = False
if st == 201:
    st2, b2 = w.admin.post(f"{INV}/opening-stock/{data(b)['id']}/post", {})
    posted = st2 == 200
c.ok(st in (409, 422) or not posted, "opening stock of a serial-tracked product with no serial numbers is refused (as the import refuses it)", (st, w.qty(ps["id"])))
c.eq(w.qty(ps["id"]), D(0), "no serial-less units on hand")
c.done()
