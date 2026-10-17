# Module test: Finance -- 2026-10-18

Status: **(a) API: 17 of 22 kept checks pass on fixture firm T1016VSH1-S; 5 fail, all five because the check's own assumption does not hold in this firm (fixture data or an already-fixed defect), none is an application defect. (b) Screens: not run: screen flows blocked by permission (flow commands refused, question open in OWNER_ANSWERS). (c) Money check on screen: not run, same reason.**

## (a) API -- scripts under `docs/qa/checks/finance/`

- Firm: T1016VSH1-S (`3c766569-...`). Accounts: Firm admin `t1016vsh1.tradeadmin`, Viewer, platform admin, an Accountant (`t1016vsh1.finaccountant`) and a Cashier (`t1016vsh1.fincashier`) added by the set-up; the second firm is the buying state's `admin2`.
- Set-up for this firm: `docs/qa/checks/finance/setup_vsh1.py` (writes `.state/finance.json` from existing accounts; the older `setup.py` runs the `ready-firm` fixture twice and builds new firms instead).
- Check-helper change (not app code): `_fin.py` now imports `ensure_user` from `_col` by name. That one matches the role's `firm_id` as well as its code (a platform admin's role list holds other firms' roles of the same code; D-IDN-19), so the finance checks that add users (`tc_fin_021`, `tc_fin_023`, set-up) pick this firm's role.
- Each script was run by its path with the repo venv python. Nothing reset, reseeded or deleted; each check makes its own scene (item, customer, documents) in the firm.

| Case / probe | Result |
| --- | --- |
| TC-FIN-001 | pass |
| TC-FIN-002 | pass |
| TC-FIN-003 | pass |
| TC-FIN-004 journal entries say which module posted them | **fail** (check assumption, see F1) |
| TC-FIN-005 | pass |
| TC-FIN-007 | pass |
| TC-FIN-012 | pass |
| TC-FIN-016 | pass |
| TC-FIN-017 | pass |
| TC-FIN-018 | pass |
| TC-FIN-019 | pass |
| TC-FIN-020 Tally export | **fail**, two steps only (see F2); the rest of the case passes (mapped names, reversed originals now in the file, per-ledger movement equals the trial balance, party names, Cashier refused) |
| TC-FIN-021 approvals by level | **fail**, first amount step (see F3); not run past it by the script |
| TC-FIN-023 sales analysis | **fail**, one step (see F4); billed basis, previous-year column and the rest pass |
| TC-FIN-026 | pass |
| TC-FIN-027 | pass |
| TC-FIN-029 | pass |
| p_fin_journal | pass |
| p_fin_other_firm | pass |
| p_fin_payment | pass |
| p_fin_tb_pl | **fail**, three steps (see F5); trial balance, balance sheet and cash flow all balance before and after |
| p_fin_year_close | pass |

Result: **17 of 22 clean, 5 failing, 0 new defects.**

## Why the five fail (each probed against the running backend)

- **F1 TC-FIN-004.** The script derives the delivery-note journal reference as `"DN-" + the invoice's number`. In this firm the delivery-note series has run ahead of the invoice series (latest `SI-26-27-000526`, latest `DN-26-27-000656`), so `DN-26-27-000500` is a different, older entry and the search finds nothing. The sales-invoice and receipt halves of the case pass (source module, description, POSTED, balanced); `source_module=delivery_note` lists 401 entries. Check must find the note through the bill instead of by number.
- **F2 TC-FIN-020.** (i) The voucher-type rule knows `PY-` payments and `-REV` reversals but not refunds: `RF-2026-2027-000001` / `-000002` (Payment, right: money out) and `RF-...-000001-REV` (Receipt, right) are flagged. (ii) "All six voucher types appear" needs a Contra voucher, which this firm has none of and the script does not make (types present: Journal, Sales, Credit Note, Purchase, Receipt, Payment, Debit Note).
- **F3 TC-FIN-021.** The "big bill" of 100 at 100.00 is 10,679.00, not 11,800.00: the firm holds a live promotion `BULK5` (7.5 percent on a large quantity, 750.00) and a standing bill discount of 200.00, both from the pricing and selling fixture data. Expected figure in the script assumes no arrangement. Prices are right; the 11,800 / 590 thresholds of the approval rules need a different quantity here.
- **F4 TC-FIN-023.** The `basis=ordered` step records the old behaviour (7 pieces, 826.00, counting the order a counter bill raises for itself). That is D-FIN-35, fixed 2026-10-16: the server now answers 4 and 472.00 (the approved order only), which is what the case text says. The check's expectation is stale.
- **F5 p_fin_tb_pl.** A 10-piece sale of 1,000.00 in this firm also earns loyalty: 23.60 (2 percent of 1,180.00) debited to 5700 Loyalty Expense and credited to 2600 Loyalty Payable, so expense is up 623.60 and profit 376.40, not 600.00 and 400.00. Every other figure in the probe holds (receivables +1,180.00, sales -1,000.00, GST 180.00, COGS +600.00, payables -1,180.00, inventory +400.00). Points cost the firm when earned, as the loyalty rule says. The probe needs the loyalty accrual added to its expectation (or a customer outside the programme).

## Defects

No new defect. Nothing from this round for `docs/DEFECTS.md`.

Known and not repeated: stock value is 0.02 below account 1200 (D-STK-20, covered by #1727).

Proposed check fixes (QA sources, not edited here): F1 find the DN by the bill; F2 add `RF-` to the settlement voucher rule and make a contra voucher in the scene; F3 size the big bill to the firm's arrangements; F4 expect (4, 472.00); F5 add the loyalty accrual.

## (b) Screens
Not run: screen flows blocked by permission (flow commands refused; question open in OWNER_ANSWERS).

## (c) Money check on screen
Not run: same reason.
