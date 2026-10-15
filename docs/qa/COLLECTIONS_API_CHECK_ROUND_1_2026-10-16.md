# Collections API check, round 1 (2026-10-16)

Driven over HTTP against the running backend (http://127.0.0.1:8000) on two
finished Wholesale fixture firms made by `docs/qa/checks/collections/setup.py`
(firm one: Firm admin, Viewer, Cashier, Firm Manager and two Bill Collectors;
firm two: a second Firm admin). Kept scripts: `docs/qa/checks/collections/`
(`_col.py` helpers, one `tc_col_*.py` per case, six `p_col_*.py` probes).
Run: `python docs/qa/checks/run.py collections`. Money is compared as exact
decimals (receipt, allocation, cash, balances, journal debit = credit).

Result: **21 of 21 scripts clean. No product defect found.** Three
case-text corrections (below). No backend code was changed.

## Cases

| Case | Result | Notes |
| --- | --- | --- |
| TC-SELL-013 no TCS on a receipt; excess becomes an advance | PASS | 472.00 bill; receipts 236.00 and 336.00 (236.00 applied): outstanding 0.00, advance 100.00; each entry Dr Bank / Cr Receivables, no `TCS-RC` entry |
| TC-SELL-014 advance applied posts nothing; reversal puts back | PASS | apply 95 leaves 5.00 (outstanding 731.00); 10 more refused ("5.00"); reversal raises outstanding by 236.00 to 967.00; second reversal refused; journal count unchanged by the apply |
| TC-SELL-073 collection sheet by collector | PASS | collector filter, no-collector customer under nobody, Overdue only (judged with `as_of`), PDF |
| TC-FIN-013 post-dated cheques | PASS (partial) | hold posts nothing, early deposit refused, due-today filter, deposit as Cheque receipt, clear posts nothing, bounce with 100.00 + 100.00 charges (entry 100/100/100/100 balanced), cancel while held, issued side hold and present. "Deposit on the cheque's date" for a future cheque cannot be driven: the server refuses money dated in the future (see not driven) |
| TC-FIN-014 mode and instrument date | PASS | cheque, UPI, cash receipts and a cheque payment keep mode, number and date; cash book and bank book Mode / Instrument columns; collections-by-mode grew by exactly 111.00 / 222.00 / 333.00 |
| TC-FIN-015 bank details and cheque leaf (server half) | PASS | see case text 1; masking (Viewer last four, Cashier full), liability account refused, layout offsets, test print, cheque PDF with payee override, cash / transfer / reversed refused |
| TC-FIN-028 discount at collection | PASS | Cashier 403 (CLEARANCE_DISCOUNT_GIVE), 59.01 refused over 5% ("59.00"), 59.00 recorded: cash 1,121.00, entry Dr Bank 1,121.00 / Dr Discount Allowed 59.00 / Cr Receivables 1,180.00, bill tax and total unchanged; terms 23.60 by the Cashier, 30.00 refused (6.40 clearance); 0% refuses 1.00, blank percentage accepts 300.00 |
| TC-FIN-037 discount is the administrator's alone | PASS | manager saves the threshold (2,500) with the percentage unchanged at 5, refused 403 changing it and refused the 50.00 discount; administrator records (cash 1,130.00) and saves 10 |
| TC-CASH-002 Cashier records a receipt (server half) | PASS | `GET /receipts/parties` works for a Cashier (`GET /customers` is 403), code and name search, no-match gives `[]`, 100.00 cash receipt listed |
| TC-FIN-030 hand over and take back change no balance | PASS | steps 2-10 driven; closing balance, position and trial-balance totals identical before, during and after |
| TC-FIN-031 collector sees only his bills | PASS | steps 3-6 on `GET /collections/my-bills`; step 7 as API refusals (receipts, customers, hand-over list, hand over, take back all 403) |
| TC-FIN-032 collector's day sheet | PASS | steps 1-9: no receipt while the switch is off, part with promise of 780.00, sheet does not add up then adds up after the office records the two receipts, switch on makes the receipt on saving, withdraw names the receipt |
| TC-FIN-033 one receipt from a parent, three shops | PASS | see case text 2; 1,000.00 = 708.00 against bills + 292.00 on account, shops 0.00, apply 118.00 later leaves 174.00, reversal restores everything |
| TC-FIN-039 cheque written to any account | PASS (partial) | steps 1-4, 6-10 (expense 1,250.00 and its print from both places, ahead cheque keeps typed name and posts nothing, duplicate number refused, customer refund 500.00, ledger account 10,000.00 voucher, cancel, return cancels the expense and gives the bank 1,250.00 back) |
| TC-FIN-041 one customer pays another's bill | PASS | steps 1-10 over HTTP; A unchanged throughout, B's statement "Paid by A", A's "Paid for B", print names both, reversal, advance applied with no new journal entry, 50.00 stays on A |

Probes (all PASS): `p_col_refund_on_account` (D-FIN-30: 500.00 receipt,
refund 200.00 leaves 300.00 unapplied, customer balance 300.00, reversal
gives back 500.00, refund over what is left refused, double reversal
refused), `p_col_shop_and_parent_pay` (a shop pays its own bill, the parent
pays another shop's; statements, account, summary and family totals agree;
both reversed restores every figure), `p_col_post_dated_cheque` (ahead cheque
posts nothing and cannot be banked, cleared or bounced; two simultaneous
deposits of one cheque, received and issued, post exactly one entry),
`p_col_over_allocation` (300.00 on a 118.00 bill, repeats, remainder and the
advance route all refused with the amount named), `p_col_other_firm_and_viewer`
(Viewer 403 on ten writes, other firm 403/404, named firm 403, anonymous 401,
nothing moved), `p_col_paise_and_deductions` (117.9882 and 275.3058 bills carried
as 117.99 / 275.31; TDS 10.00 + rounding 0.50 + bank charges 1.25 leave cash
263.56 and a balanced five-line entry; reversal is its exact mirror).

## Case-text corrections (not defects)

1. **TC-FIN-015**: "try marking a second account" is not refused. The mark
   moves: saving details with *print on documents* on a second account
   switches the first one off (`app/finance/services/bank_details.py:205-211`),
   so at most one account is marked, which is what the Expect sentence says.
   Reword the step: the second account takes the mark from the first.
2. **TC-FIN-033 step 5**: the parent's statement line for the receipt reads
   debit 0.00 / credit 0.00, not "250.00". A statement line moves only the
   balance owed (`app/customers/services/statement_service.py:67-80`); what
   is held on account is the statement header's `unapplied_advance` (292.00
   in the script's figures). Reword to "one receipt line with no amount, the
   header shows the sum held on account". The same holds for any receipt on
   account (TC-SELL-014 and TC-FIN-041).
3. **TC-FIN-033**: the bills in the case (100.00, 250.00, 400.00)
   are not reachable with 18% tax at whole units; the script uses 118.00,
   236.00 and 354.00.

## Observations (not defects, no script fails)

- `POST /receipts/{id}/reverse` accepts no reason
  (`app/settlements/schemas/__init__.py:84`, `reason` optional); the cases say
  "give a reason" and the desktop supplies one. Low, consider requiring it.
- A receipt on account first nets against the customer's outstanding at the
  account level (a 300.00 unapplied receipt on a customer owing 18.00 reads
  outstanding 0.00 / advance 282.00) while the bill still shows 18.00 owing in
  the receipt screen until it is applied. This is the stated design
  ("what an invoice owes is derived from allocations"), but the two figures
  differ by the netted amount until somebody applies the advance.

## Not driven, and why

- Every screen step (buttons, dialogs, read-only boxes, menus, helper text,
  running "left over" line, print boxes): HTTP only.
- TC-FIN-013 "Deposit on the cheque's date" for a cheque dated a week ahead,
  and TC-FIN-039 step 5 "Presented on its date": the server refuses money
  dated in the future, so a held cheque cannot be banked until its real date.
  Banking was driven with cheques dated today; the refusal before the date
  was driven.
- TC-FIN-013 "a supplier bill for the issued side": the issued cheque is
  presented on account (no allocation) rather than against a bill.
- TC-FIN-015 printing an invoice and a quotation with the bank block, and the
  audit entry masking the number.
- TC-FIN-039 step 11 (a cash expense's Print cheque) and step 12 (a user who
  may record expenses and nothing else).
- TC-FIN-030 step 10 and TC-FIN-031 steps 2 and 7: which screens the menu
  offers (driven as the API refusals above).
- TC-FIN-028 / 037 Cashier read-only boxes (UI); the 403 on save is driven.

## Screen clicks (2026-10-16)

Tried: `integration_test/run.sh sc_rc_test.dart` (the receipts click flow) in
the real Windows app against the running backend. The app built and started,
but the flow stopped at its first step: its fixture firm's administrator,
`t10069cwy.tradeadmin@fixtures.local`, no longer signs in (401, invalid email
or password), and every `sc_*` flow names that firm in `cases.dart`. **No
screen was clicked and no value read off a screen in this round.** Pointing
the click flows at a fixture firm that exists is part of away-list item 17
(screen click rounds). Backend verified, screens not.
