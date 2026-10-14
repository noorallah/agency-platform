# Costing by lot: API check round 1, 2026-10-15

Driven against the running backend at http://127.0.0.1:8000 with the kept scripts in `docs/qa/checks/lots/`
(`python docs/qa/checks/run.py lots`). API half only; screen-only steps are listed at the end.
Fixture: `test_fixture.py lot-firm` (TEST03, by lot since 2026-04-01) and `platform-admin`, both run by `setup.py`.
TC-LOT-001 uses a firm of its own still on Average (made through the API, once, re-made automatically if a run
finds it switched); TC-LOT-002 makes a fresh firm every run (provision takes about a minute). Nothing touches TEST01/TEST02.

Tally of the last run: **16 of 21 checks clean, 5 failing** (14 case checks + 7 probes).

## Per case

| Case | Result | Figures |
| --- | --- | --- |
| TC-LOT-001 preview and refusals | pass | Average shown; preview of today lists +1 item, +10 units, +300.00 value, no refusal; a day after today and a day before the latest movement refused in the preview and by the switch (422); item below zero named in the refusal and the switch refused; INVENTORY_MANAGER gets 403 on preview and switch; nothing changed. |
| TC-LOT-002 one-way switch | pass (expectation corrected, see N1) | Switch from today: By lot, switched_on = today, billing-without-stock off. LOTA 10 and LOTB 6 become lots at the item's average 41.50 (not 40 / 44); unbatched item = one lot of 10 at 31.20 (source CARRIED_FORWARD). Per-item values, the Inventory account (BOOKS) and the journal count are identical before and after (no journal). Second switch refused; stock movements dated the day before the switch refused ("no stock movement may be dated before that day"). |
| TC-LOT-003 receipt makes lots | **fail** (F1) | Two lots from two lines (10 @ 40 LOTA, 5 @ 42 LOTB) each with own batch, expiry, MRP 150, cost and LOT-... reference; source = the receipt number and date (trail). Untracked 8 @ 30 = one lot with a LOT reference and no printed batch. Untouched receipt cancels and its lot goes; receipt whose lot was sold from is refused, **but the message names the wrong lot (F1)**. |
| TC-LOT-004 picker | pass (API half) | Two LOTA lots (10 @ 40, 5 @ 44) share one `pick_group`, LOTB (other expiry) its own; nearest expiry first; quantity 12 fills 10 then 2; untracked lot has `has_printed_batch=false`, `received_on`, and the LOT reference sent separately; user without the cost permission gets no `unit_cost`. See N3 for over-ask. |
| TC-LOT-005 dispatch FEFO and cost | **fail** (F2) | 4 sold with no batch chosen: LOTA 10 -> 6, LOTB untouched; note line records LOTA 4; margin-by-lot shows LOTA 4 units cost 160.00 (not the 41 average); a lot taken to zero leaves the lot report. Bill line `cost_amount` is null (F2). |
| TC-LOT-006 two lines, two lots | **fail** (F2) | Margin by lot: LOTA 2 / sales 200 / cost 80 / margin 120; LOTB 2 / 200 / 84 / 116 (correct). Bill lines' `cost_amount` null (F2). |
| TC-LOT-007 sales return | pass | Bill of 3 LOTA + 2 LOTB; return of 4 -> LOTB +2 (to 10), LOTA +2 (to 9), each lot's unit cost unchanged (40 / 42); batch NOSUCH refused ("did not leave on the delivery"); cancel of the completed return puts lots back to 7 / 8; return of 100 refused. |
| TC-LOT-008 write-off / transfer / adjust | pass | Write-off 2 no lot: from LOTA at 40; transfer 3: from LOTA, lands in the second warehouse at 40, value 120; write-off 12 refused "LOTA 5, LOTB 10"; adjust +4 at 45.00 = new lot, source ADJUSTMENT; cost on a named lot refused. |
| TC-LOT-009 never below zero | pass | With allow-billing off, for a product that forbids and one that allows negative stock: adjust -9, purchase return 9, dispatch 9 each refused; stock stays 8. |
| TC-LOT-010 billing without stock | pass | Dispatch of 10 over 8 refused with `details.confirm = BILL_WITHOUT_STOCK`; confirmed (`?bill_without_stock=true`) takes 8 from the lot and 2 owed at 30.00; lot-shortfalls lists 2 / 2 / 30.00 with warehouse, note and confirmer; receipt of 10 @ 35 empties the report, leaves 8, and journal `<GRN>-LS` posts 10.00 (2 x (35 - 30)). Financial-year close not driven (N2). |
| TC-LOT-011 supplier bill at another rate | pass | 10 @ 40, 3 sold; bill @ 44: lot 7 units rate 44 value 308, journal puts 28.00 to the lot and 12.00 to variance; cancel returns lot to rate 40 (value 280); bill @ 38: rate 38 value 266. |
| TC-LOT-012 reports | pass | Lot rows add up to the item (18 units, 740.00) and to the valuation; Inventory account difference 0; a day before the switch: lot report empty; ageing puts 8 units in 91-180 days (LOTA received 100 days ago) and 10 in 0-30; margin by lot counts sold less returned (2 units, 200 / 80 / 120); a draft bill is not counted, an approved one is, once. |
| TC-LOT-013 cost hidden | pass | As the Viewer role (reads everything, no PRODUCT_VIEW_COST_PRICE): lots, margin, shortfalls, picker and trail all answer 200 with every rate, value, cost, margin, margin_percent, unit_cost and trail `cost_amount` null (quantities, dates and references stay); the Firm admin sees every one. |
| TC-LOT-014 trail | pass | Arrival first (receipt, +10, supplier); dispatch -3; approved bill at 0 (a draft is not listed); return +1; supplier bill 0 plus its COST_CORRECTION; write-off -1 with its own number and date; no reservation or release listed; events sum to the 7 held; unit cost 41 after the bill; unknown id answers 404. |

## Findings

### F1 (Medium): cancelling a receipt is refused because of a reservation, and the message names a lot that did not move

- Request: receive LOTA (expires +200 d) and LOTB (+180 d) on one receipt, sell 1 picking LOTA (the order's approval reserves LOTB by earliest expiry), then `POST /api/v1/goods-receipts/{id}/cancel`.
- Expected (TC-LOT-003 step 4): refused naming the lot that moved (LOTA).
- Got: 422 "... goods of its lot LOT-...(LOTB) have moved since they arrived (SO-...)". The lot named is the one the order merely reserved.
- Worse, probe `p_cancel_after_reserve_released`: receive 6, approve a sales order for 2, **cancel the order**, cancel the receipt: expected 200 (nothing was sold), got the same 422 naming the order. Any order that has ever reserved from a lot (and released it) makes the receipt uncancellable; the only way back is a purchase return.
- Cause: the "has the lot moved" query counts every `InventoryTransaction` on the lot except the receipt's own and its QC holds, so the reserve and unreserve rows of a sales order count. `app/goods_receipt/services/goods_receipt_service.py:2421-2443` (filter at line 2427; the reference is picked at 2434-2436 from the first such row, not the lot actually sold from). Should exclude RESERVE/UNRESERVE (reservation) movements, as the trail already does (TC-LOT-014).

### F2 (Medium): the bill line's cost is never published

- Request: `GET /api/v1/sales-invoices/{id}` (also the create and approve answers) for a bill off a dispatched note, as the Firm admin.
- Expected (TC-LOT-005 step 2, TC-LOT-006 step 2): line `cost_amount` = that lot's cost (4 x 40.00 = 160; 80 and 84 on two lines).
- Got: `cost_amount: null` on every line. The stored figure is right (margin-by-lot reports 160 / 80 / 84, and the trail's SALES_INVOICE event shows it), so only the API answer drops it.
- Cause: `_line_response` builds `SalesInvoiceLineResponse` field by field and omits `cost_amount` (`app/sales_invoice/services/sales_invoice_service.py:6649-6708`; field declared at `app/sales_invoice/schemas/sales_invoice.py:537`). When fixed it must be hidden without `PRODUCT_VIEW_COST_PRICE`, like the other cost fields.

### F3 (Low): the day the switch suggests is refused for any firm that already trades this year

- Request: `GET /api/v1/inventory/lot-settings/switch-preview` with no `on` (probe `p_suggested_day`; also seen in TC-LOT-002).
- Expected: the suggested day (first day of the financial year, 2026-04-01) is usable, or the suggestion moves to the earliest permitted day.
- Got: `suggested_on = 2026-04-01` with refusal "Stock last moved on 2026-10-15, so the switch-over day cannot be earlier". The screen's default therefore always starts in a refusal for any real firm; the user must pick today (as TC-LOT-001 step 1 says). `app/inventory/services/lot_switch_over.py:253-270` (suggestion) against `:300` (refusal). Judged by what Tally/Marg would do: default to the last movement day or today.

### Notes (not counted as failures)

- N1. TC-LOT-002 (4) says each batch becomes a lot; under Average the batches carry no cost of their own, so both lots carry the item's average (41.50 for 10 @ 40 + 6 @ 44), which keeps the totals exactly as before. The check expects that; the case text should say "at the item's average".
- N2. TC-LOT-010 step 6 (closing the financial year while a bill waits) was not driven: a successful close of TEST03's year would be hard to undo.
- N3. TC-LOT-004 (3): the API caps the picker's split (`fefo`) at what the lots hold (an over-ask of 100 allots 25). "The rest goes on the last lot so it still shows red" must therefore be done by the screen; not driven.
- N4. Cosmetic: `pick_group` embeds the MRP in scientific notation (`LOTB|2027-04-13|1.5E+2|||`, `app/batch_serial/services/batch_serial_service.py:2112`); the trail's SALES_INVOICE `cost_amount` is `"200.000000000000000000000000"` (unrounded).
- N5. A dispatched delivery note cannot be cancelled ("can no longer be cancelled"); the way back is a sales return (TC-LOT-007). A draft return that fails at approve/complete stays a draft and keeps counting against what can be returned until cancelled (my helpers cancel it).
- N6. Role mapping used for TC-LOT-013: the `VIEWER` role (reads everything, no cost permission). `INVENTORY_MANAGER` is refused 403 on margin-by-lot (no report permission), which is by design.

## Not driven

- Screens: the batch picker's dash and red over-ask, the settings screen's switch button and one-way warning, printed challan and bill (batch, expiry, MRP, never the LOT reference), the Trace page layout, the read-only Margin / Bills-waiting pages.
- Closing a financial year (N2).
- Side effects left behind: TEST03 now holds many `*-<tag>` products, customers and suppliers made by the checks; two firms `LT...` made for TC-LOT-001/002 (one new firm per TC-LOT-002 run).

## Files

`docs/qa/checks/lots/`: `setup.py`, `_lot.py` (helpers), `tc_lot_001.py` to `tc_lot_014.py`, probes `p_suggested_day`, `p_dispatch_beyond_a_lot`, `p_purchase_return_beyond_stock`, `p_cancel_after_reserve_released`, `p_books_agree`, `p_write_off_named_lot`, `p_transfer_named_lot`. State: `docs/qa/checks/.state/lots.json` (not committed).
