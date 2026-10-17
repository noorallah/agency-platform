# Module test: Roles and access -- 2026-10-18

Status: **(a) API clean: all 76 kept scripts in `docs/qa/checks/users-roles/` pass on fixture firm T1016VSH1-S (`python docs/qa/checks/run.py users-roles` -> "76 of 76 checks clean, 0 failing"). No stale-check fix needed. No app defect found. Screens (b) not run in this part.**

## (a) API

- Set-up: `users-roles/setup.py` runs fixtures that create new firms, so it was not run. A new `users-roles/setup_vsh1.py` writes `.state/users-roles.json` from accounts that already exist: admin = `t1016vsh1.tradeadmin`, platform admin = `t1016vsh1.platform`, firm one = T1016VSH1-S, firm two = the Masters pass's second firm (`.state/masters.json`, copied in untracked). It adds one Sales executive as the "seller" (`t1016vsh1.urseller@fixtures.local`).
- Scripts: 76 (tc_acc x11, tc_hire x4, tc_look x6, tc_role x9, tc_rtier x8, tc_tmpl x14, tc_user x14, p_ur x10), run through `run.py`, which prints only failures and a tally. Per-check assertion counts are not printed by the runner and were not tallied.
- The checks make their own users, roles and templates under a fresh tag and retire them in a `finally`, as designed.

## Stale-check fixes

None.

## Defects

None new. D-IDN-15 and D-FIN-37 (known open) were not hit by any script in this folder.

## Side effects on the firm

- One user left: `t1016vsh1.urseller@fixtures.local` (Sales executive, T1016VSH1-S), made by `setup_vsh1.py`; re-running set-up reuses it.
- Anything a check failed to retire: none seen; not audited beyond the pass result.
