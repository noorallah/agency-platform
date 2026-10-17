# Module test: Reports -- 2026-10-18

Status: **(a) API clean: all 4 kept scripts in `docs/qa/checks/reports/` pass on fixture firm T1016VSH1-S (`python docs/qa/checks/run.py reports` -> "4 of 4 checks clean, 0 failing"). One stale-check fix. No app defect found. Report screens (b) not run.**

## (a) API

- Set-up: `reports/setup.py` copies the TEST01 accounts, so it was not run. New `reports/setup_vsh1.py` writes `.state/reports.json` (admin = `t1016vsh1.tradeadmin`, platform = `t1016vsh1.platform`, seller = `t1016vsh1.urseller@fixtures.local`, the Sales executive the users-roles round made; `ensure_user` reuses it).
- Scripts and assertion counts (after the fix below): tc_rep_001 108 (all 106 catalogue reports read once as admin: 200, success, under 3 s), tc_rep_003 82 (seller 403 on every finance report; inverted range is 4xx on 75 reports), tc_rep_004 13 (D-FIN-35, orders booked vs order register), tc_rep_005 5. Total 208 assertions, 0 failing.

## Stale-check fixes

- `_rep.py`: the `it-block-schedule` report used TEST01's hard-coded financial-year id, so on T1016VSH1-S it answered 404 "Financial year not found". It now reads the first financial year of the firm at run time (same way `PRODUCT_ID` is resolved).
- `tc_rep_001.py`: a not-clean report printed `FAIL` but was never asserted, so the script exited 0 with the 404 in its output. Added `c.ok(bad == 0, ...)` so a failing report fails the script.

## Defects

None new.

## Side effects on the firm

- None beyond the shared user `t1016vsh1.urseller@fixtures.local` (Sales executive), already present from the users-roles round. The checks only read.

## Not verified

- The report screens (columns, filters, export, drill-through) in the desktop client: no screen test was run here.
- Report figures are not reconciled against the ledger beyond tc_rep_004's single order check; the scripts verify status, timing, permission and range refusal.
