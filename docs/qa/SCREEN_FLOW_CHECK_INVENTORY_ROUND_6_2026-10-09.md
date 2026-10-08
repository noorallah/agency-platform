# Inventory round 6: the screens, clicked against the real server, 2026-10-09

Cases: `SCREEN_TEST_CASES_INVENTORY.md`, sections *Round 5* and *Round 6*
(SC-ST-093 to 099). Flow: `desktop/integration_test/sc_st_test.dart`, parts
`round5` and `round6`, run in the real phase 2 app at **1366x768** on the
fixture firm `T10069CWY-S`, as the firm administrator, against the server on
port 8000 (main as #1376 left it). The HTTP half of the round is
`INVENTORY_API_CHECK_ROUND_6_2026-10-09.md`.

**Outcome: one defect of the screen, D-UI-86 (Low), fixed in this merge;
7 cases, 7 Pass** (SC-ST-099 on its second run, after the case itself was
corrected).

## What was found

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R6-1 | Low | **A products page left while its lists were loading raised an uncaught error**, *A ProductController was used after being disposed*. Nothing was lost and nothing showed on screen; the error stood in the client's log | The flow's log, as the app opened on its last screen (Products) and the flow went straight to Home | `ProductController.bootstrap` and `metadataForCategory` in `desktop/lib/ui/products/product_management_page.dart` | **Fixed** (D-UI-86): neither tells its listeners once the page has gone. `desktop/test/product_controller_definitions_test.dart`; the second run's log has no such line |

## What was clicked

| Case | Result | What the screen said and the server held |
| --- | --- | --- |
| SC-ST-093 | Pass | As round 5: one row, "1 batch near expiry"; no row for a kind the server counts at nought |
| SC-ST-094 | Pass | *Disassemble kits* on a new kit `R5K...`: **Batch for INVSCR-B** shown; empty, refused inside the dialog (*Name the batch it goes back into.*), nothing saved |
| SC-ST-095 | Pass | `INVB1` typed: "Kits disassembled as RPK-2026-2027-000011."; kits 2 to 1; `INVB1` 20 to 21 |
| SC-ST-096 | Pass | *Assemble kits*: no batch box; "Kits assembled as RPK-2026-2027-000012."; `INVB1` 21 to 20 |
| SC-ST-097 | Pass | Broken with the box empty: "Kits disassembled as RPK-2026-2027-000013."; `INVB1` 20 to 21 |
| SC-ST-098 | Pass (both runs) | *Assemble kits* on a kit kept in batches: **Batch number** and **Expiry date** shown. Empty: "R6K... is kept in batches. Name the batch the repacked goods go into: one it already has, or a new number with its dates." inside the dialog, which stayed open; no repack. With `R6B...` and a date a year on: "Kits assembled as RPK-2026-2027-000015."; the kit holds 1 in that batch and in no other row; `INVSCR-N` 106 to 105 |
| SC-ST-099 | Pass (second run) | `INVSCR-N2` has 82 free in the firm; with a reorder level of 87 the server counts 1 *below reorder level* where it counted none, and Home shows "1 below reorder level" with 1 beside it, next to the near-expiry row; with the level taken off the count is nought again |

## What the runs showed besides

- **SC-ST-099 failed on its first run, and the case was wrong, not the
  application.** It set the level five above what MAIN alone held (69); the
  alert is the item's across the firm, and `INVSCR-N2` has more free in the
  second warehouse, so nothing was below its level. The case now adds up
  what is free in every row. The level was put back by the failed run too.
- Each run of part `round6` leaves one kit `R6K...` holding one unit in a
  batch `R6B...` in MAIN and one posted repack; `INVSCR-N` is one lower.
  Part `round5` leaves what round 5's file says, and `INVB1` one higher
  (21 now).
- The sentence of SC-ST-098 calls the kits "the repacked goods": an assembly
  is a repack, and the sentence is the repack's own. Read as it stands.

## Not clicked in this round

- Home's rows for out of stock, over maximum, in transit and count sheets
  with a count above nought (over HTTP in `tc_stock_019.py`,
  `p_alert_windows.py`, `p_alert_ten.py`).
- The batch card with a window other than 30 days; Add Serial past the stock
  held, a batch with no expiry on the batch dialog, a dated movement outside
  an open period on each stock dialog: each is the server's sentence in a
  dialog that already shows server refusals.
- D-UI-84: not met. Still open, still without a stack.
- Left from rounds 2 and 3: the *short* unit ticks of a transfer's receipt,
  the serial pickers as the storekeeper (`qstore`), the challan print with
  serials, Edit of a saved draft transfer.

## The goods-types checks after the round

**35 of 35 clean**, run after the probe and the screen runs.
