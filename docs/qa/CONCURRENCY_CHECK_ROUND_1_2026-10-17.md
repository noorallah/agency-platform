# Concurrency check, round 1 -- 2026-10-17

Item 30m, part 1 (`unattended/AWAY_WORK_LIST.md`). Several TEST01 users fire
the same action at the **running** backend (http://localhost:8000) at the same
moment: calls on threads released together through a barrier, 3 to 5 per
scenario. The database-level guards are proved by the integration suite; this
proves them through HTTP with real sessions racing.

- Script: `docs/qa/checks/concurrency/run_concurrency.py` (`--only a` .. `d`
  runs one scenario alone; each makes its own item, customer and documents
  under a fresh tag). Accounts: `docs/qa/checks/concurrency/setup.py`, here
  `--adopt t1016zzxa t1016pty0 t1016kzsl` -- TEST01's Firm admin (two
  sessions), Seller, Sales manager and Accountant. No demo firm touched.
- Asserted: exactly one winner where only one may win; every loser a 4xx with
  a message, never a 500 or a dropped connection; no caller refused for who
  they are (a 403 would mean the race was never run); no number repeated.

## Results

| Scenario | What raced | Result |
| --- | --- | --- |
| a | 5 counter bills drafted at once by 4 users (one series), then 5 approved at once | **FAIL** -- D-CONC-1. Drafts: 1 x 201, 4 x 409 "This record changed since you loaded it". After topping up one at a time, the 5 approvals at once all answered 200; numbers SI-26-27-000074..000078, none repeated, none skipped. No 500. |
| b | 4 receipts of 100.00 from 3 users against one 118.00 bill | ok -- 1 x 201, 3 x 409; the bill owes 18.00 afterwards. No 500. Loser wording: D-CONC-2. |
| c | 1 order approved by 3 users at once | ok -- 1 x 200, 2 x 409; 7 pieces reserved once, not per approval. |
| d | 1 customer saved by 3 users with the same `If-Match` | ok -- 1 x 200, 2 x 409 "This record changed since you loaded it"; version moved 1 -> 2 once. |

Money check afterwards: `scripts/check_money_consistency.py TEST01` --
**"VERDICT: the books agree"**.

## Defects

**D-CONC-1 (Medium, Live).** Documents of one kind cannot be *created* at the
same moment by different people. Four bills posted together -- different users,
and in a probe also different customers and different items -- gave one 201
and three or four 409s "This record changed since you loaded it. Reload and
try again." Sales orders behave the same (4 at once: 1 x 201, 3 x 409). Nobody
loaded anything; the only row the creates share is the document's number
series. Nothing wrong is written (no repeated number, books agree), but on a
busy counter three of four desks are refused a new bill and told to reload a
record they never opened. Probable cause, from the code and not yet proved:
the series counter (`DocumentNumberSequence`, read `with_for_update` in
`document_framework_service.py`) or its numbering rule is already in the
session's identity map when the locking read returns, so the waiter keeps the
stale `version` and its UPDATE loses the version check (StaleDataError -> 409).
A locking read with `execution_options(populate_existing=True)`, as
`sales_invoice_service.py` and `counter_shifts` already do, would make the
second create wait and then take the next number. Not fixed here (report
only).

**D-CONC-2 (Low, Live).** The receipts refused in scenario b say "This record
changed since you loaded it. Reload and try again." The outcome is right --
one receipt, bill owes 18.00 -- but the person typed a new receipt and loaded
nothing. A clerk recording it one at a time is told "has 18.00 outstanding,
so 100.00 cannot be allocated"; the racing loser should hear the same.

## Not driven (part 2)

Dispatching the last units of one batch, cancelling the same order twice,
editing one product with one ETag, redeeming the same loyalty points, posting
vouchers into a period being closed, and the 15-minute five-user soak.
