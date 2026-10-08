# Inventory, round 10 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the server as #1380 left
it. Round 9 found D-STK-57 and D-STK-58, so it was not a clean round; this one
ran the 79 kept checks first, then two new probes where no round had looked:
an adjustment request through its whole life (asked for, revalued, decided
once, refused, many at once), and evidence files at their edges (on a request,
on a refused post, with no name, at the cap). The screens of the round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_10_2026-10-09.md`.

## What the round found

**The 79 kept checks: nothing**, clean on the first run.

**Both new probes found defects: D-STK-59 (Medium) and D-STK-60, D-STK-61,
D-STK-62 (Low), all inventory**, fixed in the same merge. So round 10 is
**not** a clean round and round 11 follows.

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R10-1 | Medium | **A request was judged at what it was worth on the day of asking.** 200 pieces at 10, the warehouse role limited to 500. A write-off of 40 pieces was asked for (400). A receipt of 200 at 190 into another warehouse took the average to 100, so the 40 pieces were worth 4,000. The requester approved their own request and 40 pieces left. | `p_request_lifecycle.py` on the running server | `StockAdjustmentApprovalService.approve` compared the stored `estimated_value` with the approver's limit | **Fixed** (D-STK-59): approval values the pieces at the average cost of that moment and keeps that figure on the approved request; the waiting list shows the same present worth, in one read, writing nothing |
| R10-2 | Low | **A request that could never be posted was accepted, or refused as a conflict.** An unknown reason: 201, a request nobody could approve. A product or a warehouse that is not the firm's: 409 *The request conflicts with existing data. Please retry.* | the same probe | `submit` checked nothing but the unit; the 409 was the foreign key of `stock_adjustment_requests` | **Fixed** (D-STK-60): `InventoryService.assert_postable` checks branch, warehouse, location, product, batch and reason as a direct post does; 422 in the post's own words |
| R10-3 | Low | **A file with a name or a place of only spaces was kept**, as an empty name on the movement. | `p_evidence_edges.py` on the running server | `StockAttachmentWrite` took any string of one character; the service trimmed it afterwards | **Fixed** (D-STK-61): trimmed and refused in the request model when nothing is left |
| R10-4 | Low | **Ten files was the cap on a request, not on the record.** Ten, then nine, then one more: a write-off held thirteen. | the same probe | `MAX_STOCK_ATTACHMENTS` bounded the list in the body only | **Fixed** (D-STK-62): a movement or a count sheet keeps at most ten; a request that would pass it is refused saying how many it holds |

**Seen before and after.** `p_request_lifecycle.py` failed 7 of its checks on
port 8000 and `p_evidence_edges.py` 5; both passed whole on a temporary server
running the branch (port 8011, stopped afterwards). The four unit tests added
fail with the fixes taken out (proved) and pass with them.

**Medium for R10-1, not High:** it needs the cost of an item to rise between
the asking and the deciding, and what it posts is a real, audited movement
with its journal at the true value. It is a control a firm set and the server
did not keep, which is why it is not Low.

**Low for the other three:** nothing wrong was posted. R10-2 left a request
that could only be rejected, or told the caller nothing useful; R10-3 and
R10-4 need a caller of the API (the screens pick real files, one dialog at a
time).

## Decided by me

- **A request for more than the location holds is still accepted** (R10-2):
  the goods may arrive before the decision, as with a purchase requisition in
  Tally or ERPNext; approval refuses while they have not, and the request
  goes on waiting. Driven: `p_request_lifecycle.py`, step 3.
- **The cap of ten files is on the record** (R10-4), the convention of Zoho
  Books and of this application's other documents. A transfer's two legs show
  one set of files, so they share the ten. Removing a file makes room.
- **A decided request keeps the figure it was decided at.** Only a waiting
  one is shown at today's worth.

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| One decision, once | `p_request_lifecycle.py` (33 checks) | A rejection needs a reason (none, or only spaces: 422). An approved request cannot be approved or rejected again, a rejected one cannot be approved; nothing moves twice. An unknown request is 404, an unknown status filter 422, a kind with the other kind's body 422 |
| A refused approval | the same | Approving a request for more than is held is a 422; nothing moves and the request is still waiting |
| Many at once | the same | Bulk approve of a waiting, a decided and an unknown request: the first is done, the other two refused by row, and only the first one's pieces leave |
| A request's file | `p_evidence_edges.py` (22 checks) | A file sent with a request is on the movement its approval posts |
| A refused post | the same | A write-off refused for quantity writes no movement, so no file |
| Where there is nothing | the same | An unknown movement, count or file is 404; an empty list, a missing path and an unknown field are 422; eleven files in one request are 422 |
| A cancelled count | the same | Keeps the files it had |

## A kept check made steadier

`tc_stock_014.py` (count plans and ABC classes) failed once in the second
whole run and passed alone. Not a defect of the application: every run of the
case leaves a product that moved 60,000 at cost, the firm keeps them all (19
in class A by now), and equal movers share class A in the order of their ids,
so the newest was now and then class B and its plan *covers no stock to
count*. The case now makes its mover dearer than every earlier one. Run three
times after the change, clean each time.

## The whole folder after the fixes

81 checks on the temporary server running the branch: **80 clean**, the one
failure being `tc_stock_014.py` as above (clean on its own, then changed).

## What the failed runs left on the fixture firm

From the lifecycle probe on the old server: one write-off of 40 pieces
approved by its requester, one request naming an unknown reason (rejected by
the probe), on a product and warehouses the probe made. From the evidence
probe: one write-off holding thirteen files, two of them with empty names.

## Not verified

- The integration suite was not run (no change to tenancy, keys or triggers).
- **Adjustment Approvals** on screen showing a waiting request at a changed
  worth: the list reads the same field as before; not clicked.
- A request stored before this change with a file of no name would now fail
  to be read back at approval; the fixture firm holds none waiting.
