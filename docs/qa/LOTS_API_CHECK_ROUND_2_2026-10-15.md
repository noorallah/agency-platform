# Lots (costing by lot) -- API check, round 2, 2026-10-15

Main at `dcc77770` (#1550, the round 1 fixes), backend restarted, TEST03.

`python docs/qa/checks/run.py lots`: **21 of 21 checks clean** (TC-LOT-001..014
and seven probes), after one fix to the checks themselves.

- `tc_lot_012.py` and `p_books_agree.py` read the stock valuation as one page of
  100 rows; TEST03 had grown to 110 rows with the checks' own records, so the
  TOTAL, BOOKS and DIFFERENCE rows were on page 2. Both now page through the
  whole report with `all_rows`. A check bug, not a server one.
- The five round 1 findings (D-BUY-76, D-SELL-100, D-STK-73, D-STK-74,
  D-STK-75) each re-drove clean on the live server.

**Nothing new in this module, and no High elsewhere: the API layer of lots is
closed.** The screen layer was not run: there is no `integration_test` flow for
the lot screens yet (picker groups, the dash for an unprinted lot, the Trace
page, *Bills waiting for their cost*, the switch-over setting). Lots is
**backend verified, screens not**.
