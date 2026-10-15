"""TC-FIN-041: one customer pays another customer's bill."""
import base64
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import re
import zlib

from _col import *

c = Check("tc_col_fin_041")
a = admin()
sc = Scene(a)
A, B = sc.customer(), sc.customer()
with counter(a):
    b1, b2 = sc.bill(B, "1"), sc.bill(B, "2")  # 118.00 and 236.00
day = today().isoformat()


def pdf_text(raw: bytes) -> str:
    """Return the strings shown by a reportlab PDF."""
    out: list[str] = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        chunk = m.group(1).strip()
        try:
            body = base64.a85decode(chunk[:-2]) if chunk.endswith(b"~>") else chunk
            body = zlib.decompress(body)
        except Exception:  # noqa: BLE001
            continue
        out.extend(s.decode("latin-1") for s in re.findall(rb"\(((?:\\.|[^\\)])*)\)", body))
    return "\n".join(out)


def lines(customer: dict, kind: str) -> list[dict]:
    """Return a customer's statement lines of one type."""
    got = must(a.get(f"{CU}/{customer['id']}/statement?from_date={day}&to_date={day}"), "statement")
    return [x for x in got["lines"] if x["transaction_type"] == kind]


c.eq(position(a, A), (D("0"), D("0")), "set-up: A owes and holds nothing")
c.eq(position(a, B), (D("354.00"), D("0")), "and B owes 354.00")
# 2, 3
st, body = receipt(a, A, "118.00", [(b1, "118.00")], paid_for_customer_id=B["id"])
c.eq(st, 201, "step 2: the receipt is saved")
r = data(body)
c.eq(r["party_id"], A["id"], "step 3: in A's name")
c.eq(r["allocations"][0]["party_code"], B["code"], "its allocation names B")
# 4
c.eq(position(a, B), (D("236.00"), D("0")), "step 4: B owes 118.00 less")
c.eq(owing(a, B, b1), D("0"), "B's first bill is paid")
b_receipt = [x for x in lines(B, "RECEIPT") if x["reference_number"] == r["settlement_number"]]
c.eq(len(b_receipt), 1, "B's statement has the receipt line")
if b_receipt:
    c.eq(D(b_receipt[0]["credit"]), D("118.00"), "for 118.00")
    c.ok(A["name"] in str(b_receipt[0]["remarks"]) and "Paid by" in str(b_receipt[0]["remarks"]), "saying Paid by A", b_receipt[0]["remarks"])
a_transfer = [x for x in lines(A, "RECEIPT_TRANSFER") if x["reference_number"] == r["settlement_number"]]
c.eq(len(a_transfer), 1, "A's statement has a Paid for B line")
if a_transfer:
    c.ok(B["name"] in str(a_transfer[0]["remarks"]) and b1["invoice_number"] in str(a_transfer[0]["remarks"]), "naming B and the bill's number", a_transfer[0]["remarks"])
c.eq(position(a, A), (D("0"), D("0")), "A owes and holds exactly what it did before")
# 5
status, raw = a.raw(f"{RC}/{r['id']}/print")
text = pdf_text(raw)
c.eq((status, raw[:4]), (200, b"%PDF"), "step 5: the receipt prints")
c.ok(A["name"] in text, "it reads Received from A", text[:200])
c.ok(B["name"] in text, "and names B (Paid for)")
c.ok(b1["invoice_number"] in text, "with the bill under Against")
# 6
st, body = a.post(f"{RC}/{r['id']}/reverse", {"reason": "check"})
c.eq(st, 200, "step 6: the receipt is reversed")
c.eq(position(a, B), (D("354.00"), D("0")), "B owes the bill again")
c.eq(position(a, A), (D("0"), D("0")), "A is unchanged")
# 7
adv = data(receipt(a, A, "10000.00")[1])
c.eq(position(a, A), (D("0"), D("10000.00")), "step 7: A holds 10,000.00 on account")
own = rows_of(a.get(f"{RC}/outstanding?customer_id={A['id']}"))
c.ok(b1["id"] not in {x["invoice_id"] for x in own}, "Apply offers A's own bills, not B's")
# 8
mark = journal_count(a)
st, body = a.post(f"{RC}/{adv['id']}/allocate", {"invoice_id": b1["id"], "amount": "118.00", "paid_for_customer_id": B["id"]})
c.eq(st, 200, "step 8: B's bill is applied from A's advance")
c.eq(owing(a, B, b1), D("0"), "B's bill is paid")
c.eq(position(a, A), (D("0"), D("9882.00")), "A holds 118.00 less on account")
c.eq(journal_count(a), mark, "no new journal entry")
# 9
st, body = receipt(a, A, "286.00", [(b2, "236.00")], paid_for_customer_id=B["id"])
c.eq(st, 201, "step 9: a receipt in A's name for B's second bill and 50.00 more")
c.eq(position(a, B), (D("0"), D("0")), "B owes nothing and holds nothing")
c.eq(position(a, A)[1], D("9932.00"), "the 50.00 is held on A's account, not B's")
# 10
other = sc.customer()
st, body = a.post("/api/v1/payments", {"party_id": other["id"], "settlement_date": day, "amount": "10.00", "method": "CASH", "paid_for_customer_id": B["id"], "allocations": []})
c.ok(st in (404, 422), "step 10: a payment cannot name a customer it pays for", (st, message(body)))
vendor = must(a.post("/api/v1/vendors", {"code": f"PF{sc.tag}", "name": f"Paid-for vendor {sc.tag}"}), "vendor")
c.refused(
    a.post("/api/v1/payments", {"party_id": vendor["id"], "settlement_date": day, "amount": "10.00", "method": "CASH", "paid_for_customer_id": B["id"], "allocations": []}),
    422, "Only a receipt can pay another customer's bill", "a payment to a supplier with a Paid-by customer is refused",
)
c.done()
