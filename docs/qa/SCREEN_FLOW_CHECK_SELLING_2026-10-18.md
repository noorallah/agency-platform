# Screen flow check -- Selling, part 1 (SO and DN) -- 2026-10-18

Firm T1016VSH1-S, backend localhost:8000, `integration_test/run.sh` from a short-path copy of `desktop/` (C:\w35\desktop, branch qa/selling-screens-0 at origin/main), `IT_EMAIL=t1016vsh1.<handle>@fixtures.local`, `IT_PASSWORD=Fixture@2026pw`. Case text: `docs/qa/SCREEN_TEST_CASES_BUY_SELL_PRICE.md`. Every flow started on the first try (no exit 79). No application code and no flow file changed.

## Results

| Flow | Handle | Pass | Fail | Not run |
| --- | --- | --- | --- | --- |
| sc_so_test | tradeadmin | 21 | 0 | 4 |
| sc_so_test | qsexe | 3 | 0 | 0 |
| sc_so_test | qsmgr | 3 | 0 | 0 |
| sc_so_test | qro | 2 | 0 | 0 |
| sc_dn_test | tradeadmin | 9 | 0 | 5 |
| sc_dn_test | qsexe | 1 | 0 | 0 |
| sc_dn_test | qstore | 1 | 0 | 0 |
| sc_dn_test | qsmgr | 1 | 0 | 0 |
| sc_dn_test | qro | 1 | 0 | 0 |
| **Total** | | **42** | **0** | **9** |

Passed cases (a "pass" line counts a step; some cases have several lines):
- SO tradeadmin: SC-SO-001, 006, 007, 008, 011, 017, 018, 019 (quantity 0 and -3), 020, 021, 023, 024, 025, 027, 029 (Esc and Cancel button), 034, 035, 036.
- SO roles: SC-SO-030, 031 (qsexe); SC-SO-032 and lifecycle buttons (qsmgr); SC-SO-033 (qro); menu offered for each.
- DN tradeadmin: SC-DN-001, 013, 015, 017, 018, 019, 021, 023, 030.
- DN roles: SC-DN-024 (qsexe, qro), SC-DN-025 (qstore), SC-DN-026 (qsmgr).

## Defects

None found. Observations, not defects:
- SC-SO-029 wording on screen is "Close without saving? ... Keep editing / Discard and close"; the case book says "Discard unsaved changes?" with "Keep editing / Discard changes". Case text is out of step with the app (flow logs it as INFO).
- SC-SO-035: an order held by another user was still cancelled from the stale list (status CANCELLED, hold flag stays true), which matches "a hold is a flag, not a status"; the flow passes it as written.

## Not run (skipped by the flows, with their reasons)
- SC-SO-022: no customer with a credit limit on the firm (needs the CC section's customer).
- SC-SO-028: needs an offer with a total-uses cap of 1 (OF section).
- SC-SO-026: needs a delivery-note editor session on a held order (done in the DN file).
- SC-SO-013: bulk selection checkboxes not reached in two attempts (flow limitation).
- SC-DN-029: a saved delivery note cannot be reopened for change on screen, so there is no second session to race.
- SC-DN-014: stock cannot be set to 5 without moving the firm; approved orders reserve more than the 82 on hand.
- SC-DN-016: the date box offered no future date in two attempts.
- SC-DN-020: needs a billed dispatched note (SB file).
- SC-DN-022: no carrier master record on the firm.

The other Selling screen flows (sc_qt, sc_sr, sc_sb, sc_rc and the rest) are outside this first part and were not run.
