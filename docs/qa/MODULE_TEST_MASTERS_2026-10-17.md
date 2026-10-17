# Module test: Masters (item 35) -- 2026-10-17

Status: **CLEAN 2026-10-17: (a) API, (b) screen clicks (D-MST-1 fixed; MST-VN-013 and the VIEWER round pass, #1714), (c) money check done. One Low item stays open (below).**

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

## (c) Money check -- 2026-10-17

`check_money_consistency.py T1016VSH1-S`: **the books agree.** Masters (products,
suppliers, places) post nothing themselves; the money they feed (customer and
supplier ledgers, stock valuation) is exercised in Buying, Inventory and Selling,
where it is compared on screen. Not compared on screen here: the fixture firm
holds no Masters-driven balances, so a screen comparison would be vacuous.

## Still open (Low)

Platform-admin toolbar 14px overflow at ~700px wide: unconfirmed (runs were 1600x1000 only; 800x600 not rerun for it). Everything else in Masters is closed. Next module: Buying.
