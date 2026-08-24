# Sale to receipt: stock, and the money

How an offer becomes goods off the shelf and money in the bank, which document
does each part, and where every rupee is recorded.

Everything below was **driven against a running backend** with the seeded
`ELEC01` firm, not read off the code. The money trace is from 2026-08-22; the
table map was measured on 2026-08-24, once the demo history finally held a
quotation and a return to measure. The numbers are the ones the server
produced.

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

## Which tables each step writes

Measured, not read off the models: the chain below was driven end to end
against `ELEC01` on **2026-08-24**, counting every live row in all 162 tables
of the firm store before and after each call. A step's row is exactly what
changed.

| # | Step | Tables written |
| --- | --- | --- |
| 1 | Raise the quotation | `sales_quotations` +1, `sales_quotation_lines` +1, `tax_rule_execution_logs` +1, `document_lifecycle_events` +1, `audit_logs` +2 |
| 2 | Send it | `document_lifecycle_events` +1, `audit_logs` +1 |
| 3 | Customer accepts | `document_lifecycle_events` +1, `audit_logs` +1 |
| 4 | Convert to an order | `sales_orders` +1, `sales_order_lines` +1, `tax_rule_execution_logs` +1, `document_lifecycle_events` +2, `audit_logs` +3 |
| 5 | **Approve the order** | `inventory_transactions` +1, `stock_ledger_entries` +1, `document_lifecycle_events` +1, `audit_logs` +2 |
| 6 | Raise the delivery note | `delivery_notes` +1, `delivery_note_lines` +1, `tax_rule_execution_logs` +1, `document_lifecycle_events` +1, `audit_logs` +2 |
| 7 | Approve the note | `document_lifecycle_events` +1, `audit_logs` +1 |
| 8 | **Dispatch** | `inventory_transactions` +2, `stock_ledger_entries` +2, `journal_entries` +1, `journal_lines` +2, `gl_postings` +2, `document_lifecycle_events` +1, `audit_logs` +6 |
| 9 | Raise the invoice | `sales_invoices` +1, `sales_invoice_lines` +1, `sales_invoice_sources` +1, `sales_invoice_line_taxes` +2, `sales_invoice_accounting_events` +3, `tax_rule_execution_logs` +1, `document_lifecycle_events` +1, `audit_logs` +2 |
| 10 | **Approve the invoice** | `customer_receivable_transactions` +1, `journal_entries` +1, `journal_lines` +3, `gl_postings` +3, `document_lifecycle_events` +1, `audit_logs` +4 |
| 11 | **Record the receipt** | `settlements` +1, `settlement_allocations` +1, `customer_receivable_transactions` +1, `journal_entries` +1, `journal_lines` +2, `gl_postings` +2, `audit_logs` +4 |
| 12 | Raise a sales return | `sales_returns` +1, `sales_return_lines` +1, `sales_return_sources` +1, `sales_return_line_taxes` +2, `tax_rule_execution_logs` +1, `document_lifecycle_events` +1, `audit_logs` +2 |
| 13 | Approve the return | `document_lifecycle_events` +1, `audit_logs` +1 |
| 14 | **Complete the return** | `inventory_transactions` +1, `stock_ledger_entries` +1, `customer_receivable_transactions` +1, `journal_entries` +**2**, `journal_lines` +5, `gl_postings` +5, `document_lifecycle_events` +1, `audit_logs` +7 |

Six things in that table are worth saying out loud, because none is obvious
from the code and two of them contradict a reasonable guess.

**Steps 2, 3, 7 and 13 write nothing but history.** A lifecycle event and an
audit row. That is the difference between paperwork and a movement, and it is
why the "three moments" above are the only ones that matter.

**Approving the order writes to the stock tables** — a reservation is recorded
as a movement with no quantity change, so `inventory_transactions` and
`stock_ledger_entries` both gain a row while the ledger gains nothing. A hold
is a fact about stock, so it lives with stock; it is not a fact about money,
so it never reaches the journal.

**Dispatch writes two stock rows, not one.** The reservation is released and
the goods are issued: two movements, because a stock ledger that jumped
straight from reserved to gone could not explain either.

**Raising an invoice writes tax and accounting rows before anything is
approved.** `sales_invoice_line_taxes` stores the tax breakup per component
so a bill reprints identically a year later, and
`sales_invoice_accounting_events` stages what the approval will post. Both are
written at *draft* time; neither is a ledger entry.

**Completing a sales return writes two journal entries, not one.** The credit
note reverses the sale, and a separate cost entry puts the goods back into
inventory at what the movement actually returned. They are separate because
they answer different questions and are valued from different sources — the
counterparty leg from the document, the stock leg from the movement.

**`tax_rule_execution_logs` grows on every document that prices a line** —
quotation, order, delivery note, invoice, return: five rows for one sale, each
holding three JSON documents. It is the fastest-growing table in the schema
and the reason `scripts/purge_retention.py` exists. Nothing prunes it until
somebody enables the `retention` compose profile.

### The same steps, by what they touch

| Concern | Tables | Written by |
| --- | --- | --- |
| The documents | `sales_quotations`, `sales_orders`, `delivery_notes`, `sales_invoices`, `sales_returns` and their `_lines` | steps 1, 4, 6, 9, 12 |
| Where a line came from | `sales_invoice_sources`, `sales_return_sources`, and `source_document_line_id` on the line | steps 9, 12 |
| The tax charged | `sales_invoice_line_taxes`, `sales_return_line_taxes`, `tax_rule_execution_logs` | every document that prices a line |
| Stock | `inventory_transactions`, `stock_ledger_entries`, `inventories`, `batches` | steps 5, 8, 14 |
| The general ledger | `journal_entries`, `journal_lines`, `gl_postings` | steps 8, 10, 11, 14 |
| What the customer owes | `customer_receivable_transactions`, `customers.current_outstanding` | steps 10, 11, 14 |
| Money that moved | `settlements`, `settlement_allocations` | step 11 |
| History | `document_lifecycle_events`, `audit_logs` | every step |

**`audit_logs` is the one table every single step writes**, which is the point
of it — and it is per store, not central, so this is ELEC01's own trail and no
query can ask what happened across every firm at once.

---

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

**How many copies is a preference, set from beside the Print button.** Each
copy prints as its own page set, labelled so the reader knows which one they
are holding -- Original for Recipient, Duplicate for Transporter, Triplicate
for Supplier are offered without anybody typing them, and a firm may name them
whatever it likes. Choosing none prints one unlabelled copy. Reading the
settings needs only the permission to see the document; changing them needs
`PLATFORM_SETTINGS`.

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

## What a line is discounted by

One rule, in `app/core/utils/pricing.py`, and every sales and purchase document
calls it. In order:

1. an **explicit amount** — what somebody typed in currency,
2. else an **explicit percentage**,
3. else the **customer's standing discount** (`customers.default_discount_percent`),
4. else nothing.

**`None` and `0` are different answers.** Saying nothing takes the customer's
arrangement; sending zero refuses it for this line. That distinction is the
reason the discount fields on the line-write schemas are `Decimal | None` with
no default rather than defaulting to zero, and it is what makes "this customer
gets ten percent, except on clearance stock" expressible at all.

**The rate is read on the server, not sent by the client.** There is no
sales-order or sales-invoice line editor in the desktop, conversions happen on
the server, and an API client would otherwise bypass the arrangement. The
quotation editor is the one screen that types lines, and it *shows* the rate --
prefilled, labelled with where it came from, and overridable -- because a
salesman who cannot see the discount cannot tell that it applied.

**An invoice inherits from the line it bills**, rather than re-reading the
customer: a price agreed on an order in March must not be rewritten by an edit
to the customer master in August. A rate inherits as itself; an absolute amount
is pro-rated by the share being billed.

**The discount reduces the taxable value**, so it is applied before tax and the
ledger books revenue net of it. A ten-thousand line at ten percent posts
`Dr Trade Receivables 10,620 / Cr Sales 9,000 / Cr Output Tax 1,620` — a trade
discount is never an expense.

Two refusals: a discount larger than the line, and a percentage above a
hundred. Neither was refused before 2026-08-23 outside `goods_receipt`; both
produced a negative taxable value, which the tax helpers read as zero tax while
the negative flowed on into the document total.

**Until 2026-08-23 the percentage was stored and never applied** by
`sales_invoice`, `sales_return`, `purchase_invoice` or `purchase_return`. All
four read the discount *amount* alone for both the tax base and the subtotal,
so a ten percent order was invoiced at full price with `discount_percent = 10`
sitting on the line as a lie. The three documents upstream of the invoice did
apply it, which is what made the gap hard to see: the order looked right and
the bill did not match it.

## A discount on the whole bill

A firm that agrees ten percent off an order should not have to type it on every
line. `bill_discount_percent` / `bill_discount_amount` on a quotation, sales
order, delivery note or sales invoice carry the deal; the same precedence
applies (an amount beats a rate), and the header stores the amount applied and
the rate it represents.

**It comes off what the lines already discounted to, never off the gross.** Off
the gross, each discount is computed as though the other had not happened and
the two together take off more than either was agreed to. A 15,000 document
with 500 of line discounts takes 10% of 14,500, not of 15,000.

**It is split across the lines and stored there**, in `bill_discount_amount` on
each line, in proportion to what each line is worth after its own discount.
That is the whole point: tax is charged per line, so a document-level deduction
that never reaches a taxable value reduces no tax, and the customer pays tax on
money they were never charged. The purchase order's `header_discount_amount` is
exactly that shape -- subtracted after tax -- and was deliberately not copied.

Rounding: the shares are quantised and the residual goes to the **largest**
line, so they sum exactly to the figure they split. A document whose lines do
not add up to its own total is one no reconciliation can accept.

**A conversion carries the deal, not the shares.** Converting a quotation gives
the order the bill discount amount and lets it re-split across whatever lines
it ends up with; copying each line's share would agree only for as long as the
two documents held the same lines.

**A return inherits its share** from the invoice or delivery line it credits,
pro-rated by how much of the line is coming back. Crediting the undiscounted
figure would hand back more than was ever charged. A return has no bill
discount of its own to negotiate.

**The printed bill states it** as three rows -- what the lines came to, what
was taken off, what is being taxed -- so the arithmetic is followable. The
line-level "Disc." column stays what was agreed on that line; a share of a
document-level deal is not a line discount and is not shown as one.

## Giving goods away

`free_quantity` on a line is goods supplied at nil value. It is outside the
gross and outside the tax base -- nothing is charged for it -- but stock moves
for it, so it is real inventory leaving the warehouse.

It existed on quotation, sales order and delivery note lines and **not on the
sales invoice**, so a firm could promise, order and dispatch goods free and
then not state them on the document the customer actually reads. A bill showing
ten units when eleven arrived is a bill the customer queries, and the answer
was nowhere on it. The invoice carries it as of 2026-08-23.

**The invoice inherits it from the line it bills**, pro-rated by the share
being billed, the same way an absolute discount is. An explicit figure wins and
an explicit zero refuses the inheritance.

**It cannot exceed what the source line offered.** The goods left on somebody
else's document; a bill claiming free goods nobody dispatched is one the
warehouse cannot reconcile, so it is refused rather than recorded.

The printed bill shows it beside the quantity -- "10 + 1 free" -- rather than
in a column of its own, which would be empty on almost every bill.

The desktop's quotation editor is where a line is given away. It had no field
for it on any screen, so free goods were unreachable without going to the API.

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
