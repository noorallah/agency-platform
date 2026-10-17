# Screen cases, Buying click round: 2026-10-17

Brief (AWAY_WORK_LIST item 31, Buying only): re-drive `buying_flow`, `sc_po`,
`sc_gr`, `sc_pb`, `sc_pr`, `sc_py` and the buying part of `roles_flow`
(desktop/integration_test) in the real app. No app code, DEFECTS.md or other
shared doc was edited.

## Where it ran

Fixture firm `T1016VSH1-S`, backend at localhost:8000 (health 200). Accounts and
password are those of `docs/qa/SCREEN_FLOW_CHECK_SELLING_2026-10-16.md`:
administrator `t1016vsh1.tradeadmin`, VIEWER `t1016vsh1.qro`, INVENTORY_MANAGER
`t1016vsh1.qstore`. Each flow was run through `integration_test/run.sh` from
`desktop/` with `LIMIT=580`, a brand-new TEMP/TMP folder per run and
`IT_EMAIL`/`IT_PASSWORD` set. No firm, user or master was created.

## The round is blocked by the fixture, not by the app

`T1016VSH1-S` is the selling fixture. Asked through the API with the
administrator's token: **0 vendors**, no purchase order (the product
"Detergent 1kg t1016vsh1" exists). Every Buying flow starts from a supplier
named "Principal supplier" or from an existing purchase order whose masters it
copies (`buy_data.dart` line 14), so none of them can get past its first step.
Creating a vendor over the API was not done: the brief forbids creating firms
and users, and the automatic permission check refused the vendor create, so the
fixture was left as it is. **To finish this round: add a vendor named
"Principal supplier" and at least one purchase order to this firm (or point the
round at a firm that has them), then re-run the five flows below.**

Two runner notes, neither an app finding:

* A worktree path this deep breaks the Windows build (MSB3501, "Could not find a
  part of the path ... flutter_secure_storage_windows_plugin.lastbuildstate").
  The runs were made from a `subst` drive that maps to the same checkout; the
  first build there failed once on the missing `windows/flutter/ephemeral`
  files and every later build was fine.
* The exit-79 start-up death was retried up to five times as the brief says. It
  happened only in `roles_flow_test` for `qro` (four times, then a complete run
  on the fifth); the other runs ended by themselves.

## Results

Counts are per step as the flows report them.

| Flow | User | Result |
| --- | --- | --- |
| buying_flow_test | tradeadmin | **fail** SC-PO-002 order: new, line, save: "Timed out waiting for picker entry Principal supplier" (the vendor box is empty; screen otherwise correct: New purchase order, Draft, buyer, branch HO). GR, bill, payment and return steps not run (4) |
| sc_po_test | tradeadmin / qro / qstore | not driven: "Bad state: no purchase order to copy masters from" before the first case |
| sc_gr_test | tradeadmin / qro / qstore | not driven: same error |
| sc_pb_test | tradeadmin / qro / qstore | not driven: same error |
| sc_pr_test | tradeadmin / qro / qstore | not driven: same error |
| sc_py_test | tradeadmin / qro | not driven: same error |
| sc_py_test | qstore | **pass** SC-PY-022 (Payments not offered: not offered in the menu, list answers 403) |
| roles_flow_test | qro | menu walk: **pass** (walks every offered screen; Buy area offers 13 screens); the chain steps were not reached, see below |
| roles_flow_test | qstore | menu walk: **pass**; Buy area offers goods receipts, requisitions, quality inspection, supplier statements, supplier gifts |

Tally of this round, counting each run above as one step: **3 passed**
(SC-PY-022 for qstore, two menu walks), **1 failed** in a flow's own step
(SC-PO-002), **14 runs not driven** (fixture), 4 steps not run after the
failure. The 15 "failed" that the qro roles summary prints are the menu-walk
DEFECT lines below, not broken clicks.

### roles_flow_test, Buy menu, VIEWER (qro)

The walk opens every screen the menu offers and reports a screen that only says
the user may not act. For a VIEWER these Buying screens are offered and say so:

| Screen | Text on it |
| --- | --- |
| purchases/debit-notes | Raising one needs the manage debit notes permission |
| accounting/payment-runs | Starting one needs the create permission for payments |
| masters/supplier-gifts | Recording one needs the manage supplier gifts permission |
| purchases/supplier-rebates | Recording one needs the approve purchases permission |
| purchases/principal-claims | Raising one needs the approve purchases permission |
| purchases/landed-costs | Posting one needs the approve purchases permission |

Also in the Accounts area for qro: accounting/pdc-issued ("Recording one needs
the create permission for payments, expenses or journals"). The orders, goods
receipts, bills, returns, requisitions, RFQs, rate contracts, supplier schemes,
bills of entry, quality inspection, payments and supplier statements screens
opened without such a message.

For qstore (INVENTORY_MANAGER) the Buy menu offers masters/supplier-gifts, which
says "Recording one needs the manage supplier gifts permission".

## Candidate defects (not logged in DEFECTS.md)

1. **Menu offers a Buying screen the role can only be refused on** (roles_flow,
   menu walk, qro): purchases/debit-notes, accounting/payment-runs,
   masters/supplier-gifts, purchases/supplier-rebates,
   purchases/principal-claims, purchases/landed-costs (and accounting/pdc-issued
   in Accounts). The screens read fine and the message is clear, so this may be
   by design (read-only view of the list); the flow itself calls it a defect.
   The same for masters/supplier-gifts with qstore. Needs an owner decision on
   whether a read-only role should see these entries.
2. **Fixture / flow coupling** (not an app fault): the Buying flows hard-code a
   vendor named "Principal supplier" and the `sc_*` flows need a purchase order
   to copy from. Anyone running them on a firm without those gets a time-out or
   a "Bad state" rather than a skip with a reason. A skip with a reason, as the
   selling flows do, would make this visible.
3. **Not Buying, seen on the way** (roles_flow, qstore): inventory/inventory-import
   opens a screen whose text is "Failed: 0"; and the storekeeper step "deliver
   the approved order" fails with "the newest order is DELIVERED" because the
   chain was already run on this firm (flow state, not the app).

## Not clicked

Everything past the first step of the Buying flows: purchase order create, save,
approve, edit, cancel and its negative cases (sc_po); goods receipt (sc_gr);
supplier bill (sc_pb); purchase return (sc_pr); payment and its settlement
(sc_py, administrator and qro); the chain steps of roles_flow for qro and qstore
(the Selling doc covers the sales half; the Buying half needs a purchase
officer and a vendor); the sc_* role cases for qro and qstore on orders,
receipts, bills and returns.
