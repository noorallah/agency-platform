# Inventory round 12: the screens, clicked against the real server, 2026-10-09

Cases: `SCREEN_TEST_CASES_INVENTORY.md`, sections *Round 5* and *Round 6*
(SC-ST-093 to 099), run again; no new case. Flow:
`desktop/integration_test/sc_st_test.dart`, parts `round5` then `round6`, run
in the real phase 2 app at **1366x768** on the fixture firm `T10069CWY-S`, as
the firm administrator, against the server on port 8000 (main as #1382 left
it, before this round's merge). The HTTP half of the round is
`INVENTORY_API_CHECK_ROUND_12_2026-10-09.md`.

**Outcome: nothing found on screen; 7 cases, 7 Pass, on the first run.** The
client's log of the last run holds no `APPERROR` line. The round's five
defects, D-STK-68 to D-STK-72, are the server's and the merge changes no
screen: each stock dialog already shows a server refusal and stays open on it.

## What was clicked

| Case | Result | What the screen said and the server held |
| --- | --- | --- |
| SC-ST-093 | Pass | One row on Home, "1 batch near expiry"; no row for a kind the server counts at nought |
| SC-ST-094 | Pass | *Disassemble kits* on a new kit: **Batch for INVSCR-B** shown; empty, refused inside the dialog, nothing saved |
| SC-ST-095 | Pass | `INVB1` typed: "Kits disassembled as RPK-2026-2027-000036."; kits 2 to 1; `INVB1` 26 to 27 |
| SC-ST-096 | Pass | *Assemble kits*: no batch box; "Kits assembled as RPK-2026-2027-000037."; `INVB1` 27 to 26 |
| SC-ST-097 | Pass | Broken with the box empty: "Kits disassembled as RPK-2026-2027-000038."; `INVB1` 26 to 27 |
| SC-ST-098 | Pass | *Assemble kits* on a kit kept in batches: **Batch number** and **Expiry date** shown. Empty: refused inside the dialog, which stayed open; no repack. With a batch and a date: assembled, and the kit holds 1 in that batch |
| SC-ST-099 | Pass | `INVSCR-N2` has 82 free in the firm; with a reorder level of 87 Home shows "1 below reorder level" beside the near-expiry row; with the level taken off the count is nought again |

## What the run left

One more kit of each round holding one unit, four posted repacks; `INVSCR-N`
one lower, `INVB1` one higher (27). The reorder level of `INVSCR-N2` was put
back.

## Not clicked in this round

- No owed dialog was added: the round already had findings over HTTP, so
  round 13 follows whatever the screens showed.
- **A service on a stock dialog** (D-STK-71): Adjust Stock, Opening Stock and
  Repacking with a service picked. The refusal is the server's sentence in
  dialogs that already show server refusals; over HTTP in
  `p_level_settings.py`. Whether the product pickers of those dialogs offer a
  service at all was not looked at.
- **Stock levels** on the Inventory row editor and on an opening-stock line
  with the maximum below the minimum (D-STK-72), and an opening-stock
  reference of spaces (D-STK-68): the same, over HTTP.
- Owed from rounds 10 and 11: **Adjustment Approvals** after D-STK-59, the
  **Files** dialog at its tenth file, a date after today on a stock dialog,
  Count Plans with a plan switched off, Adjustment Reasons with a blank name,
  Adjustment Limits with a mistyped role.
- Home's rows for out of stock, over maximum, in transit and count sheets
  with a count above nought (over HTTP in `tc_stock_019.py`,
  `p_alert_windows.py`, `p_alert_ten.py`).
- D-UI-84: not met. Still open, still without a stack.
- Left from rounds 2 and 3: the *short* unit ticks of a transfer's receipt,
  the serial pickers as the storekeeper (`qstore`), the challan print with
  serials, Edit of a saved draft transfer.

## The goods-types checks in the round

**35 of 35 clean** on port 8000 at the start of the round. On the temporary
server running the branch 33 of 35: `tc_mast_020.py` and `tc_mast_022.py`
no longer found the MAIN warehouse on the first fifty of the firm's
warehouses, the probes having made more. Both now search for it by code and
are clean; not the application.
