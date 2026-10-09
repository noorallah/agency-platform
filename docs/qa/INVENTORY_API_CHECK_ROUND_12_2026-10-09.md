# Inventory, round 12 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the server as #1382 left
it. Round 11 found D-STK-63 to D-STK-67, so it was not a clean round; this one
ran the 84 kept checks first, then two new probes where no round had looked:
every text the inventory requests ask for, sent as spaces and as a number
(the two shapes round 11 met), and stock levels as settings (what they accept
by each way they can be written, who may write them, a figure too large for
its column, a row that was removed). The screens of the round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_12_2026-10-09.md`.

## What the round found

**The 84 kept checks: nothing. 84 of 84 clean on the first run**, and the
goods-types checks 35 of 35.

**The new probes found five defects: D-STK-71 (Medium) and D-STK-68, 69, 70,
72 (Low), all inventory**, fixed in the same merge, and one in buying that is
logged open (D-BUY-74, Medium). So round 12 is **not** a clean round and round
13 follows.

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R12-1 | Low | **An opening-stock reference of only spaces was saved empty.** Four spaces passed `min_length=2`, the service trimmed them, and the document was kept under an empty reference; the next sent the same way was refused as its duplicate. | `p_blank_text.py` | `OpeningStockBatchWrite`, `OpeningStockImportRequest` | **Fixed** (D-STK-68): trimmed first, two characters asked for, 422 |
| R12-2 | Low | **A figure too large for its column was answered as an outage.** A level, an opening quantity or an opening cost of eighteen digits answered **503** "The database is temporarily unavailable."; a quantity and a cost that overflow only when multiplied answered **500**. | `p_level_settings.py` | `max_digits=18` with no bound on the whole part; `database_error_handler` | **Fixed** (D-STK-69): each figure stops at what its column holds (422 naming the field); a value the database refuses is a 422 for every module |
| R12-3 | Low | **A removed stock row could still have its levels written.** `PUT /inventory/{id}` on a deleted row answered 200 and changed it. | `p_level_settings.py` | `update_inventory_record` read removed rows | **Fixed** (D-STK-70): 404 |
| R12-4 | Medium | **Inventory's own writes brought a service into stock.** A product of type SERVICE took a hand-made row, an adjustment of +5 and opening stock of 3, and then held 8 units, valued. A repack could produce one. | `p_level_settings.py`, then by hand | none of the four asked the product's type | **Fixed** (D-STK-71): refused by name, 422; an adjustment downwards is still taken |
| R12-5 | Low | **An opening-stock line took levels the stock row refuses.** Minimum 9 with maximum 3, and reorder 9 with maximum 3, were saved on a line. | `p_level_settings.py` | `OpeningStockLineWrite` had no check | **Fixed** (D-STK-72): one check for both |
| R12-6 | Medium | **A goods receipt of a service puts it in stock.** Order, approve and receive 2 of a service: the warehouse holds 2. | by hand, on the branch server | buying never asks `stockless` | **Open** (D-BUY-74): the purchase chain has to leave the stock half out, which is buying's change |

**Seen before and after.** On port 8000 `p_blank_text.py` failed on the
opening reference and `p_level_settings.py` on seven of its checks. Both pass
whole on a temporary server running the branch (port 8011, stopped
afterwards): 32 and 56 checks, and the whole folder **86 of 86** there.

**Medium for R12-4:** the stock and the journal it posts agree, so no report
is out; but the valuation then carries a service as goods, and nothing on
screen says a service does not belong there. **Low for the rest:** R12-1,
R12-2 and R12-3 need a caller of the API or a figure nobody types, and
R12-5 writes levels that only make the reorder alerts odd.

## Not a defect

- **A movement's reference of spaces** (write-off, adjustment, quarantine,
  transfer): taken as nothing typed and numbered from its series, exactly as
  one left out (D-QA-16). Driven in `p_blank_text.py`.
- **A batch number of spaces on an opening line**: no batch at all; a product
  that must have one is still refused at posting.
- **A reason of spaces** on cancelling a transfer document, reversing a repack
  and rejecting a request: each was already refused by its service, 422.
- **Text sent as a number** to any of these: 422 from the schema. The one
  `mode="before"` validator in the module is the one round 11 fixed.
- **A save that names one level** clears the others: `PUT` replaces the row's
  levels, and the editor sends all four.

## Decided by me

- **A service is never held as stock**, the rule selling already follows
  (SG-3, decided there as ERPNext treats a non-stock item). Closed at
  inventory's own ways in: a stock row by hand, an adjustment upwards
  (posted, requested, or from a count sheet), opening stock, the produce side
  of a repack. **Not** closed at the common point every movement passes,
  because a goods receipt of a service goes through it and refusing there
  would stop a firm receiving a purchase order it was allowed to raise:
  that is D-BUY-74, for buying's pass. A transfer or write-off of a service
  needs stock that cannot now arrive, so neither was changed.
- **Taking a service out of stock is allowed**: a firm that already holds
  units of one (by a receipt, or from before this round) removes them with
  an adjustment downwards or a write-off.
- **The largest stock figure is 99,999,999,999,999** (and a unit cost
  999,999,999,999), the whole part of what the columns hold; decimals past
  the column's places are still rounded, as before.
- **A value the database refuses is the request's fault** (422), for every
  module, not only inventory: a retry of the same figures cannot succeed, so
  503 was the wrong thing to tell any caller. A lost connection, a timeout
  and a missing table are still 503.
- **Minimum and reorder level are not compared.** The row's own check never
  did (a reorder level below the minimum is how some firms run), and the
  opening line now follows the row.

## What the round left on the fixture firm

One opening-stock draft with an **empty reference** (made on the old server
by the probe that found R12-1); a service `S...` holding 8 units and another
holding 2 from a goods receipt (the probes of R12-4 and R12-6, on the old and
the branch server); about ten warehouses and twenty products of the probes'
own, a few drafts and small movements on them. All harmless; the two service
holdings can be taken out with an adjustment downwards.

## Also changed

`docs/qa/checks/goods_types/tc_mast_020.py` and `tc_mast_022.py` looked for
the MAIN warehouse on the first fifty of the firm's warehouses and stopped
finding it once the inventory probes had made more than fifty (33 of 35 on
the second run of the round). They now search for it by code. Not the
application.

## Not driven

- The CSV and XLSX opening-stock imports with a reference of spaces (the form
  field goes through the same schema; the JSON import was driven).
- A count sheet that counts a service upwards (it posts through the
  adjustment that is refused; unit-tested through the adjustment only).
- Any other module's figures at eighteen digits: the 422 for a value the
  database refuses covers them, but no route outside inventory was sent one.
- The integration suite (PostgreSQL) was not run; the 503 and the 422 were
  both seen over HTTP on PostgreSQL.
