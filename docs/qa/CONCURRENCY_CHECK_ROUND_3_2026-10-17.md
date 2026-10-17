# Concurrency check, round 3 -- 2026-10-17

Item 30m, scenarios h and i. Same script as rounds 1 and 2
(`docs/qa/checks/concurrency/run_concurrency.py`), run against the backend on
localhost:8000 at main 125f3c2d, TEST01 only, no app code changed. Users are
the three fixture accounts from `setup.py` plus extra sessions of the Firm
admin (`admin_b`, `admin_c`).

## Results

| Scenario | What raced | Result |
| --- | --- | --- |
| h | One customer holding 150 points; three redemptions on three different 118.00 bills at once (`POST /loyalty/redeem`, 100 points each, then a second round of 50 each against a balance of 50) | **ok** -- both rounds: 1 x 200, 2 x 422 with a named reason ("That customer holds 50.0000 points, not 100.0000."; once "SI-... owes only 18.00, and those points are worth 50.00."). Balance 150 -> 50 -> 0, never negative, exactly two redemption entries, no 500. The `_hold_customer` lock does its job. |
| i | Three manual vouchers (JV, Dr 6000 / Cr 6200, 10.00) posted by three desks while a fourth user closes their period (`PATCH /finance/accounting-periods/{id}` status CLOSED); five rounds, each in a fresh past financial year older than every TEST01 period so it could be closed and reopened | **ok on the question asked** -- no 500 in 5 rounds; no voucher posted after the close answered (posted_at never later than the close's reply); each voucher either posted (200) or was refused: 422 "Accounting period ... is closed and cannot accept postings." (2 times), or 409 (see D-CONC-5). A voucher created into the period after the close was refused by name in every round. Each period was reopened afterwards. |

The sign-in used for the close matters: the fixture Accountant gets 403 on
closing a period (`PeriodCloseScope` is not in the Accountant role), so the
close was made by a third Firm-admin session. That is the role design, not a
finding.

## Defect

**D-CONC-5 (Low-Medium, Live).** Posting independent journal vouchers into the
same period at the same time lets only one win; the others get 409 although
nothing they loaded changed. Evidence: with no close at all, three drafts
(different ids, same two accounts, same period) posted by three users at once
gave 1 x 200 and 2 x 409 in 4 of 4 runs on a fresh period ("The request
conflicts with existing data. Please retry.") and, with one voucher already
posted so the ledger balance rows exist, 1-2 x 200 and 1-2 x 409 "This record
changed since you loaded it. Reload and try again." in 4 of 4 runs. Nothing is
lost or doubled, but the first message is the generic integrity-error text and
the second tells the user to reload a record they never edited. Cause is the
stored `ledger_balances` rows (period movement and carry into later periods)
being written without a lock on the account/period balance row; the same
shape as D-CONC-1 (counter rows) before its fix. Fix direction: lock the
balance rows in a fixed order (`with_for_update`, ordered by account id), or
retry once inside `post_entry`. Severity is not High because it never loses
or duplicates a posting and a retry succeeds; a month-end batch of vouchers
posted from several desks will see it.

## Not driven

Last units of one batch, a voucher posted at the instant of a *year* close,
and the 15-minute five-user soak.
