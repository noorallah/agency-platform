# Finance API check, round 1 (2026-10-16)

Driven over HTTP against the running backend (http://127.0.0.1:8000) on two
finished Wholesale fixture firms made by `docs/qa/checks/finance/setup.py`
(firm one: Firm admin, Viewer, Accountant, Cashier; firm two: a second Firm
admin). Kept scripts: `docs/qa/checks/finance/` (`_fin.py` helpers, which
re-use the collections and buying helpers; one `tc_fin_NNN.py` per case, five
`p_fin_*.py` probes). Run: `python docs/qa/checks/run.py finance`. Money is
compared as exact decimals (journal debit = credit, trial balance, P&L, balance
sheet, challan, TDS, bank statement lines).

Result: **21 of 22 scripts clean; 1 failing on a real defect** (Tally export,
below). Two further observations. Seven case-text corrections. No backend or
desktop code was changed. The folder was run end to end twice with the same result
(scripts make their own records under a fresh tag and put every setting they
touch back).

## Setup

`python docs/qa/checks/finance/setup.py` (two `ready-firm` fixtures, an
Accountant and a Cashier added to firm one; state in
`docs/qa/checks/.state/finance.json`, not committed). Scripts that need more
users make them lazily (`ensure_user`): a Sales Manager and a Sales Executive
(approvals, analysis). Scripts that must close periods build a financial year
older than any the firm holds, because periods close oldest first, firm-wide.

## Cases

| Case | Result | Figures / notes |
| --- | --- | --- |
| TC-FIN-001 new ledger account | PASS | EXPENSE in group REV refused ("must share its group's account type"); in EXP saves; same code 409; no Delete route; PATCH changes name, description, both Requires flags, Active; code and type are not update fields (422); moving to an ASSET group refused, group and type unchanged |
| TC-FIN-002 three statements agree | PASS | 2 invoices (354.00, 236.00) + 2 receipts (354.00, 100.00): TB debit = credit, 1100 moved by exactly 136.00, P&L net = income - expense, sheet's Result for the year = P&L year to date, assets = liabilities + equity, all three on the one period |
| TC-FIN-003 closed period refuses a posting | PASS | JV reference needed (case text 1); closing June needs April and May closed first; post refused "Accounting period P03 is closed and cannot accept postings"; reopen then post works; trail gains exactly 2 rows per period closed and reopened; platform trail finds none (case text 2) |
| TC-FIN-004 source module on journals | PASS (partial) | SI -> sales_invoice, DN -> delivery_note, RC -> settlements (also contra), each balanced; search matches reference and description; TCS entry not driven (no TCS firm set up) |
| TC-FIN-005 every report opens | PASS | walks `openapi.json`: 111+ report GETs answer 200 with `page_size=5`, empties are `[]`, GST returns that this firm cannot file are refused in words (no GST number / monthly not quarterly / over 3 months), none is a 5xx |
| TC-FIN-007 cost and profit centres | PASS | duplicate code 409 "already exists", no Delete, Active toggles; 5000 made to require a centre: line without one 422 "Ledger account 5000 requires a cost centre.", with one saves and keeps it, a deactivated centre refused; flag put back |
| TC-FIN-012 bank reconciliation | PASS | 6-line CSV; check reads 6 rows, 0 issues, imports nothing; apply imports; same file again refused with issues; auto-match pairs the amount+date line and the UTR line, leaves the tied pair, the two-entry line and the orphan; manual match of a tied line; one line to two entries summing to it (300.xx + 200.xx); a non-summing match 422; unmatch; reconciliation statement balance = last line's printed balance, 99.99 under bank only; removing the statement gives the receipts back as uncleared |
| TC-FIN-016 close checks and ageing | PASS | WARN: draft journal listed with count and example, `refuses` false; BLOCK: `refuses` true and closing refused naming the draft; WARN closes. Bands [15,45,90] -> 0-14/15-44/45-89/90+; a 50-day bill (118.00) in 45-89, a 20-day supplier bill (354.00) in 15-44 on the vendor `buckets` list; due lists (0 days vs 7 days) |
| TC-FIN-017 TDS challans and 194Q | PASS | 800.00 BILL deduction -> challan 800.00 + 5.00 + 2.50 = 807.50, journal Dr 2700 800.00 / Dr 6930 7.50 / Cr 1010 807.50; CIN = BSR + ddmmyyyy + serial; duplicate CIN, deduction on two challans, wrong section refused; 26Q row shows serial, BSR and date; cancel posts the mirror and frees the deduction; the CIN is reusable. 194Q: threshold 10,000, 40,000.00 bills -> excess 30,000.00 -> 30.00; payment of 30.00 under 194Q leaves 0.00 to deduct; no PAN 5% -> 1,500.00 |
| TC-FIN-018 cash flow | PASS | operating = net profit + its lines; operating + investing + financing = net change; opening + net change = closing = Cash + Petty Cash + Bank on the TB; reconciles; net profit = P&L's; two months reconcile; Cashier 403, Accountant 200; backwards range 422 |
| TC-FIN-019 files on journals, receipts, payments | PASS | attach, list (name, type, path, caption, creator), held against exactly one document, delete (404 after), Viewer 403, add and delete both in the audit trail (`journal_entry.files_attached` / `settlement.files_attached` / `ledger_attachment.removed`), other firm 403/404. The "no ATTACHMENTS feature, no control" half is a screen |
| TC-FIN-020 Export to Tally | **FAIL** | defect 1. Everything else in the script holds: mappings rename ledgers, XML well formed, all six voucher types, every voucher balances, receivable/payable lines name the party, Cashier 403, backwards dates 422 |
| TC-FIN-021 approvals by level, bulk reject | PASS | rules 1: from 0 SALES_MANAGER, 2: from 10,000 FIRM_ADMIN; 11,800.00 bill needs both, 590.00 needs one; Approve refused naming the level; one person cannot sign two levels; last sign-off approves; reject needs a reason and clears sign-offs; bulk reject per row (2 done, the approved one refused); no rule = approves as ever; level 4 / unknown type 422 |
| TC-FIN-023 sales and purchase analysis | PASS (partial) | billed 3 pieces 300.00 + 54.00 = 354.00, cost 180.00, margin 120.00 (40.00%); previous year (back-dated bill) 2 pieces 236.00 margin 80.00; cost, margin and margin % withheld from a user without PRODUCT_VIEW_COST_PRICE, in both columns; layouts per user and per report; purchase analysis billed/received/ordered 4 x 100.00 = 472.00; rate trend. Observation 1 below |
| TC-FIN-026 ready-made accounts | PASS | Petty Cash 1005, Drawings 3100, Capital 3200, Transport 6450, Fuel 6460 once each in both firms, Transport/Fuel offered as an expense, Petty Cash under Paid from and as cash in the contra; a 50.00 Cash -> Petty Cash contra leaves the cash book total unchanged, Dr 50.00 / Cr 50.00, self-transfer refused, Viewer 403 |
| TC-FIN-027 supplier switched off for TDS | PASS | 40,000.00 bills: 800.00 under 194C (owed 46,400.00); after un-ticking and saving again with only a name change the supplier stays off at 194C; next bill deducts 0.00 (owed 47,200.00), a typed 500.00 applies to that bill only (owed 46,700.00), the next deducts 0.00; customer TCS flag survives a save; receipt 1,180.00 with 11.80 under 194Q: bank 1,168.20, TDS Receivable 11.80, customer owes 0.00 |
| TC-FIN-029 Excel (server half) | PASS (partial) | the sheet is built by the desktop; server figures behind it: register complete at any page size (no duplicate, same sum), statement and ledger running balances follow line by line, ageing bands add up, TB Total line = column sums, P&L month columns add to the Total and the October column equals the single-month P&L, payables row total = older + months + later + credits |

## Probes

| Probe | Result | What it holds |
| --- | --- | --- |
| `p_fin_journal` | PASS (34) | unbalanced (100.00 vs 90.00), all-zero, one-sided, debit-and-credit line, negative amounts, hand reference outside `JV-`, each refused 422 and writes nothing; draft moves no balance; post: Purchases +100.25, Cash -100.25, TB still balances; post twice, delete and edit of a posted entry refused; reversal posts a mirror (each line sides swapped, `reversal_of_id`), TB back to start; second reversal refused ("Only posted entries can be reversed"); draft deletes; Viewer 403 |
| `p_fin_payment` | PASS (21) | 1,180.00 bill, payment 400.25: owes 779.75; entry Dr Payables 400.25 / Cr Bank 400.25; over-payment 800.00 refused; reversal restores the bill (1,180.00), Payables and Bank; original `REVERSED`, mirror `-REV` `POSTED`; second reversal refused |
| `p_fin_year_close` | PASS (25) | close refused with both periods open; periods close oldest first; month closes with a draft inside under WARN but the year close is refused naming the draft; once the draft is removed the year closes (`is_locked`); a draft into the closed year refused; one period of a closed year cannot reopen alone; reopen: Accountant 403, Viewer 403, no reason 422, blank reason 422, firm admin with a reason 200, and the reason is in the firm's audit trail |
| `p_fin_tb_pl` | PASS (38) | before and after a sale (1,180.00, cost 600.00) and a purchase (1,180.00): TB closing debit = credit from the lines and from the printed totals; P&L income +1,000.00, expense +600.00 (the purchase is stock), profit +400.00 = sheet's Result for the year; Receivables +1,180.00, Payables -1,180.00, output tax -180.00, input tax +180.00; cash flow reconciles |
| `p_fin_other_firm` | PASS (17) | a second firm's admin gets 404 on firm one's entry in its own context and 403/404 naming firm one for read, list, trial balance, P&L, payments, years, post, create, year close; firm one's draft is untouched |

## Defects found

1. **Tally export drops every reversed original but sends its reversing mirror**
   (severity High: the file's ledgers differ from the books). Request:
   `GET /api/v1/finance/tally/export?from_date=2026-10-01&to_date=2026-10-31`
   on a firm with a reversed manual journal, reversed payments and cancelled
   TDS challans. Expected: every posted journal of the period, reversed
   originals included, so the file's per-ledger movement equals the trial
   balance's. Got: 107 vouchers for 114 entries; `JV-MJ-B33SNK`,
   `JV-MJ-CJHVTR`, `PY-2026-2027-000002..5` and cancelled challans
   `TDC-...` (status `REVERSED`) are missing while `...-REV` mirrors are
   present, so Cash closes 616.50 in the file against 316.00 on the trial
   balance and Bank 5,258.58 against 3,958.08 (one run; grows with every
   reversal). `backend/app/finance/services/tally_export.py:240`:
   `JournalEntry.status == "POSTED"`. The fix is to take `POSTED` and
   `REVERSED` (the mirror is `POSTED`, the original `REVERSED`).
   Script: `tc_fin_020.py` (fails by design until fixed).

## Observations (not driven to a verdict)

1. `GET /api/v1/sales-invoices/reports/analysis?basis=ordered` counts the
   approved order **and** a counter invoice that was raised without an order
   (7 pieces, 826.00 where the case text says approved orders instead of
   invoices: 4 pieces, 472.00). It may be deliberate (an order-less sale is
   still demand); low. `tc_fin_023.py` pins the present behaviour.
2. `POST /api/v1/report-layouts` answers 200, not 201, for a created layout
   (cosmetic).

## Case-text corrections (12_FINANCE_AND_REPORTS.md not edited)

- **TC-FIN-003, step 1**: the reference `MT-CLOSE-1` is refused. A journal
  written by hand must be `JV-...` ("A journal written by hand is referenced
  JV-<something>"). Use `JV-MT-CLOSE-1`; the step 4 message then reads
  "Journal entry JV-MT-CLOSE-1 posted."
- **TC-FIN-003, step 2**: closing June needs April and May already closed
  ("P01, which comes before it, is still open. Close them first, oldest first").
  State it, or start the case with April and May closed.
- **TC-FIN-003, step 5**: "`finance` alone would find nothing (exact match)" is
  not what the server does: `GET /api/v1/audit-logs?search=finance` is a
  partial match (255 rows on the fixture). The exact action finds the two rows
  per period (closed, reopened).
- **TC-FIN-004**: "there is no source-module filter" describes the screen. The
  API has `source_module=` (`GET /finance/journal-entries?source_module=delivery_note`).
- **TC-FIN-016**: the ageing bands are typed as upper limits (`bucket_days`
  `[15,45,90]`), giving 0-14, 15-44, 45-89, 90+. The example "0-15, 16-45,
  46-90, 90+" cannot be produced.
- **TC-FIN-021**: bulk reject of documents nobody has signed is refused for a
  Firm Administrator ("Level 1 is decided by SALES_MANAGER"); the level-1 role
  rejects. A Firm Administrator rejects once it is their level.
- **TC-FIN-023**: the basis values are `billed` and `ordered` (purchases also
  `received`); `invoiced` is refused ("invoiced is not a basis"). "Compare with
  last year" needs an open accounting period in last year; a back-dated bill
  into a month with no period is refused, so create that period first.

## Not driven, and why

- Screens: TC-FIN-006, 010, 011 (skipped by instruction), the Excel file itself
  (TC-FIN-029 steps 2-3, 11-15), ATTACHMENTS feature switch and Tally
  importing the file into a TallyPrime company (TC-FIN-020, needs TallyPrime),
  the notification bell (TC-FIN-021/022), Ctrl+K.
- TC-FIN-004 TCS journal and Credit/Debit Note vouchers in the Tally file:
  no TCS firm set up and no returns raised in these scripts.
- TC-FIN-012 close-checklist line for unmatched bank statement lines.
- TC-FIN-016 customer / supplier due lists were driven for one bill each, not
  all combinations.
- TC-FIN-017 payment prefilling the usual section on the Record Payment
  screen; the 194Q register and supplier endpoints were driven instead.
- TC-FIN-021 purchase documents, the "signed at a lower total" rule and the
  bell.
- Skipped as covered elsewhere: TC-FIN-013, 014, 015, 028, 030-033, 037, 039,
  041 (collections round 1).

## Fix and re-drive (same branch)

Defect 1 is **D-FIN-34**, fixed in this round: `TallyExportService.export`
(`backend/app/finance/services/tally_export.py`) now takes the journals that
are in the books (`IN_THE_BOOKS`: POSTED and REVERSED, the registers' set)
rather than POSTED alone, so a reversed original goes out beside its `-REV`
mirror and the file's ledgers close where the trial balance does. Guard:
`tests/unit/test_tally_export.py::test_a_reversed_journal_goes_out_with_its_mirror`.
The two observations are logged open as D-FIN-35 and D-FIN-36 (Low, reports).
The market comparison's one distributor gap is that defect; Tally import by
file is already decided as column mapping (BACKLOG, decision B3); recurring
journals, budgets and ratio analysis are BACKLOG section 55 (N7, N8).

**Tested three ways.** Backend: `test_tally_export.py` (4 passed),
`test_claude_md_names_real_things.py` (3 passed), ruff / black / mypy clean on
the changed files, and `run.py finance` re-driven on the restarted backend
(see the state file entry for the tally). UI widget tests: no screen code
changed; the Tally export is a file download the desktop saves as it comes.
UI clicks: not done -- the unit touches no screen, and the click flows'
fixture firm (t10069cwy) no longer signs in (away list item 17 repoints them).

## Market comparison

- **Voucher import/export to the accountant's own tool.** Tally, Zoho Books and
  ERPNext all export or sync to a CA's package; this one exports to Tally but
  loses reversals (defect 1) and cannot be imported from Tally by file: gap a
  distributor needs (the CA works in Tally).
- **Recurring and template journals** (Tally "memorandum"/recurring vouchers,
  Zoho recurring journals, ERPNext Journal Entry Template): none here. Nice to
  have; month-end rent, depreciation and salaries are repeated by hand.
- **Journal approval workflow and maker-checker**: Zoho and ERPNext hold a draft
  until a second person approves it; here a draft is posted by anyone with
  JOURNAL_POST and approval levels exist only for sales and purchase documents.
  Nice to have for a small distributor.
- **Period-wise year close with carried-forward balances**: Tally closes the
  year by carrying balances forward; this one derives retained earnings and
  needs no closing entry, which is simpler and is tested here. No gap.
- **Multi-currency revaluation, budgets and cost-centre reports**: Zoho/ERPNext
  offer budgets against accounts and cost centres and report by centre; this
  one has centres on lines and a `fx-revaluation` endpoint, but no budget
  versus actual and no P&L by cost centre. Nice to have.
- **Bank feeds / auto-categorisation of statement lines**: Zoho Books reads the
  bank feed and suggests rules; here statements are imported by file and matched
  on amount, date and reference. Nice to have; the file import covers a
  distributor.
- **Tally-style Day Book, Cash/Bank book, ratio analysis and cash-flow
  statement**: day book, cash book, bank book and cash flow exist and
  reconcile (tested here); ratio analysis does not. Nice to have.
