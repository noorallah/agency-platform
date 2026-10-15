"""TC-FIN-012: bank reconciliation: import a statement, auto-match, tie left, manual match of one line to two entries, unmatch, remove statement, reconciliation statement."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import random

from _fin import *

BR = "/api/v1/bank-reconciliation"
c = Check("tc_fin_012")
a = admin()
viewer = admin("viewer")
bank = account(a, "1010")
sc = Scene(a)
cust = sc.customer()
n = Decimal(random.randint(1, 98)) / 100  # cents keep each run's amounts its own
tag = suffix(4)
with counter(a):
    bills = [sc.bill(cust, "20") for _ in range(3)]  # 2,360.00 each


def pay(amount: Decimal, ref: str | None, bill: dict) -> dict:
    """Record a bank receipt from the customer against a bill."""
    st, ans = receipt(a, cust, f"{amount:.2f}", [(bill, f"{amount:.2f}")], method="BANK", instrument_reference=ref)
    c.eq(st, 201, f"receipt {amount} recorded")
    return data(ans)


r1 = pay(Decimal("1200") + n, None, bills[0])             # matches by amount and date
r2 = pay(Decimal("700") + n, f"UTR{tag}77", bills[0])    # matches by reference
t1 = pay(Decimal("500") + n, None, bills[1])             # tied pair: two equal postings
t2 = pay(Decimal("500") + n, None, bills[1])
s1 = pay(Decimal("300") + n, None, bills[2])             # two postings that sum to one line
s2 = pay(Decimal("200") + n, None, bills[2])
day = today()
d = day.strftime("%d-%m-%Y")
orphan = Decimal("99.99")
lines = [
    (r1["amount"], f"NEFT CUSTOMER {tag}", ""),
    (r2["amount"], f"NEFT {tag}", f"UTR{tag}77"),
    (t1["amount"], "CASH DEP", ""),
    (t1["amount"], "CASH DEP", ""),
]
csv = ["Date,Description,Reference,Withdrawal,Deposit,Balance"]
bal = Decimal("10000")
for amt, desc, ref in lines:
    bal += D(amt)
    csv.append(f"{d},{desc},{ref},,{amt},{bal}")
sum_amount = D(s1["amount"]) + D(s2["amount"])
bal += sum_amount
csv.append(f"{d},CHQ CLEARING {tag},,,{sum_amount},{bal}")
bal += orphan
csv.append(f"{d},BANK INTEREST {tag},,,{orphan},{bal}")
final_balance = bal
content = "\n".join(csv).encode()
fields = {"ledger_account_id": bank["id"], "name": f"Check statement {tag}"}
STM = f"{BR}/statements?ledger_account_id={bank['id']}"

c.eq(viewer.upload(f"{BR}/statements/import-file", "s.csv", content, {**fields, "apply": "true"})[0], 403, "a Viewer cannot import")
st, ans = a.upload(f"{BR}/statements/import-file", "s.csv", content, fields)
rep = data(ans)
c.eq((st, rep["rows"], rep["issues"], rep["imported"]), (200, 6, [], False), "a check without apply reads 6 rows, no issues, imports nothing")
before = len(all_rows(a, STM))
st, ans = a.upload(f"{BR}/statements/import-file", "s.csv", content, {**fields, "apply": "true"})
rep = data(ans)
c.eq((st, rep["imported"], rep["issues"]), (200, True, []), "apply imports the six lines")
c.eq(len(all_rows(a, STM)), before + 1, "one more statement")
st, ans = a.upload(f"{BR}/statements/import-file", "s.csv", content, {**fields, "apply": "true"})
rep = data(ans)
c.ok(st == 200 and rep["imported"] is False and rep["issues"], "the same file again is refused with its issues named", (st, rep.get("imported"), len(rep.get("issues", []))))
stm = next(s for s in all_rows(a, STM) if s["name"] == fields["name"])
c.eq((stm["line_count"], stm["matched_count"]), (6, 0), "the statement holds 6 lines, none matched")

am = a.post(f"{BR}/auto-match", {"ledger_account_id": bank["id"], "statement_id": stm["id"]})
c.eq(am[0], 200, "auto-match runs")
res = data(am[1])
all_lines = all_rows(a, f"{BR}/lines?statement_id={stm['id']}")
sl = {l["description"]: l for l in all_lines}
c.eq(sl[f"NEFT CUSTOMER {tag}"]["status"], "MATCHED", "the amount-and-date line is matched")
c.eq(sl[f"NEFT {tag}"]["status"], "MATCHED", "the reference line is matched")
ties = [l for l in all_lines if l["description"] == "CASH DEP"]
c.eq([l["status"] for l in ties], ["UNMATCHED", "UNMATCHED"], "the tied lines are left for a person")
c.eq(sl[f"CHQ CLEARING {tag}"]["status"], "UNMATCHED", "the line that needs two entries is left")
c.eq(sl[f"BANK INTEREST {tag}"]["status"], "UNMATCHED", "the line with nothing behind it stays unmatched")
c.ok(res["matched"] >= 2, "auto-match reports at least the two it paired", res)
m1 = sl[f"NEFT CUSTOMER {tag}"]["matches"]
c.eq([m["reference_number"] for m in m1], [r1["settlement_number"]], "the amount match is the right receipt")
c.eq([m["reference_number"] for m in sl[f"NEFT {tag}"]["matches"]], [r2["settlement_number"]], "the reference match is the right receipt")

book = {b["reference_number"]: b for b in all_rows(a, f"{BR}/book-entries?ledger_account_id={bank['id']}")}
both = [book[s1["settlement_number"]]["gl_posting_id"], book[s2["settlement_number"]]["gl_posting_id"]]
man = a.post(f"{BR}/matches", {"statement_line_id": ties[0]["id"], "gl_posting_ids": [book[t1["settlement_number"]]["gl_posting_id"]]})
c.ok(man[0] in (200, 201), "a tied line matches by hand", (man[0], message(man[1])))
sumline = sl[f"CHQ CLEARING {tag}"]
bad = a.post(f"{BR}/matches", {"statement_line_id": sl[f"BANK INTEREST {tag}"]["id"], "gl_posting_ids": [book[t2["settlement_number"]]["gl_posting_id"]]})
c.eq(bad[0], 422, "a match that does not sum to the line is refused")
two = a.post(f"{BR}/matches", {"statement_line_id": sumline["id"], "gl_posting_ids": both})
c.ok(two[0] in (200, 201), "one line matches two entries that sum to it", (two[0], message(two[1])))
un = a.delete(f"{BR}/lines/{sumline['id']}/matches")
c.ok(un[0] in (200, 204), "unmatch works", (un[0], message(un[1])))
now = {l["description"]: l for l in all_rows(a, f"{BR}/lines?statement_id={stm['id']}")}
c.eq(now[f"CHQ CLEARING {tag}"]["status"], "UNMATCHED", "and the line is unmatched again")
a.post(f"{BR}/matches", {"statement_line_id": sumline["id"], "gl_posting_ids": both})

rs = must(a.get(f"{BR}/statement?ledger_account_id={bank['id']}&as_on={day.isoformat()}"), "reconciliation statement")
c.eq(D(rs["statement_balance"]), final_balance, "the printed closing balance is the last line's balance")
c.ok(D(rs["book_balance"]) != 0, "the book balance is read", rs["book_balance"])
c.ok(any(D(x["amount"]) == orphan for x in rs["bank_only"]), "the 99.99 line with nothing behind it shows under bank only")
c.ok(rs["difference"] is not None, "a difference against the printed balance is given", rs["difference"])
rm = a.delete(f"{BR}/statements/{stm['id']}")
c.eq(rm[0], 200, "the statement is removed")
back = {b["reference_number"] for b in all_rows(a, f"{BR}/book-entries?ledger_account_id={bank['id']}")}
c.ok(r1["settlement_number"] in back, "its receipts are uncleared book entries again")
c.done()
