# Reports API check, round 1 (2026-10-16)

Driven over HTTP against the running backend with the kept scripts in
`docs/qa/checks/reports/` (`python docs/qa/checks/run.py reports`). Set-up is
`reports/setup.py`, which copies the TEST01 accounts of the masters state
(`.state/masters.json`, not committed) into `.state/reports.json`; no fixture is
run. `_rep.py` reads the report list from
`desktop/lib/ui/reports/report_catalog.dart` itself (106 reports), so the check
cannot drift from what the screen offers. The range is 2025-04-01 to 2026-12-31,
because TEST01 holds 2026-27 trading only.

Result: **3 of 4 scripts clean**; `tc_rep_003` fails on purpose for D-RPT-23.

## Checks

| Check | What | Result |
| --- | --- | --- |
| tc_rep_001 | Every catalogue report read once as the firm administrator: 200, `success`, under 3 s | 106 of 106 clean, none slow (after two parameters added to the table: `financial_year_id` for the IT block schedule, `product_id` for the rate trend) |
| tc_rep_003 | A Seller is refused every finance report with 403, never 500; a range ending before it starts is refused | 403 on every finance report, no 500 anywhere; **72 dated reports answer 200 with an empty list for an inverted range** (D-RPT-23) |
| tc_rep_004 | D-FIN-35: orders booked (`analysis?basis=ordered`) against the order register over the same range | Before the fix both came to 43,070.00 over 95 orders; after it (live, #1608) orders booked reads 25,134.00 over 33, the 62 orders the counter bills raised for themselves left out. The check asserts booked < register; the exact rule is pinned by the unit test |
| tc_rep_005 | D-FIN-36: `POST /report-layouts` saves by name | 200 on both saves, the second keeps the first's id and the new settings; delete 204 |

A footing check (total = sum of the column) was written and dropped: 104 of the
106 reports answer a bare list with no totals object, so it checked nothing.

## Findings

- **D-RPT-23** (Low, open): `GET <report>?from_date=2026-12-31&to_date=2025-04-01`
  answers 200 with an empty list on 72 dated reports (quotations, sales orders,
  delivery notes, purchases, goods receipts, returns, invoices, credit notes,
  receipts, inventory, day book, cash book, bank book, TDS). Sales analysis
  already refuses it (*The period must not run backwards.*). One shared range
  check would answer 422 for all of them; for reports round 2.
- **D-FIN-35** (fixed): orders booked counted the order a counter bill raises for
  itself when the firm types no order stage. Such an order
  (`raised_by_sales_invoice_id` set) is now left out.
- **D-FIN-36** (not a defect): the POST is a save-by-name upsert; 200 is the
  answer for a save that may replace, as for a PUT.

## Timings on PERF01

Not taken. `scripts/time_routes.py --firm-code PERF01` was refused sign-in
(*401 Invalid email or password.* for the default `perf01.admin@agency.local`):
the PERF01 account is not known on this machine. Away-list item 22 takes it up.

## Screen

No screen code changed. The sales analysis screen's *Orders booked* figures
change for a firm that bills at the counter; not clicked, because the click-flow
fixture firm no longer signs in (away-list item 17).
