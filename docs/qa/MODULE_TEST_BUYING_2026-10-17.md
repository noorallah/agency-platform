# Module test: Buying (item 35) -- 2026-10-17

Status: **(a) API clean: 33 of 33 kept checks pass on fixture firm T1016VSH1-S. One Low observation logged (D-IDN-19, Identity, not Buying). Screens (b) and money check (c) not run in this pass: "backend verified, screens not".**

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
(b) screen clicks and (c) `check_money_consistency.py T1016VSH1-S` for Buying. Open from the loop: the Viewer Buy-menu wording question (QUESTION 2026-10-17), not part of this API pass.
