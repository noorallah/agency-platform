# Inventory, round 6 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the server as #1376 left
it. Round 5 found D-UI-85, so it was not a clean round; this one ran the 72
kept checks first, then one new probe around the server's half of that fix.
The screens of the round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_6_2026-10-09.md`.

## What the round found

**Over HTTP: nothing.** The 72 kept checks were clean on the first run, the
first whole run on the server restarted on #1376. The new probe was clean
once two of its own expectations were corrected (below).

**On screen: one, D-UI-86 (Low)**, in the screens file: an error in the
client's log when a products page is left while it loads. It is fixed in the
same merge. So round 6 is **not** a clean round and round 7 follows.

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| Which parts the kit dialog asks a batch for | `p_kit_batch_tracked_kit.py` (21 checks) | A kit of a plain part and a medicine: the save and the list read afterwards each say the medicine is kept in batches and the plain part is not. The plain part, holding nothing, switched to batches: the list says both, without the kit being saved again; switched back, the list follows |
| A kit that is itself kept in batches | the same check | A kit under a Medicine category is kept in batches. Assembled naming no batch it is refused and nothing moves. Two assembled into a new batch with its dates, one into a second batch with an expiry date alone (what the dialog sends): the kits stand in their batches and the parts went. Broken, the kits leave soonest expiry first; more than are held is refused naming the kit and nothing moves |

## Set-up that was not a finding

- The probe first moved its plain part **to a Medicine category** and
  expected the part to be kept in batches afterwards. It is not, and that is
  the rule of the goods types: another category changes a product's type and
  *its switches stay as they are* (`ProductService.update_product`). The
  probe now turns the switch itself.
- The probe first expected a batch **named again beside another expiry
  date** to be refused. It is accepted and the batch keeps its own date:
  `resolve_for_receipt` leaves an existing batch's date alone, *the
  manufacturer's fact and not this delivery's to change*, the same as on a
  goods receipt. The dialog says so beside the box (*for a new batch*). The
  probe now proves the date is kept. Only the opening-stock **import** names
  the clash (*is already registered expiring ...*), because a file is checked
  before anything is written; recorded here as how each reads, not as a
  defect.

## The run

**72 of 72 clean** (the kept checks, first run). **73 of 73** with the probe,
run alone after it. The goods-types folder: see the screens file's last
section for when it was run.

## Not verified in this round

- The goods-receipt **import** path against the free-goods cap.
- The integration suite.
- The reservation lapse of TC-STOCK-018 (needs the server's timer).
