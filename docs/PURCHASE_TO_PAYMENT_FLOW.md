# Purchase to payment: stock, and the money

Updated 2026-10-02: the order's quantity picture and billing status (A33); reverse charge taken off by a return or debit note; what a firm configures (table below); input credit per bill line and where blocked tax posts; the supplier's GST type; GSTR-2B import and matching; a purchase return's outcome (credit, replacement, refund); a return off a paid bill; reorder planning from sales (backlog 69 row 12).

How a purchase becomes stock on the shelf and money out of the bank, which
document does each part, and where every rupee is recorded.

Everything below was **driven against a running backend on 2026-08-18** with the
seeded `WHOLE01` firm, not read off the code. The numbers in the trace are the
ones the server produced.

For the purchase order's own lifecycle and its statuses, see
[`PURCHASE_FRAMEWORK.md`](PURCHASE_FRAMEWORK.md). This document is about what
happens *outside* the order — to inventory and to the general ledger.

---

## The chain at a glance

```
  Purchase Order            Goods Receipt           Purchase Invoice        Payment
  ─────────────             ─────────────           ────────────────        ───────
  raise                     raise                   enter                   pay
  submit                    COMPLETE ◄── stock      APPROVE ◄── payable     ◄── money
  approve                       and the                 appears                 leaves
     │                          balance sheet
     │                              │                    │                     │
  commitment only            +10 units             Dr GRNI              Dr Payables
  no stock                   Dr Inventory          Dr Input Tax         Cr Bank
  no ledger                  Cr GRNI               Cr Payables
```

**Three moments matter.** Everything else is paperwork:

| Moment | What it does |
| --- | --- |
| **Completing a goods receipt** | Stock arrives, and the balance sheet learns |
| **Approving a purchase invoice** | The supplier becomes a creditor |
| **Recording a payment** | Money actually leaves the bank |

Nothing before those three moves a number that matters. Raising an order,
submitting it, approving it, and even raising a draft goods receipt all leave
stock and the ledger completely untouched.

---

## What a firm configures

Every row is a setting a firm changes without a release. **Where** gives the
phase 2 path (Settings gear, then the group) and the API. A firm that has set
nothing gets the default in the third column, which is the chain as it always
worked.

### Buying

| Setting | Where | Choices / default | What it changes in the chain |
| --- | --- | --- | --- |
| Purchase Settings (`purchase_workflow_settings`) | Settings > Buying > Purchase Settings; `GET/PUT /api/v1/purchases/workflow-settings` | `purchase_order_stage` and `goods_receipt_stage`: both on by default. A receipt is always raised against an order, so the receipt stage cannot be on while the order stage is off | Steps 1-4. An off stage means the bill raises that document itself. Stock still arrives at the goods receipt and the accrual still passes through Goods Received Not Invoiced |
| Default branch and warehouse (same row) | Same screen | `default_branch_id`, `default_warehouse_id`: null falls back to the firm's default branch and warehouse | Where a raised-for-you receipt puts the goods; receiving refuses a line with no warehouse |
| Reorder planning (`reorder_planning_settings`) | Settings > Buying > Purchase Settings > Reorder planning; `GET/PUT /api/v1/purchases/reorder-planning` (decision A39) | `basis` LEVELS (default) or SALES; `sales_window_days` 90, `lead_time_days` 7, `safety_days` 7, `cover_days` 30 | What *Below reorder level* lists and suggests before step 1: on SALES, every product with no typed level is reordered at average daily sales x (lead + safety) and ordered up to that plus the cover, in whole units, less what is on order; a typed level still wins (`PURCHASE_FRAMEWORK.md`) |
| Approval Limits (`role_purchase_approval_limits`) | Settings > Buying > Approval Limits; `GET/PUT /api/v1/purchases/approval-limits` (decision A30) | One `max_order_amount` per role code, compared with the order's grand total, tax included. A role with no row has no limit of its own; a person's limit is the largest of their roles' limits; somebody with none, or a platform administrator, is not limited | Step 2. An order above the approver's limit is refused at approval, naming the amount needed, and stays submitted for somebody allowed more. The approval that clears it records both figures |
| GST Documents (`gst_compliance_settings`) | Settings > Tax > GST Documents; `GET/PUT /api/v1/tax-framework/gst-compliance-settings` | `itc_claim_basis` `ALL` (default) or `MATCHED_ONLY`; `gstr2b_tolerance` 1.00 (rupees); `rule37_mode` OFF, REPORT (default) or POST; `supplier_irn_check` OFF or WARN (default) | See "GST on the purchase" below. `supplier_irn_check` warns on a bill from a supplier marked *Supplier e-invoices* that carries no IRN (§78 row 5). The same row carries the selling-side fields, described in `SALES_TO_RECEIPT_FLOW.md` |
| Trade licences (`trade_licence_settings`) | `app/trade_licences`; `GET/PUT /api/v1/trade-licences/settings` | `purchase_enforcement` OFF or `WARN` (default). Never BLOCK | A purchase order or goods receipt for a licensed product, with the firm holding no valid licence, warns. It never refuses: the goods are already on the dock |
| Party adjustments (`party_adjustment_settings`) | `GET/PUT /api/v1/party-adjustments/settings` | A rounding limit (10.00 unless set) and an approval threshold (1,000.00 unless set); see `app/party_adjustments` | Step 7: how much a payment may round off, and when a write-back needs a second person holding `PARTY_ADJUSTMENT_APPROVE` |
| Numbering Series | Settings > Firm > Numbering Series; `/api/v1/document-framework/numbering-rules` | Per document type; see `app/document_framework` for the fields | The number on every document above |
| Messaging (`messaging_settings`) | Settings > Firm > Messaging; `GET/PUT /api/v1/messaging/settings` | `is_enabled` off: a firm with no row queues and records nothing. `due_soon_days` 3; `overdue_every_days` 7 | Payment due and overdue reminders. `MESSAGING_FRAMEWORK.md` |
| Control accounts | Per firm, `ControlAccountPurpose` | `INELIGIBLE_INPUT_TAX` is *Input Tax Not Claimable*, 5450, an expense account | Where tax the firm may not claim posts. A firm without it mapped is refused the bill, not posted wrong |

### On the supplier, the product and the tax rules

| Setting | Where | Choices / default | What it changes in the chain |
| --- | --- | --- | --- |
| GST registration type | Supplier, `gst_registration_type` (`app/vendors/gst_registration.py`) | REGULAR, COMPOSITION, UNREGISTERED, OVERSEAS, SEZ. Null: a GSTIN reads as REGULAR, none as UNREGISTERED | A **declared** Composition, Unregistered or Overseas supplier charges no GST: the bill's lines carry none and no credit is claimed (A37). A null type never drops tax, even with no GSTIN on file. A *Reverse charge* rule still applies. Reaches the tax engine as `vendor_type` |
| Payment terms | Supplier, `payment_terms_days` | Default 0 | A bill's due date defaults from it when nobody typed one (`app/purchase_invoice/services/msme.py`) |
| MSME fields | Supplier, `udyam_number`, `msme_category`, `msme_written_agreement` | Category MICRO, SMALL or MEDIUM | A micro or small supplier must be paid within 45 days (15 where nothing was agreed in writing); the bill carries the date (MSMED Act s.15, Income Tax s.43B(h)). MEDIUM is recorded and outside the rule |
| Status BLOCKED | Supplier, `status` and `blocked_reason` | `blocked_reason` is required with BLOCKED and cleared otherwise | Step 1: no new purchase order can be raised to a blocked supplier, and the refusal repeats the reason |
| Input credit eligibility | Product, `itc_eligibility` | ELIGIBLE (default), BLOCKED (s.17(5)), INELIGIBLE. Changing it needs `PRODUCT_TAX_MANAGE` | The default for each bill line; the line may say otherwise. See "GST on the purchase" |
| Tax rule actions | Settings > Tax > Tax Rules | *Input credit blocked* (`INPUT_CREDIT_BLOCKED`) and *Reverse charge* | A rule that blocks credit makes the line BLOCKED when neither the line nor the product has already said something other than ELIGIBLE; reverse charge makes the firm owe the tax itself. First matching rule wins, as always (`TAX_FRAMEWORK.md`) |

---

## Step by step

### 1–2. Raise, submit, approve the order

`POST /api/v1/purchases` → `/submit` → `/approve`

Commitment only. **No stock. No ledger.** An approved purchase order is a
promise to buy; nothing has arrived and nobody is owed anything.

Approving takes `PURCHASE_APPROVE`, deliberately a different permission from the
`PURCHASE_UPDATE` needed to raise and submit, so the person who raises an order
need not be the person who commits the firm's money.

### 3. Raise the goods receipt

`POST /api/v1/goods-receipts`

Still nothing. A draft receipt is a note of what the lorry brought.

**Only an approved order can be received against** — `APPROVED`,
`PARTIALLY_RECEIVED` or `RECEIVED`. A draft or cancelled order is refused.

### 4. Complete the receipt — **stock arrives**

`POST /api/v1/goods-receipts/{id}/complete`

This is the first step that moves anything.

- **Inventory** goes up by the received quantity, per batch where the product is
  batch-tracked.
- **The purchase order** advances to `PARTIALLY_RECEIVED` or `RECEIVED`, summed
  from the completed receipts. Each order line's own picture (received,
  accepted, rejected, damaged, returned, invoiced, still to come, still to
  bill) is derived from the live receipts, bills and returns on every read
  (`app/purchase/services/line_quantities.py`), and the order's `billing_status`
  and `is_complete` come from the same figures beside its status (A33).
- **The ledger** gets:

```
Dr  1200 Inventory                      1000.00
    Cr  2300 Goods Received Not Invoiced        1000.00
```

**At cost, excluding tax.** The order was 1000 + 180 tax = 1180, and only the
1000 reaches the balance sheet — tax is not part of what the stock is worth.

The credit goes to *Goods Received Not Invoiced*, not to payables, because the
goods have arrived but the supplier's bill has not. Without this the inventory
account would only ever be credited by dispatches and would drift negative while
the warehouse filled up.

### 5. Enter the supplier invoice

`POST /api/v1/purchase-invoices`, sourced from the goods receipt

A draft invoice posts nothing.

### 6. Approve the invoice — **the payable appears**

`POST /api/v1/purchase-invoices/{id}/approve`

```
Dr  2300 Goods Received Not Invoiced    1000.00
Dr  1300 Input Tax                       180.00
    Cr  2100 Trade Payables                     1180.00
```

The accrual raised at receipt is cleared and replaced by a real liability to a
real supplier. **Inventory is deliberately untouched** — it was valued at what
the receipt cost, and re-valuing it here would double-count.

Where the supplier bills a different price from the receipt, the difference is a
**purchase price variance** posted to its own account, so the gap lands in the
P&L rather than sitting in the accrual forever explaining nothing.

**Tax on a line the firm may not claim does not go to Input Tax.** It posts to
5450 Input Tax Not Claimable; see "GST on the purchase" below.

Note the accounting shape: `GRNI` is debited and credited by equal amounts
across steps 4 and 6, so it nets to zero once the invoice arrives. A balance
sitting in that account is exactly "goods we have but have not been billed for".

### 7. Pay the supplier — **money leaves**

`POST /api/v1/payments`

```
Dr  2100 Trade Payables                 1180.00
    Cr  1010 Bank                               1180.00
```

One document type covers both directions — a receipt from a customer and a
payment to a vendor differ only in signs. `settlements.journal_entry_id` is
`NOT NULL`, because the defect it exists to prevent is a settlement that never
reached the ledger.

**What an invoice still owes is derived from `settlement_allocations`, never
stored on the invoice** -- beside returns, debit notes, applied supplier
credits and approved party adjustments, all through
`PaymentService.outstanding_invoices`.

**A payment can close a bill for less than its value** (backlog 74 row 2):
`amount` is what settles the bill, and a rounding-off or a discount the
supplier allowed is part of it that did not leave as money. Paying a 1,000.00
bill with 976.00, rounding 4.00 and a discount of 20.00:

```
Dr  2100 Trade Payables                 1000.00
    Cr  1010 Bank                                976.00
    Cr  4900 Rounding                              4.00
    Cr  4200 Discount Received                    20.00
```

Rounding is capped by the firm's limit (10.00 unless set); the deductions
must be allocated to bills; bank charges are not a payment deduction -- the
firm's own bank fee is an expense. None of this touches input tax: a lower
price after the bill is a debit note.

**A balance the firm will not pay** is a party adjustment
(`/api/v1/party-adjustments`), approved before it posts -- by a second person
holding `PARTY_ADJUSTMENT_APPROVE` above the firm's threshold (1,000.00
unless set):

```
Supplier write-back                       Set-off with the same business as a customer
Dr  2100 Trade Payables     450.00        Dr  2100 Trade Payables     600.00
    Cr  4300 Balances Written Back 450.00     Cr  1100 Trade Receivables  600.00
```

Either may name the open bills it clears; those bills then owe less on Record
Payment and the vendor outstanding and overdue reports. No tax leg, ever.

---

## The whole chain, netted

For the traced order of 10 units at ₹100 with 18% tax:

| Account | Movement |
| --- | --- |
| 1200 Inventory | **Dr 1,000.00** |
| 1300 Input Tax | **Dr 180.00** |
| 2300 Goods Received Not Invoiced | Dr 1,000 / Cr 1,000 → **nil** |
| 2100 Trade Payables | Dr 1,180 / Cr 1,180 → **nil** |
| 1010 Bank | **Cr 1,180.00** |

Stock up 10 units worth ₹1,000, input tax of ₹180 recoverable, ₹1,180 out of the
bank. The two clearing accounts return to zero, which is how you tell the chain
completed.

## The verified trace

```
opening stock: 885 units

STEP 1  PO-...-000025  DRAFT   goods 1000 + tax 180 = 1180
        stock 885      no ledger movement
STEP 2  order APPROVED
        stock 885      still no ledger movement
STEP 3  GRN-...-000012 DRAFT
        stock 885      journal: none
STEP 4  receipt COMPLETED          <-- stock arrives
        stock 885 -> 895
        order RECEIVED
        journal GRN-...-000012 [POSTED] balanced=True
          Dr  1000.00   1200 Inventory
          Cr  1000.00   2300 Goods Received Not Invoiced
STEP 5  PI-2026-2027-000007  DRAFT  total 1180
        stock 895      journal: none
STEP 6  invoice APPROVED           <-- the payable appears
        stock 895      (unchanged, on purpose)
        journal PI-2026-2027-000007 [POSTED] balanced=True
          Dr  1000.00   2300 Goods Received Not Invoiced
          Dr   180.00   1300 Input Tax
          Cr  1180.00   2100 Trade Payables
STEP 7  PY-2026-2027-000001 POSTED 1180.00   <-- money leaves
        journal PY-2026-2027-000001 [POSTED] balanced=True
          Dr  1180.00   2100 Trade Payables
          Cr  1180.00   1010 Bank
```

---

## GST on the purchase

Built 2026-10-02 (backlog 78, decisions A36 and A37; the rules and what other
products do are in `GST_DOCUMENT_COMPLIANCE.md` section 6).

### Reverse charge on a bill, and what takes it off

Where a tax rule marks a bill line *Reverse charge*, the supplier charged no
tax: the firm owes it itself, so approving the bill credits reverse-charge
payable and debits input credit per head (3.1(d) and 4(A)(3) on GSTR-3B). A
**purchase return** or a **supplier debit note** against such a bill carries no
tax of its own, so each takes the same share of the bill line's reverse charge
as its value is of the bill line's (`app/purchase_invoice/services/reverse_charge.py`):
completing the return, or approving the note, debits reverse-charge payable and
credits input credit, the bill's legs mirrored, and 3B falls by the same in
that period, so the GST payment pays less. Cancelling either mirrors its
journal and 3B drops it. Before 2026-10-02 the liability stayed in full after
the goods went back.

### Input credit is decided per bill line

Each purchase bill line carries `itc_eligibility`. It is the first that applies
of: what the line says; the product's own setting where that is not ELIGIBLE;
a tax rule's *Input credit blocked*; else ELIGIBLE
(`PurchaseInvoiceService._itc_eligibility`). Only an ELIGIBLE line's tax is
recoverable. Take a bill line of 1,000 plus 180 tax, set to BLOCKED:

```
Dr  2300 Goods Received Not Invoiced    1000.00
Dr  5450 Input Tax Not Claimable         180.00
    Cr  2100 Trade Payables                     1180.00
```

The tax is part of what the firm owes the supplier and none of it is input tax
(1300). A return off the bill and a debit note off the bill credit 5450 for
their share, in the same proportion, so a blocked line nets out like any other.
`INELIGIBLE_INPUT_TAX` is the control account behind 5450; the full rule is
under "Tax the firm may not claim is a cost, not input tax" in
`LEDGER_POSTING_RULES.md`.

On GSTR-3B, blocked credit is reported in 4(A)(5) and reversed in 4(B)(1)
(`itc_reversed_blocked`); ineligible credit never enters 4(A) and is shown in
4(D)(2) (`itc_ineligible`). A return's or debit note's blocked share is never
a 4(B)(2) reversal, because nothing was claimed.

### The supplier's GST type

A **declared** Composition, Unregistered or Overseas supplier charges no GST,
so the bill's lines carry none and no credit is claimed. A supplier with no
type set is taxed by the firm's rules as before: a GSTIN nobody typed in does
not make a supplier unregistered (A37). A *Reverse charge* rule applies to any
of them, and then the firm owes the tax itself. See
`app/vendors/gst_registration.py`.

### GSTR-2B: import, match, and what is claimed

`POST /api/v1/gst-returns/gstr2b/imports` takes the month's 2B JSON, downloaded
from the portal (no portal connection is needed). Each supplier invoice in it
is matched to the firm's own bill by the supplier's GSTIN and the supplier's
bill number, read loosely: case, spaces and punctuation ignored, leading zeros
dropped, so `INV/0001` and `inv-1` are one number
(`app/gst_returns/services/gstr2b.py`). A supplier's credit note matches the
debit note that recorded it.

| Status | Meaning |
| --- | --- |
| `MATCHED` | Found, and the date and every head of tax agree within `gstr2b_tolerance` (1.00 unless set) |
| `DIFFERENT` | Found, but something differs; the row says what, in words |
| `NOT_IN_BOOKS` | The portal shows it and the firm has no such bill |
| `MANUAL` | A person matched it by hand, where the numbers were typed beyond recognition; undoable |

Importing a month again replaces it, so the reconciliation always reads one
statement, and a hand match does not survive a re-import.
`GET /api/v1/gst-returns/gstr2b/reconciliation` adds the other side: bills
dated in the month from a registered supplier, carrying credit, that no 2B row
matched (the `in_books_only` list, counted as `IN_BOOKS_ONLY`).

**What 3B claims depends on `itc_claim_basis`.** `ALL` (default) claims every
bill and lists what 2B lacks. `MATCHED_ONLY` claims only bills matched to 2B;
the credit on the rest is held in `itc_awaiting_2b` and claimed in the month it
appears.

---

## Goods coming back

`POST /api/v1/purchase-returns`. Completing a return debits Trade Payables with
its total and takes the stock off, whatever the outcome (see "Undoing it").

### What the supplier gives for it: the outcome

Each return records an `outcome` (decision A34), set at raising and changeable
with `POST /api/v1/purchase-returns/{id}/outcome` until the return is
cancelled, because the supplier often decides after the goods have gone.

| Outcome | What happens |
| --- | --- |
| `CREDIT` (default) | The return is a supplier credit, set against a later bill |
| `REPLACEMENT` | Once the return is completed the order line is reopened for the quantity sent back, so the order reads as partly received and the next ordinary goods receipt against the same order takes the goods in. No new order, and no receipt "against the return". The ledger posts what it always posts |
| `REFUND` | The supplier pays money back against the return's credit |

A **refund** is `POST /api/v1/payments/supplier-credits/{return_id}/refunds`.
It posts `Dr cash or bank / Cr Trade Payables`, never more than is left of the
credit, dated on or after the return and not in the future, and is stored in
`supplier_credit_refunds`. It is reversed, never deleted:
`POST /api/v1/payments/supplier-credits/refunds/{refund_id}/reverse`. While a
refund stands the return cannot be cancelled or changed from a refund. A
return whose outcome is not REFUND is refused a refund by name
(`app/settlements/services/supplier_credits.py`).

### A return off a bill that is already paid

A return raised from a bill's own lines comes off that bill. If the bill was
already paid, there is nothing left on it to come off. The part the bill cannot
absorb is a supplier credit (D-BUY-20). Where the bill can absorb only some of
what was taken off it, the excess falls to its returns **newest first**, each up to what it took off that bill,
because the earlier ones fitted when they were made (`_spilled_over`). If the
bill then owes more again, say its payment is reversed, and the credit has
already been used elsewhere, the part used goes back onto the bill
(`drawn_back_onto_bills`), so the payables list and the ledger agree.

### A debit note on a bill that is already paid (decision A4)

A debit note debits payables against its bill exactly as a return off the
bill's lines does, so it follows the same rule. Until 2026-10-02 a claim larger
than the bill still owed was refused; now the part the bill cannot absorb is a
**supplier credit** on the debit note, set against another bill or paid back
like a return's. Returns and debit notes off one bill spill **newest first
whichever kind**. A claim is refused only past what the bill was worth -- its
total less what returns and other debit notes already took off it -- under a
lock on the bill.

A credit is named by its **source**: `GET /api/v1/payments/supplier-credits`
returns `source_id` and `source_type` (`PURCHASE_RETURN` or `DEBIT_NOTE`), and
`/supplier-credits/{source_id}/apply` and `/refunds` take either kind. An
application or refund row carries exactly one of `purchase_return_id` and
`debit_note_id` (migration 0218). A debit note's credit may be paid back
without an outcome to change first. Cancelling the debit note withdraws what
was set against other bills (they owe it again) and is refused while a refund
against it stands.

---

## Undoing it

| Action | Stock | Ledger |
| --- | --- | --- |
| Cancel a **draft** receipt | nothing to undo | nothing to undo |
| Cancel a **completed** receipt | reversed, line by line | mirror journal cancels it; refused outright once the receipt has been invoiced |
| Purchase return, completed | stock goes back off | posted; blocked tax credits 5450, not input tax |
| Cancel a purchase return | reversed | mirror journal cancels it; refused while a supplier refund stands against it |
| Cancel a debit note | nothing moved | mirror journal; credit it left that was set against other bills is withdrawn; refused while a supplier refund stands against it (A4) |
| Reverse a supplier refund | — | mirror journal cancels it; the return's credit is free again |
| Reverse a settlement | — | mirror journal cancels it, every deduction leg with it; allocations stop clearing invoices but still record what they had cleared |
| Cancel an approved party adjustment | — | mirror journal cancels it; the bills it named owe again; the customer's row is undone by its stored deltas |

A settlement is **reversed, never edited or deleted**. The customer-side
equivalent puts balances back by the *deltas stored on the original row* rather
than recomputing them, because a receipt of 500 against an outstanding 300
splits into 300 of balance and 200 of advance, and only that row remembers the
split.

---

## Known gaps

### Fixed: cancelling a completed receipt reverses its journal

Until 2026-08-18 the stock came back off and the journal stayed posted:
`GoodsReceiptService._reverse_inventory` called
`InventoryService.reverse_transaction` and stopped there, and `reverse_entry`
was never called for a goods receipt. The general ledger's Inventory balance
drifted **above** the warehouse by the value of every cancelled receipt, and
Goods Received Not Invoiced carried a permanent liability for goods the firm
handed back.

Cancelling now posts a mirror entry, and every account nets to zero across the
pair:

```
complete: stock 895 -> 905   journals 1
cancel:   stock 905 -> 895   journals 2
  GRN-...-000015     [REVERSED]  Dr 1000 Inventory / Cr 1000 GRNI
  GRN-...-000015-REV [POSTED]    Cr 1000 Inventory / Dr 1000 GRNI
  net per account: {Inventory: 0.00, GRNI: 0.00}
```

Two things the lookup has to get right. `reverse_entry` **copies the source
module and id onto the mirror it posts**, so a query filtering only on POSTED
would find that mirror on a second pass and reverse the reversal; the original
is identified by `reversal_of_id IS NULL`. And a receipt cancelled before it
was completed posted nothing, so there is nothing to take back — that returns
quietly rather than failing.

### A receipt that has been invoiced cannot be cancelled

The other half of the same fix, because reversing there does not balance.
Receiving posts `Dr Inventory / Cr GRNI`; approving the invoice clears that
accrual and raises a payable. Reversing the receipt afterwards would debit the
accrual a **second** time and leave it with a balance nobody can explain, while
the payable stayed exactly where it was.

So it is refused, naming what to do instead: cancel the purchase invoice first
if the invoice was wrong, or raise a **purchase return** if the goods are going
back — a return credits the supplier as well as taking the stock off, which is
the part cancelling the receipt could never do.

A **cancelled** invoice does not hold the receipt; the refusal is about a live
bill, not any bill that ever existed.

### Purchase price variance is posted but not surfaced

The posting rule handles a supplier billing a different price from the receipt,
but nothing in the desktop shows the variance or explains it.

### A return off the receipt is a credit on the supplier's account

A completed purchase return debits Trade Payables with its whole total. One
raised from the bill's own lines comes off that bill (D-BUY-6). One raised from
the **goods receipt** names no bill, and until 2026-09-19 nothing tracked it per
supplier: the payment screen still offered the whole bill, a payment could
settle it in full, and the supplier could then be deleted with the debit in
payables belonging to nobody (D-FIN-19).

It is now a **supplier credit**, the payable twin of a customer's advance:

- what a return gives is derived -- its ledger total less what its bill-sourced
  lines took off their bills -- and listed by `GET
  /api/v1/payments/supplier-credits?vendor_id=` (`app/settlements/services/supplier_credits.py`);
- `POST /api/v1/payments/supplier-credits/{return_id}/apply` sets part of it
  against one of the supplier's approved bills, recorded in
  `supplier_credit_applications`. **Nothing posts** -- the return and the bill
  already did -- and the bill's outstanding falls by the amount;
- the Payments screen has a **Supplier credits** action, and Record Payment says
  when the chosen supplier holds one;
- the vendor delete guard counts what is left of it;
- a return off a bill that was **already paid** also leaves credit, for the
  part the bill could not absorb (D-BUY-20; see "Goods coming back");
- a refund against it is the other way to use it, outcome `REFUND`;
- cancelling the return or the bill withdraws what was set between them, so the
  bill owes it again, or the credit is free again.

### Still open

Checked against `GST_DOCUMENT_COMPLIANCE.md` section 6.2 on 2026-10-02 (rule
37 and the supplier's IRN were built the same day, §78 rows 4 and 5):

- **The e-way bill number** is not on the goods receipt (the vehicle is).

### Not a gap: a payment needs no invoice

Worth stating because it looks like one. A payment with no allocations is
accepted and posted — verified, `PY-2026-2027-000002` returned `201 POSTED`
with an empty allocation list. That is an **advance to a supplier**, a real
thing a distributor does, and the money genuinely has left the bank. It sits
unallocated until an invoice arrives to apply it against.

A settlement is reversed rather than deleted if it was a mistake; the same
probe reversed cleanly to `REVERSED`.

---

## Where to look

| Thing | Where |
| --- | --- |
| The three posting rules | `app/finance/services/document_posting.py` — `post_goods_receipt`, `post_purchase_invoice`, `post_settlement` |
| Stock movement | `app/goods_receipt/services/goods_receipt_service.py` — `_post_inventory`, `_reverse_inventory` |
| Order status from receipts | `_resync_order_status`, same file |
| Which account is which | `ControlAccountPurpose`, per firm; a firm with no mapping or no open period is refused rather than posted wrong |
| What an invoice still owes | `settlement_allocations`, never a column on the invoice |
