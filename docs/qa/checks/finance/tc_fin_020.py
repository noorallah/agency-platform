"""TC-FIN-020: export to Tally: every posted journal of the period is one balanced voucher typed by its source; mappings rename ledgers; the XML is well formed and its movements equal the trial balance."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import xml.etree.ElementTree as ET
from collections import Counter

from _fin import *

c = Check("tc_fin_020")
a = admin()
per = period_of(a)
TY = {"sales_invoice": "Sales", "purchase_invoice": "Purchase", "delivery_note": "Journal", "goods_receipt": "Journal", "inventory": "Journal", "contra": "Contra", None: "Journal"}
# ensure the month holds a sale, a receipt, a purchase, a payment and a manual journal
sc = Scene(a)
cust = sc.customer()
with counter(a):
    bill = sc.bill(cust, "2")
receipt(a, cust, "100.00", [(bill, "100.00")])
bs = buy.Scene(a)
_, _, pb = bs.received_and_billed("2")
bs.pay("50.00", pb)
manual = data(a.post(JE, draft_body(a, [("6500", "11.00", "0"), ("1000", "0", "11.00")]))[1])
a.post(f"{JE}/{manual['id']}/post", {})

# mappings: rename two accounts
maps = rows_of(a.get(f"{FIN}/tally/mappings"))
two = [m for m in maps if m["account_code"] in ("6500", "6600")]
tag = suffix(4)
want = {m["account_code"]: f"Tally {m['account_name']} {tag}" for m in two}
try:
    st, ans = a.put(f"{FIN}/tally/mappings", {"mappings": [{"ledger_account_id": m["ledger_account_id"], "tally_name": want[m["account_code"]], "tally_parent": "Indirect Expenses"} for m in two]})
    c.eq(st, 200, "two accounts get their Tally names and groups")
    back = {m["account_code"]: m for m in rows_of(a.get(f"{FIN}/tally/mappings"))}
    c.eq([(back[k]["tally_name"], back[k]["mapped"]) for k in want], [(v, True) for v in want.values()], "they read back as mapped")
    s, raw = a.raw(f"{FIN}/tally/export?from_date={per['starts_on']}&to_date={per['ends_on']}")
    c.eq(s, 200, "the export answers")
    root = ET.fromstring(raw)
    c.eq(root.tag, "ENVELOPE", "the XML is well formed, an ENVELOPE")
    names = {e.text for e in root.iter("LEDGERNAME")} | {e.get("NAME") for e in root.iter("LEDGER")}
    c.ok(want["6500"] in names, "the mapped name goes out for 6500", sorted(n for n in names if n and "Office" in n))
    c.ok("Office and General Expenses" not in names, "and the default name no longer does")
    vouchers = list(root.iter("VOUCHER"))
    entries = [e for e in all_rows(a, f"{JE}?accounting_period_id={per['id']}") if e["status"] in ("POSTED", "REVERSED")]
    sent = {v.findtext("VOUCHERNUMBER") for v in vouchers}
    held = {e["reference_number"] for e in entries}
    # DEFECT (tally_export.py:240 filters status == POSTED): the originals that were later REVERSED are left out
    # while their reversing mirrors are sent, so the file's ledgers do not equal the platform's.
    c.eq(sorted(held - sent), [], "every posted or reversed journal of the period is a voucher (missing from the file)")
    c.eq(sorted(sent - held), [], "and no voucher is for anything else")
    by_ref = {e["reference_number"]: e for e in entries}
    wrong = []
    for v in vouchers:
        amounts = [D(x.text) for x in v.iter("AMOUNT")]
        if sum(amounts, Decimal(0)) != 0:
            wrong.append(("unbalanced", v.findtext("VOUCHERNUMBER")))
        src = by_ref[v.findtext("VOUCHERNUMBER")]["source_module"]
        expected = TY.get(src)
        if src == "settlements":
            num = v.findtext("VOUCHERNUMBER")
            expected = "Payment" if num.startswith("PY-") != num.endswith("-REV") else "Receipt"  # a reversal is the other kind
        if expected and v.get("VCHTYPE") != expected:
            wrong.append((src, v.findtext("VOUCHERNUMBER"), v.get("VCHTYPE")))
    c.eq(wrong, [], "every voucher balances and is typed by its source (Sales, Purchase, Contra, Receipt, Payment, Journal)")
    c.ok({"Sales", "Purchase", "Receipt", "Payment", "Contra", "Journal"} <= {v.get("VCHTYPE") for v in vouchers}, "all six voucher types appear", Counter(v.get("VCHTYPE") for v in vouchers))
    # movement per ordinary ledger equals the trial balance's period movement
    movement: dict[str, Decimal] = {}
    for v in vouchers:
        for led in v.iter("ALLLEDGERENTRIES.LIST"):
            movement[led.findtext("LEDGERNAME")] = movement.get(led.findtext("LEDGERNAME"), Decimal(0)) - D(led.findtext("AMOUNT"))
    t = tb(a, per)
    mismatch = []
    for code, tally in (("4000", "Sales"), ("1000", "Cash"), ("5200", "Cost of Goods Sold"), ("6500", want["6500"]), ("1010", "Bank")):
        line = tb_line(t, code)
        if D(line["period_debit"]) - D(line["period_credit"]) != movement.get(tally, Decimal(0)):
            mismatch.append((code, D(line["period_debit"]) - D(line["period_credit"]), movement.get(tally)))
    c.eq(mismatch, [], "(consequence of the omission above) per-ledger movement in the file equals the trial balance's for Sales, Cash, Bank, COGS and the mapped ledger")
    # receivable / payable lines name the party, not the control account
    party_names = {led.findtext("LEDGERNAME") for v in vouchers for led in v.iter("ALLLEDGERENTRIES.LIST")}
    c.ok(cust["name"] in party_names, "a receivable line names the customer of the document", cust["name"])
    c.ok(bs.vendor["name"] in party_names, "a payable line names the supplier of the document", bs.vendor["name"])
    c.eq(admin("cashier").get(f"{FIN}/tally/export?from_date={per['starts_on']}&to_date={per['ends_on']}")[0], 403, "a Cashier cannot export")
    c.eq(a.get(f"{FIN}/tally/export?from_date={per['ends_on']}&to_date={per['starts_on']}")[0], 422, "dates the wrong way round are refused")
finally:
    a.put(f"{FIN}/tally/mappings", {"mappings": [{"ledger_account_id": m["ledger_account_id"], "tally_name": m["tally_name"], "tally_parent": m["tally_parent"]} for m in two]})
c.done()
