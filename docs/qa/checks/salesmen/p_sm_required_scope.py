"""Probe: the required switch does not apply to a quotation or a return."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("p_sm_required_scope")
a = admin()
sc = Scene(a, stock="100")
inv = sell(sc, None, "5", "100", today())            # an approved bill, no salesman
lines = must(a.get(f"{SI}/{inv['id']}"), "bill read").get("lines") or []
with settings(a, salesman_required=True):
    status, body = a.post(QT, sc.quote_body("1"))
    c.eq(status, 201, f"quotation without a salesman saves ({message(body)[:150]})")
    ret = {
        "customer_id": sc.customer["id"], "branch_id": sc.branch["id"],
        "warehouse_id": sc.warehouse["id"], "return_date": today().isoformat(),
        "source_documents": [{"source_document_type": "SALES_INVOICE", "source_document_id": inv["id"]}],
        "lines": [{
            "source_document_type": "SALES_INVOICE", "source_document_id": inv["id"],
            "source_document_line_id": lines[0]["id"] if lines else None,
            "line_number": 1, "current_return_quantity": "1", "restock_quantity": "1",
        }],
    }
    status, body = a.post(SR, ret)
    c.ok("requires a salesman" not in message(body),
         "a sales return is not refused for the missing salesman", f"{status} {message(body)[:200]}")
    c.ok(status in (200, 201), "and it saves", f"{status} {message(body)[:200]}")
c.done()
