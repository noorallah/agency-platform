# Module test: Buying (item 35) -- 2026-10-17

Status: **(a) API clean: 33 of 33 kept checks pass on fixture firm T1016VSH1-S. One Low observation logged (D-IDN-19, Identity, not Buying). (b) Screens run (below): the flows' own fixture users do not exist on this firm, so the run is partial, 2 app/flow-host questions open. (c) money check printed 'the books agree' on 2026-10-17.**

## (a) API -- `python docs/qa/checks/run.py buying`

- Firm: T1016VSH1-S (`3c766569-...`), Firm admin `t1016vsh1.tradeadmin`, Viewer, platform admin, plus a Purchase Executive (`buyexec`) added by the set-up; the cross-firm cases use the Masters pass's second firm.
- Vendor "Principal supplier" (SUP-00001) already existed on the firm, so none was created; the checks make their own vendor, item and documents per case under a fresh tag (earlier runs today had already left about 100 orders on the firm; this run added to them).
- Set-up for this firm: `docs/qa/checks/buying/setup_vsh1.py` (writes `.state/buying.json` from existing accounts; the older `setup.py` makes two new fixture firms instead).
- Covered (33 checks): order raise/approve/cancel/part-receive, receipt over order, bill over received, bill approval tolerance (`tc_buy_022` with a custom approver role), cancel bill after payment, payment edges, return over received, other-firm and Viewer refusals, plus the TC-BUY series (001-102 as kept).
- First run: 32 of 33. `tc_buy_022` stopped at its set-up: the helper `ensure_user` took the first role of that code in a platform admin's list, which was another firm's `buyappr` (refused 422 correctly). This is the check helper's fault, fixed (match the role's `firm_id`), and it exposed the list behaviour logged as **D-IDN-19** (Low). Re-run: **33 of 33 clean**.
- No application code changed; nothing reset or deleted.

## Defects
| id | severity | symptom |
| --- | --- | --- |
| D-IDN-19 | Low | A platform admin inside firm A lists firm B's same-coded role (open; confirm intended). |

## Not done here
Full screen coverage of the Buying flows: the flows sign in a second user (qpmgr, qpexe, qacct, qstore, qro) that this firm does not have, and the Role cases are keyed to those handles. Cash on the firm is 1,218.48 below zero, which blocks PB and PY from starting. Re-run on a fixture firm made by the flows' own set-up. Open from the loop: the Viewer Buy-menu wording question (QUESTION 2026-10-17), not part of this API pass.

## (b) Screens -- `desktop/integration_test/run.sh sc_<x>_test.dart`

Run on main 3765ee7a against the running backend, firm T1016VSH1-S, with
`IT_EMAIL=t1016vsh1.<user>@fixtures.local`, `IT_PASSWORD=Fixture@2026pw`, users tradeadmin, viewer, buyexec. `sc_dn_test.dart` is Selling (delivery notes) and was not run.

| Flow | tradeadmin | viewer | buyexec |
| --- | --- | --- | --- |
| PO | 18 pass, 3 fail, 11 not run | 0 run | 0 run |
| GR | app exited (code 79) after SC-GR-014, twice; 5 steps passed before | 0 run | 0 run |
| PB | stopped at start: 409 cash below zero | 0 run | 0 run |
| PRT | stopped at start: 401 login | stopped, 401 | stopped, 401 |
| PY | stopped at start: 409 cash below zero | 0 pass, 1 fail | 1 pass |
| PR | 13 pass, 1 fail, 9 not run | 0 run | 0 run |
| PC | 2 pass, 4 fail, 16 not run | 0 run | 0 run |

"0 run" means the flow has no section for that handle: its Role cases belong to qpexe, qpmgr, qstore, qacct, qsexe, qro, none of which exist on this firm.

Failures:
- PO SC-PO-038/039/040, PR SC-PR-027, PRT start: `POST /auth/login answered 401 Invalid email or password` -- the second user of a two-user case (qpmgr and the like) is absent. Flow/fixture mistake, not an app defect.
- PB and PY start, PY first: `POST /api/v1/payments answered 409: Cash is already 1,218.48 below zero on 17-10-2026 and this pays N more out of it.` The app refuses correctly; the earlier API round left cash negative. Fixture state, not an app defect.
- PC SC-PC-012/016/020: `Timed out waiting for picker entry "Principal t1016vsh1"` -- the firm has no principal by that name (grid reads "No claims yet"). Fixture mistake.
- PC SC-PC-001: `not on screen: [Number, Period, Status, Total]` with an empty list ("No claims yet" replaces the headings). Probably the empty state, flow expectation; the flow wants a claim to exist.
- GR: the app process exits with code 79 about 90 seconds in, after SC-GR-014 passes, "No tests were found", same place on both tries. Unexplained; could be an app crash or a host problem. Open for the owner to look at; not retried further.
- Viewer PY SC-PY-022 `Payments not offered`: FAIL `Bad state: Payments is offered`. The same step passes for buyexec (not offered, list 403). The Viewer is offered the Payments menu entry; this matches the open Viewer Buy-menu wording question (QUESTION 2026-10-17). Possible app defect (menu shows what the role cannot open); needs the owner's decision.

No application code was changed. App defects: none certain; one possible (Viewer sees Payments). Re-run needed on a firm with the flows' fixture users and cash above zero.

## (c) Money check
`check_money_consistency.py T1016VSH1-S` printed "the books agree" on 2026-10-17.

## (b2) Screens re-run -- fixture set up, 2026-10-17 (evening)

Why the first screen round was partial was fixture state only. Fixed over the API before this run, nothing else touched:

- Seven users created on T1016VSH1-S with the check helper `ensure_user` (password Fixture@2026pw, one role each): `qsexe` SALES_EXECUTIVE, `qsmgr` SALES_MANAGER, `qstore` INVENTORY_MANAGER, `qacct` ACCOUNTANT, `qpexe` PURCHASE_EXECUTIVE, `qpmgr` PURCHASE_MANAGER, `qro` VIEWER; plus `readyadmin` FIRM_ADMIN and `readyviewer` VIEWER for the printing flow (PRT).
- Principal "Principal t1016vsh1" (code QAPRN) created over `/api/v1/products/principals`.
- One cash RECEIPT of 200,000.00 (RC-2026-2027-000054, from customer Anand Agencies t1016vsh1, instrument reference "QA FIXTURE opening cash") so payments are no longer refused.
- Money check after the receipt, before the flows: `check_money_consistency.py T1016VSH1-S` printed "the books agree".

Flows run with `integration_test/run.sh` from a short-path copy of `desktop/` (the worktree path was too long for MSBuild), main at b07f9769, `IT_EMAIL=t1016vsh1.<handle>@fixtures.local`. Start-up exit 79 retried up to 5 times per flow and handle.

| Flow | tradeadmin | Role handles |
| --- | --- | --- |
| PO | **did not complete**: 5 of 5 starts exited 79 after SC-PO-020 (5 pass, nothing failed) | qpexe, qpmgr, qsexe, qro: 1 pass each; qstore **1 fail** (SC-PO-034) |
| PR | 14 pass, 0 fail, 9 not run (skipped with reasons) | qpexe, qpmgr, qstore, qro: 1 pass each |
| PC | 5 pass, **1 fail** (SC-PC-001), 16 not run; first start exited 79, second ran | qpmgr, qpexe, qacct, qro: 1 pass each |
| PB | 15 pass, **1 fail** (SC-PB-017), 12 not run; first start exited 79, second ran | qpexe, qpmgr, qstore, qro: 1 pass each; qacct 2 pass, **1 fail** (SC-PB-031) |
| PY | 13 pass, 0 fail, 10 skipped with reasons | qacct, qro, qpexe, buyexec: 1 pass each; viewer **1 fail** (SC-PY-022) |
| GR | 14 pass, 0 fail, 11 not run (exit 0; the exit 79 of the first round did not recur) | qstore, qsexe, qro: 1 pass each; qpexe **1 fail** (SC-GR-024), qpmgr **1 fail** (SC-GR-025) |
| PRT | not a tradeadmin flow; run as readyadmin: 15 pass, 0 fail, 2 not run | readyviewer 3 pass, 0 fail |

The 401s and the cash refusal of the first round are gone; SC-PB-035/036 (stale approve and stale save with a second user), SC-PC-012/016/020 (principal picker) and SC-PY (payments) now pass. SC-PO-021 onward and SC-PO-038..040 were not reached because the PO tradeadmin run dies first.

### Failures still open (no application code changed)

| Step | What the flow saw | Reading |
| --- | --- | --- |
| PO tradeadmin, after SC-PO-020 | App process exits with code 79 about 90 s in, five starts out of five; SC-PO-021 onward never ran | Runner/host or app crash, unexplained. Same place as the first round. Not retried beyond the cap. |
| SC-GR-024 (qpexe), SC-GR-025 (qpmgr) | "New not offered": `+ New` is disabled for Purchase Executive and Purchase Manager; Complete and Cancel enabled. Warehouse (qstore) has `+ New` enabled (SC-GR-023 passes) | Probably intended: raising a receipt belongs to the warehouse role (D-ROLE-3), so the case text (PU and PM are offered New) may be out of step with the role design. Owner to confirm which is right. |
| SC-PO-034 (qstore) | Menu does not offer Purchase Orders but the server answers the list with 200 | Same family as the Viewer question below: menu and server disagree. Possible app defect, Low. |
| SC-PY-022 (viewer) | "Payments is offered" for the Viewer; buyexec is not offered it (list 403) | Unchanged from the first round: the open Viewer Buy-menu wording question (QUESTION 2026-10-17). |
| SC-PB-017 (tradeadmin) | "an unbilled receipt is not offered": the picker did not offer a receipt the flow expected to be unbilled | Needs a look by hand; may be fixture state (receipts billed by the earlier API round). |
| SC-PB-031 (qacct) | "error on screen: [SUP-1792252403366654]" when Purchase Invoices opens | The flagged text is a supplier invoice number from a row, not an error message; probably the flow's error detector matching row text. Flow issue, to confirm. |
| SC-PC-001 (tradeadmin) | `not on screen: [Number, Period, Status, Total]`: the grid shows "No claims yet" | Empty state; the flow wants a claim to exist. Fixture, not an app defect. |

### Money check after the flows

`check_money_consistency.py T1016VSH1-S` printed **1 difference**: `STOCK_VALUE_VS_INVENTORY_ACCOUNT` Account 1200 expected 334,988.96, found 334,988.94 (two paise; "a journal on the account no stock movement made"). The books agreed immediately before the flows, so one of the Buying flows (PB, PY, GR, PO) caused it. Candidate real defect (rounding of a purchase bill or return against stock value); not diagnosed here, no id assigned. Needs the owner's ruling and an id in DEFECTS.md.

### Summary
Real application defects: none certain. Open for a ruling: the 0.02 inventory difference above, PO tradeadmin exit 79, GR New for PU/PM, and menu-versus-server disagreement for Warehouse (Purchase Orders) and Viewer (Payments).

**Correction 2026-10-17 (run 76):** SC-PY-022 was run under handle `viewer`, which is not Purchase Manager (`qpmgr`); the read-only handle is `qro`. A Viewer holds PAYMENT_VIEW and `GET /payments` answers 200, so Payments is rightly offered. Not an app defect; D-BUY-79 is fixed in #1720 (registers only).

## Round 3 -- SC-PB-017 and SC-PC-001 (2026-10-17, evening)

Firm T1016VSH1-S, main at origin/main, `integration_test/run.sh` from a short-path copy of `desktop/`, handle `tradeadmin`. No application code changed.

### SC-PC-001 -- passes after a fixture claim

Fixture state, as suspected. The principal "Principal t1016vsh1" (QAPRN) has nothing claimable (preview totals 0; raising is refused "Nothing is left to claim"), so one claim was raised over the API on the principal that does: **Check Company** (code CHECKS), 2026-01-01 to 2026-10-17, free goods 60.00, claim number CLM-2026-2027-000001, remark "QA round 3 fixture claim". Nothing else touched.

`sc_pc_test.dart` tradeadmin: first start 6 steps reached (SC-PC-001, 011, 012, 016, 020 pass) then exit 79 (host death, as before); second start **passed 6, failed 0, not run 16**, exit 0. SC-PC-001 reads "Price cut claim present, + New enabled; missing []". The 16 not-run steps are the flow's own skips.

### SC-PB-017 -- not "all receipts billed"; fixture clutter plus a visibility limit of the flow

The flow makes its own unbilled receipt (`waitingGr = apiReceiptOf(admin, apiPo(admin))`) on every run, so there was no missing fixture to create and none was added. Over HTTP, `GET /goods-receipts?status=COMPLETED&billable=true` (the picker's own query) answers **133 billable receipts** for Principal supplier (242 completed in all), left over from earlier rounds and flows. The picker opened with `GRN-...-000048`, `-000047`, `-000033`, `-000032`... (oldest first within the same day; the list is sorted by `receipt_date` desc and every receipt carries today's date, so the order among them is whatever the database returns). The dialog body is a `ListView` (`lib/phase2/source_tick_dialog.dart`), which builds only the rows on screen; the new receipt is far down a 133-row list, so `screenHas(waitingNo)` is false although the server offers it. The billed receipt is correctly absent.

Run: `sc_pb_test.dart` tradeadmin, one start: **15 pass, 1 fail (SC-PB-017 "an unbilled receipt is not offered"), 12 not run**, same as round 2; no exit 79 on this run.

Reading: flow-versus-fixture, not a certain app fault. Two things for the owner: (1) the flow cannot see an off-screen row, so it needs a firm with few billable receipts, or to search/scroll in the picker; (2) possible Low app point: among receipts of the same date the picker has no tie-break, so a just-received goods receipt is not first -- a secondary sort on number or creation time desc would put it on top. Not changed here.

### Summary
SC-PC-001 now passes. SC-PB-017 still fails, from 133 stale billable receipts and a lazily built picker list, not from billed fixture state. Real application defects: none certain.
