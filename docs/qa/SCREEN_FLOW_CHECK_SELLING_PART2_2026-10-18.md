# Screen flow check -- Selling, part 2 (QT, SR and SB) -- 2026-10-18

Firm T1016VSH1-S, backend localhost:8000, `integration_test/run.sh` from a short-path copy of `desktop/` (C:\w35\desktop, refreshed from branch qa/selling-screens-1 at origin/main f03d3fe6), `IT_EMAIL=t1016vsh1.<handle>@fixtures.local`, `IT_PASSWORD=Fixture@2026pw`, `LIMIT=900`. Method as in part 1 (`SCREEN_FLOW_CHECK_SELLING_2026-10-18.md`). Case text: `docs/qa/SCREEN_TEST_CASES_BUY_SELL_PRICE.md`. No application code and no flow file changed.

## Results

| Flow | Handle | Pass | Fail | Not run |
| --- | --- | --- | --- | --- |
| sc_qt_test | tradeadmin | 20 | 0 | 4 |
| sc_qt_test | qsexe | 1 | 0 | 0 |
| sc_qt_test | qsmgr | 1 | 0 | 0 |
| sc_qt_test | qro | 1 | 0 | 0 |
| sc_sr_test | tradeadmin | 15 | 0 | 5 |
| sc_sr_test | qsmgr | 1 | 0 | 0 |
| sc_sr_test | qsexe | 1 | 0 | 0 |
| sc_sr_test | qro | 1 | 0 | 0 |
| sc_sb_test | tradeadmin | 18 | 1 | 16 |
| sc_sb_test | qsmgr | 1 | 0 | 0 |
| sc_sb_test | qsexe | 1 | 0 | 0 |
| sc_sb_test | qacct | 1 | 0 | 0 |
| sc_sb_test | qro | 1 | 0 | 0 |
| **Total** | | **63** | **1** | **25** |

Start-up and stability (exit 79 = the run died before or inside the flow, no summary line):
- sc_qt tradeadmin: exit 79 twice, passed on try 3. sc_sr tradeadmin: exit 79 four times, passed on try 5. All role runs passed first try.
- sc_sb tradeadmin: exit 79 on all five tries of the loop. The deaths were mid-flow, at different steps each time, after `tap()` hit-test warnings ("derived an Offset that would not hit test", on `sales-invoice-save` and `sales-invoice-choose-notes`, in `tickNotes` / `expectRefusal`): once after SC-SB-028, twice at SC-SB-018 (the bill editor not laid out under the tap point). Three further tries were made to capture a log (beyond the five): two died the same way, the third ran to the end and is the result counted above. This is flow flakiness (the editor sheet not settled when the key is tapped), not an application finding.

## sc_qt (Quotations)

Passed (tradeadmin): SC-QT-001, 004, 009, 010, 011 (Print not pressed: the system print preview never returns), 012, 013, 014, 016, 017, 018, 019, 020, 021, 022 (both the converted case and the stale Convert, which raised 0 further orders), 023, 024, 025, 032. Roles: SC-QT-027 (qsexe), 031 (qsmgr), 028 (qro).

Not run (the flow's own reasons): SC-QT-015 no enquiry in the fixture firm; SC-QT-026 no inactive customer (making one would change a master other cases use); SC-QT-029 no Cashier or Billing Executive user; SC-QT-030 no price floor or discount limit set.

## sc_sr (Sales returns)

Passed (tradeadmin): SC-SR-001, 004, 005, 006, 009, 010, 011, 012, 015, 016, 017, 019, 023 (HTTP), 024, 025. Roles: SC-SR-020 (qsmgr), 021 (qsexe), 022 (qro).

Not run: SC-SR-007 no service line on any bill; SC-SR-008 row tick boxes not reached (same as SC-SO-013); SC-SR-013 Return date is read-only so a future date cannot be typed; SC-SR-014 credit-only return off a never-billed note, a report matter; SC-SR-018 no credit note raised on a return in the fixture.

## sc_sb (Sales bills)

Passed (tradeadmin): SC-SB-001, 004, 005, 011 (Send and Attachments), 013, 016, 017, 018, 019, 021 (HTTP 422), 026, 027, 028, 029, 032, 038 (HTTP), 039, 041. Roles: SC-SB-036 (qsmgr), 034 (qsexe), qacct (Sales Invoices offered with no Approve or Edit), 037 (qro).

Failed: **SC-SB-020** "a billed note is not offered under Choose notes": the billed note was correctly absent, but the flow threw "an unbilled note is not offered" (the note the flow had just dispatched was not on screen). Reproduced on the final completed run and the fifth loop run. Cause not established. The Choose notes dialog text recorded in SC-SB-017 lists only eight notes (DN-26-27-000010, 011, 012, 035, 051, 052, 053, 071) in ascending order, none of this run's newest note, so the likely cause is that the newest note sits beyond what the list showed (a long list, or a page limit) rather than being withheld. This is unconfirmed: nobody scrolled or paged the dialog, and nobody checked over HTTP that the note is unbilled. It passed on 2026-10-07 (DN-26-27-000078 offered). Needs a look at the picker (file: the sales invoice editor's Choose notes dialog; flow `desktop/integration_test/sc_sb_test.dart` line 129) before it is called an application defect or a flow defect.

Not run: SC-SB-006, 007, 008, 009, 015, 022, 040 counter-sale cases (the firm bills notes; no Counter sale tick, Cash sale customer or shift); SC-SB-010 service line and delivery charge need a direct bill; SC-SB-012 coupon only on a direct bill; SC-SB-014 row tick boxes not reached; SC-SB-023 no Cash sale customer; SC-SB-024 Invoice date is read-only; SC-SB-025 no closed financial period; SC-SB-030 price floor off and a bill of notes carries the notes' prices; SC-SB-031 no customer with a credit limit; Print (inside SC-SB-011) opens the native print preview and never returns.

## Defects

One open item, SC-SB-020 above (cause undetermined, possibly flow or picker paging). No other application defect found. Observations:
- SC-QT-025 wording on screen is "Close without saving? ... Keep editing / Discard and close", the same difference from the case book as SC-SO-029 in part 1.
- The fixture firm now holds many unbilled dispatched notes for Vijaya Stores from repeated flow runs, which is what makes the Choose notes list long.
