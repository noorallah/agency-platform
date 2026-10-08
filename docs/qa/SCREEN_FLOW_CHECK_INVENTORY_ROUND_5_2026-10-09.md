# Inventory round 5: the screens, clicked against the real server, 2026-10-09

Cases: `SCREEN_TEST_CASES_INVENTORY.md`, section *Round 5* (SC-ST-093 to
097). Flow: `desktop/integration_test/sc_st_test.dart`, part `round5`, run in
the real phase 2 app at **1366x768** on the fixture firm `T10069CWY-S`, as
the firm administrator. The HTTP half of the round is
`INVENTORY_API_CHECK_ROUND_5_2026-10-09.md`.

**Outcome: one defect of the screen, D-UI-85 (Low), fixed in this merge;
then 5 cases, 5 Pass.** The cases were clicked in the app built from the
round's branch against a server running the round's branch on port 8011 (the
same stores as the server on 8000), because the fix adds one field to the kit
component list.

## What was found

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R5-1 | Low | **The kit dialog could not name a batch the server asks for.** A kit brought in as opening stock, or bought ready made, was never assembled in the warehouse, so nothing says which batch its batch-tracked part came from; the server refuses the break with *Name the batch it goes back into*, and the *Disassemble kits* dialog had no box to name it in. A kit that is itself kept in batches could not be assembled on screen for the same reason. Both worked over HTTP only (`p_kit_break_batch.py`) | reading the dialog before clicking it: round 4 left it as *not looked at* | `KitStockDialog` in `desktop/lib/ui/products/kit_components_section.dart` | **Fixed, D-UI-85**: *Disassemble kits* shows **Batch for** each part kept in batches (blank leaves it to the batch the last assembly there took it from); *Assemble kits* shows **Batch number** and **Expiry date** for a kit that is itself kept in batches; a plain kit sees no new box. The component list says which parts are kept in batches (`track_batch`) |

## What was clicked

| Case | Result | What the screen said and the server held |
| --- | --- | --- |
| SC-ST-093 | Pass | Home's TO DO: the firm had one batch near expiry and nothing else to report. One stock row, "1 batch near expiry" with 1 beside it; no row for out of stock, below reorder level, over maximum, in transit or count sheets, each of which the server counted at nought; no overflow. **Only the near-expiry row was seen with a count**: this firm had no other alert at the time |
| SC-ST-094 | Pass | *Disassemble kits* on a kit of one `INVSCR-B`, two brought in as opening stock: the dialog shows **Batch for INVSCR-B - Inv screen INVSCR-B** ("Blank: the batch the last assembly here took it from") and no box for the kit's own batch. With the box empty: "INVSCR-B - Inv screen INVSCR-B is kept in batches, and no assembly of R5K0WB6E in this warehouse says which batch it came from. Name the batch it goes back into." inside the dialog, which stayed open; no repack saved; kits 2, the batch rows unchanged; no overflow |
| SC-ST-095 | Pass | `INVB1` typed in the box: "Kits disassembled as RPK-2026-2027-000008."; kits 2 to 1; `INVB1` 19 to 20, the other rows unchanged |
| SC-ST-096 | Pass | *Assemble kits*: no batch box; "Kits assembled as RPK-2026-2027-000009."; kits 1 to 2; `INVB1` 20 to 19, no row below nought, no row without a batch |
| SC-ST-097 | Pass | *Disassemble kits* with the box empty, now that an assembly here says where the part came from: "Kits disassembled as RPK-2026-2027-000010."; kits 2 to 1; `INVB1` 19 to 20 |

Widget tests of the dialog (`desktop/test/kits_test.dart`, 14 pass) carry
what was not clicked: the **Batch number** and **Expiry date** boxes of a kit
that is itself kept in batches, the date refused unless it reads YYYY-MM-DD,
and that a break with every box empty sends no `part_batches` at all.

## What the runs showed besides

- The flow passed on its first run; nothing was changed in it afterwards.
- Each run of the part leaves one kit `R5K...` holding one unit in MAIN and
  three posted repacks; `INVB1` ends where it began.
- The app does not close itself when the flow ends; the runner cuts it off
  (as in every earlier round).

## Not clicked in this round

- Assembling a kit that is itself kept in batches: no such kit is on the
  fixture firm. The boxes are in the widget tests; the server's half is in
  `test_repack_names_the_batch_produced.py`.
- Home's rows for out of stock, below reorder level, over maximum, in transit
  and count sheets with a count above nought. Home shows the counts only, not
  the worst rows, so *worst first* (D-STK-55) has no screen to be seen on; it
  is proved over HTTP (`tc_stock_019.py`, `p_alert_ten.py`).
- The batch card with a window other than 30 days (D-STK-47): over HTTP in
  `p_alert_windows.py`.
- Add Serial past the stock held (D-STK-50), a batch with no expiry on the
  batch dialog (D-STK-48), a dated movement outside an open period on each
  stock dialog (D-STK-41): each is the server's sentence in a dialog that
  already shows server refusals.
- D-UI-84: not met in these runs, which did not open the batch and serial
  screens. Still open, still without a stack.
- Left from rounds 2 and 3: the *short* unit ticks of a transfer's receipt,
  the serial pickers as the storekeeper (`qstore`), the challan print with
  serials, Edit of a saved draft transfer.
