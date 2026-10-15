"""TC-SELL-100: approval switched off for a document: one Save completes it, and only for whoever raised it."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_100")
f = admin()
s = admin("exec")
sc = Scene(f, stock="50")
pid = sc.product["id"]
held = must(f.get(SETTINGS), "settings")
c.eq(s.put(SETTINGS, {k: held[k] for k in ("quotation_stage", "sales_order_stage", "delivery_note_stage")})[0], 403, "step 1: S cannot change the settings")
c.eq((held["sales_order_approval"], held["delivery_note_approval"], held["sales_invoice_approval"]), (True, True, True), "step 2: all three approvals start on")

with counter(f):
    f_draft = must(f.post(SI, sc.bill_body("1")), "F's draft with approval on")
    c.eq(f_draft["status"], "DRAFT", "with approval on a bill saves as a draft")


made_ids: list[str] = []


def save(api: Api, body: dict) -> tuple[int, Any]:
    """Press Save with approval switched off: create, then complete in the same step."""
    status, answer = api.post(SI, body)
    if status != 201:
        return status, answer
    made = data(answer)
    made_ids.append(made["id"])
    status, done = api.post(f"{SI}/{made['id']}/approve", {})
    return (status, done) if status != 200 else (201, done)


with counter(f, sales_invoice_approval=False):
    got = save(s, sc.bill_body("1"))
    c.eq(got[0], 201, f"step 3: S saves ({message(got[1])})")
    if got[0] == 201:
        c.eq(data(got[1])["status"], "APPROVED", "step 3: the bill is Approved")
    c.eq(stock(f, pid)[0], D(49), "step 3: stock of P falls by 1")
    big_f = save(f, sc.bill_body("500"))
    left = made_ids[-1]
    c.ok(big_f[0] in (400, 409, 422) and "stock" in message(big_f[1]).lower(), "step 4: F's bill of 500 is refused for stock", f"{big_f[0]} {message(big_f[1])}")
    other = s.post(f"{SI}/{left}/approve", {})
    c.refused(other, 403, "Only whoever raised", "step 4: S cannot approve the draft F left")
    drafts = rows_of(f.get(f"{SI}?customer_id={sc.customer['id']}&document_status=DRAFT&page_size=50"))
    c.ok(left in [d["id"] for d in drafts], "step 4: the refused bill stays a draft in the list", [d["id"] for d in drafts])
    big_s = save(s, sc.bill_body("500"))
    c.ok(big_s[0] in (400, 409, 422) and "stock" in message(big_s[1]).lower(), "step 5: S's bill of 500 is refused in words", f"{big_s[0]} {message(big_s[1])}")
    for d in rows_of(f.get(f"{SI}?customer_id={sc.customer['id']}&document_status=DRAFT&page_size=50")):
        if d["id"] != f_draft["id"]:
            f.post(f"{SI}/{d['id']}/cancel", {"reason": "check clean-up"})
with counter(f):
    got = s.post(SI, sc.bill_body("1"))
    c.eq(got[0], 201, "step 6: S saves with approval back on")
    mine = data(got[1])
    c.eq(mine["status"], "DRAFT", "step 6: it stays a draft")
    refused = s.post(f"{SI}/{mine['id']}/approve", {})
    c.refused(refused, 403, "SALES_APPROVE", "step 6: S cannot approve it")
    c.eq(must(f.post(f"{SI}/{mine['id']}/approve", {}), "F approves")["status"], "APPROVED", "step 7: F approves it")
reserved0 = stock(f, pid)[1]
with settings(f, sales_order_approval=False):
    got = s.post(SO, {
        "customer_id": sc.customer["id"], "order_date": today().isoformat(),
        "branch_id": sc.branch["id"], "warehouse_id": sc.warehouse["id"],
        "lines": [{"line_number": 1, "product_id": pid, "quantity": "2"}]})
    c.eq(got[0], 201, f"step 8: S saves an order ({message(got[1])})")
    if got[0] == 201:
        done = s.post(f"{SO}/{data(got[1])['id']}/approve", {})
        c.eq(done[0], 200, f"step 8: S completes it without SALES_APPROVE ({message(done[1])})")
        o = data(done[1]) if done[0] == 200 else data(got[1])
        c.eq(o["status"], "APPROVED", "step 8: the order is Approved")
        c.eq(stock(f, pid)[1], D(2) + reserved0, "step 8: it holds its stock")
back = must(f.get(SETTINGS), "settings")
c.eq((back["sales_order_approval"], back["sales_invoice_approval"]), (True, True), "step 9: everything is back as it was")
c.done()
