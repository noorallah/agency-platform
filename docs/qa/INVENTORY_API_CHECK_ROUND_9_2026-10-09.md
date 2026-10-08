# Inventory, round 9 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the server as #1379 left
it. Round 8 found D-STK-56, so it was not a clean round; this one ran the 77
kept checks first, then two new probes where no round had looked: the
adjustment limit when the quantity is sent in a pack unit, and the CSV and
XLSX forms of the opening-stock import that round 8 fixed and did not drive.
The screens of the round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_9_2026-10-09.md`.

## What the round found

**The 77 kept checks: nothing**, clean on the first run.

**Both new probes found a defect: D-STK-57 (Medium) and D-STK-58 (Low), both
inventory**, fixed in the same merge. So round 9 is **not** a clean round and
round 10 follows.

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R9-1 | Medium | **The adjustment limit judged the number typed, not the pieces moved.** A box of 12, 60 a piece, the warehouse role limited to 500. A write-off of **3 boxes** -- 36 pieces, 2,160 -- posted, as did an adjustment of plus and of minus 3 boxes and a write-off of one box (720). A request for 3 boxes said it was worth **180.00**, so the requester approved it themselves. | `p_limit_in_packs.py` on the running server: 12 of its 17 checks failed | `create_adjustment` and `write_off_stock` passed `data.quantity` to `assert_within_limit`, and `StockAdjustmentApprovalService.submit` to `estimate`; with `entered_uom_id` set that number is in the pack unit | **Fixed** (D-STK-57): all three read `InventoryService.moved_base_quantity`, the quantity in the stock unit; a request's quantity is the pieces it moves |
| R9-2 | Low | **An opening-stock CSV or XLSX with a cell that could not be read answered 500.** A product id that is not an id, a quantity of *lots*, a quantity of -4, a reorder level of *few*, a storage location that is not an id, a file of the heading alone, a file that is not text, and a file that is not a workbook sent as `xlsx`: each *An unexpected error occurred.* Nothing was written. | `p_opening_import_csv.py` on a server running the limit fix: 8 of its 20 checks failed | `import_opening_stock_csv` and `import_opening_stock_xlsx` built `OpeningStockLineCreate` by hand (`UUID(...)`, `Decimal(...)`), and the router decoded the file without a guard | **Fixed** (D-STK-58): the cells go through `parse_payload` as text, refused by line and field; an unreadable file and a file with no usable row are refused in a sentence; a byte-order mark is read past |

**Seen before and after.** `p_limit_in_packs.py` failed 12 checks on port
8000 and passed 17 of 17 on a temporary server running the branch (port 8011,
stopped afterwards); `p_opening_import_csv.py` failed 8 there before its fix
and passed 20 of 20 after. The unit test added for D-STK-57 fails with the fix
taken out (proved) and passes with it.

**Medium for R9-1, not High:** no screen sends a pack unit on an adjustment or
a write-off (both forms type pieces), so only a caller of the API could step
round the limit, and what it posted was still a real, audited movement with
its journal. It is a control a firm set and the server did not keep, which is
why it is not Low.

**Low for R9-2:** the route has no screen and nothing was written; the caller
was told nothing about which row.

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| The limit in pieces, beside the packs | `p_limit_in_packs.py` (17 checks) | 8 pieces (480) post under a limit of 500. 36 pieces typed as `quantity` 36 with `entered_quantity` 3 boxes was refused before the fix as well. After approval by the administrator the request takes 36 pieces off |
| A good opening-stock CSV, and a bad posting date | `p_opening_import_csv.py` (20 checks) | One row of ten is saved and posted; `posting_date=tomorrow` is a 422; a number that a refused file named is free for the corrected file |
| Inventory services that commit twice | read, not driven | No inventory service method calls two committing methods in a row: the count sheet stages and the router commits once; an inspection that writes off commits once, through the write-off. `StockAdjustmentApprovalService.approve` commits the movement and then the request's link to it; no refusal can fall between the two, so nothing can be left half done by one |

## Read and left

- **An inspection that writes off rejected goods is under the inspector's
  adjustment limit** (`InspectionService.inspect` calls `write_off_stock`,
  which enforces it). Read as intended: it is a write-off like any other.

## What the failed runs left on the fixture firm

From the limit probe on the old server: two write-offs and two adjustments in
boxes that should have been refused, and one request approved by its
requester, all on a product and a warehouse the probe made for itself. From
the CSV probe: nothing (each refusal wrote nothing, before the fix as after).

## The run

**77 of 77 clean** (the kept checks, first run). **79 kept checks** with the
two probes, both clean on a temporary server running the branch.
`tc_stock_016.py` and the three `p_opening*` checks were run again on that
server: clean.

## Not verified in this round

- A request submitted **before** the fix, in packs, and approved after it:
  its stated worth was written at submission and is not recomputed.
- The XLSX form with a good workbook over HTTP (a unit test drives it).
- The count sheet's own limit (`_assert_within_limit`) was read, not probed:
  a sheet's differences are in the stock unit already.
- The other modules' imports (branches, warehouses, customers, suppliers,
  products by JSON, tax systems and rules): their own modules' rounds.
- The integration suite.
- The reservation lapse of TC-STOCK-018 (needs the server's timer).
