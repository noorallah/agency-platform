"""TC-FIN-017: TDS challans (one section, one live challan per CIN, posts Dr TDS payable + interest / Cr bank, cancel mirrors and frees) and TDS on purchases (194Q)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import random

from _fin import *

c = Check("tc_fin_017")
a = admin()
viewer = admin("viewer")
CH = f"{FIN}/tds-challans"
bs = buy.Scene(a)
vendor = bs.new_vendor(pan="AAACT1234A", default_tds_section="194C", tds_applicable=True, gst_registration=False)
bs.vendor = vendor


def tds_bill() -> dict:
    """A 40,000.00 bill from the supplier, approved with 800.00 TDS under 194C."""
    order = bs.order(qty="400")
    made = must(a.post(buy.PI, bs.bill_body(bs.receive(order, "400"))), "bill")
    must(a.post(f"{buy.PI}/{made['id']}/approve", {}), "approve")
    return made


b1, b2 = tds_bill(), tds_bill()
sup = data(a.get(f"{FIN}/tds-sections/suppliers/{vendor['id']}")[1])
c.eq((sup["section"], sup["pan"], D(sup["rate_percent"])), ("194C", "AAACT1234A", D("2")), "the supplier's usual section is 194C at 2%")
open_ids = {d["id"] for d in rows_of(a.get(f"{CH}/open-deductions?section=194C"))}
c.ok({b1["id"], b2["id"]} <= open_ids, "both bills' deductions are open for a challan")
c.eq([d for d in rows_of(a.get(f"{CH}/open-deductions?section=194J")) if d["id"] in (b1["id"], b2["id"])], [], "and not under another section")

serial = str(random.randint(10000, 99999))
bank = account(a, "1010")
body = {"deposited_on": today().isoformat(), "bsr_code": "0510308", "challan_serial": serial, "section": "194C", "paid_from_account_id": bank["id"],
        "interest_amount": "5.00", "fee_amount": "2.50", "deductions": [{"kind": "BILL", "id": b1["id"]}]}
c.eq(viewer.post(CH, body)[0], 403, "a Viewer cannot make a challan")
st, ans = a.post(CH, body)
c.eq(st, 201, "a challan is saved")
ch = data(ans)
c.eq((D(ch["tax_amount"]), D(ch["interest_amount"]), D(ch["fee_amount"]), D(ch["total_amount"])), (D("800.00"), D("5.00"), D("2.50"), D("807.50")), "its tax is the sum of the deductions chosen (800.00); total with interest and fees 807.50")
c.eq((ch["section"], ch["status"], ch["cin"]), ("194C", "POSTED", f"0510308{today().strftime('%d%m%Y')}{serial}"), "one section, posted, CIN = BSR + date + serial")
entry = entry_by_id(a, ch["journal_entry_id"])
codes = {x["id"]: x["code"] for x in rows_of(a.get(f"{FIN}/ledger-accounts?page_size=200"))}
net: dict[str, Decimal] = {}
for ln in entry["lines"]:
    net[codes[ln["ledger_account_id"]]] = net.get(codes[ln["ledger_account_id"]], Decimal(0)) + D(ln["debit_amount"]) - D(ln["credit_amount"])
c.eq(net, {"2700": D("800.00"), "6930": D("7.50"), "1010": D("-807.50")}, "it posts Dr TDS Payable 800.00, Dr Interest and Fees on TDS 7.50, Cr Bank 807.50")
c.ok(balanced(entry), "the entry balances")
c.ok(b1["id"] not in {d["id"] for d in rows_of(a.get(f"{CH}/open-deductions?section=194C"))}, "the deduction is no longer open")
# one live challan per CIN
dup = a.post(CH, {**body, "deductions": [{"kind": "BILL", "id": b2["id"]}]})
c.ok(dup[0] in (409, 422), "a second live challan with the same CIN is refused", (dup[0], message(dup[1])))
c.ok(a.post(CH, {**body, "challan_serial": serial[:-1] + "0" if serial[-1] != "0" else serial[:-1] + "1", "deductions": [{"kind": "BILL", "id": b1["id"]}]})[0] in (409, 422), "a deduction already on a challan cannot go on a second")
wrong = a.post(CH, {**body, "challan_serial": str(random.randint(10000, 99999)), "section": "194J", "deductions": [{"kind": "BILL", "id": b2["id"]}]})
c.ok(wrong[0] in (409, 422), "a challan carries one section: a 194C deduction on a 194J challan is refused", (wrong[0], message(wrong[1])))

# the return fills the challan against the deductee row
fy_q = ("2026-27", "Q3")
rows = all_rows(a, f"{FIN}/reports/tds-26q?financial_year={fy_q[0]}&quarter={fy_q[1]}")
row = next(r for r in rows if r["document_number"] == b1["invoice_number"])
c.eq((row["challan_serial"], row["challan_bsr_code"], row["challan_date"]), (serial, "0510308", today().isoformat()), "the 26Q row shows the challan serial, BSR code and date")
row2 = next(r for r in rows if r["document_number"] == b2["invoice_number"])
c.eq(row2["challan_serial"], "", "and a deduction with no challan shows none")
c.eq(a.raw(f"{FIN}/tds-returns/26q?financial_year={fy_q[0]}&quarter={fy_q[1]}")[1][:2], b"PK", "the return's own workbook downloads")

# cancel
c.refused(a.post(f"{CH}/{ch['id']}/cancel", {"reason": ""}), 422, "", "cancel without a reason is refused")
st, ans = a.post(f"{CH}/{ch['id']}/cancel", {"reason": "wrong bank"})
c.eq(st, 200, "the challan cancels")
done = data(ans)
c.eq((done["status"], done["cancel_reason"]), ("CANCELLED", "wrong bank"), "CANCELLED with the reason")
rev = entry_by_id(a, done["reversal_journal_entry_id"])
c.eq(sorted((D(x["debit_amount"]), D(x["credit_amount"])) for x in rev["lines"]), sorted((D(x["credit_amount"]), D(x["debit_amount"])) for x in entry["lines"]), "a mirror journal is posted")
c.ok(b1["id"] in {d["id"] for d in rows_of(a.get(f"{CH}/open-deductions?section=194C"))}, "the deduction is free again")
c.refused(a.post(f"{CH}/{ch['id']}/cancel", {"reason": "again"}), 422, "", "cancelling twice is refused")
again = a.post(CH, body)
c.eq(again[0], 201, "the CIN can be used again once the first is cancelled")

# ---- 194Q
held = data(a.get(f"{FIN}/tds-194q/settings")[1])
vend = bs.new_vendor(pan="AAACT1234A", gst_registration=False)
bs.vendor = vend
order = bs.order(qty="400")
q_bill = must(a.post(buy.PI, bs.bill_body(bs.receive(order, "400"))), "194Q bill")
must(a.post(f"{buy.PI}/{q_bill['id']}/approve", {}), "approve")
try:
    c.eq(viewer.put(f"{FIN}/tds-194q/settings", {"is_enabled": True})[0], 403, "a Viewer cannot switch 194Q on")
    c.eq(a.put(f"{FIN}/tds-194q/settings", {"is_enabled": True, "threshold_amount": "10000", "rate_percent": "0.1", "rate_without_pan_percent": "5"})[0], 200, "194Q on: threshold 10,000, 0.1%, 5% without PAN")
    s = data(a.get(f"{FIN}/tds-194q/suppliers/{vend['id']}")[1])
    c.eq((D(s["purchases"]), D(s["excess"]), D(s["due"]), D(s["to_deduct"]), s["applies"]), (D("40000.00"), D("30000.00"), D("30.00"), D("30.00"), True), "40,000.00 of bills without GST: the rate on the 30,000.00 excess is 30.00")
    paid = a.post(PAY, {"party_id": vend["id"], "settlement_date": today().isoformat(), "amount": "1000.00", "method": "BANK", "tds_amount": "30.00", "tds_section": "194Q", "allocations": [{"invoice_id": q_bill["id"], "amount": "1000.00"}]})
    c.eq(paid[0], 201, "a payment with 30.00 TDS under 194Q is recorded")
    s2 = data(a.get(f"{FIN}/tds-194q/suppliers/{vend['id']}")[1])
    c.eq((D(s2["deducted"]), D(s2["to_deduct"])), (D("30.00"), D("0.00")), "194Q already deducted on the posted payment is taken off what is still to deduct")
    reg = [r for r in all_rows(a, f"{FIN}/reports/tds-194q") if r["vendor_id"] == vend["id"]]
    c.eq([(D(r["excess"]), D(r["deducted"])) for r in reg], [(D("30000.00"), D("30.00"))], "the 194Q register shows the supplier's excess and deduction")
    nopan = bs.new_vendor(gst_registration=False)
    bs.vendor = nopan
    o2 = bs.order(qty="400")
    nb = must(a.post(buy.PI, bs.bill_body(bs.receive(o2, "400"))), "no-PAN bill")
    must(a.post(f"{buy.PI}/{nb['id']}/approve", {}), "approve")
    n = data(a.get(f"{FIN}/tds-194q/suppliers/{nopan['id']}")[1])
    c.eq((D(n["rate_percent"]), D(n["to_deduct"])), (D("5.000"), D("1500.00")), "a supplier with no PAN: 5% on the 30,000.00 excess = 1,500.00")
finally:
    a.put(f"{FIN}/tds-194q/settings", held)
c.done()
