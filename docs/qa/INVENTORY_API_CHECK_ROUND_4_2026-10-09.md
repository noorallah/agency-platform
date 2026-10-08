# Inventory, round 4 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`). Round 4 first built the rules the
earlier rounds had left open (#1373: D-STK-41, 42, 43, 45, 46, 47, 48, 50, 53,
54 and D-BUY-67), then ran the 63 kept checks against them, sorted the six
that failed, and added four probes around the new rules. The screens of this
round are not clicked yet; they follow in their own file.

## What the round found

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R4-1 | Low | Home's stock alerts listed ten rows of each kind in whatever order the database returned them. The counts were right; the rows under them were not the worst, though the to-do says so. The fixture firm passed ten low items during the round, and the check's new one was counted and not listed | `tc_stock_019` failing on *low row: got None* | `stock_alerts` | **Fixed, D-STK-55**: worst first within each kind, the product code settling a tie. Unit-tested; **not yet seen live** (it merges with the round) |
| R4-2 | Low | D-PERF-3, open since 2026-10-05 as *a large answer is sometimes reset*, is repeatable and has a cause: a request carrying `Connection: close` loses any answer past 327,680 bytes, 19 seconds in. Three checks met it on every run once the firm's by-product summary grew past that size | three checks ending on `ConnectionResetError`, alone as well as in the run | the server library on this PC, not the application: a 20-line app does the same | **Open, D-PERF-3**, now with the exact case. The check client keeps its connection, as the desktop does, so the checks no longer meet it |

## The six that failed after #1373, sorted

| Check | What it was | What was done |
| --- | --- | --- |
| `tc_stock_019` | R4-1, a defect | fixed; the check now asks that a row is listed or outranked by ten worse ones, and that each kind comes worst first |
| `d_stk_20` | the paisa between the stock account and the valuation, now recorded as a known limit (stock is valued to four places, the ledger posts two) | the check allows two paise and says why |
| `p_audit` | the check's own set-up, refused by three of the new rules: a repack into a batch-tracked product named no batch (D-STK-53), its batch had no expiry date (D-STK-48), its serial number was added for a unit nobody held (D-STK-50) | the set-up names a batch with its date, and adds the number for a unit that was received and scrapped |
| `p_stale_version` | the same two refusals in its set-up | the batch carries its expiry date; the serial is one that arrived on a receipt |
| `p_books_agree`, `p_roles_reads`, `tc_stock_017` | R4-2: `GET /inventory/summary/by-product` is 392,721 bytes on this firm | the check client keeps its connection |

In the first run one more check, `p_kit_tracked_parts`, stopped on *409 This
record changed since you loaded it* while creating a purchase order. Another
check was being run by hand at the same moment, so two orders were numbered
together and one was asked to try again; it passed alone and in the run
after. That is the numbering series refusing a collision, not a finding.

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| A count posted after the stock moved | `p_count_adds_up.py` | 50 held, the sheet drawn up, ten written off, 49 counted: the posted line reads Expected 40, Counted 49, Variance +9, the three agree, and the warehouse holds 49 (D-STK-45) |
| Free goods on a receipt | `p_receipt_free_cap.py` | An order of 10 with 2 free: the first receipt takes 5 and both free units; the second is refused a third (*... has 0 left to give: 2 free on the order, 2 already received*) and saved without one; the shelf holds 12. An order that promised none refuses any on its receipt (D-BUY-67) |
| Breaking a kit with a batch-tracked part | `p_kit_break_batch.py` | The five parts go back into the batch the kit's last assembly drew from, never onto a row with no batch. A kit brought in as stock and never assembled in the warehouse is refused (*Name the batch it goes back into*), nothing moves, and it breaks once the batch is named (D-STK-53) |
| A note naming no bin and no batch | `p_bin_batch_split.py` | Three of an early-expiring batch in a bin and five of a later one on the warehouse's own row: a note for six takes the early batch whole from the bin and three of the later one, two movements, no row below zero, the two still owed stay reserved and ship next (D-STK-54) |
| The round's rules behind their own checks | `p_dates`, `p_batch_dates`, `p_tracking`, `p_repack_batchless`, `p_bins`, `p_stale_version` | All clean in the run: these were the failing rows of round 3, kept as the regression for the fixes in #1373 |

## The run

**57 of 63 clean** in the first run after #1373, the six above failing.
**66 of 66 clean** in the run after the checks were sorted and the four
probes and the keep-alive client were in, against the server as #1373 left
it.

One assertion was added after that run, to `tc_stock_019`: an item short by
more than any before it must head the low rows. The fixture firm's listed
rows all had the same shortfall, so nothing else in the check could tell the
new order from the old. It fails against the server as #1373 left it, which
is the point of it, and is the check to run first once D-STK-55 is live; the
result is recorded in the screens file of this round.

## Not verified in this round

- **D-STK-55 on the running server**, when this file was written: the fix
  merges with it. See the screens file of this round for the run after.
- **The screens**: Repacking with a batch-tracked product, the kit dialog
  (it has no batch boxes, so a batch-tracked kit cannot be assembled from
  it), Home's alert tile and the batch card for a firm whose near-expiry
  window is not 30 days, and D-UI-84.
- The test book's case lines and the user guide's lines for the round's
  rules.
- A cancelled receipt giving its free goods back to the order, and two lines
  of one receipt sharing one order line's free goods: unit-tested, not driven.
- The goods-receipt import path against the free-goods cap.
- The integration suite.

## Added on 2026-10-09 with the screens of the round

`SCREEN_FLOW_CHECK_INVENTORY_ROUND_4_2026-10-09.md` is the screens file: three
Repacking cases clicked, three pass, and the D-STK-55 line (seen live over
HTTP after the restart on #1374).

**One more kept check, `p_serial_past_stock.py` (16 checks, clean):** D-STK-50
had only its unit tests. With nothing held a number is refused, with a
warehouse named or without; two held take two numbers and refuse the third
(*This warehouse holds 2 of ... and 2 are already numbered*); a unit in another
warehouse makes no room in the first and takes its own number; a scrapped
number is not counted, and is refused its way back past the stock. That makes
67 kept checks; the 66 were not run again as a whole after it.

**The goods-types checks, which share two fixture firms with this folder,
were run as a whole: 35 of 35 clean** after five of them were sorted. None was
a defect of the application:

| Check | What it was | What was done |
| --- | --- | --- |
| `tc_mast_026` | it asks for *a firm with no tracked product*, and the inventory checks leave batch- and serial-tracked products holding stock in the generic firm, which nothing may delete; the menu rightly read BATCH, EXPIRY, SERIAL | the check has a Generic firm of its own (`plain` in `setup_firms.py`, T10099EJJ-F) |
| `tc_mast_019` | it read the pharmacy firm's whole list of goods types in use, and the inventory checks take Electronics into use there | it asks about Medicine alone, and reads the firm that starts with nothing from `plain` |
| `tc_mast_023`, `tc_mast_029`, `q_serial_twice`, `q_serial_move_untracked` | each added a serial number for a product with no stock, which D-STK-50 refuses | each brings the units in first (`one_in_stock` in `goods_types/_lib.py`) |

The case lines are written: TC-STOCK-024 to 029 in `07_INVENTORY.md`,
TC-BUY-099 in `06_PURCHASING.md`, and section 7.2, 7.3 and 6 of the
application guide carry the rules. Still not done from the list above: the
kit dialog, Home's tile and the batch card on screen, D-UI-84, the two
free-goods cases over HTTP, the receipt import path and the integration
suite.

## Round 4 is not a clean round

It found one new row (R4-1, Low, fixed) and pinned the cause of an old one
(R4-2). By the rule of the pass a round 5 follows the screens of this one.
