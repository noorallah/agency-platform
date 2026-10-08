# Inventory round 3: the screens, clicked against the real server, 2026-10-08

Cases: `SCREEN_TEST_CASES_INVENTORY.md`, section *Round 3* (SC-ST-088 and
089). Flow: `desktop/integration_test/sc_st_test.dart`, part `round3`, run in
the real phase 2 app at **1366x768** against the backend restarted on #1371,
on the fixture firm `T10069CWY-S`, as the firm administrator. The HTTP half of
the round is `INVENTORY_API_CHECK_ROUND_3_2026-10-08.md`.

**Outcome: 2 cases, 2 Pass. No defect of the screen.** Only the Repacking
screen was clicked, because it is the one screen the round's fix reaches.
Nothing under `desktop/lib` was edited.

## What was clicked

| Case | Result | What the screen said and the server held |
| --- | --- | --- |
| SC-ST-088 | Pass | "INVSCR-S is tracked by serial number, and a repack moves a quantity without naming units. Move the units as themselves: a transfer, a sale or a write-off names each one." inside the New repack dialog, which stayed open with its lines; no repack saved; INVSCR-S 12 before and after |
| SC-ST-089 | Pass | "Repack posted."; one more repack; of the three batches of INVSCR-B the one expiring first lost the unit (INVB1 19 to 18), the others unchanged |

## What the runs showed besides

- The first run failed SC-ST-088 before it began: the press on **New repack**
  straight after the list opened was lost and no dialog came. The flow now
  lets the list settle first; the second run passed both. This is the flow's
  timing, not the screen's: a person does not press within the same frame.
- The first run of all signed in as the default user, who has no menu on this
  firm: the part needs `IT_EMAIL` / `IT_PASSWORD` of the fixture's
  administrator, as every part of this file does.

## Not clicked in this round

- The kit's own screens (components, assemble, break): the refusals reach them
  as the same server message, proved over HTTP only
  (`p_kit_tracked_parts.py`).
- Left from round 2 and still not clicked: the *short* unit ticks of a
  transfer's receipt, the serial pickers as the storekeeper (`qstore`), the
  challan print with serial numbers, Edit of a saved draft transfer.
