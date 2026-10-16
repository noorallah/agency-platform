# Screen cases, lot margins (L3): click tests against the real server, 2026-10-16

Flow: `desktop/integration_test/sc_mrg_test.dart`. Book: `07_INVENTORY.md`,
TC-LOT-015 to TC-LOT-022 (the screen steps; the HTTP halves are
`docs/qa/checks/lots/tc_lot_015.py` .. `tc_lot_022.py`).
Firm **TEST03** (*Test Fixtures Lot Firm*, by lot), the `lot-firm` fixture
reused as it stood. Users: `t1016gxe3.lotadmin@fixtures.local` (Firm admin)
and `t1016gxe3.lotviewer@fixtures.local` (VIEWER, no
`PRODUCT_VIEW_COST_PRICE`, no `BATCH_UPDATE`), password `Fixture@2026pw`.
Window 1600x1000.

Every run makes its own masters over HTTP, as the admin, **before the app
starts** (so the screens read them at sign-in), named with the minute and the
user (`1022A` = 10:22, admin):

- a goods type `GM<tag>` with retail 25 / wholesale 12.5 and a category on it
  (`0<n> margins`, sorts first in the product form);
- three batch-tracked products with margins 25 / 12.5 and a selling price of
  **70** (not a lot price, so a line priced from the product shows):
  **MA** `0M<tag>-A` (the receipt), **MC** `0M<tag>-C` with two lots received
  over HTTP, C1 at 80 (PTR 100.00, PTS 90.00) and C2 at 80 with retail 40
  (PTR 112.00, PTS 90.00), and **MD** `0M<tag>-D` with one lot D1 at 80;
- customers *LM retailer* (trade class RETAILER) and *LM stockist*
  (STOCKIST), a supplier;
- for MD: an approved order of 2 at 100, its delivery note dispatched, and a
  **draft bill** from the note; a second **draft order** of 2 at 100;
- an approved purchase order of four lines of 10 MA at 80, and one of a
  single line for the refusals.

In the Viewer run the four MA lines are received over HTTP.

## How to run it

From `desktop/` in Git Bash, one run at a time, each in a brand-new
`TEMP`/`TMP` folder:

```
IT_EMAIL=t1016gxe3.lotadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1500 bash integration_test/run.sh sc_mrg_test.dart
IT_EMAIL=t1016gxe3.lotviewer@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1500 bash integration_test/run.sh sc_mrg_test.dart
```

`IT_PART=product`, `receipt`, `lot`, `order`, `bill` or `counter` (comma
separated) runs those parts; the masters are made every time. A whole admin
run takes about five minutes after the build. Five of eleven runs died with
"did not complete" (`PathNotFoundException ... flutter_test_listener.*`) or
"Unable to start the app on the device"; the parts were then run on their own
in new folders. **One such cut-off landed inside the counter part and left
TEST03 billing directly** (order and note stages off, default branch and
warehouse set) until it was put back by hand from the audit trail's
`before_data` (all three stages on, both defaults null). The flow now puts the
stages back as soon as the last counter step has read the screen, as well as
in its `finally`.

What the flow does, as the Firm admin: Masters > Products > New, the margins
category, a brand, retail typed 30, Save, then again with -1; Buy > Goods
Receipts > New on the four-line order, typing accepted 10 and a batch on each
line and in the side panel MRP 130 / retail 40 (line 2), PTR 104 (line 3),
PTR 104 **then** retail 40 (line 4), **Save receipt** (the MRP warning keeps it
open), each line's saved figures read, then **Save & complete**; a second
receipt refused twice; Stock > Batches, the lot `A0<tag>`, Open, Edit, retail
price 108, then 85; Sell > Sales Orders > New for the retailer and the
stockist with MC, the **Price level** box switched each way; the draft order
and draft bill opened for their cost and margin, the order's quantity changed
unsaved; with the order and note stages off over HTTP, Sell > Sales Invoices >
New (the counter) for the retailer, MC, quantity 15, saved as a draft, and
again with a rate of 105 typed. As the Viewer: the lot page, the draft order
and the draft bill. Every value on screen is set beside what the server
returned; app errors and overflows are counted the whole time.

## Results

| Case | Step | Firm admin | Viewer | Screen vs server |
| --- | --- | --- | --- | --- |
| TC-LOT-015 | 1: a product in the type's category | PASS | — | Boxes Retail margin % "25.0000", Wholesale "12.5000"; the type 25 / 12.5 |
| TC-LOT-015 | 2: retail 30 typed, saved | PASS | — | "Product created."; server retail 30.0000, wholesale 12.5000, category the type's |
| TC-LOT-015 | 4: a margin of -1 | PASS | — | Refused, editor open, nothing saved: "The request validation failed. \| retail_margin_percent: Input should be greater than or equal to 0" (see findings) |
| TC-LOT-016 | 1: margins blank | PASS | — | Saved line on screen PTR 100.00, PTS 90.00, margins 25% / 12.5%; server 100.00 / 90.00, 25 / 12.5 |
| TC-LOT-016 | 2: MRP 130, retail 40 | PASS | — | Screen 112.00 / 90.00, 40% / 12.5%; server the same |
| TC-LOT-016 | 3: completed, each lot | PASS | — | "... completed. The stock is posted."; lots A0..A3 hold 100/90, 112/90, 104/90, 104/90 with margins 25, 40, 30, 30 / 12.5 |
| TC-LOT-017 | 1: PTR 104 typed, margin blank | PASS | — | Screen 104.00, margin 30%; server 104.00, 30.0000 |
| TC-LOT-017 | 2: PTR 104 then retail 40 typed | PASS after fix | — | Before the fix the margin box **emptied the typed price**: saved PTR 112.00, margin 40 (D-UI-109). After: PTR box keeps 104, saved 104.00 / 30%, server the same |
| TC-LOT-018 | 1: the MRP warning | PASS | — | Banner "Line 2: Retail price (PTR) 112.00 is 132.16 with tax, above the MRP 130.00; 110.16 before tax sits at the MRP." and the same beside the line, word for word the server's `mrp_warning`; no other line warned; the window stayed open |
| TC-LOT-018 | 2: above the MRP before tax | PASS | — | "Line 1: PTR 112.00 cannot exceed the MRP 100.00."; no receipt on the server |
| TC-LOT-018 | 3: PTS above PTR | PASS | — | "Line 1: PTS 112.00 cannot exceed the PTR 88.00: a stockist buys at or below the price to a retailer."; no receipt |
| TC-LOT-019 | 1: the lot page | PASS | PASS | Retail price (PTR) 100.00, margin 25.0000, Wholesale price (PTS) 90.00, margin 12.5000; server the same |
| TC-LOT-019 | 2: retail 108.00 | PASS | — | Saved; page reads 108.00 / 35.0000, PTS 90.00 unchanged; server 108.00 / 35.0000 / 90.00 |
| TC-LOT-019 | 3: retail 85.00 | PASS | — | Form stays open: "PTS 90.00 cannot exceed the PTR 85.00: ..."; server still 108.00 |
| TC-LOT-019 | 4: without BATCH_UPDATE | — | PASS | No Edit on the lot; `PUT /batch-serial/batches/{id}` as the Viewer 403 |
| TC-LOT-020 | 1: a retailer | PASS after fix | — | Helper "Usual for this customer: Retail", line 100.00; server 100.00 at Retail (BATCH_PTR). Before the fix the line takes the product's price (D-UI-110) |
| TC-LOT-020 | 2: switched to Wholesale | PASS after fix | — | Line 90.00; server 90.00 (BATCH_PTS). Failed before the fix (D-UI-110) |
| TC-LOT-020 | 3: a stockist | PASS | — | Helper "Usual for this customer: Wholesale", line 90.00; server 90.00 at Wholesale |
| TC-LOT-020 | 4: switched to Retail | PASS | — | Line 100.00; server 100.00 |
| TC-LOT-021 | 1: the draft order | PASS after fix | — | Cost "160.00 est.", Margin "40.00 · 25.0%", strip "Cost 160.00 · Margin 40.00 (25.0%)"; server 160 (estimate), 40, 25.00 %. Before the fix opening it overflowed the line by 15 px (D-UI-111) |
| TC-LOT-021 | 2: quantity changed unsaved | PASS | — | Quantity 3: the line's cells empty, strip "... · as last saved" |
| TC-LOT-021 | 1: the draft bill | PASS | — | Cost "160.00" (no est., dispatched), Margin "40.00 · 25.0%", strip as above; server gross 200, cost 160, margin 40, 25.00 %, totals 160 / 40 |
| TC-LOT-021 | 3: without the cost permission | — | PASS | Order and bill opened with Open: no Cost or Margin header, no cost cells, no strip; server sends `cost_amount`, `margin_amount`, `cost_total` null |
| TC-LOT-022 | 1-2: 15 over two lots | PASS | — | Line split into 10 at 100.00 and 5 at 112.00, note "Line 1 split into 2 lines: its lots sell at 2 prices on this bill."; server availability C1 fefo 10 at 100.00, C2 fefo 5 at 112.00 |
| TC-LOT-022 | the split bill saved as a draft | PASS | — | "Invoice created as a draft."; server lines 10 at 100.0 and 5 at 112.0; the draft cancelled afterwards |
| TC-LOT-022 | 4: rate 105 typed | PASS | — | Both parts 105 |

Last runs: Firm admin passed 25, failed 0, not run 4 (in three part runs:
product/receipt/lot, order/bill, counter, after the fixes); Viewer passed 4,
failed 0, not run 4. No app error and no overflow after the fixes.

## Defects

| Id | Severity | Screen | What | Status | Guard |
| --- | --- | --- | --- | --- | --- |
| D-UI-109 | Medium | Goods receipt, by lot, side panel | Typing a retail (or wholesale) margin after typing the price **emptied the typed price**, so the lot was priced from the margin (112.00) instead of the price typed (104.00), against "a typed price wins over its margin". Only a price carried in from a saved draft should be cleared. | Fixed: `ptrTyped` / `ptsTyped` on the draft line; the margin clears only a carried-in price | `goods_receipt_lot_margins_test.dart`: *by lot: a price typed, then a margin, keeps the typed price (D-UI-109)* |
| D-UI-110 | High | Sales order and counter bill, a firm by lot | The price asked for a line (`GET /price-levels/unit-prices`) carried no `branch_id` / `warehouse_id`, so the server fell back to the product's selling price (`source: PRODUCT`) for every level: asked by hand for the run's MC (selling 100), Retail and Wholesale both answered 100.00, where with the two ids they answer 100.00 (BATCH_PTR) and 90.00 (BATCH_PTS). The line therefore showed the product's price whatever the level, and the order saved at it. Found when TC-LOT-020 step 2 disagreed with the server; the flow's products now sell at 70 so the two cannot coincide. | Fixed: `ApiClient.unitPrices` takes `branchId` / `warehouseId`; the order passes its own, the counter bill the firm's default branch and warehouse | `price_level_on_the_bill_test.dart`: *... the price is asked from the order branch and warehouse ... (D-UI-110)* and *a counter line is priced from the default branch and warehouse (D-UI-110)* |
| D-UI-111 | Low | Sales order, a saved batch-tracked line | The product cell stacks the product, the stock note and the Batch choice in a 52-px row: "A RenderFlex overflowed by 15 pixels on the bottom" (`sales_order_editor_phase2.dart`, the product Column) on opening the draft order. | Fixed: a batch-tracked line is 70 px high | `sales_order_editor_test.dart`: *a saved batch-tracked line fits its product, stock note and batch choice (D-UI-111)* |

Observation, not registered: the product form's refusal of a margin of -1
is the server's raw validation sentence, naming the field by its API name
(`retail_margin_percent`) rather than *Retail margin %*. The case asks only
that the field be named.

No server defect found: every server figure matched the book.

## Not clicked

- TC-LOT-015 step 3 (the goods type changed afterwards): HTTP, `tc_lot_015.py`.
- TC-LOT-016/017 step 3 "open each lot" on the Batches page for every lot:
  read over HTTP after completion; the page itself is clicked in TC-LOT-019
  for one lot.
- TC-LOT-020 step 5 (renaming and deleting Retail in *Price levels*): HTTP,
  `tc_lot_020.py`.
- TC-LOT-021 step 4 (print and PDF): the printing round.
- TC-LOT-021 on an **approved** bill: only the draft bill was opened.
- TC-LOT-022 step 1 choosing both lots in the picker by hand: the line was
  split from the earliest-expiry shares the picker read; step 3 (the bare line
  refused) is HTTP, `tc_lot_022.py`.
- Margins on the goods type screen itself and the customer's trade-class
  words on the customer form.
