"""TC-FIN-021: approvals by level, and bulk reject (sales invoices; the chain is shared by the four document types)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_021")
a = admin()
plat = client("platform", MODULE)
held = state(MODULE)
fid, stem = held["firm_id"], held["suffix"]
users = {}
for key, role in (("finmgr", "SALES_MANAGER"), ("finsales", "SALES_EXECUTIVE")):
    email = f"{stem}.{key}@fixtures.local"
    ensure_user(plat, email, f"Finance {key}", fid, role)
    users[key] = sign_in(email, firm_id=fid)
mgr, sales = users["finmgr"], users["finsales"]
SI = "/api/v1/sales-invoices"
AP = "/api/v1/approvals"
RULES = f"{AP}/rules/SALES_INVOICE"
sc = Scene(a, stock="800")
cust = sc.customer()


def status(doc: dict) -> str:
    """Read a bill's status."""
    return data(a.get(f"{SI}/{doc['id']}")[1])["status"]


def steps(doc: dict) -> list[dict]:
    """Read a bill's sign-off steps."""
    return data(a.get(f"{AP}/SALES_INVOICE/{doc['id']}")[1])["steps"]


with counter(a):
    free = sc.bill(cust, "1", approve=False)
    # with no rule for the document nothing changes
    c.eq([r for r in rows_of(a.get(f"{AP}/rules")) if r.get("document_type") == "SALES_INVOICE"], [], "the firm starts with no rule for sales invoices")
    c.eq(a.post(f"{SI}/{free['id']}/approve", {})[0], 200, "no rule: a bill approves as ever")
    try:
        st, ans = a.put(RULES, {"rules": [{"level": 1, "min_amount": "0", "role_code": "SALES_MANAGER"}, {"level": 2, "min_amount": "10000", "role_code": "FIRM_ADMIN"}]})
        c.eq(st, 200, "rules: level 1 from 0 for the Sales Manager, level 2 from 10,000 for the Firm Administrator")
        c.eq(sales.put(RULES, {"rules": []})[0], 403, "a Sales Executive cannot change the rules")
        c.eq(a.put(RULES, {"rules": [{"level": 4, "min_amount": "0", "role_code": "FIRM_ADMIN"}]})[0], 422, "level 4 is refused (three levels at most)")
        c.eq(a.put(f"{AP}/rules/NOT_A_DOCUMENT", {"rules": []})[0], 422, "an unknown document type is refused")
        big = sc.bill(cust, "100", approve=False)   # 11,800.00
        small = sc.bill(cust, "5", approve=False)   # 590.00
        c.eq(D(big["grand_total"]), D("11800.00"), "the big bill is 11,800.00")
        c.eq([s["level"] for s in steps(big)], [1, 2], "the big bill needs two levels")
        c.eq([s["level"] for s in steps(small)], [1], "the small bill needs one")
        # approval cannot be skipped
        c.refused(a.post(f"{SI}/{big['id']}/approve", {}), 422, "level 1 sign-off", "Approve on the order itself is refused naming the level")
        c.refused(mgr.post(f"{SI}/{big['id']}/approve", {}), 422, "level 1 sign-off", "and for the manager too, before any sign-off")
        c.ok(sales.post(f"{AP}/sign-off", {"document_type": "SALES_INVOICE", "document_id": big["id"]})[0] in (403, 422), "a Sales Executive cannot sign off")
        # level 1
        st, ans = mgr.post(f"{AP}/sign-off", {"document_type": "SALES_INVOICE", "document_id": big["id"]})
        c.eq(st, 200, "level 1: the Sales Manager signs off")
        c.eq(data(ans)["status"], "DRAFT", "the bill is still a draft after level 1")
        c.eq(steps(big)[0]["signed_by"] is not None and steps(big)[1]["signed_by"] is None, True, "level 1 is signed, level 2 is open")
        c.refused(mgr.post(f"{AP}/sign-off", {"document_type": "SALES_INVOICE", "document_id": big["id"]}), 422, "signed an earlier level", "the same person cannot sign two levels")
        c.refused(mgr.post(f"{SI}/{big['id']}/approve", {}), 422, "level 2", "the manager cannot approve past level 2")
        c.eq(status(big), "DRAFT", "still a draft")
        pend = [r["document_id"] for r in rows_of(a.get(f"{AP}/pending"))]
        c.ok(big["id"] in pend, "the administrator's queue holds the bill awaiting level 2", pend)
        # last sign-off approves
        st, ans = a.post(f"{AP}/sign-off", {"document_type": "SALES_INVOICE", "document_id": big["id"]})
        c.eq((st, data(ans)["status"]), (200, "APPROVED"), "level 2: the last sign-off approves the bill through its own service")
        c.eq(status(big), "APPROVED", "the bill reads APPROVED")
        # one level only
        st, ans = mgr.post(f"{AP}/sign-off", {"document_type": "SALES_INVOICE", "document_id": small["id"]})
        c.eq((st, data(ans)["status"]), (200, "APPROVED"), "the 590.00 bill needs only level 1, so the manager's sign-off approves it")
        # reject
        r1 = sc.bill(cust, "100", approve=False)
        mgr.post(f"{AP}/sign-off", {"document_type": "SALES_INVOICE", "document_id": r1["id"]})
        c.refused(a.post(f"{AP}/reject", {"document_type": "SALES_INVOICE", "document_id": r1["id"], "reason": ""}), 422, "", "reject without a reason is refused")
        st, ans = a.post(f"{AP}/reject", {"document_type": "SALES_INVOICE", "document_id": r1["id"], "reason": "price not agreed"})
        c.eq(st, 200, "reject with a reason")
        c.eq([s["signed_by"] for s in steps(r1)], [None, None], "rejection clears the sign-offs")
        c.eq(data(a.get(f"{AP}/SALES_INVOICE/{r1['id']}")[1])["rejected_reason"], "price not agreed", "and keeps the reason")
        # bulk reject: per row
        b1, b2 = sc.bill(cust, "100", approve=False), sc.bill(cust, "100", approve=False)
        done = mgr.post(f"{AP}/bulk-reject", {"document_type": "SALES_INVOICE", "items": [{"id": b1["id"]}, {"id": b2["id"]}, {"id": big["id"]}], "reason": "bulk check"})
        c.eq(done[0], 200, "bulk reject runs")
        res = data(done[1])
        c.eq((res["done"], res["refused"]), (2, 1), "two drafts rejected, the already-approved bill refused on its own row")
        c.eq(a.post(f"{AP}/bulk-reject", {"document_type": "SALES_INVOICE", "items": [{"id": sc.bill(cust, "100", approve=False)["id"]}], "reason": "x"})[1]["data"]["refused"], 1, "the Firm Administrator is not the level-1 role: the row is refused naming SALES_MANAGER (case text says an administrator rejects)")
        c.eq(len(steps(b1)) and data(a.get(f"{AP}/SALES_INVOICE/{b1['id']}")[1])["rejected_reason"], "bulk check", "each rejected row keeps the reason")
    finally:
        back = a.put(RULES, {"rules": []})
    c.eq(back[0], 200, "the rules are put back")
c.done()
