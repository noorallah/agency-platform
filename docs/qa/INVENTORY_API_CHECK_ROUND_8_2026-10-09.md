# Inventory, round 8 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the server as #1378 left
it. Round 7 found D-BUY-73, so it was not a clean round; this one ran the 75
kept checks first, then two new probes where no round had looked: the
inventory module's own JSON import, and the purchase-bill import that round 7
fixed and did not drive. The screens of the round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_8_2026-10-09.md`.

## What the round found

**The 75 kept checks: nothing**, clean on the first run.

**One of the two new probes found a defect, D-STK-56 (Low, inventory)**,
fixed in the same merge. So round 8 is **not** a clean round and round 9
follows.

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R8-1 | Low | **An opening-stock import refused at posting left its draft behind.** Ten of a product imported and posted. The same product again under a new reference number was refused, rightly (*Line 1 already has posted opening stock in this warehouse ...*) -- and a draft document stayed under that number. The corrected payload, another product under the same number, was then refused: *Opening stock reference number already exists.* | `p_opening_import_json.py` on the running server: 1 document under the refused number where there should be none, and a 409 for the corrected payload | `InventoryService.import_opening_stock_json` called the committing `create_opening_stock_batch` and then the committing `post_opening_stock_batch`. The CSV and XLSX forms of the same route go through it | **Fixed** (D-STK-56): the draft and its posting are staged and committed once (`stage_opening_stock_batch`, `stage_post_opening_stock_batch`), as the file import (`import-file`) already did |

**Seen on both servers.** The probe failed 4 of its checks on port 8000 and
passed all 12 on a temporary server running the branch (port 8011, stopped
afterwards). The unit test added with the fix fails with the fix taken out
(two documents where one is expected) and passes with it.

**Low, not Medium:** the route has no screen. Opening Stock's **Import from
file** is `POST /inventory/opening-stock/import-file`, which wrote all or
nothing already (`p_opening_import.py`). The draft left behind held no stock
and no journal; it cost the caller the reference number.

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| The purchase-bill import refused at its second record (round 7's unproven third of D-BUY-73) | `p_bill_import_refused.py` (14 checks) | Six received. A file of two bills on the receipt's line, the second taking nine, is refused: *Record 2 of 2: Invoice quantity exceeds the available source quantity ... Nothing was imported.*, and the supplier has no bill. Two and two is saved as two drafts with their own numbers. With two left to bill, a file of two and then one is refused at its second record and its first is not kept; one and one is saved, four bills covering the six |
| Opening stock by JSON, the parts that were right before the fix | `p_opening_import_json.py` (12 checks) | The first import is saved and posted and stocks ten; a number already used is refused and stays one document; without `auto_post` the import is a draft that stocks nothing; a payload that is not JSON is a 422 |

## Set-up that was not a finding

- The bill probe first sent bills that named no goods receipt. The fixture
  firm raises an order and a receipt before a bill, so the file was refused
  at its **first** record (*... each bill line must name the goods receipt it
  bills.*). The probe now bills a receipt.
- It then gave one supplier bill number to both records and expected a
  refusal. Both were saved: a supplier bill number given twice is a
  **warning** on the bill (`duplicate_warning`), not a refusal, in a file as
  on the form. Read as it stands, not raised. The probe refuses its second
  record by quantity instead.

## What the failed runs left on the fixture firm

One draft opening-stock document `OSJ-...-B` (the defect itself, on the old
server), holding nothing. Two draft bills under one supplier bill number and
one more draft bill on a receipt of six, from the bill probe's first shapes.

## The run

**75 of 75 clean** (the kept checks, first run). **77 kept checks** with the
two probes: the bill probe clean on port 8000 as it stands, both clean on a
temporary server running the branch.

## Not verified in this round

- The CSV and XLSX forms of `POST /inventory/opening-stock/import` over HTTP
  (they build their lines and call the JSON method the probe drives).
- The other modules' imports (branches, warehouses, customers, suppliers,
  products by JSON, tax systems and rules) were not read for the same shape;
  they belong to the rounds of their own modules.
- The integration suite.
- The reservation lapse of TC-STOCK-018 (needs the server's timer).
