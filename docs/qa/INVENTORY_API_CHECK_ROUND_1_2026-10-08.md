# Inventory module, API check, round 1 (2026-10-08)

Method: `.claude/skills/test-module/SKILL.md`. Every case and probe is a kept script under
`docs/qa/checks/inventory/` (`setup.py` writes `.state/inventory.json`; `python docs/qa/checks/run.py inventory`
runs all). Backend at main head `099054e8`, driven over HTTP on a fixture firm. Application code was not changed.

**Tally (second full run, after the fixture was repaired): `34 of 55 checks clean, 21 failing`.**
All 20 case scripts pass except `tc_stock_011`; the 21 failures are the findings below, kept failing as their regression.
"Confirmed" = observed twice (solo run and full run) and the service code read. "Observed" = seen over HTTP only.

## Fixture

| What | Code / account |
| --- | --- |
| Firm used for every write | `T1008FTRV-F` (the goods-type round's generic firm). Books opened by me through `POST /firms/{id}/open-books`. No new firm was made. |
| Accounts on it (password `Fixture@2026pw`) | admin `t1008ftrv.genericadmin@` (FIRM_ADMIN), manager `t1008ftrv.genericmanager@` (FIRM_MANAGER), store `t1008ftrv.invstore@` (INVENTORY_MANAGER), sales `t1008ftrv.invsales@` (SALES_MANAGER), read-only `t1008ftrv.invviewer@` (VIEWER), all `@fixtures.local` |
| "Other firm" for cross-firm ids | TEST02 (`t1008nnr7.t2admin@`), read-only use of its ids |
| Side effect on a second fixture | pharmacy firm `T1008MK9X-F` was given a GST template, head office and books, one ELECTRONICS category/product with 4 serial-less units and one serial (D-STK-19 re-measure) |
| Left behind in the generic firm | negative stock and cost differences from the defect probes (F3, F4), movements dated 2030 and 1999 (F15), a count series in FY 2029-2030; the system reason DAMAGE was switched off by an early probe run and switched on again |

Because of that residue the firm-wide valuation `DIFFERENCE` row is not 0.00 on this firm. Every books check therefore compares
**deltas of the movements it makes**, never the absolute figure.

## Cases

| Case | Result | What was compared |
| --- | --- | --- |
| TC-STOCK-001 | PASS | rows 10/10/0, by-product summary 10, ledger +4 +6 naming each GRN, balances 4 and 10, type filter, valuation 600 |
| TC-STOCK-002 | PASS | 47 / 3 / total 50, TRANSFER_OUT and TRANSFER_IN with the reference, no journal, 999 refused naming availability |
| TC-STOCK-003 | PASS | write-off Dr Inventory adjustment 60 / Cr Inventory 60; hold 2: current 47, available 47, quarantine 2; release back to 49; no journal for quarantine; hold 999 refused |
| TC-STOCK-004 | PASS | count over 2 lines, one counted (49 of 50), variance -1, one ADJUSTMENT, journal Dr 60, uncounted line untouched, posted count not editable or postable twice |
| TC-STOCK-005 | PASS | three batches, 5 dispatched from B2 (earliest unexpired), B1 expired untouched, dashboard counts the expired batch |
| TC-STOCK-006 | PASS | order for 10 with 3 held saves and approves; dispatch 422 "Insufficient available stock for dispatch line."; note stays APPROVED |
| TC-STOCK-007 | PASS (API half) | another firm's warehouse/product/branch id in a filter answers an empty 200 on list, ledger, transactions; the remembered-filter screen behaviour is not API |
| TC-STOCK-008 | PASS | 5 serials AVAILABLE in the receiving warehouse, status filter, detail, warranty dates writable on the serial. Case text wrong, see below |
| TC-STOCK-009 | PASS | TO- numbering, dispatch 30 left / 20 in transit, no journal, books unchanged, challan PDF, receive 18 (3 damaged): 15 sellable, 3 blocked, shortage 120 journalled Dr adjustment, cancel after dispatch returns stock, draft cancel, received cancel refused ("A received transfer is final"), over-free dispatch refused |
| TC-STOCK-010 | PASS | INTERNAL_USE, STAFF, DISPLAY post to Stock used in business / Staff welfare / Samples and display; DAMAGE to Inventory adjustment; own reason with its own account; inactive and unknown reason refused |
| TC-STOCK-011 | **FAIL (F3)** | wastage 1 percent: consumed 600, wastage 6, pack at 14.85 (594), books fall by 6 only; no wastage moves no books; cancel reverses both; "consume 9999 of 40" is accepted |
| TC-STOCK-012 | PASS | assemble 5 (10 DET + 5 OTH, kit at 140 each = 700, books unmoved), disassemble 1, over-assembly refused, kit in kit refused, dispatch of 8 with 4 assembled assembles the other 4 |
| TC-STOCK-013 | PASS | stop-sale batch skipped, returns-due window, expiry = manufacturing + 365, typed expiry stands, FIFO takes the first received, PICK draws nothing silently and a picked batch dispatches. Case text wrong in two places, see below |
| TC-STOCK-014 | PASS | heavy mover class A, undispatched not listed (= C), plan sheet carries exactly the A product, blind sheet hides expected until posted, next due = last counted + 30 |
| TC-STOCK-015 | PASS | files on adjustment, write-off, transfer (readable from both legs), posted count; delete soft and audited on the holder |
| TC-STOCK-016 | PASS | limit 500: 300 posts, 2,040 refused naming the limit, requests move nothing, requester cannot approve, admin approval posts unchanged, rejection keeps its reason, no double approve, bulk approve of two, no limit = direct again |
| TC-STOCK-017 | PASS | incoming = order less receipts (6), identity projected = available + incoming - outgoing holds at product and warehouse after each step. The branch and firm summaries break it (F6) |
| TC-STOCK-018 | PASS (returns half) | rule on: sellable part to quarantine, damaged as before; release to shelf; cancel of a completed return takes it out of quarantine; rule off: straight to shelf. **Not driven:** the lapse itself, see below |
| TC-STOCK-019 | PASS | low / out / over-maximum counts grow by one each and clear with the stock; ageing carries issued last year and turnover 0.33 (5 of 15) |
| TC-STOCK-020 | PASS | labels A4_65, A4_24, ROLL_50X25 and a receipt's labels are PDFs, cancelled receipt refused; Discontinued still sells, refused on a purchase order by name; Not for sale refused on a sales order, still bought |

## Findings

Ids are provisional (F1..). Severity: High = wrong money, stock, tax or data loss.

| Id | Sev | Symptom | Request that shows it (script) | Likely file:line | Basis |
| --- | --- | --- | --- | --- | --- |
| F1 | High | `PUT /inventory/{id}` rewrites the row's branch, warehouse and **product** from the body: 10 units of product A become 10 units of product B (or move warehouse) with no movement, no ledger row, no cost; a second row appears | `PUT /inventory/{row}` with another `product_id` (`p_levels`) | `backend/app/inventory/services/inventory_service.py:820-824` (`update_inventory_record`; its docstring says thresholds and status only) | Confirmed |
| F2 | High | A batch or an AVAILABLE serial number that still holds stock can be deleted (204). The stock row stays, the batch vanishes from the list, the order then refuses "The batch named is not one of this product's batches"; a deleted serial leaves quantity and serial count apart, so a serial dispatch cannot be completed | `DELETE /batch-serial/batches/{id}` and `/serials/{id}` on stocked records (`p_delete_with_stock`) | `backend/app/batch_serial/services/batch_serial_service.py:793-809` (`delete_batch`), `:1495-1503` (`delete_serial`): no stock or usage test | Confirmed |
| F3 | High | A repack consumes more than is held: bulk 40 minus 999 = -959, 1 pack created at the cost of 999 units (59,940); the firm valuation then differs from the Inventory account by 3.00 per such repack. Product forbids negative stock | `POST /inventory/repacks` consume 999 against 10 (`p_negative_stock`, `tc_stock_011`) | `inventory_service.py:2228-2280` (`stage_repack_movement`) and `repacking.py:193-215`: no availability test (kits are protected because `KitService.stage_assembly` checks first) | Confirmed |
| F4 | Medium | A negative adjustment larger than the stock is accepted on a product whose `allow_negative_stock` is false: 10 on hand, `quantity -999` leaves -989 and posts a journal | `POST /inventory/adjustments` (`p_negative_stock`) | `inventory_service.py:2143-2225` (`stage_adjustment_movement`) | Confirmed |
| F5 | Medium | A sales order reserves its whole quantity even when stock is short, so a later order starves an earlier one: 4 held, order A for 3 then order B for 4 reserves 7; A's dispatch is refused "Insufficient available stock for dispatch line." and Available shows -3. Outgoing (case 017) can then never show a shortage | two orders, then dispatch the first (`p_overreserve`) | `inventory_service.py:2993-3070` (`record_sales_order_reservation`, no cap); gate `app/delivery_note/services/delivery_note_service.py:3658` | Confirmed |
| F6 | Medium | `GET /inventory/summary/by-branch` and `/by-firm` return incoming 0, outgoing 0 and **projected 0** whatever the stock and the open orders (projected should equal available + incoming - outgoing) | one open purchase order for 7 (`p_summary_scope_projected`) | `inventory_service.py:415-447` (`stock_by_firm`) and `:449-` (`stock_by_branch`) never call `_with_pipeline` (`:631`) that the product and warehouse rollups use | Confirmed |
| F7 | Medium | A DRAFT opening-stock batch can never be edited: any `PUT` is 409 "The operation violates inventory uniqueness constraints." (old lines deleted and new ones inserted in one flush; the unit of work inserts first) | `PUT /inventory/opening-stock/{id}` quantity 1 to 2 (`p_opening_stock_edit`) | `inventory_service.py:1166-1173` (`update_opening_stock_batch`) | Confirmed |
| F8 | Medium | `POST /inventory/counts` and `/count-plans` accept another firm's warehouse id, another firm's product id on a line, and (counts) a warehouse under a different branch than the one named; the post is refused later for the product, never for the warehouse | `p_cross_firm_ids`, `p_branch_scope` | `backend/app/inventory/services/physical_count_service.py:180` (`create`), `count_planning.py:132` (`create`): no `_validate_references` as the other writes do | Confirmed |
| F9 | Medium | An adjustment reason can be pointed at any ledger account (Inventory, Cash, Payables, Sales). With Inventory: a write-off of 2 lowers the valuation by 120 and the books by 0 | `POST /inventory/adjustment-reasons` with `ledger_account_id` of INVENTORY, then a write-off (`p_reasons`) | `backend/app/inventory/services/adjustment_reasons.py:227-238` (`_assert_account` checks ownership only, not account type) | Confirmed |
| F10 | Medium | A goods receipt accepts a batch whose expiry is before its manufacturing date, and a product that tracks expiry accepts a batch with neither date. The purchase-order line and the batch master do refuse the first | `POST /goods-receipts` mfg +10 days, expiry +5; batch with no dates (`p_batch_dates`) | `backend/app/goods_receipt/services/goods_receipt_service.py:1741-1790` (no check; `purchase_service.py:2893` has it) | Confirmed |
| F11 | Medium | CSV export writes a product name beginning `=` raw: `=1+1 export probe` opens as a formula in a spreadsheet | `GET /inventory/export?search=...` (`p_export`) | `inventory_service.py:5248-5250` (`_csv`) and `:3814-` | Confirmed |
| F12 | Medium | Every export is cut at 5,000 rows without saying so (inventory and ledger, csv and xlsx). A busy firm's stock ledger passes that in weeks | none driven (the fixture holds 1,290 ledger rows) | `inventory_service.py:3820, 3865, 3921, 3965` (`page_size=5000`) | Code read only |
| F13 | Medium | D-STK-19 still stands in a different form: opening stock (form: create then post) for a serial-tracked product is accepted, giving units with no serial number that no dispatch can use (a dispatch needs serial ids). The file import refuses it. The 403 naming SERIAL_NUMBER from the register no longer reproduces: a pharmacy firm records the serial | `d_stk_19` | `inventory_service.py` `_build_opening_stock_lines`; `opening_stock_import.py` module docstring (serial-numbered stock is refused) | Confirmed |
| F14 | Low | A filter value the server cannot read is a 500: `status=` on inventory, batches, serials, lots, opening stock; `transaction_from=` / `transaction_to=` on transactions and ledger | `p_bad_filters` | `app/inventory/api/router.py:207, 661, 717, 786` (model validated by hand in the handler); same pattern in `app/batch_serial/api/router.py` list handlers | Confirmed |
| F15 | Low | If-Match is ignored on `PUT counts/{id}`, `count-plans/{id}`, `adjustment-reasons/{id}`; `PUT stock-transfers/{id}` honours it but a lines-only edit does not move the version, so a stale replay saves | `p_stale_version` | `router.py` (only `:914, :1390, :1922` take `ExpectedVersion`); `stock_transfers.py:241-270` | Confirmed |
| F16 | Low | Movements that post no journal accept any date: a transfer, quarantine hold, transfer document, count or repack dated 2030-01-01 or 1999-01-01 is stored (write-off and adjustment are refused by the period rule) | `p_dates` | `inventory_service.py` `transfer_stock`, `stage_quarantine`; `stock_transfers.py`; `repacking.py`; `physical_count_service.py` | Confirmed |
| F17 | Low | A batch number is accepted on a product that does not track batches (a batch row is created); a blank batch number is accepted on the batch master | `p_tracking`, `p_batch_dates` | `goods_receipt_service.py` batch resolution; `batch_serial_service.py:467` (`create_batch`) | Confirmed |
| F18 | Low | A second write-off with a reference already used is refused in journal words: "A journal entry with reference X already exists." | `p_reference_numbers` | `inventory_service.py` write-off path to `DocumentPostingService` | Confirmed |
| F19 | Low | `incoming_quantity` / `outgoing_quantity` / `projected_quantity` come back as `10.00000000000000` (14 decimals) beside `10.0000` | `p_number_format` | `inventory_service.py:631-643` (`_with_pipeline`), `app/inventory/services/pipeline.py` | Confirmed |
| F20 | Low | D-STK-18 stands: the batch summary card counts an emptied near-expiry batch (card 1, dashboard 0) | `d_stk_18` | `batch_serial_service.py:826-840` (no stock test) | Confirmed |
| F21 | Low | D-STK-20 stands, reproduced without pharmacy data: receipts 7 @ 61.37 and 5 @ 49.99, three dispatches of 2: valuation 339.77, books 339.76. A positive adjustment of 2 at average 60.0276 also credits 120.06 against 120.05 valued | `d_stk_20`, `p_books_agree` (tolerance 0.05 so it does not hide gross errors) | valuation rounds per row, journal per document (see D-PRC-56) | Confirmed |
| F22 | Low | A posted count line shows Expected 50, Counted 49, Variance +9 when 10 were written off between opening and posting (variance is against the live stock, expected is the figure at opening) | observed in a scratch run, not kept | `physical_count_service.py` post | Observed |
| F23 | Low | Sales-return units marked scrap are valued (Dr Inventory for all 6 returned) yet sit in no stock bucket, so they stay in the valuation and cannot be written off. The code says this is deliberate ("the firm owns them for valuation") | observed, not kept | `inventory_service.py:2960-2985` | Observed, by design? |

Outside the module (one line each, not chased): product update (`PUT /products/{id}`) needs the whole form: a body with only code, name
and type is read as "tracking switched off, units cleared" and refused on a stocked product ("base unit, inventory unit, batch tracking ...
cannot be changed"), which looks like the omission-is-an-instruction trap in the repo rules. The SALES_MANAGER role holds no INVENTORY_* code
at all (every inventory read is 403), so check what the order editor's stock panel does for that role.

## Case text wrong

* **TC-STOCK-008**: "Warranty End a year from today" is true only of data seeded by script. A goods receipt carries no warranty dates and a
  product has no warranty period; the dates are entered on the serial (Serial Numbers > edit). Say: "Warranty Start/End are empty until
  somebody enters them on the serial."
* **TC-STOCK-011**: "wastage 1" is **1 percent** of the consumed value (field `wastage_percent`). Say "wastage 1 percent".
* **TC-STOCK-013**: "a batch within the stop-sale days is refused at dispatch": it is *skipped* by the FEFO pick when another batch can cover
  the line, and refused only when it is the only batch. The sentence "Dispatch an order, then set FEFO, PICK and dispatch again" works only
  from the product editor (a save needs the whole form).
* **TC-STOCK-014**: "anything not dispatched C": `GET /inventory/abc-classes` lists dispatched products only; a product not listed is C.
* **TC-STOCK-017**: Outgoing is "approved lines less delivered less reserved". Because an order reserves its full quantity even beyond stock (F5),
  Outgoing is normally 0 and the shortage shows as a negative Available instead.
* **TC-STOCK-018**: the lapse cannot be driven over HTTP: it runs on the server timer from `order_date`. Note which half was driven (returns hold).
* **TC-STOCK-004**: add "if stock moved between opening and posting, Difference is against the live stock, not the Expected column" (F22).
* **TC-STOCK-010**: add that any seeded reason, DAMAGE included, can be switched off, after which a write-off naming it is refused "is not an
  active stock adjustment reason".

## Timings (fixture firm only, read only, three runs each, milliseconds)

| Route | At 230 products / 600 ledger rows | At 425 products / 1,290 ledger rows |
| --- | --- | --- |
| `GET /inventory/reports/stock-statement?from_date=2026-04-01&to_date=today&page_size=100` | 106, 109, 142 | 268, 261, 261 |
| `GET /inventory/reports/stock-valuation?page_size=100` | 87, 95, 89 | 246, 241, 239 |
| `GET /sales-invoices/reports/analysis/invoices?from_date=2026-04-01&to_date=today` | 78, 110, 32 | 31, 25, 28 |

The invoice analysis answered 0 rows: this fixture raised no invoice (the stock chain stops at the delivery note), so its time says nothing
about volume. The two stock reports roughly double when the data does; PERF01 volume was not touched.

## Not driven, and why

* Screens (rule: backend verified, screens not).
* TC-STOCK-007 remembered-filter behaviour and TC-STOCK-018 reservation lapse: UI state and a server timer.
* Storage nodes (bins) on any stock write, lots beyond create/edit/role/ETag, kits with batch- or serial-tracked components.
* Cutover of a financial year, closed accounting periods on stock writes, multi-unit conversions (box/piece), landed cost.
* Volume: the 5,000-row export cut (F12) was read in code, not reproduced.
* Messaging on stock events, loyalty, and anything priced.

## Roles (probe results, all passed)

`p_roles_writes` (26 write endpoints x manager, store, sales, read-only) and `p_roles_reads` (32 reads x 4) compare each answer with the
live role's codes read from `/roles/{id}/permissions`: 403 exactly when the code is not held. Seeded facts worth knowing: INVENTORY_MANAGER
lacks only INVENTORY_MANAGE_SETTINGS (so it cannot set adjustment limits, as intended); VIEWER holds INVENTORY_VIEW, LEDGER_VIEW,
TRANSACTION_VIEW, BATCH_VIEW and SERIAL_VIEW and wrote nothing; SALES_MANAGER holds none.
