# Module test: Masters (item 35) -- 2026-10-17

Status: **part (a) API done, parts (b) UI and (c) money on screen NOT done; module not yet clean.**

## (a) API -- round 2 (39 kept checks, `python docs/qa/checks/run.py masters`)

- First run: 38 of 39. `tc_mast_015` failed: a blank customer code was refused
  "The next 50 numbers of the series CUSTOMER_CODE_DEFAULT are all in use".
- Cause (**D-CONC-2**, High): #1670 re-reads the locked counter with
  `populate_existing`; a request session does not autoflush, so the increment made
  while stepping over a taken number was discarded and the same number was offered
  fifty times. Any firm with one typed code ahead of its counter could not save a
  customer, supplier or product with a blank code. Documents hit the same path.
- Fix #1706 (`reserve_number` flushes first); request-shaped test
  `test_stepping_over_a_taken_code_works_in_a_request_session` fails without it.
- After the fix and a backend restart: **39 of 39 clean**.

## Still to do for this module

(b) click every Masters screen as Admin and one limited role at 800x600 and full
size (known open: D-UI-114 delivery note unit); (c) compare Masters-fed reports
with `check_money_consistency.py`; repeat until a round finds nothing new.
