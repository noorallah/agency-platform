# Sale to receipt: stock, and the money

How an offer becomes goods off the shelf and money in the bank, which document
does each part, and where every rupee is recorded.

Everything below was **driven against a running backend on 2026-08-22** with the
seeded `ELEC01` firm, not read off the code. The numbers in the trace are the
ones the server produced.

The mirror of [`PURCHASE_TO_PAYMENT_FLOW.md`](PURCHASE_TO_PAYMENT_FLOW.md),
which does the same for buying. For the territory a sale is filed against, see
[`TERRITORY_FRAMEWORK.md`](TERRITORY_FRAMEWORK.md); for how the tax on a line is
decided, [`TAX_FRAMEWORK.md`](TAX_FRAMEWORK.md).

---

## The chain at a glance

```
  Quotation        Sales Order       Delivery Note      Sales Invoice    Receipt
  ─────────        ───────────       ─────────────      ─────────────    ───────
  raise            (converted)       raise              raise            record
  send             approve ◄── stock APPROVE            APPROVE ◄──      ◄── money
  accept               reserved      DISPATCH ◄── stock   receivable         arrives
     │                    │            leaves, and          appears
     │                    │            cost is known           │              │
  nothing moves     a hold, not     Dr COGS              Dr Receivables  Dr Bank
  no stock          a movement      Cr Inventory         Cr Sales        Cr Receivables
  no ledger         no ledger                            Cr Output Tax
```

**Three moments matter.** Everything else is paperwork:

| Moment | What it does |
| --- | --- |
| **Approving a sales order** | Stock is reserved, and credit is committed |
| **Dispatching a delivery note** | Goods leave, and cost of goods sold is known |
| **Approving a sales invoice** | The customer becomes a debtor |
| **Recording a receipt** | Money actually arrives |

A quotation moves nothing at all. Neither does raising an order, a draft
delivery note, or a draft invoice.

---

## Step by step

### 1. Quotation — a price offered

`POST /api/v1/quotations` → `/send` → `/accept`

`DRAFT → SENT → ACCEPTED`, or `DECLINED` / `CANCELLED`.

**Nothing moves.** Creating, sending and accepting a quotation left the
customer's outstanding, the unapplied advance, every reserved and on-hand
quantity and the journal count identical — checked, because a document that
quotes prices and computes tax looks like it ought to.

`EXPIRED` is **derived from `valid_until`, never stored**. Nothing sweeps the
table at midnight, and a job that had not run yet would let a stale quote
through; an expired quotation simply cannot be accepted or converted.

The quotation is optional. A firm can raise a sales order directly.

### 2. Convert — the offer becomes an order

`POST /api/v1/quotations/{id}/convert`

Conversion builds the order through `SalesOrderService.create_order`, so credit
control, tax at the order's date and document numbering all happen **on the
order** rather than being copied from the quote. A second conversion is refused
by name: *"already became SO-2026-2027-000013"*.

### 3. Approve the order — **stock is reserved, credit is committed**

`POST /api/v1/sales-orders/{id}/approve`

Two things happen, in this order, and the order matters:

1. **Credit is assessed.** Under `WARN` the assessment is recorded on the
   order; under `BLOCK` it raises *before* anything is reserved. Credit is
   committed here because approving is the promise — invoicing only bills it.
   Exposure is `current_outstanding - unapplied_advance + this document`.
2. **Stock is reserved.** `reserved_quantity` per line.

A reservation is **a hold, not a movement**. On-hand is unchanged; available
falls by the reserved amount. In the trace, 907 on hand stayed 907 while
available went 907 → 903.

**No ledger entry.** Nothing has left the building and nobody owes anything.

### 4. Raise the delivery note

`POST /api/v1/delivery-notes`

`DRAFT → APPROVED → DISPATCHED → COMPLETED`, or `CANCELLED` / `CLOSED`.

The note names **only the sales order** it delivers — customer, branch and
warehouse all come from the order, and each line names a `sales_order_line_id`
rather than repeating the product. There is no way to deliver something the
order does not contain.

A draft or approved note still moves nothing.

### 5. Dispatch — **the goods leave**

`POST /api/v1/delivery-notes/{id}/dispatch`

This is the first step that moves anything.

- **The order's reservation is released** for the delivered quantity, batch by
  batch, ranked by earliest expiry — so the batch freed is the one the issue
  then draws from.
- **Inventory falls** by the delivered quantity.
- **The ledger gets the cost of the sale:**

```
Dr  5200 Cost of Goods Sold              401.95
    Cr  1200 Inventory                           401.95
```

**Valued from the movement, not from the invoice.** Those four units sold for
₹250 each; they left stock at the moving average of ₹100.4875. Cost of goods
sold is what the warehouse gave up, and the difference between the two is the
margin — which appears on its own, as revenue minus cost, rather than being
computed anywhere.

Two refusals guard this step: available stock short of the delivered quantity,
and a reservation that does not cover it (unless the note allows over-delivery).
A failed posting **fails the dispatch** — stock that has moved with no
accounting entry behind it is the gap this closes.

### 6. Raise the invoice

`POST /api/v1/sales-invoices`

A draft invoice posts nothing. Each line names its source — a delivery note
line, a sales order line, or nothing at all for a manual invoice.

### 7. Approve the invoice — **the customer becomes a debtor**

`POST /api/v1/sales-invoices/{id}/approve`

```
Dr  1100 Trade Receivables              1180.00
    Cr  4000 Sales                              1000.00
    Cr  2200 Output Tax                          180.00
```

**Inventory is deliberately untouched.** The goods were valued when they left at
dispatch; touching stock again here would double-count. This entry is about what
the customer owes, which is a different number entirely — ₹1,180 against a cost
of ₹401.95.

Like dispatch, the posting is allowed to **fail the approval**: a missing
control account or a closed accounting period refuses it rather than leaving an
approved invoice with no journal.

Credit control runs again here, on the same policy as the order.

Two things about the amounts:

- **Revenue takes everything that is not tax** — the taxable base plus line
  charges, header charges and round-off. Those belong in accounts of their own
  and will move there when this posts a line per component; lumping them into
  revenue for now keeps the entry balanced and the receivable exactly equal to
  what the customer owes.
- Tax comes from `TaxRuleService.simulate` per line. Tax that is *included in
  the price* and tax under *reverse charge* are reported separately and are
  **not** added to the document total.

### 8. Record the receipt — **money arrives**

`POST /api/v1/receipts`

```
Dr  1010 Bank                           1180.00
    Cr  1100 Trade Receivables                  1180.00
```

One document type covers both directions — a receipt from a customer and a
payment to a vendor differ only in signs. `settlements.journal_entry_id` is
`NOT NULL`, because the defect it exists to prevent is a settlement that never
reached the ledger.

**What an invoice still owes is derived from `settlement_allocations`, never
stored on the invoice.**

An overpayment splits: the balance goes to zero and the remainder becomes an
*unapplied advance*, and only the transaction row remembers the split. That is
why a settlement is **reversed rather than edited or deleted** — a mirror
journal cancels it, the allocations stop clearing but still record what they had
cleared, and the customer's balances are put back by the deltas stored on the
original row rather than recomputed.

Handing an advance back is a **refund** (`POST /api/v1/refunds`), which posts
`Dr Trade Receivables / Cr Bank` and, since 2026-08-22, can be reversed like any
other settlement.

---

## The whole chain, netted

For the traced sale of 4 units at ₹250 with 18% tax, costing ₹100.4875 each:

| Account | Movement |
| --- | --- |
| 1200 Inventory | **Cr 401.95** |
| 5200 Cost of Goods Sold | **Dr 401.95** |
| 4000 Sales | **Cr 1,000.00** |
| 2200 Output Tax | **Cr 180.00** |
| 1100 Trade Receivables | Dr 1,180 / Cr 1,180 → **nil** |
| 1010 Bank | **Dr 1,180.00** |

Stock down 4 units worth ₹401.95, revenue of ₹1,000, output tax of ₹180 owed to
the government, ₹1,180 into the bank, and ₹598.05 of gross margin sitting as the
difference between 4000 and 5200. Receivables return to zero, which is how you
tell the chain completed.

## The verified trace

```
opening:  EXT5M 907 on hand, 907 available     customer owes 133,220.55
          243 journal entries

1  QT-2026-2027-000003   DRAFT → SENT → ACCEPTED
   stock 907/907 unchanged     customer 133,220.55 unchanged     entries 243

2  SO-2026-2027-000014   converted from the quotation, then APPROVED
   stock 907 on hand, 903 available, 4 reserved                  entries 243

3  DN-...-000012         APPROVED
   stock unchanged                                               entries 244

4  DN-...-000012         DISPATCHED
   stock 903 on hand, 4 reservation released                     entries 245
   Dr 5200 Cost of Goods Sold 401.95 / Cr 1200 Inventory 401.95

5  SI-2026-2027-000010   grand total 1,180.00, tax 180.00, APPROVED
   customer owes 134,400.55                                      entries 246
   Dr 1100 Receivables 1,180.00 / Cr 4000 Sales 1,000.00
                                / Cr 2200 Output Tax 180.00

6  RC-2026-2027-000005   1,180.00 allocated to the invoice
   customer owes 133,220.55 again                                entries 247
   Dr 1010 Bank 1,180.00 / Cr 1100 Receivables 1,180.00
```

`scripts/verify_sample_data.py` passed all five checks on all three stores
afterwards.

---

## Sending the bill

`GET /api/v1/sales-invoices/{id}/print` returns the invoice as a PDF, rendered
on the backend so the layout is right in one place and so the same bytes can be
attached to an email when that arrives. Viewing is the permission: a printed
bill shows nothing the screen does not.

**Everything statutory is read from the record, never recomputed.** The tax
components come from `sales_invoice_line_taxes`, the place of supply and the
due date from the invoice itself. Rules are effective-dated, so asking the tax
engine again at print time can answer differently from what the customer was
billed -- which is the whole reason those columns exist.

What a firm owns is the matter around that spine, in
`document_print_templates`, one row per firm per document type:

| Fixed for every firm | The firm's to set |
| --- | --- |
| The document title's presence, both GSTINs, invoice number and date | Title wording, accent colour, letterhead note |
| Place of supply, reverse-charge flag | Bank block, terms, declaration, jurisdiction |
| HSN per line, rate and amount per tax component | Optional columns: discount, batch, expiry |
| The HSN-wise tax summary, total in words | Which copies to print, page size, margins |

A firm that has configured nothing still prints a correct tax invoice: the
platform defaults live in code rather than in seeded rows, so a new firm needs
no setup to bill somebody.

---

## Goods coming back

`POST /api/v1/sales-returns` — `DRAFT → APPROVED → COMPLETED → CLOSED`, or
`CANCELLED`.

Completing a return posts **two** entries, because a sale had two:

```
Dr  4100 Sales Returns                   (the credit note)
Dr  2200 Output Tax
    Cr  1100 Trade Receivables

Dr  1200 Inventory                       (the goods, at what came back)
    Cr  5200 Cost of Goods Sold
```

The credit note is applied up to what the customer owes, and any excess becomes
an unapplied advance — the same split a receipt makes. Cancelling a completed
return reverses both entries, and the cost entry is reversed **at the movement
value** so the gap between the average then and now stays in cost of goods sold
rather than distorting inventory.

---

## Two rules worth carrying

**Stock moves at dispatch; money moves at invoice approval.** They are
deliberately separate events, which is why cost of goods sold belongs to the
delivery note and revenue to the invoice. A firm that dispatches without
invoicing has goods gone and nothing owed — visible, correct, and exactly what
the accounts should say.

**A ledger leg facing stock is valued from the movement; a leg facing the
customer is valued from the document.** Goods arrive at one average and leave at
another. Every forward posting here already followed that rule; three reversals
did not, and all three were fixed on 2026-08-22.
