# Module test: Tax (GST returns, e-invoice, TCS, RCM) -- 2026-10-18

Status: **(a) API: 16 of 19 kept compliance scripts pass on fixture firm T1016VSH1-S (firm two T1016SOTP-S); 3 fail, all three because the check assumes a firm that holds only its own three bills (check assumption, not an application defect). The RCM GTA script is not a repeatable check and was not run (see below). No new application defect. (b) Screens: not run: screen flows blocked by permission (flow commands refused, question open in OWNER_ANSWERS). (c) Money check on screen: not run, same reason.**

## (a) API -- scripts under `docs/qa/checks/compliance/` and `docs/qa/checks/rcm/`

- Firm one: T1016VSH1-S (`3c766569-...`), admin `t1016vsh1.tradeadmin`; firm two (the one a check may change, and the "other firm" of the isolation probe): T1016SOTP-S (`4eed4de4-...`), its `t1016sotp.t2admin`. Platform admin `t1016vsh1.platform`.
- Set-up: new `docs/qa/checks/compliance/setup_vsh1.py` (the older `setup.py` runs the `compliance-firm` fixture twice and builds new firms). Neither fixture firm had a GST number, so it gives each a Tamil Nadu GSTIN (valid check character), a product `<STEM>-P` at HSN 340220, a registered buyer `-B2B` (valid GSTIN and PAN), a walk-in `-B2C` and three bills in the shape of the fixture: A (10 x 100, B2B, registered with the sandbox portal), B (5 x 100, B2B, registered), C (3 x 100, B2C, not registered). Unlike the fixture, A is **not collected**; no check turned out to need it. Re-running finds what exists. Writes `.state/compliance.json` (not committed).
- Each script was run by its path with the repo venv python. Nothing reset, reseeded or deleted. The only writes besides the set-up are each check's own customers and bills (firm two) and the GST document policy, which the checks put back.

| Script | Steps | Result |
| --- | --- | --- |
| tc_comp_001 GSTR-1 for the month | 12 | **fail**, 4 steps (C1) |
| tc_comp_002 cancelling a B2C bill | 7 | pass |
| tc_comp_003 GSTR-3B agrees with GSTR-1 | - | **fail**, 3 steps (C2) |
| tc_comp_004 e-invoice list, SANDBOX marks | - | **fail**, 1 step (C3) |
| tc_comp_005 buyer with no GSTIN refused | 3 | pass |
| tc_comp_006 | 11 | pass |
| tc_comp_007 TCS: nothing collected | 13 | pass |
| tc_comp_008 | 10 | pass |
| tc_comp_009 | 16 | pass |
| tc_comp_010 | 10 | pass |
| tc_comp_018 | 11 | pass |
| tc_comp_021 | 8 | pass |
| tc_comp_022 | 9 | pass |
| tc_comp_023 | 7 | pass |
| p_comp_cancel_drops | 8 | pass |
| p_comp_gstr_agree | 8 | pass |
| p_comp_other_firm (another firm refused, 401/403) | 11 | pass |
| p_comp_period_limit (more than three months refused) | 12 | pass |
| p_comp_sandbox_marks (nothing reads LIVE) | 26 | pass |
| rcm/check.py (RCM GTA round 1) | 31 in its log | **not run** (R1) |

Result: **16 passed, 3 failed, 1 not run** (of 20 scripts). The passing scripts hold 170 steps; the three failing ones had 8 failing steps between them (the failing scripts' other steps passed, including A and B under B2B with the right place of supply and tax).

TDS is not covered by a kept script in either folder (no `tds` check exists); e-way bills are covered inside tc_comp_006 / 009 / 010.

## Why the three fail (probed against the running backend)

- **C1 tc_comp_001.** The case expects one B2CS row (33 / 18 percent / 300), one HSN row (340220, 18 pieces, 1,800) for the month. T1016VSH1-S already trades this month, so GSTR-1 also holds other rows: two B2CS rows (the other at 12 percent, 3,157.00 taxable) and three HSN rows, one of them an empty HSN (11,359 pieces, 877,742.99) from items that have no HSN. The B2B half (one buyer, A and B, 1,000/90/90 and 500/45/45, place of supply 33, no CDNR gap, no unplaced invoice) passes. Check assumes a firm that holds only A, B and C.
- **C2 tc_comp_003.** Expects 3B outward 1,800.00 / 162.00 / 162.00, no notes and nil net ITC; the firm holds other sales (882,699.99 taxable), credit notes (5,812.70) and purchases (ITC 38,338.20). The agreement of 3B with 1 for firm two and the other steps pass; the delta-based probe `p_comp_gstr_agree` passes, which is the right form.
- **C3 tc_comp_004.** Expects the two registrations to be `SI-26-27-000001` and `-000002`; they are `-000540` and `-000541`. Everything else (SBX marks, SANDBOX / REGISTERED, no LIVE, no e-way bill yet) passes.
- **R1 rcm/check.py.** A round-1 driver, not a kept check: it is tied to the test firm RCM01 (`87f8344b-...`, exists, GSTIN set), a hard-coded branch id and absolute figures (3.1(d) taxable 16,000 and so on), reads a `state.json` that is not kept (set-up scripts `setup.py` .. `setup6.py` make it) and records a GST payment and a debit note, which a second run would repeat. Its last log shows 31/31 passed on 2026-10-17. Pointing it at T1016VSH1-S needs a rewrite as `tc_rcm_*`: its own vendors, bills and deltas.

## Defects

No new application defect. Nothing for `docs/DEFECTS.md`. Compliance defects of the same area are already recorded (D-CMP-17, D-CMP-22, D-CMP-26, D-PRC-50).

Proposed check fixes (QA sources, not edited here): C1 and C2 compare against the month's figures read before the check's own bills (delta, as `p_comp_gstr_agree` does) or filter by the B2B buyer; C3 find A and B through `.state` invoice ids instead of numbers; R1 turn into a kept `tc_rcm_*` on a fixture firm; add a TDS check if TDS is to be covered.

## (b) Screens
Not run: screen flows blocked by permission (flow commands refused; question open in OWNER_ANSWERS).

## (c) Money check on screen
Not run: same reason.

