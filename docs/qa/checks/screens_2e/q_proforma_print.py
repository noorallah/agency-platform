"""D-UI-71: a proforma prints, for whoever may read it, and for nobody else.

Reads TEST01 with the accounts the goods types checks made (their state file),
so run `goods_types/setup.py` first on a fresh machine. Takes the firm's
newest proforma, or raises one against an approved order when there is none;
it withdraws nothing and sends nothing.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import Check, client, data, message

MODULE = "goods_types"
c = Check("q_proforma_print")
admin, sales, store = (
    client("admin", MODULE), client("sales", MODULE), client("store", MODULE))
other_firm = client("test02_admin", MODULE)
ROOT = "/api/v1/proforma-invoices"

status, body = admin.get(f"{ROOT}?page_size=1")
if status != 200:
    raise SystemExit(f"PRECONDITION proforma list: {status} {message(body)}")
rows = data(body) or []
if not rows:
    status, body = admin.get(
        "/api/v1/sales-orders?document_status=APPROVED&page_size=1")
    orders = data(body) or []
    if status != 200 or not orders:
        raise SystemExit("PRECONDITION no proforma and no approved order on TEST01")
    status, body = admin.post(ROOT, {
        "sales_order_id": orders[0]["id"],
        "proforma_date": orders[0]["order_date"],
    })
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION raise: {status} {message(body)}")
    rows = [data(body)]
proforma = rows[0]
path = f"{ROOT}/{proforma['id']}/print"

status, pdf = admin.raw(path)
c.eq(status, 200, "the administrator prints it")
c.ok(pdf[:4] == b"%PDF", "the answer is a PDF", pdf[:20])
c.ok(len(pdf) > 1500, "the PDF holds a page", len(pdf))

# Whoever may read the list may print; whoever may not is refused the same.
for name, api in (("sales", sales), ("store", store)):
    reads, _ = api.get(f"{ROOT}?page_size=1")
    prints, _ = api.raw(path)
    c.eq(prints, 200 if reads == 200 else 403,
         f"{name}: print follows PROFORMA_VIEW (list answered {reads})")

status, _ = other_firm.raw(path)
c.eq(status, 404, "another firm's administrator is told it does not exist")

status, _ = admin.raw(f"{ROOT}/00000000-0000-0000-0000-000000000000/print")
c.eq(status, 404, "an id nobody holds is not found")

c.done()
