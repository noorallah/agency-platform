# Inventory, round 11 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the server as #1381 left
it. Round 10 found D-STK-59 to D-STK-62, so it was not a clean round; this one
ran the 81 kept checks first, then two new probes where no round had looked:
a count plan at its edges (what it accepts, a plan over nothing, two sheets
from one plan, a plan removed or switched off with its sheet open), and
adjustment reasons and limits as settings (a reason removed or switched off
while a request names it, what the list of limits accepts, whom a limit of
nothing binds, who may write it). A third probe was written for what the
first one turned up. The screens of the round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_11_2026-10-09.md`.

## What the round found

**The 81 kept checks: nothing of their own.** 79 were clean on the first run.
`p_trial_balance.py` and `p_scrap_return.py` failed because of this round's
own probing, which is how R11-4 was found: see below. Both were clean again
once the probe's entries were offset.

**The new probes found five defects: D-STK-66 and D-STK-67 (Medium) and
D-STK-63, D-STK-64, D-STK-65 (Low), all inventory**, fixed in the same merge.
So round 11 is **not** a clean round and round 12 follows.

| # | Severity | What | How it was found | Where | State |
| --- | --- | --- | --- | --- | --- |
| R11-1 | Low | **A name of only spaces was kept.** A count plan and an adjustment reason named with three spaces were saved (and a reason renamed to them) and listed as a blank row. A limit on a role of three spaces answered **500**. | `p_count_plan_edges.py`, `p_reason_limit_settings.py` on the running server | `CountPlanWrite.name`, `AdjustmentReasonWrite.name` and `StockAdjustmentLimitItem.role_code` took any string of one character | **Fixed** (D-STK-63): trimmed and refused in the request model when nothing is left |
| R11-2 | Low | **A count plan switched off still drew a sheet.** It was never due, and *Draw sheet* went on opening count sheets. | `p_count_plan_edges.py` | `CountPlanService.draw_sheet` never read `is_active` | **Fixed** (D-STK-64): refused by name, 422 |
| R11-3 | Low | **A reason whose code was sent as a number answered 500.** | `p_reason_limit_settings.py` | the `mode="before"` validator called `.strip()` on whatever arrived | **Fixed** (D-STK-65): a value that is not text is left to be refused, 422 |
| R11-4 | Medium | **Every stock write took a date after today.** A count sheet dated tomorrow, inside the open period, was drawn and posted: 3 pieces left the shelf today and the ledger row and its journal were dated tomorrow. A write-off, an adjustment, a transfer and opening stock dated tomorrow were accepted the same way. From then on the trial balance's Inventory and the stock valuation's books figure differed by the value moved (60.00 after two runs), which is what failed two kept checks. | a count dated ahead in `p_count_plan_edges.py`, then a scratch run of each stock write | the only rule on a stock date was *inside an open period* (D-STK-41) | **Fixed** (D-STK-66): a stock write dated after the firm's own today is refused, 422, by `assert_stock_date_not_ahead`; today and earlier are unchanged |
| R11-5 | Medium | **A limit could be set on a role nobody holds.** `NO_SUCH_...` was saved as a limit. `inventory_manager` in lower case was saved as typed and bound nobody: the warehouse role wrote off stock worth 10 under a "limit" of 5. | `p_reason_limit_settings.py` | `replace_limits` kept the text it was sent | **Fixed** (D-STK-67): matched whatever its case, kept under the role's own code, and refused by name when the firm has no such role |

**Seen before and after.** On port 8000 `p_count_plan_edges.py` failed 2 of
its checks and `p_reason_limit_settings.py` 10; each stock write dated
tomorrow was accepted there (scratch run). All three probes pass whole on a
temporary server running the branch (port 8011, stopped afterwards): 46, 60
and 17 checks. `p_dated_ahead.py` was **not** run on the old server, so as to
leave no more entries dated ahead on the fixture firm.

**Medium for R11-4, not High:** what it posts is a real movement with a
balanced journal at the true value, and the two reports agree again once the
date arrives. But stock leaves today on tomorrow's date and the books and the
valuation disagree in between, with nothing on screen saying why.

**Medium for R11-5:** nothing wrong is posted, but it is a control the firm
set and the server did not keep, silently. *Adjustment Limits* offers the
roles in a picker to somebody who may list roles and takes a typed code from
somebody who may not, so a typing mistake there was enough.

**Low for the other three:** nothing wrong was posted, and R11-1 (for the
role) and R11-3 need a caller of the API.

## Decided by me

- **No stock write is dated after today** (R11-4). ERPNext refuses a stock
  posting in the future; Tally takes a post-dated voucher but keeps it out of
  the books until its date. Here stock moves the moment an entry is saved, so
  only the first convention can hold. "Today" is the firm's own
  (`firm_today`), not the server's. The rule covers the inventory module's
  own writes: write-off, adjustment, a request for approval, transfer
  (direct and as a document), quarantine, repack, count sheet (drawn, posted,
  or drawn from a plan) and opening stock (saved, changed, imported). A
  delivery note, a receipt or a return dated ahead belongs to buying and
  selling and is **not** changed here; it was not probed.
- **A plan switched off draws nothing** (R11-2); a count sheet for the
  warehouse can still be opened directly. The convention of an inactive
  schedule in ERPNext and Zoho Inventory.
- **Two sheets may be open from one plan**, as two sheets may be open on one
  warehouse: each is measured against the stock at the moment it is posted,
  so counting 9 on both leaves 9. Driven: `p_count_plan_edges.py`, step 3.
- **A plan may be removed while its sheet is open**; the sheet stays, takes
  its count and posts. A cancelled sheet is not a count: the plan stays due.
- **A limit of 0 lets through stock that cost nothing** (worth 0, not above
  0), and binds everything else. The administrator, with no limited role, is
  not bound.
- **A reason removed while a request names it**: the approval is refused by
  name and the request goes on waiting; adding the code back lets it through.
- **The same unchecked role code in three other settings** (purchase approval
  limits, discount limits, approval rules) is logged as **D-CFG-27**, open,
  for their own passes: found by reading, not driven, and none is High.

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| What a plan accepts | `p_count_plan_edges.py` (46 checks) | Every 0, -1 or 367 days, a frequency that is not a number, class D, an unknown warehouse or bin, an unknown field: refused. A change to every 0 days is refused and the plan keeps its 7 |
| A plan over nothing | the same | Saved and due; its sheet is refused (*covers no stock to count*) and no sheet is left behind |
| Two sheets from one plan | the same | Both post; 9 counted twice leaves 9; the plan shows counted today and next due in 7 days |
| A cancelled sheet | the same | Does not count as counted; the plan is still due |
| A plan removed | the same | Gone from the list; drawing, changing or removing it again is 404; its open sheet still reads, takes a count and posts |
| A reason removed or switched off | `p_reason_limit_settings.py` (60 checks) | Leaves the list (or the active list); a waiting request naming it is refused at approval and still waits; a new request or write-off naming it is refused; the code can be taken again and the request then goes through |
| A reason's code | the same | One letter, a space inside, an unknown field: 422. A code another reason holds: 409 |
| What the limits accept | the same | A negative amount, one that is not a number, three decimals, no amount, one role twice (also with spaces round it): 422, and the saved list is unchanged |
| Who writes the limits | the same | The warehouse role and a viewer: 403; the warehouse role may read them |
| A limit of nothing, and the whole list replaced | the same | As decided above; a role left out of the list has no limit afterwards; an empty list clears them all |
| Today is still today | `p_dated_ahead.py` (17 checks) | Each stock write dated today is accepted; a refusal moves nothing; a draft of opening stock cannot be moved to tomorrow and keeps its date |

## The two kept checks that failed, and what was done about it

`p_trial_balance.py` and `p_scrap_return.py` compare the trial balance's
Inventory with the valuation's books figure for the whole firm. Two scratch
runs of this round each posted a count dated tomorrow that took 3 pieces at
10 off the shelf, so the two figures stood 60.00 apart (and would have until
the next day). To leave the fixture firm usable by every later run, one
adjustment of **+6 pieces at 10, dated tomorrow**, was posted on a product of
its own (`CMP...`): the entries dated ahead now sum to nothing. Both checks
were clean straight after. This was done on the old server, before the fix,
which would now refuse it.

## The whole folder after the fixes

84 checks (the 81 and the three new probes) on the temporary server running
the branch: **84 of 84 clean**, in one run. The goods-types checks on the
same server: **35 of 35 clean**.

Unit tests, by file (no full suite): the 45 files that touch the stock
services, the limits or the plans ran once on the branch, 749 passed; the
nine that did not were six set-ups and one test that put a limit on a role
before making the role, and two tests of D-STK-41 that expected a date in
2030 to be refused for its period. Those four files were corrected and run
again with the docs guard: 40 passed. `ruff`, `black` and `mypy` clean on the
files changed.

## What the runs left on the fixture firm

From the probes on the old server: a count plan and a reason named with
spaces and a limit on a role that does not exist, each removed again by the
probe that made it; one sheet drawn from a plan that was switched off
(cancelled); a write-off of one piece under the lower-case "limit"; and a
handful of movements dated 2026-10-10 on products the probes made (two posted
counts, a write-off, two adjustments, a transfer), summing to nothing in
value, with two unposted opening-stock drafts dated the same day.

## Not verified

- The integration suite was not run. `known_role_codes` reads `roles` through
  the platform store on PostgreSQL, the way `role_codes` beside it does; that
  path was driven over HTTP on the temporary server (the probe's lower-case
  and unknown-role cases), not by an integration test.
- A delivery note, goods receipt or return dated ahead (buying and selling).
- The seed scripts were not run against the new date rule; they date their
  history in the past.
- A limit stored earlier under a role since removed stays in the list until
  the list is next saved, when it is refused by name.
