# Screen cases, Buying click round: 2026-10-17 (second run, with a vendor)

Brief (AWAY_WORK_LIST item 31, Buying only): re-drive `buying_flow`, `sc_po`,
`sc_gr`, `sc_pb`, `sc_pr`, `sc_py` and the buying part of `roles_flow`
(desktop/integration_test) in the real app. No app code, DEFECTS.md or other
shared doc was edited, and no flow file needed a fix. This replaces the first
run of the same day (#1692), which stopped at the first step because the
fixture held no vendor.

## Where it ran

Fixture firm `T1016VSH1-S`, backend at localhost:8000. Accounts and password
are those of `docs/qa/SCREEN_FLOW_CHECK_SELLING_2026-10-16.md` (login email is
the handle plus `@fixtures.local`): administrator `t1016vsh1.tradeadmin` and
VIEWER `t1016vsh1.qro`.

Set-up done over the API as the firm administrator (owner said yes): vendor
"Principal supplier" (SUP-00001) and one purchase order (draft, 10 x
"Detergent 1kg t1016vsh1" at 60, Head Office / Main Warehouse). The permission
system allowed both; nothing was refused. The flows then create their own
orders, receipts, bills, returns and payments in the firm (the order list
reads 96 orders by the end), as every earlier round did.

Each flow ran through `integration_test/run.sh` with `LIMIT=580`, retried only
on the exit-79 start-up death, at most 5 tries. Exit-79 deaths: sc_po_test
tradeadmin 5 of 5 (never a complete run; the best try is reported),
sc_py_test tradeadmin twice (then a run that failed on data), sc_gr_test qro
once, roles_flow_test three times for tradeadmin and three for qro. The
worktree path is shallow, so the MSB3501 deep-path build error did not occur.

## Results

| Flow | User | Result |
| --- | --- | --- |
| buying_flow_test | tradeadmin | **7 passed, 1 failed, 1 not run.** Passed: SC-PO-002 (new order), order list total, SC-PO-003, SC-PO-004, SC-PO-005, SC-GR-002 (receipt off the order), SC-PR-002/003 (return). Failed: SC-PB-002 (defect 2). Payment not run (no bill). |
| buying_flow_test | qro | not applicable: stops at SC-PO-002 "Timed out waiting for a New button" because the VIEWER has no New on Purchase Orders (correct); the flow is an administrator flow. |
| sc_po_test | tradeadmin | **17 passed, 0 failed, rest not reached.** Every try died with exit 79 mid-flow; try 1 got furthest. Passed: SC-PO-001, 009, 010, 011, 012, 013, 014, 018, 019, 020 (x2), 024, 027, 028, 029, 031 (x2). Cases after SC-PO-014 in the flow's order were not reached. |
| sc_po_test | qro | **pass** (1 of 1) |
| sc_gr_test | tradeadmin | **14 passed, 0 failed, 11 not run** (flow skips: batch/serial tracking, quarantine, transport boxes, file picker, date picker, stock consumed after receipt, one covered elsewhere). Passed: SC-GR-001, 003, 008, 010, 012, 013, 014 (x2), 017, 018, 019, 020, 022, 029. |
| sc_gr_test | qro | **pass** (1 of 1) |
| sc_pb_test | tradeadmin | **14 passed, 2 failed, 12 not run.** Passed: SC-PB-001, 004, 010, 011, 014, 015, 016, 017, 021, 022, 024, 025, 026, 028. Failed: SC-PB-035, SC-PB-036 (defect 3, fixture). Not run: SC-PB-005 to 009, 012, 013, 018, 019, 020, 027, 034 (no foreign-currency supplier, TDS section, closed period, tolerance or capital-goods line in the fixture; file picker and IRN dialog not drivable). |
| sc_pb_test | qro | **pass** (1 of 1) |
| sc_pr_test | tradeadmin | **13 passed, 1 failed, 9 not run.** Passed: SC-PR-001, 004, 009, 010, 011, 012 (x2), 013, 014, 018, 019, 020, 021. Failed: SC-PR-027 (defect 3, fixture). |
| sc_pr_test | qro | **pass** (1 of 1) |
| sc_py_test | tradeadmin | **10 passed, 0 failed on the best try (try 1, then exit 79); the third try failed on data.** Passed: SC-PY-001, 003, 011 (x3), 012, 015, 017, 018, 019. The third try failed on its first step: POST /payments answered 409 "Cash holds 207.52 ... and this pays 708.00 out of it", because the earlier tries of this round had spent the fixture's cash (defect 5). |
| sc_py_test | qro | **pass** (1 of 1) |
| roles_flow_test | tradeadmin | menu walk **pass**; one flagged screen: `inventory/inventory-import` "opens a screen saying: Failed: 0" (not a Buy screen; the text is a count label, so most likely the walker's keyword match rather than an error). Chain steps not reached. |
| roles_flow_test | qro | menu walk **pass**, 14 screens flagged (defect 1); chain steps not reached. |

Tally of flow steps for the administrator: **75 passed, 4 failed** (SC-PB-002,
SC-PB-035, SC-PB-036, SC-PR-027) across buying_flow, sc_po, sc_gr, sc_pb,
sc_pr and sc_py. VIEWER: 5 flow passes (sc_po, sc_gr, sc_pb, sc_pr, sc_py),
buying_flow not applicable, roles menu walk 14 flagged screens.

## Defects and failures (not fixed, as the brief says)

1. **VIEWER Buy menu offers screens that only answer "no permission"**
   (roles_flow_test, qro, step "menu: <path>"):
   - `purchases/debit-notes`: "Raising one needs the manage debit notes permission."
   - `accounting/payment-runs`: "Starting one needs the create permission for payments."
   - `masters/supplier-gifts`: "Recording one needs the manage supplier gifts permission."
   - `purchases/supplier-rebates`: "Recording one needs the approve purchases permission."
   - `purchases/principal-claims`: "Raising one needs the approve purchases permission."
   - `purchases/landed-costs`: "Posting one needs the approve purchases permission."

   The same walk flags eight screens in Sell and Accounts with the same kind
   of message (credit notes, customer debit notes, enquiries, customer
   rebates, PDC received, PDC issued, party adjustments, contra vouchers),
   14 in all. They open and say why the user cannot act, so they may be a
   read-only view with a notice, but a VIEWER is offered them in the menu.
2. **SC-PB-002 (buying_flow_test, tradeadmin): bill off the receipt does not
   save.** "the editor stayed open after purchase-invoice-save". The editor
   showed a new purchase invoice against
   GRN-T1016VSH1-S-HO-2026-2027-000001 (Draft) with the messages "Choose the
   supplier first" and "Choose receipts (1 waiting)", so the supplier was not
   carried over from the receipt, or the flow picks the fields in the wrong
   order. sc_pb_test raises the same bill over HTTP and SC-PB-004 passes, so
   only the typed path failed. Needs a manual look. Repro: buying_flow_test,
   tradeadmin, the bill step.
3. **Fixture gap, not an app defect: SC-PB-035, SC-PB-036 (sc_pb_test) and
   SC-PR-027 (sc_pr_test)** sign a second user in over HTTP as `qpmgr`, which
   this selling fixture does not have: "POST /api/v1/auth/login answered 401
   Invalid email or password". The fixture has qsexe, qsmgr, qstore, qacct,
   qro and viewer. A buying fixture (qpexe, qpmgr) is needed for the
   stale-save and stale-approve cases.
4. **Runner:** exit-79 start-up deaths made sc_po_test never complete in five
   tries, and cut sc_py_test and roles_flow_test short. Not an app finding.
5. **sc_py_test is not repeatable on one fixture:** each run pays money out of
   Cash and the cash gate refuses the next run's payments (409). Cash needs
   topping up between runs, or the flow should read the balance first.

## Not verified / not clicked

- sc_po_test cases after SC-PO-014 (never reached in five tries).
- sc_py_test beyond the ten listed; reversals and advance application.
- Chain steps of roles_flow_test (the walks only).
- Roles other than administrator and VIEWER (purchase executive, purchase
  manager, warehouse): they need a buying fixture.
- Batch and serial receipts, quarantine, foreign currency, TDS and TCS bills,
  closed period, tolerance, capital goods, e-invoice IRN, file attachments.
- The hand-made purchase order was left as a draft; the flows copy masters
  from the newest order.
