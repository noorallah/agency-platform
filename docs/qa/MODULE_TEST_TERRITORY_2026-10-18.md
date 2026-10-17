# Module test: Territory and salesmen -- 2026-10-18

Status: **(a) API clean: 157 of 157 kept checks pass in 17 scripts on fixture firm T1016VSH1-S, after one stale-check fix. No app defect found. Screens (b) not run in this part.**

## (a) API -- `docs/qa/checks/salesmen/`

- Firm: T1016VSH1-S (`3c766569-...`); accounts `t1016vsh1.tradeadmin`, `.viewer`, `.platform`, plus a Sales executive `t1016vsh1.smexec` added by the set-up; the cross-firm cases use the Masters pass's second firm (`admin2`).
- Set-up: new `docs/qa/checks/salesmen/setup_vsh1.py` (same shape as `buying/setup_vsh1.py`; writes `.state/salesmen.json` from existing accounts). The older `setup.py` builds two new fixture firms and was not run.
- The folder holds the kept scripts for Territory (`tc_terr_007`), Salesmen (`tc_sell_114`-`118`, `p_sm_*`) and Incentives (`tc_incent_*`). There is only one `tc_terr_*` script; the other territory cases have no kept script.
- Each script run on its own (the `run.py` runner was not used: it reads `.state` from the checks folder, same result).

| Script | Checks | Result |
| --- | --- | --- |
| tc_incent_006 | 11 | pass (after fix) |
| tc_incent_007 | 19 | pass (after fix) |
| tc_incent_008 | 3 | pass |
| tc_incent_013 | 16 | pass |
| tc_incent_014 | 17 | pass |
| tc_sell_114 | 7 | pass |
| tc_sell_115 | 13 | pass |
| tc_sell_116 | 9 | pass |
| tc_sell_117 | 11 | pass |
| tc_sell_118 | 5 | pass |
| tc_terr_007 | 5 | pass |
| p_sm_delete_in_use | 6 | pass |
| p_sm_inactive | 5 | pass |
| p_sm_order_keeps | 4 | pass |
| p_sm_other_firm | 7 | pass |
| p_sm_read_write_split | 16 | pass |
| p_sm_required_scope | 3 | pass |
| **Total** | **157** | **157 pass** |

## Stale checks fixed

First run: 15 scripts clean, `tc_incent_006` (7 failures) and `tc_incent_007` (1) failed. Every failing figure was low by a fixed share: Asha collected 5,634.50 against 5,900, Bala 4,322.34 against 4,720, commission 411 against 420, 73.26 against 80, 55.50 against 60. Cause: the Offers pass left live promotions on this firm (stacking `BULK5`, a quantity-5 rule), and the checks sell 20-40 units with no discount field, so an offer applied. The app behaved as designed (silence takes the arrangement). Fix, one place: `sell()` in `_sm.py` now sends `discount_percent: "0"` on its order line, an explicit refusal of every arrangement. Re-run: both pass, and the other 15 scripts still pass with the change. Check files only; no app code.

## Suspected app defects

None.

## Not verified: screens

Part (b) was not run: the Territory screens (areas, routes and beats, route customers and visit order), the Salesmen master and the incentive/target screens. Only the HTTP surface was driven. Also only one territory script is kept (`tc_terr_007`); the rest of the `tc_terr_*` series is not covered by a kept script here.

No application code changed; nothing reset or deleted. The scripts add salesmen, customers, products and documents on the firm under fresh tags (this round added about 30 invoices and their receipts to T1016VSH1-S).
