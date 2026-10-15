"""TC-BUY-067: a typed free quantity is kept, and 0 refuses the scheme."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_067")
a = admin()
sc = Scene(a)
must(a.post("/api/v1/supplier-schemes", {
    "vendor_id": sc.vendor["id"], "product_id": sc.product["id"], "buy_quantity": "10", "free_quantity": "2",
    "valid_from": today().isoformat(),
}), "scheme")


def free_of(qty: str, free: str | None, day: str | None = None) -> Decimal:
    """Save a draft order and return the free quantity its line kept."""
    body = sc.order_body(qty=qty, free=free)
    if day:
        body["purchase_date"] = day
    return D(must(a.post(PO, body), "order")["lines"][0]["free_quantity"])


c.eq(free_of("25", "0"), D(0), "a typed 0 stays 0: zero refuses the scheme")
c.eq(free_of("25", "1"), D(1), "a typed 1 stays 1")
c.eq(free_of("9", None), D(0), "nine units earn nothing")
c.eq(free_of("25", None), D(4), "blank takes the scheme")
c.eq(free_of("25", None, (today() - timedelta(days=3)).isoformat()), D(0), "an order dated before the scheme started takes no free goods")
c.done()
