# Module test: Commission -- 2026-10-18

Status: **(a) API clean: 66 of 66 kept checks pass in 5 scripts on fixture firm T1016VSH1-S. No stale check, no app defect found. Screens (b) not run in this part.**

## (a) API -- `docs/qa/checks/salesmen/`

- Scripts: the glob `docs/qa/checks/*/tc_comm*` matches nothing; the kept commission and incentive scripts are `tc_incent_*`, which live in the `salesmen` folder (shared with the Salesmen round).
- Set-up: `salesmen/setup_vsh1.py` (writes `.state/salesmen.json` from existing accounts; needs the Masters pass's `.state/masters.json`, copied in untracked). Nothing created on the server by set-up.
- Each script run on its own, targeted; `run.py` not used; no pytest or flutter.

| Script | Subject | Checks | Result |
| --- | --- | --- | --- |
| tc_incent_006 | per-line rate blend, ladder floor, target met | 11 | pass |
| tc_incent_007 | commission amounts and report rows | 19 | pass |
| tc_incent_008 | commission scenario | 3 | pass |
| tc_incent_013 | commission scenario | 16 | pass |
| tc_incent_014 | commission scenario | 17 | pass |
| **Total** | | **66** | **66 pass** |

The offers-related fix from the salesmen round (`sell()` in `_sm.py` sends `discount_percent: "0"` so live promotions on the firm do not alter figures) is already on main and holds.

## Suspected app defects

None.

## Not verified

- Screens (part b): not run.
- Payout lifecycle over HTTP (accrual snapshot, approval journal, `COMMISSION_PAY` separate from `COMMISSION_MANAGE`, refusal for a role holding only MANAGE, one live payout per person per overlapping period) has no kept script among these five; they cover rules, ladders, targets and report figures. No new script was written in this round.
- `goods_types/tc_mast_029` mentions commission but is a Masters check and was not run here.

No application code or check code changed; nothing reset or deleted. The scripts add salesmen, customers, products and documents on the firm under fresh tags.
