# Inventory (stock, batches, lots, serial numbers): the screens, clicked against the real server, 2026-10-08

Cases: `SCREEN_TEST_CASES_INVENTORY.md`. Flows:
`desktop/integration_test/sc_st_test.dart` and `sc_bs_test.dart`, run in the
real phase 2 app at **1366x768** against the running backend, in 13 runs, on
the fixture firm `T10069CWY-S` only (no demo firm touched, no firm made). Round
1 of the module; nothing was fixed (no file under `desktop/lib` or `backend/`
was edited). The data the cases need (warehouse `QW2`, products `INVSCR-*`,
batches, serials, Medicine and Electronics taken into use) was made over HTTP
by `unattended/scratch/inv_screens/setup.py`.

**Outcome: 110 cases in the book. 95 Pass (7 of them only after the flow's own
mistake was corrected, which is not a screen fault), 8 Fail for the findings
below, 7 Not run.** No screen overflowed at 1366x768 (no `RenderFlex` report in
any run) and the app threw one error of its own, an unhandled `Concurrent
modification during iteration: Instance(length:7) of '_GrowableList'`, three
times (batch delete, and the Serial Numbers list); the report carries no package
frame, so no file:line.

## Findings (provisional ids)

| Id | Severity | Case | Symptom | Where | Fault |
| --- | --- | --- | --- | --- | --- |
| S1 | High | SC-BS-012 | A batch holding 20 on hand was deleted from the row menu: "Delete batch?" asked, "Batch deleted." The stock row stays and points at a deleted batch. Repeated over HTTP on a new batch with 5: `DELETE /batch-serial/batches/{id}` answers 204 | confirm text `desktop/lib/ui/inventory/batch_management_page.dart:1062-1070` ("This cannot be undone", no mention of stock); the refusal belongs in the batch service | Server (no guard); screen adds no warning |
| S2 | Medium | SC-ST-059 | A repack consuming 999,999 of a product holding 59 posted ("Repack posted."), leaving MAIN at -999,938. Transfer and Write off refuse the same quantity in words | `desktop/lib/ui/inventory/repack_dialog.dart:97-109` (`_validate` has no available check); server repack in `inventory_service.py` ~2245 | Both |
| S3 | Medium | SC-ST-025 | New adjustment of -99,999 on a product holding 9 posted at once, stock -99,990, no warning (seen twice, two runs) | `desktop/lib/ui/inventory/inventory_management_page.dart:2561-2565` (only "non-zero" is checked) | Server accepts; screen says nothing |
| S4 | Medium | SC-ST-026 | The New adjustment dialog has no Batch box for a batch-tracked product, so the movement cannot name the batch (D-STK-1). The firm's own `INVSCR-P` (batch category) got a stock row with no batch from such an adjustment | `inventory_management_page.dart:2382-2589`; `StockAdjustmentDraft` 2194-2256 has no `batch_id` | Screen |
| S5 | Medium | SC-ST-022/025 (rows) | Transactions' Quantity column shows the size without its sign: a -59 and a +59 adjustment both read `59`; the balance column is the only clue. The server sends the absolute quantity and `direction` null. (The Stock Ledger tab does sign a repack reversal: `-9,99,999`) | `inventory_management_page.dart:1370`; server transaction response | Server and screen |
| S6 | Medium | SC-BS-024 | A serial whose warranty ends before it starts saved with no message (seen twice: screen, then HTTP) | serial form `batch_management_page.dart` ~1842-1950 (no date check); server serial create | Both |
| S7 | Medium | SC-BS-030/031 | Expiry Monitor shows the batches list's four counters (Batches, Near expiry, Expired, Quarantine), not its own six (Expired today, In 7 days, In 30 days, Expired, Quarantine, Recalled). The six are built in code; the server's dashboard says 30-day = 1. Seen in two runs (admin and read-only) | `batch_management_page.dart:855-860` builds the six; the phase 2 counter hoist keeps the other page's four | Screen |
| S8 | Low | SC-BS-008 | A batch with selling price 90 and MRP 50 saved (seen twice, screen and HTTP). PTR/PTS are guarded against the MRP, this is not | batch form 1453-1470; server | Both |
| S9 | Low | SC-ST-038, SC-BS-018 | Refusals in raw validation wording: a counted quantity of -4 answers only "The request validation failed."; a lot quantity of -5 answers "quantity: Input should be greater than or equal to 0" | `physical_count_sheet_dialog.dart` `_save` (shows the server's message as it is); server validation text | Server wording; screen shows it unchanged |
| S10 | Low | SC-ST-076 | The Adjustment Limits refusal names the role code ("The limit for SALES_MANAGER ...") while the row shows "Sales Manager" | `desktop/lib/ui/inventory/adjustment_limits_dialog.dart:107-112` | Screen |
| S11 | Low | SC-ST-021/041 | Transactions' Type column shows raw codes (`QUARANTINE_RELEASE`, `ADJUSTMENT_REVERSAL` for a cancelled repack) while its own filter and labels use words ("Quarantine release", "Repack cancelled") | `inventory_management_page.dart:1365-1366` against labels 84-106 | Screen |
| S12 | Low | SC-ST-029 (code only, not driven) | The opening stock reference is prefilled `OPEN-001` (`inventory_management_page.dart:2721-2723`), the pattern D-QA-16 removed from adjustments; a second opening stock sent as it stands is refused ("Opening stock reference number already exists.", seen at SC-ST-033) | same lines | Screen |
| S13 | Low | SC-ST-036 | The book and `07_INVENTORY.md` say **Open Count**; the button reads **+ New count** | `physical_count_page.dart` toolbar | Docs |

Not findings: the Stock Ledger of the read-only user once answered "Unable to
load inventory data / Cannot reach the API server." (SC-ST-072); the ledger
answers 200 over HTTP for the same user and it did not repeat, so it is the
known development-PC connection reset (D-PERF-3), not a screen fault. Two
runs of `sc_bs_test.dart` ended without finishing at about 2:30 each
(app gone, no error in the log); the sections were re-run.

## Results, administrator (FA, `tradeadmin`)

Where a case failed first on the flow's own mistake (wrong row, wrong
warehouse default, a prefilled cost) it is shown as Fail, then Pass: the flow
was corrected, the screen was not at fault.

| Case | Result | What the screen did |
| --- | --- | --- |
| SC-ST-001 | Pass | Columns Product, Branch, Warehouse, Current, Available, Reserved, Status; INVSCR rows |
| SC-ST-002 | Pass | Only INVSCR-S after the search; the others returned when cleared |
| SC-ST-003 | Pass | Details dialog with Inventory ID, stock buckets, levels |
| SC-ST-004 | Fail, then Pass | First: menu drop-down missed after a dialog; then: Out of stock preset applied, INVSCR-N not listed. The filter is remembered for the user, so the flow clears it |
| SC-ST-005 | Pass | "Stock transferred."; MAIN 100 to 97, QW2 0 to 3 |
| SC-ST-006 | Pass | "97.0 available here" and "a transfer writes no journal" |
| SC-ST-007 to 009 | Pass | "Enter how much is moving."; again for 0; "This location holds 97.0000, so 9999999.0000 cannot be moved out of it."; open, typing kept |
| SC-ST-010, 011 | Pass | "Choose the warehouse it is going to."; "A reference needs at least two characters ..." |
| SC-ST-012 | Pass | "Stock written off."; 60 to 59; ledger `WRITE_OFF` |
| SC-ST-013 to 015 | Pass | 0 and 99999 refused in words; "Choose the customer it was given to." |
| SC-ST-016 | Pass | Server's sentence kept in the dialog: "This location holds 2.0000, so 54 cannot be written off from it."; remarks kept; nothing saved |
| SC-ST-017, 018 | Fail, then Pass | First pick landed on the QW2 row (flow); then hold 2 gave `quarantine_quantity` 2 and release 0, "Quarantine updated." |
| SC-ST-019, 020 | Pass | "This location holds 0.0000, so 5.0000 cannot be moved out of it."; the same for 9999999 |
| SC-ST-021 | Pass | Date, Type, Reference, Product, Warehouse, Quantity, New balance |
| SC-ST-022 | Fail, then Pass | First: the dialog defaulted to QW2 (flow); then MAIN 60 to 65, reference on the list |
| SC-ST-023, 024 | Pass | "Enter a non-zero quantity." |
| SC-ST-025 | **Fail** | S3: "Inventory adjustment posted." for -99,999; dialog closed |
| SC-ST-026 | **Fail** | S4: no Batch box |
| SC-ST-027 | Pass | Evidence absent with no row, enabled with one |
| SC-ST-028 to 030 | Pass | Draft saved ("Opening stock draft saved."), Post draft: "Opening stock posted.", MAIN 97 to 104 (the first try went to QW2: flow) |
| SC-ST-031 to 033 | Pass | "Each line needs product and quantity greater than zero."; "... is batch-tracked: give its batch number."; "Opening stock reference number already exists." in the dialog |
| SC-ST-034 | Fail, then Pass | First: the cost box was prefilled from the product, so no warning (flow); with cost 0 typed: warns once, saves on the second press |
| SC-ST-035 to 037 | Pass | List; sheet over 7 lines, difference shown, posted, MAIN -1; abandoned sheet moved nothing |
| SC-ST-038 | Pass (see S9) | "The request validation failed." only; sheet open |
| SC-ST-039, 040 | Pass | Ledger with Balance; "Ledger details" dialog |
| SC-ST-041 | **Not run** | The "Transaction type" drop-down of the filter panel could not be driven in three tries (the menu did not show its entries); harness, not judged |
| SC-ST-042 to 044 | Pass | Records / Current / Available / Low / Out of stock / Negative; INVSCR-S found; "No search results" |
| SC-ST-045 to 048 | Pass | TO-2026-2027-000001 draft, dispatched (MAIN 65 to 61, status DISPATCHED), received (QW2 9 to 13) |
| SC-ST-049, 050 | Pass | "The two warehouses must be different."; "Enter a quantity above zero on every line." |
| SC-ST-051 | Pass | 999,999 saved as a draft (refusal is at Dispatch) |
| SC-ST-052 | Pass | "The source holds 61.0000 available, so 999999.0000 cannot be sent from it." inside the Dispatch dialog; status stays DRAFT |
| SC-ST-053 | Pass | Reason prompt; "Transfer cancelled."; CANCELLED |
| SC-ST-054 to 058 | Pass | "Repack posted." N2 -2, N +4; "Add at least one product to produce."; "Enter a quantity above zero ..."; "Wastage is a percentage ..." |
| SC-ST-059 | **Fail** | S2 |
| SC-ST-060 | Pass | "Repack cancelled."; N back by 4 |
| SC-ST-061 to 064 | Pass | Two requests by IM listed; "Approved. The stock has moved."; "Rejected."; Approve disabled with no row |
| SC-ST-065 to 068 | Pass | Reasons listed; saved; "Name is required."; "There is already a reason SCR...." |
| SC-ST-069 | Pass | Inventory Settings opens |
| SC-ST-075, 076 | Pass (see S10) | "Adjustment limits saved."; "The limit for SALES_MANAGER must be an amount of zero or more." |
| SC-BS-001 to 003 | Pass | INVB1 listed; search; Add Batch saved and listed |
| SC-BS-004 | Pass | "The expiry date ... is before the manufacturing date ... Check the two dates." |
| SC-BS-005 | Pass | "A batch with this batch number already exists for the product." |
| SC-BS-006, 007 | Pass | "Required" under the box; "INVSCR-N is not tracked by batch ..." |
| SC-BS-008 | **Fail** | S8 |
| SC-BS-009 to 011 | Pass | "Batch: INVB1"; Edit saved the remarks; row menu Delete asked "Delete batch?" then "Batch deleted." |
| SC-BS-012 | **Fail** | S1 |
| SC-BS-013 | **Not run** | The Status drop-down of the filter panel was not reachable (panel state); harness |
| SC-BS-014 to 019 | Pass | Lots list, Add Lot saved; "Required"; "A lot with this lot number already exists for the product."; lot quantity -5 refused (S9); "Lot: ..." |
| SC-BS-020, 021 | Pass | INVS-0001 to -0003 listed; Add Serial saved |
| SC-BS-022 | Pass | "This serial number already belongs to a unit in this firm." |
| SC-BS-023, 025 | Pass | "Required"; "INVSCR-N is not tracked by serial number ..." |
| SC-BS-024 | **Fail** | S6 |
| SC-BS-026, 027 | Pass | "Serial: INVS-0002" with the warranty; Status SOLD filter drops the AVAILABLE ones |
| SC-BS-030, 031 | **Fail** | S7 |
| SC-BS-032, 033 | Pass | Refresh without an error; INVB1 in the grid |

## Role matrix

| Case | User | Result | What was seen |
| --- | --- | --- | --- |
| SC-ST-070 | FM `qfmgr` | **Not run on screen** | Over HTTP: inventory list 200, ledger 200, adjustment 422 (the same as the inventory manager, who is offered everything) |
| SC-ST-071 | IM `qstore` | Pass (11 of 11) | Stock offers all 16 items (Inventory to Export; Adjustment Approvals included); Transfer, Write off, Quarantine enabled; every Stock tab opens; New opening stock absent; New transfer, New repack, New batch enabled |
| SC-ST-072 | RO `qro` | Pass (13 of 14) | 13 stock items offered, no Adjustment Approvals; Transfer, Write off, Quarantine absent; New opening stock absent, New transfer and New repack present but disabled, New batch absent; adjustment API 403. The one failure was the ledger's transient "Cannot reach the API server." |
| SC-ST-073 | SM `qsmgr`, SE `qsexe` | **Not run on screen** | Over HTTP the inventory list, transactions and adjustment all answer 403; the goods-types round (SC-GM-001) already showed no Stock area for a sales manager |
| SC-BS-040 | FM | Not run | |
| SC-BS-041 | IM | Not run on screen | The menu list above offers Batches, Lots, Serial Numbers, Expiry Monitor; batch create is enabled for the user |
| SC-BS-042 | RO | Pass (4 of 4) | Batches, Lots, Serial Numbers, Expiry Monitor open; no New; Expiry Monitor shows the same four counters (S7) |
| SC-BS-043 | SM, SE | Not run | 403 over HTTP |

## Overflow at 1366x768

None reported. Screens opened: Inventory, Inventory details, the Transfer,
Write off and Quarantine dialogs, Transactions and the Adjustment dialog,
Opening Stock and its dialog, Physical Count and a 7-line sheet, Stock Ledger,
Stock Summary, Stock Search, Stock Transfers and its dialogs, Repacking and its
dialog, Adjustment Approvals, Adjustment Reasons, Inventory Settings, Adjustment
Limits, Batches (list, details, form), Lots, Serial Numbers, Expiry Monitor.

## Not run, and why

- SC-ST-041 and SC-BS-013: the drop-downs in the "+ filter" panel did not open
  under the harness (three tries and two tries); the harness, not judged.
- SC-ST-070, SC-ST-073, SC-BS-040, 041 (screen), 043: run budget (13 runs);
  the HTTP answers are recorded above.
- TC-STOCK-005 to 008, 011 to 020 on screen (batch dispatch, kits, count
  plans, labels, evidence upload, reservations): the file picker and the
  selling side are outside this round's flows; the batch and serial lists and
  dialogs above are what was clicked.
- Export / Import (07-S08, S09): the operating system's file window.

## Records left on T10069CWY-S

Warehouse `QW2`; goods types Medicine and Electronics set **in use** (this is
what makes the four tracking screens appear on the firm); products
`INVSCR-N`, `-N2`, `-B`, `-S`, `-P` and their categories; stock on them (MAIN
and QW2); batches `INVB1`, `INVB2` (deleted by SC-BS-012, 20 on hand left on
its stock row), `INVB3` (deleted, 5 on hand), `INVB4`, `BSM*`, `BSA*` (deleted),
lots `LOT*`, serials `INVS-0001` to `-0003`, `INVS-REV1`, `BSS*`, `BSW*`;
opening stocks `OS8STQW`, `OS97D36` (posted), `OZ8STQW`, `OZ97D36` (drafts);
transfers TO-...-000001 (received) and 000002, 000003 (cancelled); repacks
RPK-...-000001 and 000002 (cancelled); counts PC-...-000001 (posted), 000002 and
000003 (cancelled); adjustment reasons `SCR*`; adjustment limits cleared back to
none; adjustment-approval requests decided. The firm's original product
`T10069CWY-DET` was not changed.
