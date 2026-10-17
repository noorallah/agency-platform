# Screen flow check -- Selling, part 3 (RC and PF) -- 2026-10-18

Firm T1016VSH1-S, backend localhost:8000, `integration_test/run.sh` from the short-path copy C:\w35\desktop (`integration_test/`, `lib/` and `pubspec.yaml` refreshed from branch qa/selling-screens-3 at origin/main a8c95eef), `IT_EMAIL=t1016vsh1.<handle>@fixtures.local`, `IT_PASSWORD=Fixture@2026pw`, `LIMIT=900`. Method as in parts 1 and 2. Case text: `docs/qa/SCREEN_TEST_CASES_BUY_SELL_PRICE.md`. No application code and no flow file changed; no data reset.

## Results

| Flow | Handle | Pass | Fail | Not run |
| --- | --- | --- | --- | --- |
| sc_rc_test | tradeadmin | 18 | 0 | 7 |
| sc_rc_test | qsexe | 1 | 0 | 0 |
| sc_rc_test | qsmgr | 1 | 0 | 0 |
| sc_rc_test | qro | 1 | 0 | 0 |
| sc_pf_test | tradeadmin | 14 | 0 | 1 |
| sc_pf_test | qsexe | 2 | 0 | 0 |
| sc_pf_test | qsmgr | 1 | 0 | 0 |
| sc_pf_test | qro | 1 | 0 | 0 |
| **Total** | | **38** | **0** | **8** |

Start-up: sc_rc tradeadmin died before the summary on try 1 and passed on try 2; every other run passed first try.

## sc_rc (Receipts)

Passed (tradeadmin): SC-RC-001, 003, 004, 005, 008 (Send not offered, Print enabled, Files opens; Print not pressed), 009, 012 (empty and 0), 013, 014 (date picker offers no day after today; HTTP receipt dated tomorrow answered 422), 017, 018, 019, 020, 021, 022, 029, 030 (HTTP 422). Roles: SC-RC-024 (qsexe, Receipts not offered, list 403), 025 (qsmgr, same), 026 (qro, readable, no New or Reverse).

Not run (the flow's own reasons): SC-RC-006 no TDS master in the fixture; SC-RC-007 no early-payment discount on any bill; SC-RC-010 no payment promise; SC-RC-011 Collection Sheet not reached; SC-RC-015 no closed financial period; SC-RC-016 Mode and account default to Cash, no empty state; SC-RC-028 needs the cashier user.

## sc_pf (Proformas)

Passed (tradeadmin): SC-PF-001, 002, 003, 004 (Withdraw, and Withdraw without a reason refused), 006 (Print not pressed), 007, 008, 009, 010, 011, 012, 013, 018. Roles: SC-PF-014 (qsmgr), 015 and 017 (qsexe), 016 (qro).

Not run: SC-PF-005 an approved order cannot be edited on screen, so it cannot change under its proforma.

## Defects suspected

None. Observations, not findings:
- SC-RC-005 (cheque receipt) logs "instrument date null" and SC-RC-009 / 019 log "bill outstanding null of ..." although the steps pass. These look like the flow reading a field name the receipt/invoice JSON does not carry; the instrument date and the restored outstanding were therefore not independently confirmed from the record. Worth a look at the flow's field names, not an app defect on this evidence.
- SC-RC-017: after pressing Record with no customer, the newest receipt read back customer null, amount 10.00 (a receipt created earlier in the run, not this press); saved=0 and the dialog stayed open, so the refusal stands.
