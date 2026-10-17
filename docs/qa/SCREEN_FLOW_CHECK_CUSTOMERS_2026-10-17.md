# Screen cases, Customers/Masters click round: 2026-10-17

Brief (AWAY_WORK_LIST item 31, Customers/Masters only): re-drive `sc_cm`,
`sc_cc`, `sc_cp` and the customers part of `roles_flow` (desktop/integration_test)
in the real app. No app code, DEFECTS.md or other shared doc was edited.

## Where it ran

Fixture firm `T1016VSH1-S`, backend at localhost:8000 (health 200). Accounts and
password are those of `docs/qa/SCREEN_FLOW_CHECK_SELLING_2026-10-16.md`:
administrator `t1016vsh1.tradeadmin`, VIEWER `t1016vsh1.qro`. Each flow was run
through `integration_test/run.sh` from `desktop/` with `LIMIT=580`, a fresh
TEMP/TMP folder per run and `IT_EMAIL`/`IT_PASSWORD` set. No firm, user or master
was created by hand; only what the flows themselves create (a commission rate,
receipts and their applications, one coupon offer the flow retired again).
The exit-79 start-up death occurred only in `roles_flow_test` for `qro` (four
times in the first attempt, one more in a second; a complete run on the next).
The roles flow's customer step belongs to `qsexe` ("open a customer, credit
limit"); for the two accounts asked for, its customers part is the menu walk.

## Results

| Flow | User | Result |
| --- | --- | --- |
| sc_cm_test | tradeadmin | **5 passed, 5 failed, 1 not run.** Passed: SC-CM-012 (Rate "" and "-3" refused), SC-CM-013, SC-CM-022, SC-CM-011. Failed: SC-CM-001 "Bad state: not on screen: [Applies to, On, In force, Status]"; SC-CM-012 Rate "0": the dialog closed and "Commission rate recorded. In force, Everything" (a 0% rule was saved); SC-CM-016 x3 (no dates, To before From, no collections): "Timed out waiting for field From" with the Payouts view on screen showing "No payouts" and "+ Accrue". SC-CM-005 skipped by the flow (accruing a real period would hold the period) and with it CM-015..021, CM-006..010. |
| sc_cm_test | qro | **pass** SC-CM-027: readable, Add rule / Edit / Accrue / Adjust / Approve / Pay / Cancel all absent |
| sc_cc_test | tradeadmin | **12 passed, 0 failed, 3 not run.** SC-CC-001, 002, 003, 004, 006, 007, 008, 009, 010 (x2), 016. Not run (flow skips): CC-005 (report screen), CC-011 (no second customer), CC-015 (no Counter Sales user). |
| sc_cc_test | qro | **pass** SC-CC-014: readable, list 200, Apply / Customer credits / Reverse absent |
| sc_cp_test | tradeadmin | **0 passed, 11 failed, 11 not run.** Ten steps: "Bad state: Promotions not offered" (SC-CP-001, 008 x2, 009, 010, 011 x2, 016, 001 save, 002); SC-CP-007: "Timed out waiting for settings card sales/promotions". Settings > Set up shows the cards Pricing, Territories & routes, Account structure, Party lists, Item lists, Locations; Pricing reads "Price lists, price levels, promotions, loyalty / Opens one screen". The flow's 11 other cases skip themselves (need priced documents or a file chooser). |
| sc_cp_test | qro | **fail** SC-CP-020: "Bad state: Promotions not offered to RO" (same cause) |
| roles_flow_test | tradeadmin | menu walk **pass**; masters/customers offered and opened without a refusal message. Summary 1 passed, 1 failed (the failure is DEFECT line inventory/inventory-import "Failed: 0") |
| roles_flow_test | qro | menu walk **pass**; masters/customers offered (Masters area: customers, vendors, products, branches, warehouses, trade-licences) and opened without a refusal message. Summary 1 passed, 14 "failed" = DEFECT lines below |

## Candidate defects (not logged in DEFECTS.md)

1. **SC-CM-012, Rate 0 is accepted** (tradeadmin): the Add commission rate
   dialog saved a rule at 0% and said "Commission rate recorded". The flow
   expects it to be refused (negative and empty are). Either the case is stale
   (0 may be meant as "no commission") or the form lets a pointless rule in. Left
   behind in the fixture firm: one in-force 0% rule on "Everything".
2. **Flows out of step with the Settings layout** (SC-CP all, SC-CM-001/016, not
   necessarily app faults): `openSetUp(tester, 'sales/promotions')` finds no
   such card; promotions sit behind the combined Pricing card. SC-CM-001 looks for
   the Rates columns "Applies to, On, In force, Status" and SC-CM-016 for the field
   "From" in the Accrue dialog; neither was found where the flow looked, with the
   Commission screen otherwise open. Needs a look at whether the flow or the
   screen changed (the Coupons side was therefore not driven at all this round).
3. **Menu offers a screen the VIEWER can only be refused on** (roles_flow, qro,
   customers side): sales/credit-notes, sales/customer-debit-notes,
   sales/enquiries, sales/customer-rebates, accounting/pdc-received,
   accounting/party-adjustments, accounting/contra-vouchers (plus the buying ones
   in the Buying file: debit-notes, payment-runs, supplier-gifts,
   supplier-rebates, principal-claims, landed-costs, pdc-issued). Messages are
   clear ("Raising one needs the manage credit notes permission"); may be by
   design as read-only lists. Owner decision, as in the Buying file.
4. Seen on the way, not customers: inventory/inventory-import opens a screen
   saying "Failed: 0" (administrator and, per Buying file, others).

## Not verified / not clicked

The Coupons screen (create, generate codes, duplicate, dates, cancel; roles SM,
FS) because it was never reached; commission accrual, adjust, approve, pay,
cancel and their negative cases (the flow skips them to keep the period free,
and the Accrue dialog was not reachable); the commission and credits role cases
for qacct, qsmgr and qsexe (only the VIEWER was asked for); the salesperson's
customer/credit-limit step of roles_flow (qsexe); the customer master editor
itself (no flow in this list opens it beyond the menu walk). The failures in
SC-CM-001/016 were read from the flow's own text, not by looking at a
screenshot.
