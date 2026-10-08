# Inventory, round 3 over HTTP -- 2026-10-08

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`). The round began with the 56 checks
of round 2 as its regression (51 clean, the five open rows failing, as
expected), then probed what the earlier rounds had left unverified. Six new
checks are kept. The screens of this round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_3_2026-10-08.md`.

## What the round found

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R3-1 | Medium | A kit with a batch-tracked part could not be assembled: ten of the part on the shelf in two batches, five needed, *this location has free 0, so 5 cannot be repacked*. A delivery note for more kits than were assembled failed the same way. A repack consuming a batch-tracked product with no batch named was read against the stock row with no batch | probe of kits with tracked parts | `RepackService.stage_post` | **Fixed, D-STK-51, #1371** |
| R3-2 | Medium | A repack, and a kit, moved serial-tracked stock under its units: one of three consumed left two on hand and three units AVAILABLE; one produced added stock with no unit | the same probe | `RepackService.stage_post`, `KitService.replace` | **Fixed, D-STK-52, #1371** (refused in words; naming units there is backlog 90 row 7) |
| R3-3 | Low | A repack that produces a batch-tracked product with no batch named puts it on the stock row with no batch; breaking a kit does the same to its parts | the same probe | `RepackService.stage_post` | Open, D-STK-53: needs a batch box on the Repacking screen first |
| R3-4 | Low | Four in a bin and an order for ten: a note line naming no bin is refused *Insufficient available stock for dispatch line.*; the note naming the bin ships the four | probe of bins | the dispatch gate reads one storage node | Open, D-STK-54: a rule for firms that run bins |

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| A back order beside batches | `p_backorder_tracked.py` | Four in batch A and an order for ten; five arrive in batch B and a later order takes three of them. Each order holds real stock where it found it and the back order sits on the row with no batch. The earlier order ships its four of A and the two free of B; the later one ships its three; nothing goes below zero |
| A back order beside a batch a person chose | the same | A later order naming the batch cannot take the goods behind an earlier one; the earlier order ships them, naming the batch |
| A back order beside serial units | the same | A later order naming a unit is refused and both units stay AVAILABLE; the earlier order ships the two and they read SOLD |
| A closed month | `p_closed_period.py` | With the first month of the year closed, a write-off, an adjustment and the posting of opening stock dated in it are refused (*No open accounting period covers ...*) and no stock moves. The month is opened again by the check |
| Round 2's refusals as a storekeeper | `p_roles_round_2.py` | The second write-off under a used reference is 409 and the batch priced above its MRP is 422 for the inventory manager, as for the administrator |
| Kits with a batch-tracked part, after the fix | `p_kit_tracked_parts.py` | Assembled earliest expiry first across two batches; a shortage names the part; a note for three kits assembles the two it lacks; a serial-tracked product is refused on both sides of a repack and as a kit's part, with stock and units unchanged |

## The run after #1371

**55 of 62 checks clean.** The seven that fail are the rows still open, and
stay as the regression for their fixes:

| Check | Row | Why it is still open |
| --- | --- | --- |
| `d_stk_20` | D-STK-20 | a paisa between the stock account and the valuation at an average with more than two decimals |
| `p_batch_dates` | D-STK-48 | whether a date is compulsory is the goods type's to say (backlog 89) |
| `p_dates` | D-STK-41 | the rule for a movement that posts no journal is not decided |
| `p_stale_version` | D-STK-42 | two people fill one count sheet, left on purpose |
| `p_tracking` | D-STK-43 | the receipt takes a batch on purpose |
| `p_repack_batchless` | D-STK-53 | new this round; needs the screen's batch box |
| `p_bins` | D-STK-54 | new this round; one assertion, the rule is not decided |

In the first run of the round one check ended on a dropped connection
(`ConnectionResetError`) rather than on an assertion; it passed in the run
after the restart and is not counted as a finding.

## Not verified in this round

- The cost of the back-order look-through on a product with many holds at
  PERF01's volume (not timed).
- A back order with stock spread over several bins, and a kit whose parts are
  in a bin.
- Breaking a kit whose part is batch-tracked (the parts land on the row with
  no batch: D-STK-53).
- The stop-selling window on a part going into a kit: reasoned from the
  allocator the repack now shares with the dispatch, and unit-tested for an
  expired batch only.

## Round 3 is not a clean round

It fixed two Medium rows, so by the rule of the pass a round 4 follows: the
kept checks first, then probes around the two fixes.
