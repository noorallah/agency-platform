# Screen cases, costing by lot (L2): click tests against the real server, 2026-10-16

Flow: `desktop/integration_test/sc_lot_test.dart`. Book: `07_INVENTORY.md`,
TC-LOT-001 to TC-LOT-014 (the screen steps; the HTTP halves are
`docs/qa/checks/lots/`).
Firm **TEST03** (*Test Fixtures Lot Firm*, by lot since 2026-04-01), built by
`scripts/test_fixture.py lot-firm` through `docs/qa/checks/lots/setup.py`,
which also made the Viewer and a firm still on Average (**LTAFEDMW**) for
TC-LOT-001. Users: `t1016gxe3.lotadmin@fixtures.local` (Firm admin),
`t1016gxe3.lotviewer@fixtures.local` (VIEWER, no `PRODUCT_VIEW_COST_PRICE`)
and `ltafedmw.admin@fixtures.local` (Firm admin of the Average firm), password
`Fixture@2026pw`. Window 1600x1000.

Every run makes its own masters over HTTP, named with the minute it started
and the run's user (`0705V` = 07:05, viewer): a supplier *LT supplier*, a
customer *LT buyer*, a batch- and expiry-tracked product **B** and a plain
product **P**, codes `0L<tag>-B` / `0L<tag>-P` so they sort first in the lot
reports, and an approved purchase order for B of 10 at 40 and 5 at 42. Then
over HTTP: 8 of P at 30 with no batch (an unprinted lot), and 5 of B at 44 into
a second `LOTA` agreeing with the first in batch, expiry and MRP (so the
picker has a group), and an approved order for 3 of B and 2 of P at 50 (59
with tax, under the MRP of 60). In the Viewer run the two B lots are received
over HTTP too, since a Viewer receives nothing.

## How to run it

From `desktop/` in Git Bash, one run at a time, each in a brand-new
`TEMP`/`TMP` folder:

```
IT_EMAIL=<suffix>.lotadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1200 bash integration_test/run.sh sc_lot_test.dart
IT_EMAIL=<suffix>.lotviewer@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1200 bash integration_test/run.sh sc_lot_test.dart
IT_PART=average IT_EMAIL=<average firm code>.admin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=900 bash integration_test/run.sh sc_lot_test.dart
```

The admin run takes about four minutes after the build, the Viewer three, the
Average part one. `IT_PART=settings`, `receipt`, `picker`, `reports` or
`trace` runs one part; `average` runs only when named. Five of fourteen runs
died with "did not complete" (`PathNotFoundException ...
flutter_test_listener.*`) or "Unable to start the app on the device"; the same
flow then ran in a new folder.

What the flow does, as the Firm admin: Settings > Stock > **Costing method**
(window), reads it and turns *Allow billing when no lot holds the stock* on and
off; Buy > Goods Receipts > New on the B order, typing accepted quantity,
batch `LOTA` / `LOTB`, the expiry (date picker, six months out) and MRP 60 on
each line, then **Save & complete**; Reports > Financial > *Stock valuation by
lot*, then as on the day before the switch; Sell > Delivery Notes > New on the
order, reading the **Batches** picker of each line; the four lot reports; Stock
> Batches, search `LOTA`, the run's row, Open, **Trace**. Every write is read
back over HTTP. As the Viewer: the same screens, with the delivery note opened
from the list (the admin raises a draft over HTTP). App errors and overflows
are counted the whole time.

## Results

| Case | Step | Firm admin | Viewer | Note |
| --- | --- | --- | --- | --- |
| TC-LOT-002 | 3: Costing method reads By lot, its day, no way back | PASS | PASS | "By lot, since 2026-04-01"; no day box, no *Switch to by lot*; the billing switch matches the server, enabled for the admin, disabled for the Viewer |
| TC-LOT-002 | 3: the billing switch turns and is kept | PASS | — | Server false -> true ("Bills may now go out when no lot holds the stock.") -> false ("A bill now needs a lot that holds the stock.") |
| TC-LOT-003 | 1: a receipt of two batch lines completed on the screen | PASS | — | GRN-TEST03-HO-2026-2027-000234 "completed. The stock is posted."; server: two lots, LOTA 10 at 40 and LOTB 5 at 42, expiry 2027-04-16 as typed, received today |
| TC-LOT-003 | 3: Stock valuation by lot, a row per lot at its own cost | PASS | PASS | Admin rows LOTA 10 / 40.00 / 400.00, LOTB 5 / 42.00 / 210.00, LOTA 5 / 44.00 / 220.00, each with its reference, received and expiry date and MRP value, as the server; Viewer: same rows, Cost rate and Value at cost read **—** (server sends null) |
| TC-LOT-012 | 2: as on the day before the switch the lot report is empty | PASS | PASS | As on 2026-03-31: *Nothing to report*; server 0 rows |
| TC-LOT-004 | 2: the picker groups the lots that agree | PASS | — | Two rows for three lots: *LOTA, 2 lots, exp 16-04-2027, can take 15, MRP 60.00*, cost 40.00-44.00; *LOTB*, 42.00; as the server's two pick groups |
| TC-LOT-004 | 4: the unprinted lot shows a dash and its received date | PASS | — | Label "-", *received 16-10-2026 · no expiry · can take 8*; our `LOT-...` reference not shown |
| TC-LOT-013 | 1: the batch picker, without the cost permission | — | PASS | The Viewer is offered no New, and Open on a draft note is the read-only view, which has no picker (see findings); availability asked as the Viewer: 3 lots, pick groups sent, **no unit cost** |
| TC-LOT-012/013 | Stock valuation by lot opens | PASS | PASS | Grid; server 100 rows (page 1); Viewer sent no rate/value |
| TC-LOT-012/013 | Margin by lot opens | PASS | PASS | Grid; server 65 rows; Viewer sent no cost/margin |
| TC-LOT-012 | Stock ageing opens | PASS | PASS | Grid; server 100 rows. **The Viewer is sent `rate` and `value`** (see findings) |
| TC-LOT-012/013 | Bills waiting for their cost opens | PASS | PASS | Grid; server 5 rows; *Cost used* column for the admin only |
| TC-LOT-014 | 1-2: Batches > LOTA > Trace | PASS | PASS | Reference, printed batch LOTA, received 16-10-2026; events as the server, the goods receipt first (admin: receipt and the delivery note that took 3, with a Cost column and unit cost 40.00); Viewer: no unit cost, no Cost column |
| TC-LOT-001 | 1: Average firm, the preview | PASS (Average firm admin) | — | "Average cost"; day 2026-10-16; 1 item, 1 lot, 10, 600.00 as the server; no refusal, *Switch to by lot* enabled (not pressed) |
| TC-LOT-001 | 2: a day after today | PASS | — | "The switch-over day 2026-10-17 is after today (2026-10-16)."; Switch off; firm still Average |
| TC-LOT-001 | 2: a day before the latest movement | PASS | — | "Stock last moved on 2026-10-16, so the switch-over day cannot be earlier ..."; Switch off; firm still Average |

Last full runs: Firm admin passed 14, failed 0, not run 4; Viewer passed 10,
failed 0, not run 4; Average firm admin passed 4, failed 0, not run 2. No app
error and no overflow in any run.

Not driven on the screen:

- **TC-LOT-001** step 3 (no product below zero on the new firm) and step 4
  (HTTP); the switch itself was not pressed, since it is one way.
- **TC-LOT-002** steps 1-2 and 4-6: the fixture firm is already by lot; the
  switch is one way and driven over HTTP.
- **TC-LOT-003** step 2 (the plain receipt is made over HTTP) and step 4
  (cancel after a sale, HTTP only).
- **TC-LOT-004** step 1 (the third-cost receipt is made over HTTP) and step 3
  (typing over a group is the picker's own widget test).
- **TC-LOT-005 to TC-LOT-011**: dispatch, returns, write-offs, settlement and
  supplier bills are HTTP cases.
- **TC-LOT-012** steps 1 (the plain *Stock valuation* totals), 4-5 (the run
  raises no bill).
- **TC-LOT-013** step 1 for the Viewer's *Trace* bill amount: the run's lot has
  no bill on it.

## Findings

1. **Screen, fixed:** the Batches, Lots and Serial Numbers search boxes said
   *Search batch number, product…* (lot / serial likewise), but the server
   matches the number alone, so searching the product's code or name gave *No
   search results*. The hints now read *Search batch number…* /
   *Search lot number…* / *Search serial number…*
   (`desktop/lib/ui/inventory/batch_management_page.dart`); guarded by
   `desktop/test/inventory_sections_test.dart` ("the ... search box promises
   only the number", which fails on the old hints).
2. **Server, not fixed:** *Stock ageing* (`GET
   /api/v1/inventory/reports/stock-ageing`) and *Stock valuation* (`GET
   /api/v1/inventory/reports/stock-valuation`) send `rate` and `value` to a
   VIEWER without `PRODUCT_VIEW_COST_PRICE` (e.g. 0L0621A-B: 20 at 41.50 =
   830.00), while *Stock valuation by lot*, *Margin by lot*, *Bills waiting for
   their cost*, the picker and the Trace all leave cost out for the same user.
3. **By design, recorded:** the batch picker is in the delivery note editor,
   which a Viewer is never offered (no New; Open is the read-only view), so the
   TC-LOT-013 step 1 picker can only be clicked by a user who may make a note
   but lacks the cost permission. The server's half was checked as the Viewer.
4. **Transient:** two opens of *Stock valuation by lot* (one admin, one
   Viewer) answered *Cannot reach the API server.*, and the same request over
   HTTP took 0.1 s; a reopen worked. It is the desktop's `IOException` on a
   dropped connection, the drop `harness.dart` already retries for its own
   reads; not lot-specific.
