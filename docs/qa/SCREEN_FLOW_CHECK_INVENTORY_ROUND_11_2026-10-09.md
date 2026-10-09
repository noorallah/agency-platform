# Inventory round 11: the screens, clicked against the real server, 2026-10-09

Cases: `SCREEN_TEST_CASES_INVENTORY.md`, sections *Round 5* and *Round 6*
(SC-ST-093 to 099), run again; no new case. Flow:
`desktop/integration_test/sc_st_test.dart`, parts `round5,round6`, run in the
real phase 2 app at **1366x768** on the fixture firm `T10069CWY-S`, as the
firm administrator, against the server on port 8000 (main as #1381 left it,
before this round's merge). The HTTP half of the round is
`INVENTORY_API_CHECK_ROUND_11_2026-10-09.md`.

**Outcome: nothing found on screen; 7 cases, 7 Pass, on the first run.** The
client's log of the run holds no `APPERROR` line. The round's five defects,
D-STK-63 to D-STK-67, are the server's and the merge changes no screen: each
stock dialog and the three settings dialogs already show a server refusal and
stay open on it.

## What was clicked

| Case | Result | What the screen said and the server held |
| --- | --- | --- |
| SC-ST-093 | Pass | One row on Home, "1 batch near expiry"; no row for a kind the server counts at nought |
| SC-ST-094 | Pass | *Disassemble kits* on a new kit `R5K...`: **Batch for INVSCR-B** shown; empty, refused inside the dialog (*Name the batch it goes back into.*), nothing saved |
| SC-ST-095 | Pass | `INVB1` typed: "Kits disassembled as RPK-2026-2027-000032."; kits 2 to 1; `INVB1` 25 to 26 |
| SC-ST-096 | Pass | *Assemble kits*: no batch box; "Kits assembled as RPK-2026-2027-000033."; `INVB1` 26 to 25 |
| SC-ST-097 | Pass | Broken with the box empty: "Kits disassembled as RPK-2026-2027-000034."; `INVB1` 25 to 26 |
| SC-ST-098 | Pass | *Assemble kits* on a kit kept in batches: **Batch number** and **Expiry date** shown. Empty: refused inside the dialog, which stayed open; no repack. With `R6B...` and a date a year on: "Kits assembled as RPK-2026-2027-000035."; the kit holds 1 in that batch; `INVSCR-N` 101 to 100 |
| SC-ST-099 | Pass | `INVSCR-N2` has 82 free in the firm; with a reorder level of 87 Home shows "1 below reorder level" beside the near-expiry row; with the level taken off the count is nought again |

## What the run left

One kit `R5K...` holding one unit, one kit `R6K...` holding one in a batch
`R6B...`, four posted repacks; `INVSCR-N` one lower (100), `INVB1` one higher
(26). The reorder level of `INVSCR-N2` was put back.

## Not clicked in this round

- No owed dialog was added: the round already had findings over HTTP, so
  round 12 follows whatever the screens showed.
- **A date after today on a stock dialog** (D-STK-66): Write off, Adjust,
  Transfer, a new count sheet and opening stock with tomorrow picked. The
  refusal is the server's sentence in dialogs that already show server
  refusals; over HTTP in `p_dated_ahead.py`. Whether a date picker offers
  tomorrow at all was not looked at.
- **Count plans** with a plan switched off (D-STK-64) and **Adjustment
  Reasons** with a blank name (D-STK-63): the same, over HTTP in
  `p_count_plan_edges.py` and `p_reason_limit_settings.py`.
- **Adjustment Limits** (D-STK-67): the dialog offers the roles in a picker,
  or takes a typed code from a user who may not list roles; a mistyped code
  is now refused in the dialog by the server's sentence. Not opened.
- **Adjustment Approvals** after D-STK-59 and the **Files** dialog at its
  tenth file (D-STK-62), owed from round 10.
- Home's rows for out of stock, over maximum, in transit and count sheets
  with a count above nought (over HTTP in `tc_stock_019.py`,
  `p_alert_windows.py`, `p_alert_ten.py`).
- D-UI-84: not met. Still open, still without a stack.
- Left from rounds 2 and 3: the *short* unit ticks of a transfer's receipt,
  the serial pickers as the storekeeper (`qstore`), the challan print with
  serials, Edit of a saved draft transfer.

## The goods-types checks in the round

**35 of 35 clean**, on the temporary server running the branch.
