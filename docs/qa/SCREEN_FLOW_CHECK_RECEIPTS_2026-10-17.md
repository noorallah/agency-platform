# Screen cases, Receipts and Loyalty click round: 2026-10-17

Brief (AWAY_WORK_LIST item 31, Receipts + Loyalty only): re-drive `sc_rc_test`
and `sc_ly_test` (desktop/integration_test) in the real app. No app code,
DEFECTS.md or other shared doc was edited. One flow file was fixed (below).

## Where it ran

Fixture firm `T1016VSH1-S`, backend at localhost:8000 (health 200). Accounts and
password are those of `docs/qa/SCREEN_FLOW_CHECK_SELLING_2026-10-16.md`; the
login email is the handle plus `@fixtures.local` (the handle alone is refused
with "A valid email address is required", which cost one wasted attempt).
Administrator `t1016vsh1.tradeadmin`, ACCOUNTANT `qacct`, VIEWER `qro`. Each flow
ran through `integration_test/run.sh` from `desktop/` with `LIMIT=580`,
`IT_EMAIL`/`IT_PASSWORD` set. No firm, user or master was created by hand; only
what the flows create (receipts, their reversals, one loyalty adjustment).
Exit-79 start-up deaths: `sc_rc_test` tradeadmin four times, then a complete run
on the fifth try (the limit); none elsewhere.

## Results

| Flow | User | Result |
| --- | --- | --- |
| sc_rc_test | tradeadmin | **18 passed, 0 failed, 7 not run.** Passed: SC-RC-001, 003, 004, 005, 008, 009, 012 (empty and 0), 013, 014, 017, 018, 019, 020, 021, 022, 029, 030. Not run (flow skips): RC-006 (no TDS master in the fixture), RC-007 (no early-payment discount offered), RC-010 (no payment promise), RC-011 (Collection Sheet not reached), RC-015 (no closed period), RC-016 (no empty state for Mode/account), RC-028 (needs the cashier user). |
| sc_rc_test | qacct | **pass** SC-RC-027: Receipts offered, list 200, New and Reverse enabled |
| sc_rc_test | qro | **pass** SC-RC-026: Receipts offered, list 200, + New and Reverse absent |
| sc_ly_test | tradeadmin | **11 passed, 0 failed, 10 not run**, after the flow fix. Passed: SC-LY-001, 002, 004, 006, 012 (x3), 013, 014 (x2), 016. Not run: LY-005 (needs a bill part-paid by points, then cancelled), LY-003, 007..011, 015, 020, 021 (no points box on the bill editor in this build, or a second scheme state is needed). First run, before the fix: 0 passed, 11 failed, all "Bad state: Loyalty not offered". |
| sc_ly_test | qro | **pass** SC-LY-019 (after the fix): Loyalty offered, Adjust points and Expire lapsed disabled, Put points back absent, Scheme settings opens with Save disabled. First run, before the fix: failed "Loyalty not offered to Read Only". |

## Flow fixed (stale, not an app defect)

`desktop/integration_test/sc_ly_test.dart`, `openLoyalty()`: it called
`openSetUp(tester, 'masters/loyalty')`, which looks for a Settings card
`setup-card-masters/loyalty`. Loyalty is now a tab of the Pricing subject screen
(`lib/phase2/settings_subject.dart`), as Promotions is (the same cause as the
SC-CP failures in the Customers round). The helper now taps
`menu-area-settings`, `setup-section-Pricing`, `setup-subject-pricing`, then
`subject-tab-masters/loyalty`, the sequence `sc_ofl_test` already uses for
promotions. `harness.dart` `openSetUp` itself is untouched. `sc_rc_test` needed
no change.

## Candidate defects

None found as app defects. Things worth a look, none failing a step:

1. **Loyalty "Scheme settings" is enabled for the VIEWER** (SC-LY-019): the
   dialog opens, Save is disabled, so nothing can be changed; the book's wording
   says read-only, so this is probably by design (a read-only view of the scheme).
2. **Flow log values read "null"** on SC-RC-005 (cheque receipt: "instrument date
   null" although the date box was shown and the receipt saved as CHEQUE) and on
   SC-RC-009 / 019 ("bill outstanding null of ..."). The steps pass, so these may
   be the flow reading a field the API no longer returns under that name (a probe
   gap), but SC-RC-005's instrument date is worth a manual check that the date
   typed is actually stored on the receipt.
3. **SC-RC-003 reports "5 allocations summing 900.0000000000001"**, a float sum in
   the flow's own arithmetic, not a stored value; noted only so it is not mistaken
   for a rounding fault.

## Not verified / not clicked

Receipt with TDS section (RC-006); early-payment discount (RC-007); payment
promise tie-in (RC-010); Collection Sheet (RC-011); posting into a closed period
(RC-015); empty Mode/account (RC-016); the cashier-user and statement cases
(RC-028); roles SM and FS for receipts and loyalty (only ACCOUNTANT and VIEWER were
asked for). Loyalty: points spent on a bill, reversal when that bill is cancelled,
and expiry with real lapsed points (LY-003, 005, 007..011, 015, 020, 021),
because the flow skips them; Scheme settings with Points expire switched on
(SC-LY-014 "Expire after 0 months" was not driven, as it would change the scheme).
SC-LY-014 negative worth was prevented by the input box (digits and a point only),
so no refusal message was seen.
