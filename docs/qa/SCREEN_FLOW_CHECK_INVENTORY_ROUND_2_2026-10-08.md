# Inventory round 2: the screens, clicked against the real server, 2026-10-08

Cases: `SCREEN_TEST_CASES_INVENTORY.md`, section *Round 2* (SC-ST-077 to 087)
and three cases of round 1 clicked again. Flows:
`desktop/integration_test/sc_st_test.dart` (parts `round2` in its pieces
`r2xfer`, `r2doc`, `r2open`, `r2ref`, then `backorder` and `count`) and
`sc_bs_test.dart` (parts `batches`, `lots2`), run in the real phase 2 app at
**1366x768** against the running backend on the fixture firm `T10069CWY-S`, as
the firm administrator. The HTTP half of the round is
`INVENTORY_API_CHECK_ROUND_2_2026-10-08.md`.

**Outcome: 14 cases, 14 Pass. No new defect of the screens or the server; one
Low observation registered (D-STK-50).** No screen overflowed at 1366x768 and
the app reported no error of its own in any run. Nothing under `desktop/lib` or
`backend/` was edited.

## What was clicked

| Case | Result | What the screen said and the server held |
| --- | --- | --- |
| SC-ST-077 | Pass | Heading "Pick the units that are moving - 0 of 2 picked", then "1 of 2 picked"; "Pick one serial number per unit moving: 2 needed, 1 picked."; dialog open, the 2 kept, nothing moved |
| SC-ST-078 | Pass | "Stock transferred."; QW2 two more; units 1 and 2 AVAILABLE in QW2, unit 3 still in MAIN |
| SC-ST-079 | Pass | "0 of 2 picked" to "2 of 2 picked"; "Draft saved."; the draft names units 3 and 4 |
| SC-ST-080 | Pass | "Line 1 (INVSCR-S) sends 2 serial-tracked units but 1 serial number is picked: pick 1 more on the transfer." inside the Dispatch dialog, which stayed open; status Draft |
| SC-ST-081 | Pass | "Transfer dispatched."; status DISPATCHED; units 3 and 4 IN_TRANSIT |
| SC-ST-082 | Pass | "Tick which 1 unit(s) of INVSCR-S - Inv screen INVSCR-S arrived damaged: 0 ticked."; dialog open; still DISPATCHED |
| SC-ST-083 | Pass | "Transfer received."; the details read "Serial numbers, line 1: ...-3, ...-4 (damaged)"; QW2 two more; unit 3 AVAILABLE and unit 4 DAMAGED, both in QW2 |
| SC-ST-084 | Pass | Helper text "2 of 2 entered"; "Opening stock draft saved."; "Opening stock posted."; both units AVAILABLE in MAIN |
| SC-ST-085 | Pass | "Line 1 (R2S...) brings in 3 serial-tracked units but 2 serial numbers are entered: enter 1 more on the opening stock line."; still a Draft; stock 0 |
| SC-ST-086 | Pass | "A write-off with the reference WR... already exists: give this one a reference of its own, or leave the box empty to have it numbered."; dialog open, reference kept, on hand unchanged |
| SC-ST-087 | Pass | The screen asked "No invoice yet ... Dispatch anyway"; the note reads DISPATCHED; the row went from On hand 4, Reserved 10 to On hand 0, Reserved 6, Available -6 |
| SC-ST-038 (again) | Pass | "INVSCR-N - Inv screen INVSCR-N: a count cannot be less than nothing." on the sheet, which stayed open (D-UI-83) |
| SC-BS-008 (again) | Pass | "Selling price 90.00 cannot exceed the MRP 50.00."; dialog open; nothing saved (D-STK-49) |
| SC-BS-018 (again) | Pass | "A lot cannot hold less than nothing."; dialog open; nothing saved (D-UI-83) |

## Seen and written down

- **D-STK-50 (Low, registered).** Add Serial numbers a unit into a warehouse
  without looking at the stock held there. The flow numbers six units before
  each run, so the fixture firm now reads 30 AVAILABLE units of `INVSCR-S` in
  MAIN against 12 held, and the picker offers all of them.
- **Not a defect: a unit named on a draft transfer is still offered to the
  next transfer.** A draft holds nothing, of units as of quantity; the second
  document to dispatch is the one refused.
- **Not a defect: the dispatch of SC-ST-087 raised no toast** that the flow
  caught after *Dispatch anyway*; the list showed the new status. Not chased.

## The flow's own mistakes, corrected

- SC-ST-080 failed in the first run because the list had been read before the
  draft was made over HTTP; the flow now presses Refresh.
- SC-ST-085 first met a different refusal ("already has posted opening stock in
  this warehouse") because SC-ST-084 had just posted the same product; both now
  use a product of the run's own, the refusal first.
- The app ended by itself in four runs (exit 79, no error in its log, 3.3 to
  3.5 GB of memory free), as it did in round 1. The part now also runs in
  pieces, and each piece was run until it finished.

## Not clicked

- The pickers as any user but the firm administrator.
- The unit ticks for a **short** receipt (only damaged was clicked; short is
  covered over HTTP by `d_stk_19.py` and by the widget tests).
- The challan print with its serial numbers, and the Edit of a saved draft.
- SC-BS-002 and 005 failed again in the `batches` part for the reason round 1
  recorded (the flow is not re-runnable on this firm: `INVB2` was deleted by the
  defect of round 1, and the check reads the typed number off the message).

## Records left on T10069CWY-S

Units `R2<stamp>-*` of `INVSCR-S` from six runs (AVAILABLE in MAIN and QW2, two
DAMAGED in QW2), `INVSCR-S` at 12 in each warehouse, transfers
`TO-2026-2027-000005` to `-000016` (received or cancelled; the drafts the ended
runs left were cancelled over HTTP and the one left in transit was received),
a product `R2S<stamp>` per run (the last holds an opening stock posted and one
left in draft), one product `R2B<stamp>` with an order owed six, opening stock
`SN<stamp>` and `SX<stamp>`, write-offs `WR<stamp>`, counts `PC-2026-2027-000004`
to `-000006`.
