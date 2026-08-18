# Purchase to payment: stock, and the money

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
  from the completed receipts.
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
stored on the invoice.**

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

## Undoing it

| Action | Stock | Ledger |
| --- | --- | --- |
| Cancel a **draft** receipt | nothing to undo | nothing to undo |
| Cancel a **completed** receipt | reversed, line by line | mirror journal cancels it; refused outright once the receipt has been invoiced |
| Purchase return, completed | stock goes back off | posted |
| Reverse a settlement | — | mirror journal cancels it; allocations stop clearing invoices but still record what they had cleared |

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
