"""TC-USER-009: a Counter Sales hire gets the till and not the ledger (server half)."""
from _ur import *

c = Check("tc_user_009"); sc = Scene()
try:
    row, u = sc.hire("counter", "counter-sales")
    c.eq(codes(sc, roles_of(sc.admin, row["id"], one())), ["BILLING_EXECUTIVE", "CASHIER"], "the job two roles")
    c.eq(u.post("/api/v1/receipts", {})[0], 422, "Receipts is allowed (validation, not 403)")
    c.eq(u.post("/api/v1/payments", {})[0], 422, "Payments is allowed")
    for path in ("/api/v1/finance/journal-entries", "/api/v1/refunds"):
        c.eq(u.post(path, {})[0], 403, f"{path} is refused")
    for path in ("/api/v1/finance/trial-balance", "/api/v1/finance/accounts", "/api/v1/finance/ledgers"):
        st = u.get(path)[0]
        c.ok(st in (403, 404, 422), f"{path} is not readable by the till", st)
    for path in (U, R, "/api/v1/permissions", T):
        c.eq(u.get(path)[0], 403, f"no Platform part: GET {path}")
finally:
    sc.cleanup()
c.done()
