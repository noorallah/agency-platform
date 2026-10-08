# Inventory, round 7 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the server as #1376 left
it (#1377 changed the desktop alone). Round 6 found D-UI-86, so it was not a
clean round; this one ran the 73 kept checks first, then two new probes where
no round had looked. The screens of the round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_7_2026-10-09.md`.

## What the round found

**The 73 kept checks: nothing**, clean on the first run.

**One of the two new probes found a defect, D-BUY-73 (Medium, buying)**,
fixed in the same merge. So round 7 is **not** a clean round and round 8
follows.

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R7-1 | Medium | **A refused import of goods receipts left its earlier records behind as drafts.** A file of two receipts on one order line (10 ordered, 2 free), 5 each, taking 2 and then 1 of the free goods, was refused for the second with the single save's sentence, naming no record -- and the first stayed as a draft receipt. That draft holds the order line's quantity and its free goods, so the corrected file (1 and 1 free) was then refused too: *2 free on the order, 2 already received* | `p_receipt_import_free.py` on the running server: 1 live receipt on the order after the refused file where there were none, 2 after a second refused file | `GoodsReceiptService.import_receipts` looped over the committing `create_receipt`. Read beside it, `PurchaseService.import_orders` and `PurchaseInvoiceService.import_invoices` did the same | **Fixed** (D-BUY-73): all three stage every record and commit once through `stage_records`, as the purchase-return import (D-BUY-62) and the five selling imports (D-PRC-85) already did. The refusal reads *Record 2 of 2: ... Nothing was imported.* |

**Seen on both servers.** The probe failed 8 of its checks on port 8000 and
passed all 16 on a temporary server running the branch. The purchase-order
import was driven by hand the same way, the second record naming a product
that is not the firm's: on the old server the first order was kept (1 order
for the supplier after the refused file); on the branch none, and *Record 2
of 2: Selected product is not available in this firm. Nothing was imported.*
A good file of two wrote two drafts numbered one after the other on both.
**The purchase-bill import was not driven**: it is the same change, held by
the guard in `test_import_payload_refusals.py` and the bill module's own
tests.

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| The receipt import against the free-goods cap | `p_receipt_import_free.py` (16 checks) | The cap of D-BUY-67 is met by an imported receipt as by a typed one, and the records of one file count against each other: 2 and 1 of 2 free is refused at the second, 0 and then 3 free alone is refused, 1 and 1 is taken as two drafts with their own numbers; completed, the shelf holds 12 and a file of one more free unit is refused |
| A note and a kit that is itself kept in batches | `p_kit_batch_kit_dispatch.py` (16 checks) | Two of a Medicine kit assembled into a named batch, parts on the shelf for more. A delivery note for three is raised and approved, and refused at dispatch (*Insufficient available stock for dispatch line.*): no kit leaves and no part is taken, where a plain kit would have had the third assembled behind the note (D-STK-53). One more assembled into the batch by name, the same note ships, the batch is empty, nothing of the kit is left reserved and no further part went. A plain kit of the same part, none assembled, ships three and six parts go into them |

## Set-up that was not a finding

- The kit probe first raised a **second order** for the two assembled kits
  and expected it to ship. It was refused, rightly: the first order, approved
  for three, already holds those two (and stands one short on a row that
  holds nothing, which is how an order past the shelf is carried -- see
  `p_overreserve.py`). The probe now ships the first order's own note once
  the third kit exists.
- The refusal of the note is the dispatch's general sentence and names no
  product, for a kit as for any line (`tc_stock_006.py` pins it). Read as it
  stands, not raised.

## What the failed runs left on the fixture firm

Two draft goods receipts of 5 on one purchase order of the probe's own
product (the defect itself, on the old server), and one draft purchase order
from the hand-driven refused file. They hold nothing but their own order.

## The run

**73 of 73 clean** (the kept checks, first run). **75 kept checks** with the
two probes; both clean on a temporary server running the branch (port 8011,
stopped afterwards).

## Not verified in this round

- The purchase-bill import over HTTP (above).
- The integration suite.
- The reservation lapse of TC-STOCK-018 (needs the server's timer).
