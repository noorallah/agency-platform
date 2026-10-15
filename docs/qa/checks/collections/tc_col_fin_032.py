"""TC-FIN-032: the collector's day sheet adds up to the receipts."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from datetime import timedelta

from _col import *

c = Check("tc_col_fin_032")
a = admin()
col = admin("collector1")
c1, c2 = collector_ids()
sc = Scene(a)
cust = sc.customer()
t = today().isoformat()
CS = "/api/v1/customers/credit-settings"
held = must(a.get(CS), "credit settings")
wanted = {
    k: held[k]
    for k in (
        "enforcement", "warn_at_percent", "block_at_percent", "cash_discount_days",
        "cash_discount_percent", "overdue_interest_rate", "interest_grace_days",
        "collector_records_receipt",
    )
}


def switch(on: bool) -> None:
    """Switch 'Collectors record their own receipts'."""
    must(a.put(CS, {**wanted, "collector_records_receipt": on}), "credit settings")


def sheet() -> dict:
    """Read the collector's day sheet as the office sees it."""
    return must(a.get(f"{COL}/day-sheet?day={t}&collector_id={c1}"), "day sheet")


def handover_of(bill: dict) -> str:
    """Return the id of the handover that carries a bill."""
    for row in all_rows(col, f"{COL}/my-bills", 50):
        if row["invoice_id"] == bill["id"]:
            return row["handover_id"]
    raise SystemExit(f"PRECONDITION bill {bill['invoice_number']} is not on the collector's list")


try:
    switch(False)
    with counter(a):
        bills = [sc.bill(cust, "10") for _ in range(4)]  # 1,180.00 each
    c.eq(hand(a, [b["id"] for b in bills[:3]], c1)[0], 201, "step 1: three bills handed to the collector")
    # an earlier run's unreceipted lines would make today's sheet not add up: clear them
    for left in sheet()["rows"]:
        if left["settlement_id"] is None and left["cancelled_at"] is None:
            a.post(f"{COL}/returns/{left['id']}/withdraw", {"reason": "check clean-up"})
    start = sheet()
    c.eq(start["collector_records_receipt"], False, "the firm's switch is off")
    # 3
    full = must(col.post(f"{COL}/my-bills/returns", {"handover_id": handover_of(bills[0]), "outcome": "COLLECTED", "amount_collected": "1180.00", "payment_mode": "CASH", "return_date": t}), "collected")
    c.eq(full["settlement_id"], None, "step 3: no receipt exists: the office records it")
    c.eq(D(full["outstanding_before"]), D("1180.00"), "it owed 1,180.00")
    c.eq(owing(a, cust, bills[0]), D("1180.00"), "and still owes its full amount")
    c.eq(
        [r["return_outcome"] for r in all_rows(col, f"{COL}/my-bills", 50) if r["invoice_id"] == bills[0]["id"]],
        ["COLLECTED"], "it stays on his list marked Collected",
    )
    # 4
    promised = (today() + timedelta(days=3)).isoformat()
    part = must(col.post(f"{COL}/my-bills/returns", {"handover_id": handover_of(bills[1]), "outcome": "PART", "amount_collected": "400.00", "payment_mode": "CASH", "promised_on": promised, "return_date": t}), "part")
    c.eq(D(part["amount_collected"]), D("400.00"), "step 4: Part collected carries 400.00")
    c.ok(part["payment_promise_id"], "a promise for the rest exists", part.get("payment_promise_id"))
    promise = [p for p in all_rows(a, f"{COL}/promises?customer_id={cust['id']}", 50) if p["id"] == part["payment_promise_id"]]
    c.eq(len(promise), 1, "it is on Payment Promises")
    if promise:
        c.eq(D(promise[0]["amount"]), D("780.00"), "for the 780.00 left")
        c.eq(promise[0]["collector_id"], c1, "in his name")
        c.eq(promise[0]["promised_on"], promised, "on the day he named")
    # 5
    none = must(col.post(f"{COL}/my-bills/returns", {"handover_id": handover_of(bills[2]), "outcome": "NOT_COLLECTED", "note": "shop closed", "return_date": t}), "not collected")
    c.eq(D(none["amount_collected"]), D("0"), "step 5: Not collected carries nothing")
    # 6
    day = sheet()
    live = [r for r in day["rows"] if r["cancelled_at"] is None]
    was = [r for r in start["rows"] if r["cancelled_at"] is None]
    c.eq(len(live) - len(was), 3, "step 6: three new lines")
    c.eq(D(day["amount_stated"]) - D(start["amount_stated"]), D("1580.00"), "stated is the first bill plus the part: 1,580.00")
    c.eq(D(day["amount_receipted"]) - D(start["amount_receipted"]), D("0"), "in receipts is nothing")
    c.eq(D(day["amount_not_receipted"]) - D(start["amount_not_receipted"]), D("1580.00"), "1,580.00 is not receipted")
    c.eq(day["adds_up"], False, "the sheet says it does not add up")
    for key, by in (("collected_bills", 1), ("part_bills", 1), ("not_collected_bills", 1)):
        c.eq(day[key] - start[key], by, f"{key} grew by one")
    # 7
    r1 = must(a.post(f"{COL}/returns/{full['id']}/receipt"), "receipt 1")
    r2 = must(a.post(f"{COL}/returns/{part['id']}/receipt"), "receipt 2")
    c.ok(r1["settlement_number"], "step 7: line one names its receipt", r1.get("settlement_number"))
    c.ok(r2["settlement_number"], "and line two names its receipt")
    c.eq(owing(a, cust, bills[0]), D("0"), "the first bill owes nothing")
    c.eq(owing(a, cust, bills[1]), D("780.00"), "the second owes the rest")
    day = sheet()
    c.eq(day["adds_up"], True, "the sheet says it adds up")
    c.eq(D(day["amount_not_receipted"]), D("0"), "stated equals receipted: nothing is left unreceipted")
    c.eq(D(day["amount_receipted"]) - D(start["amount_receipted"]), D("1580.00"), "receipted grew by 1,580.00")
    rcpts = {x["settlement_number"]: x for x in all_rows(a, f"{RC}?customer_id={cust['id']}", 50)}
    c.eq(set(rcpts), {r1["settlement_number"], r2["settlement_number"]}, "each receipt is on Receipts")
    c.eq(rcpts[r1["settlement_number"]]["settlement_date"], t, "dated today")
    c.eq(D(rcpts[r2["settlement_number"]]["allocated_amount"]), D("400.00"), "applied to its bill")
    # 8
    switch(True)
    c.eq(hand(a, [bills[3]["id"]], c1)[0], 201, "step 8: a fourth bill is handed over")
    n_before = len(all_rows(a, f"{RC}?customer_id={cust['id']}", 50))
    fourth = must(col.post(f"{COL}/my-bills/returns", {"handover_id": handover_of(bills[3]), "outcome": "COLLECTED", "amount_collected": "1180.00", "payment_mode": "CASH", "return_date": t}), "fourth")
    c.ok(fourth["settlement_number"], "the receipt is made on saving", fourth.get("settlement_number"))
    c.eq(len(all_rows(a, f"{RC}?customer_id={cust['id']}", 50)), n_before + 1, "it is on Receipts")
    c.eq(owing(a, cust, bills[3]), D("0"), "the fourth bill is paid")
    c.ok(bills[3]["id"] not in [r["invoice_id"] for r in all_rows(col, f"{COL}/my-bills", 50)], "the fourth bill leaves his list")
    c.eq(sheet()["adds_up"], True, "the sheet still adds up")
    c.eq(col.get(RC)[0], 403, "he still has no Receipts screen")
    # 9
    st, body = col.post(f"{COL}/my-bills/returns/{fourth['id']}/withdraw", {"reason": "mistake"})
    c.ok(st in (409, 422), "step 9: withdrawing the line is refused", (st, message(body)))
    c.ok(fourth["settlement_number"] in message(body), "naming the receipt to reverse first", message(body))
finally:
    switch(bool(held["collector_records_receipt"]))
c.done()
