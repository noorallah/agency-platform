# Inventory, round 5 over HTTP -- 2026-10-09

Fixture firm **T1008FTRV-F**, the kept checks of `docs/qa/checks/inventory/`
(`python docs/qa/checks/run.py inventory`), against the server as #1374 left
it. Round 4 found D-STK-55, so it was not a clean round; this one ran the 67
kept checks first, then five new probes around the alerts and around the
rules round 4 built. The screens of the round are in
`SCREEN_FLOW_CHECK_INVENTORY_ROUND_5_2026-10-09.md`.

## What the round found

**Over HTTP: nothing.** The 67 kept checks were clean on the first run and
the five probes were clean as written, apart from their own set-up.

**On screen: one, D-UI-85 (Low)**, in the screens file: the kit dialog could
not name a batch the server asks for. It is fixed in the same merge. So round
5 is **not** a clean round and round 6 follows.

## Probed and found right

| Probe | Check | What holds |
| --- | --- | --- |
| Scrap coming back from a customer | `p_scrap_return.py` (17 checks) | Twenty in at 60, ten sold, two back as scrap: the shelf still holds ten, the damaged figure reads two, the books rise by 120. A write-off of two empties the damaged figure and leaves the shelf at ten; the books fall by 120; the valuation holds ten at 60 and the trial balance's Inventory is the books figure. A write-off of eleven is refused and moves nothing. A second scrap return, cancelled after completion, takes its unit out of the damaged figure again (D-STK-46) |
| The same for a product kept in batches | `p_scrap_return_batch.py` (10 checks) | Ten of one batch in, six sold, two back as scrap naming the batch: the batch's own row holds four on the shelf and two damaged, and no row without a batch appears. A write-off naming the batch takes the damaged two first. One naming no batch leaves no figure below nought and makes no row without a batch |
| Near expiry on Home and on the batch card | `p_alert_windows.py` (20 checks) | Three batches of one item, 20 days, 45 days, and 45 days held whole in quarantine. At a window of 60 days Home's alerts and the batch card each count three more, the quarantined batch among them; at 30 each counts one more; at nought both read nought; the two figures are equal at every window. The near-expiry rows come soonest first, ten at most. The firm's window is put back (D-STK-47) |
| Goods in transit | the same check | A draft transfer is not in transit; dispatched, one more item is counted and its row reads the quantity, the most on its way first; cancelled, the count is back |
| Exactly ten of a kind, eleven, and ties | `p_alert_ten.py` (14 checks) | In a firm with no other levels: ten items with a reorder level and nothing held are ten *out of stock*, none of them *low* as well, listed with the largest level first. An eleventh with a level of nought is counted and is the one not listed. A twelfth level with the worst is listed beside it, the product code settling which comes first, and the least short drops off. A stock row with no level at all is not an alert. With the levels taken off the firm reads no alert (D-STK-55) |
| Free goods given back, and shared by two lines | `p_receipt_free_back.py` (10 checks) | An order of 10 with 2 free. One receipt of two lines on the one order line: 2 and 1 free is refused together, 1 and 1 is saved and puts 12 on the shelf. With both received another free unit is refused. The receipt cancelled, the shelf is empty and the order line has its 2 to give again: a new receipt takes both and the shelf holds 12, no more (D-BUY-67) |

## Set-up that was not a finding

- `p_alert_ten.py` first tried to stock its items in the goods-types checks'
  plain firm (**T10099EJJ-F**), the only fixture firm with no levels of its
  own. That firm has no control accounts, so opening stock is refused
  (*This firm has no ledger account configured for: INVENTORY,
  OPENING_BALANCE_EQUITY*), which is the rule. The probe gives its items a
  stock row with a reorder level and nothing held instead, so the kind it
  proves at ten, eleven and a tie is *out of stock*; *low* and *over maximum*
  worst first are in `tc_stock_019.py`. One draft opening-stock sheet from
  that first try is left in the plain firm, unposted.
- An item with a reorder level of **nought** and nothing held is counted as
  out of stock. A level somebody typed, even nought, is a level; a row with
  no level is not counted. Recorded here as how it reads, not as a defect.

## The run

**67 of 67 clean** (the kept checks, first run, about eight minutes).
**72 of 72** with the five probes, each run alone after it; `p_alert_ten`
twice, to see that it leaves the plain firm as it found it. The goods-types
folder, which shares two firms with this one and lends the plain firm:
**35 of 35 clean** after the probes.

After the merge the backend was restarted on the round's code, and the
whole inventory folder was not run again on it: the server change of the
round is one more field on the kit component list.

## Not verified in this round

- The goods-receipt **import** path against the free-goods cap.
- The integration suite.
- A *low* or *over maximum* kind at exactly ten in a firm with no other
  levels (needs a fixture firm with control accounts and no stock history).
- The reservation lapse of TC-STOCK-018 (needs the server's timer).
