# Module test: Commission payout lifecycle -- 2026-10-18

Status: **76 of 76 kept checks pass in 4 scripts on fixture firm T1016VSH1-S, against the running backend. No app defect found.**

Scripts are in `docs/qa/checks/salesmen/` (`tc_comm_001..004.py`, helper `_comm.py`). Each runs alone, makes its own item, customer, salesman, rule and one collected sale dated two days ago, and exits non-zero on a failure. Set-up: `salesmen/setup_vsh1.py` (state only). No pytest or flutter run.

| Script | Subject | Checks | Result |
| --- | --- | --- | --- |
| tc_comm_001 | accrue makes DRAFT payouts; amount snapshotted after the rule rate changes 10% to 25%; second accrue for the same, overlapping-start and containing period refused; one live payout remains | 17 | pass |
| tc_comm_002 | accruer cannot approve (403); another MANAGE holder approves; accrual journal POSTED and equals payable; approve again refused for three users; no second journal | 19 | pass |
| tc_comm_003 | MANAGE-only user approves but pay is 403; SALES_MANAGER pay is 403; a PAY holder who did not approve pays; payment journal distinct, reference ends `-PAY`; pay twice refused; approver cannot pay (403); cancel posts `<accrual>-REV` reversing the accrual; cancelled payout frees the period | 25 | pass |
| tc_comm_004 | draft takes note and reasoned adjustment; `status` in the update body is 422 (PAID, APPROVED, CANCELLED); update of an APPROVED payout refused; status, payable, notes and version unchanged | 15 | pass |
| **Total** | | **76** | **76 pass** |

## Actors

Firm admin accrues; ACCOUNTANT users `commacct1` (approves) and `commacct2` (pays); a firm custom role `comm-mgr-only` (COMMISSION_VIEW + COMMISSION_MANAGE) user `commmgr`; a SALES_MANAGER user `commsmgr`. Users and role are created once per firm by `_comm.actors()` and reused; nothing is reset or deleted.

## Findings

- No app defect.
- Brief assumption corrected, not a defect: SALES_MANAGER holds neither COMMISSION_MANAGE nor COMMISSION_PAY (seed grants only VIEW). So "MANAGE only" cannot be tested with that role; the check uses a custom MANAGE-only role for "allowed on approve, refused on pay", and SALES_MANAGER separately for "refused on pay".
- Segregation of duties (D-TER-4) is exercised: accruer cannot approve, approver cannot pay.

## Leftovers on the firm

A role `comm-manage-only` was created by the platform admin during the first (failed) attempt; it carries no firm and cannot be assigned. It is harmless, left in place (nothing deleted). Checks use `comm-mgr-only`, created by the firm admin.
