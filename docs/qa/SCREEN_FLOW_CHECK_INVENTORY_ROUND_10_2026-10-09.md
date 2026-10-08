# Inventory round 10: the screens, clicked against the real server, 2026-10-09

Cases: `SCREEN_TEST_CASES_INVENTORY.md`, sections *Round 5* and *Round 6*
(SC-ST-093 to 099), run again; no new case. Flow:
`desktop/integration_test/sc_st_test.dart`, parts `round5,round6`, run in the
real phase 2 app at **1366x768** on the fixture firm `T10069CWY-S`, as the
firm administrator, against the server on port 8000 (main as #1380 left it).
The HTTP half of the round is `INVENTORY_API_CHECK_ROUND_10_2026-10-09.md`.

**Outcome: nothing found on screen; 7 cases, 7 Pass, on the first run.** The
client's log of the run holds no `APPERROR` line. The round's four defects,
D-STK-59 to D-STK-62, are the server's and the merge changes no screen: the
approvals list reads the same field it read before, and the file dialogs
already show a server refusal.

## What was clicked

| Case | Result | What the screen said and the server held |
| --- | --- | --- |
| SC-ST-093 | Pass | One row on Home, "1 batch near expiry"; no row for a kind the server counts at nought |
| SC-ST-094 | Pass | *Disassemble kits* on a new kit `R5K...`: **Batch for INVSCR-B** shown; empty, refused inside the dialog (*Name the batch it goes back into.*), nothing saved |
| SC-ST-095 | Pass | `INVB1` typed: "Kits disassembled as RPK-2026-2027-000028."; kits 2 to 1; `INVB1` 24 to 25 |
| SC-ST-096 | Pass | *Assemble kits*: no batch box; "Kits assembled as RPK-2026-2027-000029."; `INVB1` 25 to 24 |
| SC-ST-097 | Pass | Broken with the box empty: "Kits disassembled as RPK-2026-2027-000030."; `INVB1` 24 to 25 |
| SC-ST-098 | Pass | *Assemble kits* on a kit kept in batches: **Batch number** and **Expiry date** shown. Empty: refused inside the dialog, which stayed open; no repack. With `R6B...` and a date a year on: "Kits assembled as RPK-2026-2027-000031."; the kit holds 1 in that batch; `INVSCR-N` 102 to 101 |
| SC-ST-099 | Pass | `INVSCR-N2` has 82 free in the firm; with a reorder level of 87 Home shows "1 below reorder level" beside the near-expiry row; with the level taken off the count is nought again |

## What the run left

One kit `R5K...` holding one unit, one kit `R6K...` holding one in a batch
`R6B...`, four posted repacks; `INVSCR-N` one lower (101), `INVB1` one higher
(25). The reorder level of `INVSCR-N2` was put back.

## Not clicked in this round

- No owed dialog was added: the round already had findings over HTTP, so
  round 11 follows whatever the screens showed.
- **Adjustment Approvals** after D-STK-59: a waiting request whose item has
  become dearer now shows its present worth in the list and is
  refused on that figure. Not opened on screen; over HTTP in
  `p_request_lifecycle.py`.
- The **Files** dialog of a movement at its tenth file (D-STK-62): the
  refusal is the server's sentence in a dialog that already shows server
  refusals. Over HTTP in `p_evidence_edges.py`.
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

## The goods-types checks in the round

**35 of 35 clean**, run after the probes, on the server before the merge.
