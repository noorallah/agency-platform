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
