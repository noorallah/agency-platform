# Module test: Collections -- 2026-10-18

Status: **(a) API clean: 21 of 21 kept checks pass on fixture firm T1016VSH1-S. No defects found. (b) Screens: not run: screen flows blocked by permission. (c) Money check: not run: screen flows blocked by permission.**

## (a) API -- `python docs/qa/checks/run.py collections`

- Firm: T1016VSH1-S (`3c766569-...`). Accounts: Firm admin `t1016vsh1.tradeadmin`, Viewer, platform admin, plus a Cashier, a Firm Manager and two Bill Collectors (`t1016vsh1.col*`) added by the set-up. The cross-firm cases use the Masters pass's second firm (`t1016sotp.t2admin`).
- Set-up for this firm: `docs/qa/checks/collections/setup_vsh1.py` (writes `.state/collections.json` from existing accounts; the older `setup.py` builds two new fixture firms instead and the previous state pointed at one of those).
- Covered (21 checks): the TC-COL series (cash 002; sell 013/014/073; fin 013/014/015/028/030-033/037/039/041) and six probes: over-allocation, paise and deductions, post-dated cheque, refund on account, shop-and-parent pay, other-firm and Viewer refusals. Receipts, settlements, advances/customer credits and bill-collector handovers are exercised; loyalty is covered only as far as those series reach it.
- Check-helper fix (not app code): `ensure_user` in `_col.py` took the first role of that code in a platform admin's list, which can be another firm's role (same fault found in Buying, see D-IDN-19). It now matches the role's `firm_id`. Not hit in this run, as the roles resolved, but made safe.
- Result: **21 of 21 clean, 0 failing.** No application code changed; nothing reset or deleted. The checks make their own customers and documents under a fresh tag, so this run added receipts and settlements to the firm.

## Defects
None found. No id proposed.

## (b) Screens
Not run: screen flows blocked by permission.

## (c) Money check
Not run: screen flows blocked by permission.

## Not done here
Screen coverage of Collections flows and the closing money check (`check_money_consistency.py T1016VSH1-S`). Note the Buying record left a 0.02 STOCK_VALUE_VS_INVENTORY_ACCOUNT difference on this firm (D-STK-20 tolerance since changed in #1727); a money check run after this pass should be read with that in mind.
