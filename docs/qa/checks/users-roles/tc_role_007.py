"""TC-ROLE-007: a custom role codes become exactly those screens (the server half)."""
from _ur import *
from _roles import night_desk

c = Check("tc_role_007"); sc = Scene()
try:
    role = night_desk(sc)
    holder = sc.user("holder")
    must(sc.admin.put(f"{U}/{holder['id']}/firms/{one()}/roles", {"ids": [role["id"]]}), "give the role")
    u = sc.sign_in(holder)
    for path in ("/api/v1/customers", "/api/v1/receipts?page_size=1", "/api/v1/sales-invoices"):
        c.eq(u.get(path)[0], 200, f"GET {path} is offered")
    c.eq(u.post("/api/v1/receipts", {})[0], 422, "Record Receipt is allowed")
    for path in ("/api/v1/vendors", "/api/v1/purchases", "/api/v1/products", "/api/v1/payments", "/api/v1/finance/journal-entries"):
        c.eq(u.get(path)[0], 403, f"GET {path} is refused (no Buy, Stock or Money)")
    c.eq(u.get(U)[0], 403, "no Platform part")
    c.eq(u.post("/api/v1/customers", {})[0], 403, "customers are view-only")
finally:
    sc.cleanup()
c.done()
