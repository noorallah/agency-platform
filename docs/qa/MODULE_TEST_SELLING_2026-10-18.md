# Module test: Selling (item 35) -- 2026-10-18

Status: **(a) API clean: 27 of 27 kept checks pass on fixture firm T1016VSH1-S after two check fixes (first run 22 of 27). No application defect found, none logged. (b) screens not run in this pass. (c) money check printed 'the books agree' on 2026-10-18.**

## (a) API -- `python docs/qa/checks/run.py selling`

- Firm: T1016VSH1-S (`3c766569-...`), Firm admin `t1016vsh1.tradeadmin`, Viewer, platform admin, plus a Sales Executive (`sellexec`) added by the set-up; the cross-firm cases use the Masters pass's second firm.
- Set-up for this firm: `docs/qa/checks/selling/setup_vsh1.py` (writes `.state/selling.json` from existing accounts; the older `setup.py` makes two new fixture firms instead).
- Covered (27 checks): TC-SELL series as kept (005-108), credit block, stage switched off, line discount total, return approval, round-off returns, salesman required, other-firm and Viewer refusals.
- First run: 22 of 27, five failing (`p_sell_stage_off`, `tc_sell_011`, `tc_sell_094`, `tc_sell_104`, `tc_sell_105`). All five are check-versus-firm-configuration, not the application:
  - This firm has loyalty switched on (2 points per rupee) and an ACTIVE promotion BULK5; the checks were written against ready-firm, which has neither.
  - Loyalty posts a separate journal entry `LOY-<bill number>`, whose reference contains the bill number, so the `journal()` helper in `_sell.py` returned it as a second entry for the bill (the extra 2% debit/credit in 011, 094, 105 and stage_off). Fix: the helper skips entries with `source_module == "loyalty"`.
  - BULK5 took about 8% off the large lines in `tc_sell_104` (500 and 1000 units). A silent discount takes the arrangement; a typed `0` refuses it (rule in CLAUDE.md, Pricing). Fix: the check's order and quotation lines now send `"discount_percent": "0"`.
- Re-run: **27 of 27 clean**.
- No application code changed; nothing reset or deleted; no firm configuration changed (loyalty and BULK5 left as they were).

## Defects
None new.

## (c) Money check
`backend/scripts/check_money_consistency.py T1016VSH1-S` printed "VERDICT: the books agree" on 2026-10-18 (after the checks ran).

## Not done here
(b) Screen flows for Selling (SC-SO, SC-SI, SC-DN, SC-SR and the like) were not run in this pass. The checks run on a firm with loyalty and a promotion live, so they now neither prove the loyalty/promotion-off ready-firm case nor were they run there; the ready-firm run via `setup.py` was not repeated.
