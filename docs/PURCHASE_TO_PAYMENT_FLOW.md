# Purchase to payment: stock, and the money

Brought up to date 2026-10-04, release 1.3.0: every menu path is the 1.3.0 path (light menu, Settings page), the settings table matches `CONFIGURATION_SETTINGS_GUIDE.md`, and a section carries what release 1.2.0 added to the chain (requisitions, order amendments, approval levels, bill tolerance, budgets, quality inspection, payment runs, landed costs). The traced figures below are from 2026-08 and are unchanged.

Updated 2026-10-02: the order's quantity picture and billing status (A33); reverse charge taken off by a return or debit note; what a firm configures (table below); input credit per bill line and where blocked tax posts; the supplier's GST type; GSTR-2B import and matching; a purchase return's outcome (credit, replacement, refund); a return off a paid bill; reorder planning from sales (backlog 69 row 12). Brought up to #947 the same night: a debit note's excess as supplier credit (A4); the preferred supplier (A18); rule 37; the supplier's IRN on the bill; the e-way bill on the goods receipt; a batch's MRP from the receipt (§78 rows 4-6, A41).

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

### Where each step is in 1.3.0

A path such as *Buy > Purchase Orders* means: open **Buy** in the menu bar, then
the item. **All Buy screens** is the link at the foot of the drop-down; the
daily list is what the drop-down shows first. **Ctrl+K** finds any screen.

| Step | Where |
| --- | --- |
| Requisition (what to buy), convert to orders | Buy > All Buy screens > Documents > **Requisitions**; Reports > Operational > Below reorder level |
| 1-2. Purchase order, submit, approve, amend | Buy > **Purchase Orders** |
| Approvals waiting for a level's sign-off | Buy > All Buy screens > Documents > **Approvals** |
| Quality inspection of received goods | Buy > All Buy screens > Documents > **Quality Inspection** |
| 3-4. Goods receipt, complete | Buy > **Goods Receipts** |
| 5-6. Purchase invoice, approve | Buy > **Purchase Invoices** |
| 7. Payment, supplier credits | Buy > **Payments**; Buy > All Buy screens > Money > Payment Runs, Post-dated Cheques |
| What the firm owes a supplier | Buy > **Supplier Statements** |
| Purchase return, supplier debit note | Buy > **Returns & notes** > Purchase Returns, Debit Notes |
| Landed costs, supplier rebates, principal claims, supplier gifts | Buy > All Buy screens > Money > Landed Costs, Supplier Rebates, Principal Claims, Supplier Gifts |
| Rate trend, purchase analysis, dashboard | Buy > All Buy screens > Insight |
| GSTR-2B matching, rule 37 | Accounts > All Accounts screens > Tax filing > GSTR-2B Reconciliation, Rule 37 (180 days) |
| The ledger entries each step posts | Accounts > **Journal Entries** |
| Stock after each step | Stock > All Stock screens > Stock > **Inventory**; Stock > **Stock Ledger** |

---

## What a firm configures

Every row is a setting a firm changes without a release. **Where** gives the
1.3.0 path (the gear, then *Settings* and its group, or *Set up*) and the API. A firm that has set
nothing gets the default in the third column, which is the chain as it always
worked.

### Buying

| Setting | Where | Choices / default | What it changes in the chain |
| --- | --- | --- | --- |
| Purchase Settings (`purchase_workflow_settings`) | Settings > Buying > Purchase Settings; `GET/PUT /api/v1/purchases/workflow-settings` | `purchase_order_stage` and `goods_receipt_stage`: both on by default. A receipt is always raised against an order, so the receipt stage cannot be on while the order stage is off. The same screen holds *Rate may exceed the order by (%)* and *Whole bill may exceed the order by (amount)* (no check by default: past either, approving the bill needs `PURCHASE_APPROVE_OVER_TOLERANCE` and names each line), *Order quantities off the supplier's terms* (**Warn**, or Refuse) and *Past a purchase budget* (**Warn**, or Needs approval, which needs `PURCHASE_APPROVE_OVER_BUDGET`) | Steps 1-4. An off stage means the bill raises that document itself. Stock still arrives at the goods receipt and the accrual still passes through Goods Received Not Invoiced |
| Default branch and warehouse (same row) | Same screen | `default_branch_id`, `default_warehouse_id`: null falls back to the firm's default branch and warehouse | Where a raised-for-you receipt puts the goods; receiving refuses a line with no warehouse |
| Reorder planning (`reorder_planning_settings`) | Reports > Operational > Below reorder level > Reorder planning; `GET/PUT /api/v1/purchases/reorder-planning` (decision A39) | `basis` LEVELS (default) or SALES; `sales_window_days` 90, `lead_time_days` 7, `safety_days` 7, `cover_days` 30 | What *Below reorder level* lists and suggests before step 1: on SALES, every product with no typed level is reordered at average daily sales x (lead + safety) and ordered up to that plus the cover, in whole units, less what is on order; a typed level still wins (`PURCHASE_FRAMEWORK.md`) |
| Approval Limits (`role_purchase_approval_limits`) | Settings > Buying > Approval Limits; `GET/PUT /api/v1/purchases/approval-limits` (decision A30) | One `max_order_amount` per role code, compared with the order's grand total, tax included. A role with no row has no limit of its own; a person's limit is the largest of their roles' limits; somebody with none, or a platform administrator, is not limited | Step 2. An order above the approver's limit is refused at approval, naming the amount needed, and stays submitted for somebody allowed more. The approval that clears it records both figures |
| GST Documents (`gst_compliance_settings`) | Settings > Tax > GST Documents; `GET/PUT /api/v1/tax-framework/gst-compliance-settings` | `itc_claim_basis` `ALL` (default) or `MATCHED_ONLY`; `gstr2b_tolerance` 1.00 (rupees); `rule37_mode` OFF, REPORT (default) or POST; `supplier_irn_check` OFF or WARN (default); `eway_bill_limit` 50,000 | See "GST on the purchase" below. `supplier_irn_check` warns on a bill from a supplier marked *Supplier e-invoices* that carries no IRN (§78 row 5); `eway_bill_limit` is the receipt value above which a receipt with no e-way bill is warned about (§78 row 6). The same row carries the selling-side fields, described in `SALES_TO_RECEIPT_FLOW.md` |
| Trade licences (`trade_licence_settings`) | Settings > Set up > Party lists > **Licence Check**; `GET/PUT /api/v1/trade-licences/settings` | `purchase_enforcement` OFF or `WARN` (default). Never BLOCK | A purchase order or goods receipt for a licensed product, with the firm holding no valid licence, warns. It never refuses: the goods are already on the dock |
| Party adjustments (`party_adjustment_settings`) | Accounts > All Accounts screens > Books > Party Adjustments; `GET/PUT /api/v1/party-adjustments/settings` | A rounding limit (10.00 unless set) and an approval threshold (1,000.00 unless set); see `app/party_adjustments` | Step 7: how much a payment may round off, and when a write-back needs a second person holding `PARTY_ADJUSTMENT_APPROVE` |
| Approval Levels | Settings > Firm > Approval Levels (purchase levels need `PURCHASE_MANAGE_SETTINGS`) | None: one approval is enough. A rule is a document type (purchase order, purchase bill), a level 1 to 3, a from-amount and a role | Steps 2 and 6: a document at or above a rule's amount needs each level signed in order, by different people, the last signature approving. Approving early is refused naming the level and role; a total that rises after a signature needs that level again; *Reject* needs a reason |
| Purchase Budgets | Settings > Buying > Purchase Budgets | None | Step 2: a monthly amount by branch and category; *Used* is the value before tax of approved orders dated in the month. Going over warns or needs approval, as chosen under *Past a purchase budget* in Purchase Settings |
| Numbering Series | Settings > Firm > Numbering Series; `/api/v1/document-framework/numbering-rules` | Per document type; see `app/document_framework` for the fields | The number on every document above |
| Messaging (`messaging_settings`) | Settings > Firm > Messaging; `GET/PUT /api/v1/messaging/settings` | `is_enabled` off: a firm with no row queues and records nothing. `due_soon_days` 3; `overdue_every_days` 7; `overdue_stop_after_days` 90 (A12) | Payment due and overdue reminders. `MESSAGING_FRAMEWORK.md` |
| Control accounts | Per firm, `ControlAccountPurpose` | `INELIGIBLE_INPUT_TAX` is *Input Tax Not Claimable*, 5450, an expense account | Where tax the firm may not claim posts. A firm without it mapped is refused the bill, not posted wrong |

### On the supplier, the product and the tax rules

| Setting | Where | Choices / default | What it changes in the chain |
| --- | --- | --- | --- |
| GST registration type | Masters > Vendors > the supplier, `gst_registration_type` (`app/vendors/gst_registration.py`) | REGULAR, COMPOSITION, UNREGISTERED, OVERSEAS, SEZ. Null: a GSTIN reads as REGULAR, none as UNREGISTERED | A **declared** Composition, Unregistered or Overseas supplier charges no GST: the bill's lines carry none and no credit is claimed (A37). A null type never drops tax, even with no GSTIN on file. A *Reverse charge* rule still applies. Reaches the tax engine as `vendor_type` |
| Supplier e-invoices | Supplier, `issues_e_invoices` (form; import column `EInvoicing`) | Off | Step 5: the bill from such a supplier is warned about until it records the supplier's IRN, under `supplier_irn_check` |
| Preferred supplier | Masters > Products > the product, `preferred_vendor_id` (A18) | Null | Before step 1: *Below reorder level* drafts the order to this supplier, else to the one last billed |
| Payment terms | Masters > Vendors > the supplier, `payment_terms_days` | Default 0 | A bill's due date defaults from it when nobody typed one (`app/purchase_invoice/services/msme.py`) |
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

The receipt records the **e-way bill** the goods came on, `eway_bill_number`
(12 digits) and `eway_bill_date` -- typed here, or once the receipt is completed
with `PUT /api/v1/goods-receipts/{id}/eway-bill`, audited. A receipt whose total
is above the firm's `eway_bill_limit` with no number carries `eway_bill_warning`;
for an unregistered supplier the warning says the e-way bill is the buyer's to
raise (rule 138). Warned, never refused (§78 row 6). A batch-tracked line may
carry the batch's `mrp` and `selling_price`, which the batch keeps (A41).

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

A draft invoice posts nothing. The bill records the **supplier's IRN**,
`supplier_irn` (64 hexadecimal characters, read off the QR code, stored lower
case); on an approved bill, `PUT /api/v1/purchase-invoices/{id}/supplier-irn`,
audited. `irn_warning` on the response says when the supplier e-invoices and
the bill has none (`supplier_irn_check`, CGST rule 48(4)), and, whatever the
setting, when another bill already carries the same IRN. Warned, never refused:
the firm still owes the money (§78 row 5).

**The supplier's bill itself** (PG-4, §86 row 16) is kept with the bill, and
the delivery challan or a photo of the goods with the receipt:
`POST /api/v1/purchase-invoices/{id}/files` and
`POST /api/v1/goods-receipts/{id}/files` take one multipart `file` (PDF, JPG or
PNG, at most 10 MB, checked by its contents) and an optional `caption`;
`GET .../files` lists them without their bytes, `GET .../files/{file_id}/content`
downloads one under its own name and type, and `DELETE .../files/{file_id}`
removes one, soft and audited. Viewing needs the document's view code
(`PURCHASE_VIEW`; on a receipt `PURCHASE_RECEIVE` also reads); uploading and
removing need `PURCHASE_CREATE` or `PURCHASE_UPDATE` on a bill and
`PURCHASE_RECEIVE` on a receipt. Files can be added at any status -- a paid
bill still needs its paper -- and posting never reads them. List rows carry
`attached_file_count` for a paper clip. The bytes live in the firm's own store
(`docs/API_AND_PERSISTENCE_CONVENTIONS.md`).

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

**TCS the supplier charged (206C(1H), PG-6)** is typed on the bill as a rate,
an amount or both (a typed amount wins; a rate alone is taken on the grand
total including GST). It is not GST and changes no taxable value. Approving
adds one leg and grows the payable by it -- on the bill above with 1.18 of TCS:

```
Dr  1430 TCS Receivable                    1.18
    Cr  2100 Trade Payables                     1181.18   (with the lines above)
```

The supplier is owed `grand_total + tcs_amount - tds_amount`; the payment,
the outstanding list and the payables report all read that figure, and
*TCS paid to suppliers* (`/reports/tcs-paid`) totals it by quarter for the
26AS match.

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

**Paid over the counter: approve and pay in one step** (PG-3, §86 #19).
`POST /api/v1/purchase-invoices/{id}/approve` takes an optional body
`{"payment": {"method": "CASH"|"BANK", "payment_mode", "amount",
"payment_date", "instrument_reference", "instrument_date", "narration"}}`.
With it, approving the bill (step 6) also records an ordinary payment -- the
row `POST /payments` writes, numbered from the same series -- allocated to that
bill, and both are staged and committed once (`stage_approve` then
`PaymentService.create`, which never commits). The amount defaults to what the
bill owes once approved (its grand total) and the date to the bill's own; less
leaves the rest outstanding, and more is refused rather than kept as an
advance, which is recorded on its own through Payments. Any refusal -- more
than the bill owes, no cash or bank account mapped -- rolls back the approval
too, including the receipt a bill typed alone (§38) would have completed. The
block needs `PAYMENT_CREATE` on top of `PURCHASE_APPROVE` (403 without it);
without the block the approval is unchanged. Undoing the money is the usual
`POST /payments/{id}/reverse`, which leaves the bill approved and owing.

### What is owed, by supplier and month, against 2100

`GET /api/v1/purchase-invoices/reports/payables` (backlog §85, PG-2;
`app/purchase_invoice/services/payables_report.py`) answers "what do we owe
each supplier" as at any date: one row per supplier, each open bill's
outstanding in its invoice month (or due month, `basis=due`), older bills in
**Older**, and a **Credits** column for everything on the supplier's account
that names no bill -- a return off a goods receipt, the part of a return or
debit note its bill could not absorb, and money paid on account -- less the
credit already set against bills and what suppliers paid back. **Outstanding**
therefore sums every document that posts to 2100, and the report checks its
total against the 2100 balance at the as-of date read from the journal
(`books_check.ledger_balance`, `books_check.difference`); a difference is
shown, never hidden. `view=paid` shows the payments per supplier per month,
checked against what they debited 2100 with. It replaces the old *Vendor
outstanding* report (`/reports/outstanding`, kept one release), which listed
bills alone and so overstated what was owed by the supplier credits
(D-BUY-32). A branch filter drops the books check: payments and refunds name
no branch.

### A supplier abroad: the bill and the payment in its currency (PG-12 part A)

A supplier with `currency_code` set (say USD) starts each new bill in it; a
bill may also name `currency_code` and must then carry `exchange_rate`, the
rupees one unit was worth on the bill's date. Rates and totals stay in USD as
typed; `base_tax_total` and `base_grand_total` are the rupees, each leg
converted and rounded on its own. A bill of 10 at 100 USD booked at 83:

```
receipt   Dr 1200 Inventory           83,000.00   (the order's rate)
          Cr 2300 GRNI                83,000.00
bill      Dr 2300 GRNI                83,000.00
          Cr 2100 Payables            83,000.00
```

Paid in full in USD at 84 (`POST /payments` with `currency_code` "USD",
`exchange_rate` 84, `amount` 1000 and the allocation in USD):

```
          Dr 2100 Payables            83,000.00   (the bill's rupee value)
          Dr 4950 Exchange Gain/Loss   1,000.00   (a loss; a gain is a credit)
          Cr 1000 Cash                84,000.00   (1,000 x 84)
```

Part of it pays in proportion: 400 USD at 84 clears 33,200 (400 x 83) and
costs 33,600, leaving 600 USD and 49,800 owed. The outstanding list shows both;
the allocation keeps `currency_amount`, `base_amount` and the rupees paid as
`amount`. Reversing the payment mirrors all three legs. Rupees cannot be set
against the bill, and *Paid now* refuses it. `POST /finance/fx-revaluation`
restates the open USD at a period end and reverses itself the next day. The
ledger rules are in `docs/LEDGER_POSTING_RULES.md`.

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
(1300). A return off the bill (or off the receipt the bill billed) and a
debit note off the bill credit 5450 for
their share, in the same proportion, so a blocked line nets out like any other.
`INELIGIBLE_INPUT_TAX` is the control account behind 5450; the full rule is
under "Tax the firm may not claim is a cost, not input tax" in
`LEDGER_POSTING_RULES.md`.

On GSTR-3B, blocked credit is reported in 4(A)(5) and reversed in 4(B)(1)
(`itc_reversed_blocked`); ineligible credit never enters 4(A) and is shown in
4(D)(2) (`itc_ineligible`). A return's or debit note's blocked share is never
a 4(B)(2) reversal, because nothing was claimed.

### The GST purchase register and HSN summary

Reports > Financial > *GST purchase register* and *HSN summary of purchases*
(`GET /api/v1/purchase-invoices/reports/gst-register` and `/hsn-summary`,
backlog 86 row 17) list a period's approved and closed bills by tax head --
supplier GSTIN, taxable value, IGST, CGST, SGST, cess, tax not claimable
(BLOCKED or INELIGIBLE lines), reverse-charge tax and total -- and the same
inward supplies folded by HSN code and unit. Heads are read off each line's
stored components through the same `_bucket` GSTR-3B uses, leaving out tax
included in the price; a product with no HSN sits under a blank code. Supplier
debit notes are not netted in yet: a note keeps one tax amount per line, not
its components by head.

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

### Rule 37: a bill unpaid 180 days

`GET /api/v1/gst-returns/rule37`, behind **Accounts > All Accounts screens > Tax filing > Rule 37 (180
days)**, lists every bill dated (the supplier's date, else ours) more than 180
days ago with credit
claimed and money still owed -- what it owes read from the payments service, so
payments, returns and debit notes all count -- and the credit to reverse in
proportion to the unpaid share, less what already stands reversed; a bill paid
since shows its reclaim. Under `rule37_mode` the firm chooses OFF, REPORT
(default: listed, nothing posted) or POST, under which
`POST /api/v1/gst-returns/rule37/post` posts. Posting moves the credit to
*Input Tax Not Claimable* (5450) and a reclaim moves it back, one journal per bill,
recorded in `itc_reversals` (`LEDGER_POSTING_RULES.md`). GSTR-3B reports the
reversals in 4(B)(2) and reclaims in 4(A)(5) and 4(D)(1). Interest under s.50
is not computed.

---

## What release 1.2.0 added to the chain

Each is off, or has no effect, until a firm switches it on or sets a figure;
nothing in the traced chain above changes for a firm that does not.

- **Requisitions.** A requisition (Buy > All Buy screens > Documents >
  Requisitions, or *Raise requisition* on Reports > Operational > Below reorder
  level) is submitted and approved, and *Convert to orders* makes one **draft
  order per supplier**, priced from that supplier's terms. It moves nothing.
- **Supplier terms on the order.** A supplier's catalogue (their code, price,
  pack, minimum order and multiple, lead time) and standing discount fill a new
  order's blank price and discount, the expected date, and a hint for the
  multiple.
- **Amending an approved order** (Purchase Orders > Amend) keeps each revision
  and asks for approval again when the total rises past the approver's limit.
- **Approval levels and approval limits** (see the table above) decide who may
  approve an order or a bill: levels by amount and role, limits by role.
- **Quality inspection.** For a product or category marked *Inspect on
  receipt*, received goods wait in quarantine until released or rejected
  (Buy > All Buy screens > Documents > Quality Inspection); the receipt's
  ledger entry is unchanged.
- **Payment runs** (Buy > All Buy screens > Money > Payment Runs). Pick the
  bills due by a date, approve once (`PAYMENT_RUN_APPROVE`, which the cashier
  does not hold), and one payment per supplier is posted as step 7 posts it; a
  bank file is exported.
- **Landed costs** (Buy > All Buy screens > Money > Landed Costs). Freight,
  duty or handling is spread over completed receipts by value, quantity or
  weight: the share belonging to stock still on hand raises the stock's average
  cost, and the share belonging to goods already sold goes to cost of goods
  sold. The journal is Dr Inventory and Cost of Goods Sold, Cr *Expenses
  Included in Valuation*, so the chain's receipt and bill entries are not
  disturbed. See `LEDGER_POSTING_RULES.md`.
- **Money in more modes.** A payment records Cash, UPI, cheque, NEFT or card
  with its number and date; a post-dated cheque is held, posting nothing, until
  its date.

---

## Goods coming back

`POST /api/v1/purchase-returns`. Completing a return takes the stock off and,
whatever the outcome (see "Undoing it"), posts it in up to two parts
(D-BUY-26):

- **Before billing** -- the part of a goods receipt line no approved bill has
  reached yet: **Dr GRNI / Cr Inventory** at the receipt's cost. No payable and
  no tax, because neither existed yet, and what is left to bill on the receipt
  line falls by that much -- the supplier bills what the firm kept. A bill for
  more is refused, on save and at approval, naming the line. The receipt's
  response shows `left_to_bill_quantity` and `left_to_bill_amount` per line and
  in total.
- **After billing** -- anything beyond that, and every line raised off a bill:
  a debit note, **Dr Trade Payables** with its tax-inclusive value, input tax
  reversed head by head as the bill claimed it.

Example: 6 received at 100 + 18%, 3 billed, 4 returned -- 3 come off GRNI
(300), 1 is a debit note (Dr Payables 118, Cr CGST 9, Cr SGST 9), and
Inventory is credited 400. The return line records the split
(`unbilled_quantity`, `grni_amount`).

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
| Cancel a **completed** receipt | reversed, line by line | mirror journal cancels it; refused outright once the receipt has been invoiced, or while a completed return stands against it |
| Purchase return, completed | stock goes back off | posted; what went back before billing debits GRNI at the receipt's cost with no tax (D-BUY-26); the rest is a debit note, input tax reversed head by head (CGST, SGST, IGST) as the bill claimed it, whether raised off the bill or off the receipt it billed (D-BUY-28); blocked tax credits 5450, not input tax |
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
37, the supplier's IRN and the e-way bill on the receipt were built the same day,
§78 rows 4-6):

- Nothing: rows 4-6 of section 6.3 were all built on 2026-10-02.

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
