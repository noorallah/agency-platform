# Screen test cases: inventory (stock, batches, lots, serial numbers)

Written 2026-10-08, round 1 of the inventory module. Edited by hand, like
`SCREEN_TEST_CASES_GOODS_TYPES.md` beside it.

## Purpose

`07_INVENTORY.md` (TC-STOCK-001 to 020, screen checks 07-S01 to S18) says what
the stock rules are. This book is what a **person sees and can do** on the
Stock screens of the phase 2 desktop: the Inventory list and its Transfer,
Write off and Quarantine dialogs, Transactions and the New adjustment dialog,
Opening Stock, Physical Count, Stock Ledger, Stock Summary, Stock Search, Stock
Transfers, Repacking, Adjustment Approvals, Adjustment Reasons, Inventory
Settings and Adjustment Limits (ids `SC-ST-`), and Batches, Lots, Serial
Numbers and the Expiry Monitor (ids `SC-BS-`).

Kinds: **Positive** (save, then read the result back from the screen and the
server), **Negative** (the screen says why in words; the dialog stays open with
the typing kept; nothing is saved: N1 to N3 of the buying and selling book), and
**Role** (what each user is offered and refused).

Click flows: `desktop/integration_test/sc_st_test.dart` and `sc_bs_test.dart`,
one step per case id, run at 1366x768:

```bash
# from desktop/, Git Bash, backend running, one run at a time
IT_EMAIL=t10069cwy.tradeadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' \
  IT_PART=lists,actions LIMIT=900 bash integration_test/run.sh sc_st_test.dart
# sc_st parts: lists, actions, adjust, opening, count, views, transfers,
#              repack, approvals, settings, round2 (or its pieces r2xfer,
#              r2doc, r2open, r2ref), backorder
# sc_bs parts: batches, lots, serials, expiry
# any other user (qfmgr, qstore, qro, qsmgr, qsexe) runs the Role cases only
```

## Users and data

Fixture firm `T10069CWY-S`, users `t10069cwy.<handle>@fixtures.local`, password
`Fixture@2026pw`.

| Id | Handle | Role | Stock access |
| --- | --- | --- | --- |
| FA | `tradeadmin` | Firm administrator | all |
| FM | `qfmgr` | `FIRM_MANAGER` | read and write |
| IM | `qstore` | `INVENTORY_MANAGER` | read and write |
| RO | `qro` | `VIEWER` | read |
| SM / SE | `qsmgr`, `qsexe` | sales | none (the server answers 403) |

Made over HTTP on that firm by `unattended/scratch/inv_screens/setup.py`:
Medicine and Electronics taken into use (so the Batches, Lots, Serial Numbers
and Expiry Monitor screens are offered); warehouse `QW2`; products `INVSCR-N`
(100) and `INVSCR-N2` (60), plain; `INVSCR-B` (Medicine: batch and expiry) with
batches `INVB1` (expires in 20 days) and `INVB2` (400 days), 20 each;
`INVSCR-S` (Electronics: serial) with `INVS-0001` to `-0003`.

## Stock lists and dialogs (Stock menu)

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-ST-001 | Positive | FA | Stock > Inventory | Columns Product, Branch, Warehouse, Current, Available, Reserved, Status; rows; no overflow |
| SC-ST-002 | Positive | FA | Search `INVSCR-S` | Only that product; clearing the search brings the rest back |
| SC-ST-003 | Positive | FA | Pick a row; **Open** | A details dialog with the stock figures |
| SC-ST-004 | Positive | FA | + filter; **Preset: Out of stock**; Apply | A product holding 100 is not listed |
| SC-ST-005 | Positive | FA | Pick `INVSCR-N`; **Transfer**; 3, Move it to `QW2`, a reference; Transfer | Dialog closes; MAIN 3 less, QW2 3 more on the server; the list shows it |
| SC-ST-006 | Positive | FA | Open Transfer | The dialog says how much is available and that a transfer writes no journal |
| SC-ST-007 to 009 | Negative | FA | Transfer with the quantity empty, 0, 9999999 | The dialog's banner names the problem; stays open; typing kept; nothing saved |
| SC-ST-010 | Negative | FA | Transfer with no destination | "Choose the warehouse it is going to."; nothing saved |
| SC-ST-011 | Negative | FA | Transfer with the reference `X` | "A reference needs at least two characters ..." |
| SC-ST-012 | Positive | FA | Pick `INVSCR-N2`; **Write off**; 1, reason Damage, a reference; Write off | MAIN 1 less; ledger row `WRITE_OFF` |
| SC-ST-013, 014 | Negative | FA | Write off 0; Write off 99999 | Refused in words; dialog open |
| SC-ST-015 | Negative | FA | Write off with the reason that names a customer, none chosen | "Choose the customer it was given to." |
| SC-ST-016 | Negative | FA | Open Write off; another user takes the stock; type a quantity the screen allowed; Write off | **The server's** sentence on screen; dialog open; remarks kept; nothing saved |
| SC-ST-017 | Positive | FA | Pick `INVSCR-N`; **Quarantine** > Hold back 2 | Server `quarantine_quantity` 2 |
| SC-ST-018 | Positive | FA | Quarantine > Release 2 | `quarantine_quantity` 0 |
| SC-ST-019 | Negative | FA | Release 5 with nothing held | Refused in words; open |
| SC-ST-020 | Negative | FA | Hold back 9999999 | Refused in words; open |
| SC-ST-021 | Positive | FA | Stock > Transactions | Columns Date, Type, Reference, Product, Quantity |
| SC-ST-022 | Positive | FA | **+ New**; Product `INVSCR-N2`; Quantity 5; a reference; Post adjustment | MAIN +5 on the server; the reference is on the list |
| SC-ST-023, 024 | Negative | FA | New adjustment with the quantity empty; with 0 | "Enter a non-zero quantity." |
| SC-ST-025 | Negative | FA | New adjustment of -99999 | The server's refusal in the dialog; remarks kept; nothing saved |
| SC-ST-026 | Negative | FA | New adjustment, product `INVSCR-B` (batch-tracked) | A Batch box is offered, or the adjustment cannot land on an untracked row (D-STK-1) |
| SC-ST-027 | Positive | FA | Transactions: Evidence with no row, then with a row | Disabled, then enabled |

## Opening Stock

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-ST-028 | Positive | FA | Stock > Opening Stock | Reference and Status columns, or the empty state |
| SC-ST-029 | Positive | FA | **+ New**; Reference; Product `INVSCR-N`; Quantity 7; Unit cost 60; Save | A draft is saved and listed |
| SC-ST-030 | Positive | FA | Pick it; **Post draft** | MAIN 7 more on the server |
| SC-ST-031 | Negative | FA | A line with a product and no quantity | "Each line needs product and quantity greater than zero." |
| SC-ST-032 | Negative | FA | `INVSCR-B` with no batch number | "... is batch-tracked: give its batch number." |
| SC-ST-033 | Negative | FA | A reference already used | The server's refusal in the dialog; typing kept; nothing saved |
| SC-ST-034 | Negative | FA | No unit cost: Save twice | First press warns that the stock is valued at zero and saves nothing; the second saves |

## Physical Count

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-ST-035 | Positive | FA | Stock > Physical Count | Count Number column, or "No counts yet" |
| SC-ST-036 | Positive | FA | **+ New count**, warehouse MAIN, Open; type held less 1 against `INVSCR-N`; Save progress; Post count | Difference -1 shows while typing; MAIN 1 less after posting |
| SC-ST-037 | Positive | FA | Open a count, type a figure, **Abandon sheet**, confirm | Nothing moves |
| SC-ST-038 | Negative | FA | Type -4 as a counted quantity; Save progress | Refused in words |

## Ledger, Summary, Search

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-ST-039 | Positive | FA | Stock > Stock Ledger; search `INVSCR-N2` | Its movements, with a balance column |
| SC-ST-040 | Positive | FA | Pick a ledger row; **Open** | A details dialog |
| SC-ST-041 | Positive | FA | Transactions > + filter > Transaction type Write off > Apply | The adjustment row drops out |
| SC-ST-042 | Positive | FA | Stock > Stock Summary | Records / Out of stock counts |
| SC-ST-043 | Positive | FA | Stock > Stock Search, `INVSCR-S` | Found |
| SC-ST-044 | Negative | FA | Search for text nothing has | An empty-state message |

## Stock Transfers (document)

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-ST-045 | Positive | FA | Stock > Stock Transfers | Transfer, Status columns |
| SC-ST-046 | Positive | FA | **New transfer**: MAIN to QW2, `INVSCR-N2` x 4; Save draft | A numbered draft on the list |
| SC-ST-047 | Positive | FA | Pick it; **Dispatch** | MAIN 4 less |
| SC-ST-048 | Positive | FA | **Receive** | QW2 4 more |
| SC-ST-049 | Negative | FA | MAIN to MAIN | "The two warehouses must be different." |
| SC-ST-050 | Negative | FA | No quantity | "Enter a quantity above zero ..." |
| SC-ST-051 | Negative | FA | 999999 | Saved as a draft or refused in words (recorded); the refusal then comes at Dispatch (SC-ST-052) |
| SC-ST-052 | Negative | FA | Dispatch a draft that asks for more than MAIN holds | The server's sentence on screen |
| SC-ST-053 | Positive | FA | Cancel a draft with a reason | Status CANCELLED |

## Repacking

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-ST-054 | Positive | FA | Stock > Repacking | Repack column, or "No repacks yet" |
| SC-ST-055 | Positive | FA | **New repack**: consume 2 `INVSCR-N2`, produce 4 `INVSCR-N`; Post repack | N2 -2, N +4 |
| SC-ST-056 | Negative | FA | No produce line | "Add at least one product to produce." |
| SC-ST-057 | Negative | FA | Quantity 0 | "Enter a quantity above zero on every line." |
| SC-ST-058 | Negative | FA | Wastage 100 | "Wastage is a percentage from 0 up to, but not including, 100." |
| SC-ST-059 | Negative | FA | Consume 999999 | The server's refusal in the dialog; nothing saved |
| SC-ST-060 | Positive | FA | Pick the repack; **Cancel repack** with a reason | Stock reversed |

## Approvals, Reasons, Settings

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-ST-061 | Positive | FA | Two requests raised over HTTP by IM; Stock > Adjustment Approvals | Both listed under Pending |
| SC-ST-062 | Positive | FA | Pick one; **Approve** | Posted; pending falls by one |
| SC-ST-063 | Positive | FA | Pick one; **Reject** with a reason | Nothing posted; pending falls by one |
| SC-ST-064 | Negative | FA | Approve with no row picked | Disabled |
| SC-ST-065 | Positive | FA | Settings > Stock > Adjustment Reasons | The firm's reasons (Damage, Expiry ...) |
| SC-ST-066 | Positive | FA | **+ New**; Code, Name; Save | On the server and on the list |
| SC-ST-067 | Negative | FA | A code and no name | Refused in words |
| SC-ST-068 | Negative | FA | A code already used | The server's refusal; typing kept |
| SC-ST-069 | Positive | FA | Settings > Stock > Inventory Settings | Opens with its two defaults |
| SC-ST-075 | Positive | FA | Settings > Stock > Adjustment Limits; Add role `INVENTORY_MANAGER`, 500; Save | The server holds the limit |
| SC-ST-076 | Negative | FA | Add a role with no amount; Save | Refused in words; nothing saved |

## Round 2: serial units on the move, a used reference, a back order

Added 2026-10-08 with round 2 (D-STK-40, D-STK-44, D-STK-39). The flow numbers
six units `R2<stamp>-1` to `-6` of `INVSCR-S` on the MAIN shelf before it
starts, and makes a serial-tracked product of its own for the two opening stock
cases, because opening stock is posted once per item and warehouse.

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-ST-077 | Negative | FA | Inventory, pick `INVSCR-S` at MAIN; **Transfer**; Move it to QW2; Quantity 2; tick one unit; Transfer | The heading reads "1 of 2 picked"; "Pick one serial number per unit moving: 2 needed, 1 picked."; dialog open, typing kept, nothing moved |
| SC-ST-078 | Positive | FA | The same with two units ticked | "Stock transferred."; QW2 2 more; the two units read AVAILABLE in QW2 on the server, a third stays in MAIN |
| SC-ST-079 | Positive | FA | Stock Transfers; **New transfer** MAIN to QW2, `INVSCR-S` x 2; tick two units; Save draft | The heading goes from "0 of 2 picked" to "2 of 2 picked"; a draft is saved and names the two units |
| SC-ST-080 | Negative | FA | A draft that names one unit of two (made over HTTP); pick it; **Dispatch**; confirm | "Line 1 (INVSCR-S) sends 2 serial-tracked units but 1 serial number is picked: pick 1 more on the transfer."; the dialog stays open; status stays Draft |
| SC-ST-081 | Positive | FA | Pick the draft of SC-ST-079; **Dispatch**; confirm | "Transfer dispatched."; both units read IN_TRANSIT |
| SC-ST-082 | Negative | FA | **Receive**; Damaged 1; tick nothing; Receive | "Tick which 1 unit(s) of ... arrived damaged: 0 ticked."; dialog open; not received |
| SC-ST-083 | Positive | FA | The same with the damaged unit ticked | "Transfer received."; QW2 2 more; one unit AVAILABLE and one DAMAGED, both in QW2; the details line names the damaged one |
| SC-ST-084 | Positive | FA | Opening Stock; **+ New**; a serial-tracked product; Quantity 2; two numbers in **Serial numbers**; Save; pick it; **Post draft** | The helper text counts "2 of 2 entered"; the draft saves; posting makes the two units AVAILABLE in MAIN |
| SC-ST-085 | Negative | FA | A draft of 3 units numbering two (made over HTTP); pick it; **Post draft** | "Line 1 (...) brings in 3 serial-tracked units but 2 serial numbers are entered: enter 1 more on the opening stock line."; still a Draft; no stock |
| SC-ST-086 | Negative | FA | **Write off** 1 of `INVSCR-N2` under a reference; then a second write-off under the same reference | "A write-off with the reference ... already exists: give this one a reference of its own, or leave the box empty to have it numbered."; dialog open, typing kept, nothing moved |
| SC-ST-087 | Positive | FA | A product with 4 in MAIN, an approved order for 10 and an approved note for 4 (made over HTTP); Sell > Delivery Notes; pick the note; **Dispatch**; Dispatch anyway | The note is dispatched; the stock row reads On hand 0, Reserved 6, Available -6 (TC-STOCK-022 on screen) |

The refusals of round 2 that already had a case are re-clicked rather than
renumbered: SC-ST-038 (the count sheet now names the line), SC-BS-008 (a
selling price above the MRP) and SC-BS-018 (a lot below nothing).

## Role cases (stock)

| Id | Kind | User | Steps | Expected |
| --- | --- | --- | --- | --- |
| SC-ST-070 | Role | FM | Menu; Inventory buttons; each Stock tab; New buttons | Offered what the server allows |
| SC-ST-071 | Role | IM | same | same |
| SC-ST-072 | Role | RO | same | Rows readable; Transfer, Write off, Quarantine, New buttons absent or disabled |
| SC-ST-073 | Role | SM, SE | same | No Stock area; the server answers 403 |

## Batches, Lots, Serial Numbers, Expiry Monitor

| Id | Kind | User | Steps on screen | Expected on screen |
| --- | --- | --- | --- | --- |
| SC-BS-001 | Positive | FA | Stock > Batches | Batch, Product, Status, Expiry columns; `INVB1` listed |
| SC-BS-002 | Positive | FA | Search `INVB2` | Only that batch |
| SC-BS-003 | Positive | FA | **+ New**; product `INVSCR-B`; number; dates; MRP 120, price 100; Create | Saved, closed, listed |
| SC-BS-004 | Negative | FA | Expiry before manufacturing | "... before ..." in words; open; typing kept |
| SC-BS-005 | Negative | FA | A batch number already used for the product | Refused naming it |
| SC-BS-006 | Negative | FA | No batch number | Refused in words |
| SC-BS-007 | Negative | FA | A product that tracks no batch | "... is not tracked by batch ..." |
| SC-BS-008 | Negative | FA | Selling price 90 above MRP 50 | Refused (or recorded as accepted) |
| SC-BS-009 | Positive | FA | Pick `INVB1`; **Open** | "Batch: INVB1" with its fields |
| SC-BS-010 | Positive | FA | Open > Edit; change Remarks; Save | The server holds the remarks |
| SC-BS-011 | Positive | FA | Right-click the new batch > Delete > confirm | "Delete batch?" asked; gone |
| SC-BS-012 | Negative | FA | Delete `INVB2`, which holds 20 | The server's sentence on screen; the batch stays |
| SC-BS-013 | Positive | FA | + filter > Status EXPIRED > Apply | An AVAILABLE batch drops out |
| SC-BS-014 | Positive | FA | Stock > Lots | Opens |
| SC-BS-015 | Positive | FA | **+ New**; product, Lot Number, Quantity 10; Create | Saved, closed, listed |
| SC-BS-016 to 018 | Negative | FA | No number; a number already used; quantity -5 | Refused in words; open |
| SC-BS-019 | Positive | FA | Pick a lot; **Open** | "Lot: ..." |
| SC-BS-020 | Positive | FA | Stock > Serial Numbers | `INVS-0001` to `-0003` |
| SC-BS-021 | Positive | FA | **+ New**; product `INVSCR-S`; number; warranty dates; Create | Saved, closed, listed |
| SC-BS-022 to 025 | Negative | FA | A number already used; no number; warranty ending before it starts; a product that tracks no serial | Refused in words; open |
| SC-BS-026 | Positive | FA | Pick `INVS-0002`; **Open** | "Serial: INVS-0002" with the warranty |
| SC-BS-027 | Positive | FA | + filter > Status SOLD | AVAILABLE serials drop out |
| SC-BS-030 | Positive | FA | Stock > Expiry Monitor | Six cards and the batch grid |
| SC-BS-031 | Positive | FA | Read the 30-day card | Matches the server's `expire_in_30_days` (INVB1 expires in 20 days) |
| SC-BS-032 | Positive | FA | Refresh | No error panel |
| SC-BS-033 | Positive | FA | Read the grid | `INVB1` with its expiry |
| SC-BS-040 to 043 | Role | FM, IM, RO, SM/SE | Menu; each tracking tab; New offered | Offered what the server allows; RO has no New |
