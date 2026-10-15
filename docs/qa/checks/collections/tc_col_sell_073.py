"""TC-SELL-073: the collection sheet, by collector."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_sell_073")
a = admin()
c1, c2 = collector_ids()
sc = Scene(a)
mine = sc.customer(payment_terms_days=30, collector_id=c1)
nobody = sc.customer(payment_terms_days=30)
with counter(a):
    bill = sc.bill(mine, "10")  # 1,180.00
    other = sc.bill(nobody, "10")
c.eq(D(bill["grand_total"]), D("1180.00"), "the bill is 1,180.00")


def sheet_rows(query: str, invoice: dict) -> list[dict]:
    """Return the sheet rows of one bill under a query."""
    return [r for r in all_rows(a, f"{COL}/sheet{query}", 100) if r["invoice_id"] == invoice["id"]]


rows = sheet_rows(f"?collector_id={c1}", bill)
c.eq(len(rows), 1, "the bill is on the chosen collector's sheet")
if rows:
    row = rows[0]
    c.eq(D(row["outstanding"]), D("1180.00"), "outstanding 1,180.00")
    c.eq(row["collector_id"], c1, "the bill is under the chosen collector")
    c.eq(row["customer_id"], mine["id"], "the customer is named")
    c.eq(row["promise_id"], None, "the promise columns are blank")
    c.eq(row["promised_amount"], None, "no promised amount")
    c.eq(row["days_overdue"], 0, "not overdue")
    c.ok(row["due_date"], "a due date is shown", row.get("due_date"))
c.eq(len(sheet_rows(f"?collector_id={c1}", other)), 0, "a customer with no collector is not under him")
c.eq(len(sheet_rows(f"?collector_id={c2}", bill)), 0, "nor is the bill under the other collector")
whole = sheet_rows("", other)
c.eq(len(whole), 1, "the unfiltered sheet lists the bill of the customer with no collector")
if whole:
    c.eq(whole[0]["collector_id"], None, "...under nobody (the fixture customer has no account manager)")
c.eq(len(sheet_rows(f"?collector_id={c1}&overdue_only=true", bill)), 0, "Overdue only hides a bill not yet due")
late = sheet_rows(f"?collector_id={c1}&overdue_only=true&as_of=2026-12-31", bill)
c.eq(len(late), 1, "judged on a later day the bill is overdue and listed")
if late:
    c.ok(late[0]["days_overdue"] > 0, "with its days overdue", late[0]["days_overdue"])
c.eq(len(sheet_rows(f"?collector_id={c1}&overdue_only=false", bill)), 1, "unticking Overdue only brings it back")
status, raw = a.raw(f"{COL}/sheet/pdf?collector_id={c1}")
c.eq(status, 200, "Print sheet answers")
c.eq(raw[:4], b"%PDF", "and it is a PDF")
c.done()
