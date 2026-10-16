# Screen cases, Selling click round: 2026-10-16

Brief: re-drive `selling_flow`, `negative_flow`, `roles_flow`, `sc_so`, `sc_qt`,
`sc_dn`, `sc_sr`, `sc_rc` and `sc_sb` (desktop/integration_test) in the real app.

## Where it ran

Fixture firm `T1016VSH1-S` (suffix `t1016vsh1`, built by
`backend/scripts/test_fixture.py selling-firm`), against the backend at
localhost:8000. Owner approved (OWNER_ANSWERS.md, 2026-10-16 21:05) creating the
role users over the API on that firm only. Created, all with password
`Fixture@2026pw`, member of `T1016VSH1-S` only, one role each:

| Handle | Role |
| --- | --- |
| `t1016vsh1.qsexe` | SALES_EXECUTIVE |
| `t1016vsh1.qsmgr` | SALES_MANAGER |
| `t1016vsh1.qstore` | INVENTORY_MANAGER |
| `t1016vsh1.qacct` | ACCOUNTANT |
| `t1016vsh1.qro` | VIEWER |
| `t1016vsh1.viewer` | VIEWER (spare) |

Administrator: `t1016vsh1.tradeadmin` (FIRM_ADMIN). Each flow was run from
`desktop/` with `LIMIT=580` and a brand-new TEMP/TMP folder. No flow hard-codes a
firm (the firm comes from the account), so only the sign-in was changed.

One change to a flow file: `harness.dart` `chooseIn` now calls `ensureVisible`
on the picker entry before tapping it. In a firm that has grown to 30 delivery
notes the invoice entry in the sales-return box lay below the visible part of
the menu, the tap missed, and the flow reported "Timed out waiting for a box
keyed sales-return-returning-...". That was the flow, not the app.

## The runner dies part-way through (not an app finding)

Many long runs ended with exit 79 ("did not complete") one to five minutes in,
with no error from the app, no crash event and plenty of free memory. It
happened at different steps on different attempts of the same flow, and every
short run completed. These were retried (up to 3 at a time, as the log shows)
and each step below is taken from the attempt that got furthest. Flows still not
finishing on any attempt are marked "partial".

## Results

| Flow | User | Result |
| --- | --- | --- |
| selling_flow_test | tradeadmin | **15 of 15 passed** (SC-QT-002/003/005/006/007/008, SC-SO-002/003, SC-DN-002/003/004, SC-SB-002/003, SC-RC-002, SC-SR-002/003). The first complete run, after the `chooseIn` fix. Before it: 14 passed, return step timed out. |
| negative_flow_test | tradeadmin | 7 passed, 5 not: see below |
| roles_flow_test | qsexe | menu walk, raise an order and find no Approve, open customers: all passed |
| roles_flow_test | qsmgr | menu walk, find the salesperson draft and approve: passed |
| roles_flow_test | qstore | menu walk, deliver the approved order (note saved, approved, dispatched): passed, run directly after qsmgr in the same chain |
| roles_flow_test | qacct | menu walk passed; bill the note FAILED ("Timed out waiting for a New button"); record a receipt passed |
| roles_flow_test | qro | menu walk passed (read only) |
| sc_so_test | tradeadmin | 21 passed, 0 failed, 4 not run |
| sc_so_test | qsexe / qsmgr / qro | SC-SO-030, 031 / SC-SO-032 and SM buttons / SC-SO-033: all passed |
| sc_qt_test | tradeadmin | partial: 17 passed (SC-QT-001, 016..025, 021..024, 009, 010, 011, 004, 012), 0 failed; the run dies before the end every time, so the remaining cases did not run |
| sc_qt_test | qsexe / qsmgr / qro | SC-QT-027 / 031 / 028: all passed |
| sc_dn_test | tradeadmin | 9 passed, 0 failed, 5 not run |
| sc_dn_test | qsexe / qsmgr / qstore / qro | SC-DN-024 / 026 / 025 / 024: all passed |
| sc_sr_test | tradeadmin | 15 passed, 0 failed, 5 not run |
| sc_sr_test | qsmgr / qsexe / qro | SC-SR-020 / 021 / 022: all passed |
| sc_rc_test | tradeadmin | 18 passed, 0 failed, 7 not run |
| sc_rc_test | qacct / qsexe / qsmgr / qro | SC-RC-027 / 024 / 025 / 026: all passed |
| sc_sb_test | tradeadmin | 19 passed, 0 failed, 16 not run |
| sc_sb_test | qsmgr / qsexe / qacct / qro | SC-SB-036 / 034 / (AC buttons) / 037: all passed |

"Not run" cases in the administrator flows are the flows' own SKIPs (counter
sales, no credit-limit customer, no closed period, no carrier master, no TDS
master, grid tick-boxes not reached, Print opening the native preview), each with
its reason printed in the log; none is an app fault.

### negative_flow_test, steps

| Step | Result |
| --- | --- |
| order: open a new one | pass |
| order: save with no customer and no product | pass |
| order: fill customer and product | pass |
| order: quantity 0 | pass, but flagged below (N-1) |
| order: quantity -5 | pass, but flagged below (N-1) |
| return: more than was billed | pass (after the `chooseIn` fix) |
| receipt: far more than the customer owes | pass (taken as an advance, as designed) |
| offer: ends before it starts | not driven: "Timed out waiting for settings card sales/promotions" |
| coupon: a code that already exists | not driven: follows from the step above |
| purchase order: approve a second time | not driven: this fixture firm holds no approved purchase order |

The last three are the flow and fixture: Settings is now organised by subject
(`lib/phase2/settings_subject.dart`) and `openSetUp` still looks for the old
`setup-card-sales/promotions` card; and the selling firm has no purchase order.
They need the flow's navigation updated, which is more than a constant, so they
were not changed here.

## Defects (app), for the owner to register

None found among the passing and failing steps of the selling chain itself. Two
candidate rows from the flows' own checks:

* **N-1, desktop, negative_flow_test.dart, step "order: quantity 0" and "order:
  quantity -5".** Saving a sales order with quantity 0 or -5 is refused (nothing
  is saved) but, in this flow's check, no text on screen says why. In `sc_so_test`
  the same refusal is observed saying "Check the fields marked below. | Enter the
  quantity." (SC-SO-019 passed), so N-1 may be the negative flow reading the screen
  too early; confirm by hand before registering.
* **R-1, desktop or role seed, roles_flow_test.dart, user `qacct` (ACCOUNTANT),
  step "menu: walk every offered screen".** The menu offers Ledgers, IT Block
  Schedule, Trial Balance, Profit and Loss, Balance Sheet and Cash Flow, and each
  opens a screen saying "You do not have permission to perform this action." A
  screen offered in the menu should open for the role that is offered it. Either
  the menu should hide these for ACCOUNTANT or the role should hold the view
  codes.

## Flow expectations that do not match the seeded roles (not defects)

* **qacct "bill the note":** `roles_flow_test.dart` expects the accountant to
  create and approve a sales invoice. `ACCOUNTANT` alone is offered Sales
  Invoices with no New button (the book's own SC-SB-AC case passes with "Approve
  absent, Edit absent"). The flow's expectation, not the role, should change, or
  the fixture should give `qacct` BILLING_EXECUTIVE as well; the owner decides.
* **Menu walk "defects":** the walk flags any screen text containing "permission",
  "failed" or "error". For VIEWER and the sales roles these are the read-only
  notes on screens they may read ("Recording one needs the approve sales
  permission.", "Failed: 0" on inventory import, "0 errors, 0 warnings" on GST
  checks). They are working as designed and show up as "failed N" in each user's
  summary line; the lists are in the logs, and the same wording appears for qsexe
  (3), qsmgr (3), qstore (2) and qro (15).

## Order dependence

The role chain hands documents on by being the newest on the server. Other flows
create newer orders, so the chain was run again by itself, in order, qsexe then
qsmgr then qstore then qacct, and passed up to qacct's bill. Run the chain right
after one another and before any other order-raising flow.

## Logs

Per-run logs are in `agency-it-<flow>.log` under each run's temp folder; the
first complete run for each step is described above.
