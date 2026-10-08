# Inventory round 4: the screens, clicked against the real server, 2026-10-09

Cases: `SCREEN_TEST_CASES_INVENTORY.md`, section *Round 4* (SC-ST-090 to
092). Flow: `desktop/integration_test/sc_st_test.dart`, part `round4`, run in
the real phase 2 app at **1366x768** against the backend restarted on #1374,
on the fixture firm `T10069CWY-S`, as the firm administrator. The HTTP half of
the round is `INVENTORY_API_CHECK_ROUND_4_2026-10-09.md`.

**Outcome: 3 cases, 3 Pass. No defect of the screen.** Only the Repacking
screen was clicked: it is the one screen round 4 gave new boxes. Nothing under
`desktop/lib` was edited.

## What was clicked

| Case | Result | What the screen said and the server held |
| --- | --- | --- |
| SC-ST-090 | Pass | No Batch number box before a product was chosen. With `INVSCR-B` on the produce line: **Batch number** ("One it already has, or a new number") and **Expiry date** ("YYYY-MM-DD, for a new batch") under it, none under the consumed line of `INVSCR-N`. Post with the box empty: "INVSCR-B - Inv screen INVSCR-B is kept in batches. Enter the batch the produced goods go into." inside the dialog, which stayed open; no repack saved; the three batch rows unchanged; no overflow |
| SC-ST-091 | Pass | Batch number `R4NEW`, no expiry: "INVSCR-B tracks expiry, so batch R4NEW needs an expiry date. Enter the expiry date, or the manufacturing date where the product has a shelf life."; the dialog open with `R4NEW` still typed; no repack saved; the batch rows unchanged |
| SC-ST-092 | Pass | Batch number `INVB1`: "Repack posted."; repacks 6 to 7 (`RPK-2026-2027-000007`); `INVSCR-N` 108 to 107; `INVB1` 18 to 19, `INVB2` 20 and `INVB3` 5 unchanged |

## D-STK-55 live

Home's stock alerts list each kind worst first (D-STK-55, #1374): seen live
over HTTP, not on the screen. `tc_stock_019.py` failed on the server before
the restart and passed on the server after it (18 checks, 2026-10-08 20:10
UTC): an item short by more than 100,000 is the first LOW row. The Home tile
itself was not opened in this round.

## What the runs showed besides

- The first run failed SC-ST-092: it named `INVB2`, and the server answered
  that batch INVB2 needs an expiry date. **Not a defect of the round.** On
  this fixture firm the batches `INVB2` and `INVB3` were deleted on 2026-10-08
  by the round 1 screen cases while they held stock, which is D-STK-25 (fixed
  the same day: a batch that holds stock can no longer be deleted). Their
  stock rows remain and still read the old numbers, so to the server `INVB2`
  is a number the product does not have, and a new batch of a dated product
  needs its date. The case now names `INVB1`, a live batch, and passed on the
  second run. The two orphaned rows are left as they are: they are what a
  firm that met D-STK-25 before its fix would hold, and nothing in round 4
  reads them wrongly.
- The app does not close itself when the flow ends; the runner cuts it off
  (as in every earlier round).

## Not clicked in this round

- The kit's Assemble / Disassemble dialog. It has no batch boxes: a kit that
  is itself kept in batches, and a break that must name the batch, can be done
  over HTTP only (`p_kit_break_batch.py`), and the dialog shows the server's
  refusal. Whether that refusal reads well in the dialog was not looked at.
- Home's stock alert tile (worst first) and the batch card with a window other
  than 30 days (D-STK-47): proved by `tc_stock_019.py` and by
  `test_near_expiry_is_one_definition.py`, not on screen.
- Add Serial past the stock held (D-STK-50), a batch with no expiry on the
  batch dialog (D-STK-48), a dated movement outside an open period on each
  stock dialog (D-STK-41): each is the server's sentence in a dialog that
  already shows server refusals; none was clicked.
- D-UI-84 (*Concurrent modification during iteration* while the batch and
  serial screens are clicked): not met in these runs, which did not open those
  screens. Still open, still without a stack.
- Left from rounds 2 and 3 and still not clicked: the *short* unit ticks of a
  transfer's receipt, the serial pickers as the storekeeper (`qstore`), the
  challan print with serial numbers, Edit of a saved draft transfer.

## How to run it again

```bash
# from desktop/, Git Bash, backend running
IT_EMAIL=t10069cwy.tradeadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' \
  IT_PART=round4 LIMIT=200 bash integration_test/run.sh sc_st_test.dart
```

Each run of SC-ST-092 moves one unit from `INVSCR-N` into batch `INVB1`.
