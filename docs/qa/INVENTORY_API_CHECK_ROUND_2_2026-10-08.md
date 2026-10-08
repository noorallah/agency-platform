# Inventory, round 2 over HTTP -- 2026-10-08

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the backend restarted on
`main` after #1366 and again after #1368. The screens of this round are not in
this file: they have not been clicked yet.

## What the round changed

| Unit | PR | What |
| --- | --- | --- |
| (a) | #1366, #1367 | Serial numbers follow a transfer; opening stock types its units (D-STK-40) |
| (b) | #1368 | An order owed more than is held ships what is on the shelf (D-STK-39); D-STK-44, D-STK-49, D-UI-83 |

## One finding of this round

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R2-1 | Medium | D-STK-39 was wider than registered: with four held, ONE order for ten could not ship the four (*Insufficient available stock for dispatch line.*). No second order was needed; the order's own back order stood in its way | `p_backorder_ships.py`, written before the fix | the dispatch gate of `delivery_note_service.py` | Fixed with D-STK-39 in #1368 |

## The run after #1368

**51 of 56 checks clean.** `p_overreserve`, `p_backorder_ships` and
`p_reference_numbers` pass now. The five that fail are the rows still open, and
stay as the regression for their fixes:

| Check | Row | Why it is still open |
| --- | --- | --- |
| `d_stk_20` | D-STK-20 | a paisa between the stock account and the valuation at an average with more than two decimals |
| `p_batch_dates` | D-STK-48 | whether a date is compulsory is the goods type's to say (backlog 89) |
| `p_dates` | D-STK-41 | the rule for a movement that posts no journal is not decided: a draft dated ahead is how some firms plan |
| `p_stale_version` | D-STK-42 | two people fill one count sheet, left on purpose |
| `p_tracking` | D-STK-43 | the receipt takes a batch on purpose: goods that have arrived have to be receivable |

## Not verified in this round

- Nothing was clicked on screen: the serial pickers of unit (a), the count
  sheet's and the lot form's new refusals (widget tests only).
- The batch case of D-STK-39 over HTTP (a later order holding real stock on a
  second batch): unit-reasoned, not driven.
- A dispatch of a line whose batches a person chose, or of serial units, beside
  a back order: those paths do not use the allocator and were not driven.
- D-STK-49 and the write-off reference over HTTP by a role other than the
  administrator.
