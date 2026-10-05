# Purchasing: the workflow, and what it touches

How a firm buys — from raising an order to paying the supplier — and which
other modules each step depends on.

Verified against the code and the running backend on 2026-08-18; the quantity picture, return outcomes and reverse charge on returns added 2026-10-02. Every status,
transition and side effect below was read from the service that performs it,
not remembered. Where something is *not* built, this file says so rather than
describing the intent.

## The chain

```
  Purchase Order ──→ Goods Receipt ──→ Purchase Invoice ──→ Payment
   DRAFT              DRAFT             DRAFT               (settlement)
   SUBMITTED          COMPLETED ✱       APPROVED ✱
   APPROVED           CLOSED            CLOSED
   CANCELLED          CANCELLED ✱       CANCELLED
   CLOSED
                          │
                          └──→ Purchase Return
                                DRAFT → APPROVED → COMPLETED ✱ → CLOSED

  ✱ = the transition with a side effect outside its own module
```

Four documents, four separate modules, each with its own permissions, routes
and tables. The sidebar files the last three under Purchases; they are not tabs
of it.

**Only four transitions do anything outside their own module**, and knowing
which is most of understanding this area:

| Transition | What it does |
| --- | --- |
| Goods Receipt → **Complete** | posts stock into inventory |
| Goods Receipt → **Cancel** (after completing) | reverses that stock |
| Purchase Invoice → **Approve** | posts the journal to the general ledger |
| Purchase Return → **Complete** | takes stock back off |

Everything else is paperwork and status.

---

## 1. Purchase Order

`app/purchase` · `/api/v1/purchases` · permissions `PURCHASE_*`

### Lifecycle

```
DRAFT ──submit──→ SUBMITTED ──approve──→ APPROVED
  │                   │                     │
  └───────────────────┴──── cancel ─────────┴──→ CANCELLED
                                              └──→ CLOSED
```

`POST /{id}/submit`, `/approve`, `/cancel`, `/close`, plus `/restore` for a
soft-deleted order.

**Approval cannot be skipped.** `approve` on a draft is refused with *"Submit
the order first"*, so the control point cannot be routed around. Approving
needs `PURCHASE_APPROVE`; a user with only `PURCHASE_UPDATE` sees Submit and
not Approve, so the person raising an order need not be the one committing the
firm's money.

**Approval limits by amount** (backlog 68 row 4, 2026-10-01).
`role_purchase_approval_limits` gives each role a largest order it may approve,
per firm, judged on the order's grand total including tax --
`PurchaseApprovalLimitService` in `app/purchase/services/approval_limit.py`,
the buying sibling of the discount limit. A person's limit is the largest among
their roles that have one; nobody is limited until a limit is set, and a
platform administrator never is. Above it `approve` is refused naming the
amount it needs and the order stays SUBMITTED; the approval that clears it puts
`approval_limit: {order_amount, approver_limit}` on the APPROVED event. Bulk
approve goes through the same `approve_order`, so each row is judged alone. An
order a bill raises (order stage off) is approved with `enforce_limit=False`.
`GET/PUT /api/v1/purchases/approval-limits` (view / `PURCHASE_MANAGE_SETTINGS`);
Settings > Buying > Approval Limits on the desktop.

**Both steps are reachable from two places**, as of 2026-08-18: the workspace
toolbar, acting on the selected row, and the toolbar inside the open order
itself. The second is the one that matches how the decision is actually made
— you read the lines, then approve — and it does not close the document: the
dialog keeps the order the server returned, so the status, the approval note
and both buttons re-gate in place and the timeline picks up the new entry.

**Permission decides whether the button is there; status decides whether it
does anything.** No `PURCHASE_APPROVE` and there is no Approve button at all,
which is the point — somebody who can approve can see that they can, and
somebody who cannot is not shown a control they will never be able to press. An
unsaved order offers neither.

### What an edit does to the status

Nothing, with one exception.

`PUT /{id}` used to write `data.status` straight onto the row. Because
`PurchaseOrderUpdate` defaults that field to DRAFT, a client that said nothing
about the status silently reset the order -- an approved one back to DRAFT, and
a partially received one too, where the receipt resync could never move it
again because it only touches an order already in the receiving part of its
life. The desktop echoed back the status it last read, so from that client the
fault was the mirror image: an approved order could be edited from any amount to
any other and stay approved.

The status is now the lifecycle endpoints' alone. The one status change an edit
causes is deliberate:

| Editing an order that is | Result |
| --- | --- |
| DRAFT or SUBMITTED | edited, status unchanged |
| APPROVED | edited, **returned to DRAFT** -- `purchase.approval_withdrawn` in the history |
| PARTIALLY_RECEIVED or RECEIVED | **refused** |
| CANCELLED or CLOSED | **refused** |

Approving is a statement about a particular document, so changing the document
withdraws it and the order goes round again. A received order is refused because
its quantities and prices are what a goods receipt was matched against and what
stock was posted at -- raise a purchase return instead.

The desktop asks before it opens the editor on an approved order, and disables
Edit entirely for the four refused states, so the rule is visible rather than
discovered through a 422.

### Receiving moves the order, ordering does not

`GoodsReceiptService._resync_order_status` writes `PARTIALLY_RECEIVED` and
`RECEIVED` as receipts complete, and walks the order back down — to
`PARTIALLY_RECEIVED`, then to `APPROVED` — as they are cancelled. The received
quantity is **summed from the completed receipts** every time rather than
incremented, so cancelling retraces the same path instead of needing a second,
subtractive implementation to get wrong.

Only an order already in the receiving part of its life is moved. A DRAFT,
SUBMITTED, CANCELLED or CLOSED order is left alone: receiving against a
cancelled order is a different problem, and quietly reviving one here would
hide it.

**Existing orders were not backfilled.** The resync is event-driven, so an
order fully received before 2026-08-18 still reads APPROVED until its next
receipt event. Sweeping them would rewrite live document status in every firm
store, which deserves its own change.

`PARTIALLY_ORDERED` and `ORDERED` are still declared and still unwritten. The
`ORDERED` that appears in `purchase_service.py` is a *line* status, not the
order's.

Two things follow that are easy to trip on:

- the Purchase Orders status bar offers no Received segment, so a received
  order is visible under All and through the advanced filter, not as its own
  view;
- "what is still outstanding" is computed from the receipts themselves
  (below), never read off the order's status.

### One quantity picture per line, and a billing status (backlog 69 row 5, A33)

Receipts, bills and returns each kept their own idea of how much of an order
line they had dealt with, and the order showed none of it. Since 2026-10-02
`app/purchase/services/line_quantities.py` answers it once, for a whole page of
orders in a fixed number of statements, and the order response carries it:

| Figure | Counts |
| --- | --- |
| received, accepted, rejected, damaged | completed or closed goods receipts against the line |
| returned | completed or closed purchase returns, traced back through the receipt or the bill they were raised off |
| invoiced | **approved** or closed bills, raised off the line or off a receipt of it (a draft has not happened) |
| pending receipt | ordered less received, plus what a *replacement* return reopened |
| to invoice | accepted less returned less invoiced |

All of it is **derived on every read and never stored**: a counter on the line
is one more thing to disagree with the documents. The order also carries
`billing_status` (`NOT_INVOICED`, `PARTIALLY_INVOICED`, `INVOICED`) and
`is_complete` (every line received in full and nothing left to bill) *beside*
its lifecycle status rather than as new statuses, so billing never overwrites
how far receiving got. The figures appear once the order has left draft and are
never sent back on a save.

### What a line carries

Product, ordered quantity, free quantity, unit price, discount, tax profile,
purchase UOM and inventory UOM, warehouse and storage node, batch and expiry
requirements, remarks. Header carries vendor, branch, warehouse, buyer,
purchase type, currency, expected delivery and the document number.

**A line carries something** (D-BUY-53). An order line, a typed receipt line
and a bill line need a quantity above 0 or free goods above 0; a return line
needs a quantity above 0. "Line 2 orders a quantity of 0 and nothing free.
Type a quantity, or leave the line off the order." The refusal is raised where
the document is **saved** -- create, edit, amend -- and not by a preview, where
the line being typed has no quantity yet. A bill line of 0 stands when its
receipt or order line is free goods alone, which is how such a line is billed.
A rate contract line and a supplier's quoted line need a rate above 0.

**A bill line that names no unit takes its source line's** (D-BUY-49).

**A purchase requisition is numbered `PRQ-`**, not the purchase return's `PR-`
(D-BUY-46, migration `20261005_0327` for stores that had already raised one;
numbers already issued stay as issued). For the same reason a rate contract is
`RTC-`, not the customer receipt's `RC-` (D-BUY-57), and a reverse-charge
self-invoice `RSI-`, not the sales invoice's `SI-` (D-BUY-58; migration
`20261005_0328`). **Every document type has a default prefix of its own**: a
number is issued by stepping over numbers of the same type and over journal
references, so two types under one prefix take the same numbers as soon as
one of them posts no journal under its number.
`test_no_two_document_types_share_a_default_prefix` in
`tests/unit/test_purchase_document_series_defaults.py` fails the build on the
next pair.

---

## 2. Goods Receipt

`app/goods_receipt` · `/api/v1/goods-receipts` · permissions `PURCHASE_*`

### Lifecycle

```
DRAFT ──complete──→ COMPLETED ──close──→ CLOSED
  │                     │
  └──── cancel ─────────┴──→ CANCELLED
```

**Only APPROVED purchase orders can be received against.** The desktop's order
picker filters on it (`PurchaseQuery(status: 'APPROVED')`), which is why steps
1 and 2 above are not optional.

### Complete is the step that moves stock

`complete_receipt` validates, then posts. In order:

1. every line still references a real purchase-order line;
2. **received so far + this receipt ≤ ordered**, counted across *all* receipts
   against that order -- completed **and closed** receipts both count, since
   closing a receipt does not send its goods back. Over-receipt is refused for
   every receipt; a receipt used to be able to lift the cap itself with
   `allow_over_receipt` and widen it with `over_receipt_percent`, both on its
   own request body (D-BUY-16). A tolerance, where a firm wants one, is the
   firm's setting and does not exist yet;
3. a product whose profile sets *require batch on receipt* is refused without a
   batch number, naming the product.

Then stock rises by **accepted + free quantity**. Rejected and damaged
quantities are deliberately excluded — the firm did not take them. A
`GOODS_RECEIPT` row lands in the stock ledger; where a batch number was typed,
the goods land in **that batch's** stock row and the batch appears in the
register, rather than in the product's single undifferentiated row.

Completing an already-completed receipt is a no-op, not an error. A cancelled
or closed receipt cannot be completed.

### Cancel reverses the stock

This is the part most easily missed. `cancel_receipt` calls
`_reverse_inventory`, which walks each posted line and reverses its movement,
and records the number of reversed lines on the audit entry. Cancelling a
completed receipt **takes the goods back off the shelf**; it is not a status
change.

Cancelling a draft costs nothing, because nothing was posted. Cancelling
something already cancelled or closed does nothing at all.

### Partial deliveries

Raise a second receipt against the same order. Because the over-receipt check
counts every earlier receipt, the outstanding quantity is always derived rather
than stored, and receiving more than was ordered is refused at completion.

---

## 3. Purchase Invoice

`app/purchase_invoice` · `/api/v1/purchase-invoices` · permissions `PURCHASE_*`

### Lifecycle

```
DRAFT ──approve──→ APPROVED ──close──→ CLOSED
  │                    │
  └──── cancel ────────┴──→ CANCELLED
```

An invoice is raised from one of three sources
(`PurchaseInvoiceSourceType`): `GOODS_RECEIPT`, `PURCHASE_ORDER` or `MANUAL`.
Each line carries `source_document_line_id`, so what was billed can be traced
to what was received.

### Approve posts to the general ledger

`approve_invoice` calls `DocumentPostingService.post_purchase_invoice` **before
the commit**, so a posting failure fails the approval rather than leaving an
approved invoice with no journal. Only a draft can be approved.

The goods value clears the **receipt accrual** rather than touching inventory
again — the stock was already valued at what the receipt cost it. That is why
receiving and invoicing do not double-count.

Not all the tax on a bill is claimable. Each bill line carries an **input
credit** decision (Eligible, Blocked or Ineligible), and what the supplier is
under GST (regular, composition, unregistered, overseas, SEZ) is set on the
supplier; blocked tax is booked as cost, never as input tax. The rules, the
GSTR-2B match and the posting are in `docs/PURCHASE_TO_PAYMENT_FLOW.md`
("GST on the purchase").

---

## 4. Purchase Return

`app/purchase_return` · `/api/v1/purchase-returns` · permissions `PURCHASE_*`

### Lifecycle

```
DRAFT ──approve──→ APPROVED ──complete──→ COMPLETED ──close──→ CLOSED
  │                    │                      │
  └──── cancel ────────┴──────────────────────┴──→ CANCELLED
```

**Two steps, not one.** Approving a return does not move stock; completing it
does, through `record_purchase_return`. Only an approved return can be
completed, and a return with no lines is refused.

For a batch-tracked product the line names the batch being sent back — a
dropdown of that product's registered batches, defaulting to the one the
receipt brought in. There is no free-text batch box, by design.

**Completion sends back only goods that are there** (D-BUY-44, D-BUY-45).
Goods an inspection rejected *for a return* leave the quarantine bucket,
first; anything beyond them leaves sellable stock, and is refused when the
location does not hold it available -- "This location holds 1.0000 available,
so 2.0000 cannot be returned to the supplier from it." -- unless the product
is marked *allow negative stock*. Like a transfer and unlike a dispatch: goods
that have been sold cannot be crated up for the supplier.

### What the supplier gives back, and a bill already paid (A34, D-BUY-20)

A return records an **outcome**, changeable until it is cancelled because the
supplier often decides after the goods have gone: `CREDIT` (the default, set
against a later bill), `REPLACEMENT` (completing the return reopens the order
line for the quantity sent back, so the next ordinary goods receipt against the
same order takes the goods in) or `REFUND` (money in against the return's
credit, `Dr cash or bank / Cr payables`, reversed rather than deleted; the
return cannot be cancelled while a refund stands). A return raised off a bill
that is already paid has nothing on the bill left to come off, so the part the
bill cannot absorb becomes a **supplier credit**. The mechanics, accounts and
routes are in `docs/PURCHASE_TO_PAYMENT_FLOW.md` ("Goods coming back").

**Reverse charge** (#897). When the bill charged tax under reverse charge, the
supplier charged none, so the return carries no tax of its own, and until
2026-10-02 the liability and the input credit the bill raised stayed in full
after the goods went back. A returned line now takes the same share of its bill
line's reverse charge as its value is of the bill line's
(`app/purchase_invoice/services/reverse_charge.py`); completing the return
debits reverse-charge payable and credits input tax per head, the bill's legs
mirrored, and GSTR-3B (3.1(d) and 4(A)(3)) falls by the same in that period. The
supplier's credit note below does the same.

### The supplier's credit note, with no goods back (backlog 68 row 10)

A rate difference or a discount after billing that the **supplier** credits
is recorded as a debit note (`app/debit_note`) carrying the supplier's credit
note number and date -- one event seen from two sides, so one document
(OWNER_DECISIONS A31). It needs nothing of its own: the debit note names the
bill, approving it posts Dr payable / Cr input tax (by head) and price
variance, the bill's outstanding is derived lower, the supplier statement
names the supplier's note, and GSTR-3B 4(B)(2) reverses the credit; cancelling
reverses all of it. Both fields or neither, not dated before the supplier's
bill, and one supplier's number on one live note. A claim on a bill already
paid leaves its excess as a **supplier credit** (decision A4), the same rule as
a return off a paid bill (`docs/PURCHASE_TO_PAYMENT_FLOW.md`). It takes its bill's reverse
charge share off the same way a return does. Reason *Discount after
billing* (`DISCOUNT`) joins price difference and short supply.

---

## 5. Paying the supplier

`app/settlements` · `/api/v1/payments` · `/api/v1/receipts` · `/api/v1/refunds`

Money out to a vendor and money in from a customer are **one document type**
differing only in sign: `SettlementType` is `RECEIPT` or `PAYMENT`.

A settlement posts to the ledger through `DocumentPostingService.post_settlement`,
and `settlements.journal_entry_id` is **NOT NULL** — the defect that column
exists to prevent is a settlement that never reached the books.

A settlement is **reversed, never edited or deleted**: a mirror journal cancels
it, and the allocations stop clearing invoices while still recording what they
had cleared.

---

## What purchasing depends on

| Module | What it provides | Where it bites |
| --- | --- | --- |
| `vendors` | who is being bought from | a purchase order requires a vendor |
| `products` | what is bought, and its batch/expiry rules | `require_batch_on_receipt` decides whether a receipt can complete |
| `branches` | branch, warehouse and storage node | stock posts to the warehouse the line names |
| `uom` | `convert_quantity` per line | purchase UOM → inventory UOM; a factor of 1 short-circuits |
| `tax` | `TaxRuleService.simulate` per line | this **is** the tax calculation, not a preview; it must never commit |
| `batch_serial` | batch, lot, serial and expiry | a batch number on a receipt line resolves to a real batch |
| `inventory` | the stock ledger and stock rows | receipts post here; returns and cancellations reverse here |
| `finance` | the general ledger | invoice approval and settlements post journals |
| `document_framework` | numbering, states, timeline events | every document number and history entry |
| `business` | module and feature gating | a firm without the `PURCHASES` module sees none of this |
| `search` | Ctrl+K over purchase orders | results open the Purchase Orders grid |

Purchasing does **not** touch territory, routes or beat plans — those are
sales-side. It also does not touch credit control: `CreditControlService`
constrains what a *customer* owes, not what the firm owes a vendor.

---

## Use cases

### A straight buy

1. **Purchase Orders → New**, pick the vendor, add lines, save → `DRAFT`
2. **Submit** → `SUBMITTED`
3. **Approve** → `APPROVED`  *(needs `PURCHASE_APPROVE`)*
4. **Goods Receipts → New Receipt**, pick the approved order, set accepted
   quantities, save → `DRAFT` — **no stock yet**
5. **Complete** → stock posts; check **Inventory → Stock Ledger** for
   `GOODS_RECEIPT +qty`
6. **Purchase Invoices → New**, source the goods receipt, **Approve** → the
   journal posts
7. **Payments** → settle the vendor

### A delivery that arrives in two parts

Steps 1–5, accepting part of the order. Raise a second receipt against the same
order and complete it: the over-receipt check counts the first, so the second
can only take what is still outstanding. Note the order still reads `APPROVED`
throughout — see *the four statuses nothing sets*.

### Goods arrive damaged

Enter the damaged quantity on the receipt line rather than the accepted one.
Completing posts **accepted + free** only, so damaged stock never enters the
building on paper. If it was accepted in error, cancel the completed receipt —
that reverses the posting — and receive again correctly.

### Sending goods back

**Purchase Returns → New** against the receipt, choose the batch being
returned, **Approve**, then **Complete**. Stock comes off at completion, not at
approval.

### A batch-tracked product

Type the batch number and expiry on the receipt line. Completion resolves it to
a real batch, and the stock lands in that batch's row. A product whose profile
requires a batch is refused at completion without one, naming the product — the
guard exists so batch-tracked stock cannot enter untracked and surface only at
a recall.

### Buying without an order

Raise the invoice with source `MANUAL`. There is no receipt, so no stock moves;
this is for services and expenses rather than goods. Goods always need an
order and a receipt (`goods_receipts.purchase_order_id` is NOT NULL, and a
bill naming an order is refused, D-BUY-14) -- unless the firm has switched
stages off, below.

### Stage switches: a firm that types only the bill

Built 2026-09-30 (`docs/BACKLOG.md` §38), the twin of the sales stages.
`purchase_workflow_settings` holds one row per firm: `purchase_order_stage`,
`goods_receipt_stage`, and a default branch and warehouse. Every stage defaults
**on**; a firm with no row is on the whole chain. `GET/PUT
/api/v1/purchases/workflow-settings` reads it with `PURCHASE_VIEW` and writes it
with `PURCHASE_MANAGE_SETTINGS`, held by neither purchase role -- turning
receipts off means the bill, not whoever counted the goods in, confirms what
arrived. On the desktop it is Purchases > Purchase Settings > **Buying stages**.

| Orders | Receipts | What a bill names | What saving the bill raises |
| --- | --- | --- | --- |
| on | on | a completed goods receipt | nothing |
| on | off | an approved purchase order | a draft receipt of what the bill charges |
| off | off | the supplier and products | a submitted, approved order and a draft receipt |
| off | on | -- | refused: a receipt continues an order nobody typed |

`PurchaseChainService` (`app/purchase_invoice/services/purchase_chain_service.py`)
raises them through the real services, so the documents are real:

- **Approving the bill completes its own draft receipt first**, so stock arrives
  and *Goods Received Not Invoiced* is posted and cleared in the one step and
  nets to zero.
- **An order the bill raised is submitted and approved by the bill.** Approval
  is a control where a person raises an order; here the person typing the bill
  is the only approver there is (decided by industry standard, 2026-09-28).
- **Cancelling a draft bill cancels the receipt and order it raised.** Editing
  such a draft withdraws them and raises them again from the new lines.
- **An approved bill's cancel leaves the receipt**: the goods are in stock, and
  a purchase return is what takes them back.
- A bill of products carries batch, expiry and free goods per line, which the
  raised receipt takes -- nobody else will ever record them. Stock goes to the
  default warehouse (or the branch's default when none is set).

The desktop follows the switches: Goods Receipts leaves the menu when receipts
are off, the Purchase Orders tab when orders are off (Purchase Settings stays),
and the bill editor offers an order picker or a supplier and product lines in
place of the receipt picker. Purchase returns are never hidden.

---

## Reorder suggestions (backlog 42.9, 2026-10-01)

`GET /api/v1/purchases/reports/below-reorder` (Reports > Operational > *Below
reorder level*) lists each warehouse and product whose available stock is at or
below its reorder level (`minimum_level` where none is set; the stock rows of
one warehouse added up, the highest level on any of them taken). It shows what
is **on order** -- open orders for that warehouse, drafts included, less what
their completed receipts took in -- the product's **preferred supplier**
(`products.preferred_vendor_id`, decision A18, migration 0221) where one is set
and still live and active, else the supplier **last billed** for it -- and a
**suggested** quantity: up to `maximum_level` less available and on order, or
the shortfall to the reorder level where no maximum is set, never negative. The
rate is the last bill's when that bill was the same supplier's and in the stock
unit, else the product's purchase price. A product never billed but with a
preferred supplier can be ordered straight away.

`POST /api/v1/purchases/reorder-drafts` (Purchase Orders > "..." > *Below
reorder level...*, tick rows, **Raise draft orders**) stages one DRAFT per
supplier per warehouse through `PurchaseService.stage_order` and commits once
(`app/purchase/services/reorder.py`). A row no longer below its level, with no
supplier, or with nothing left to order refuses the batch by name. Because
drafts count as on order, running it twice does not order twice.

### Reorder on what sold (backlog 69 row 12, decision A39, 2026-10-02)

`GET`/`PUT /api/v1/purchases/reorder-planning` (`reorder_planning_settings`,
migration 0215; reading takes `PURCHASE_VIEW` or `REPORT_VIEW`, writing
`PURCHASE_MANAGE_SETTINGS`). **LEVELS**, the default and what a firm with no row
gets, is the report above. **SALES** adds every product nobody typed a level
for, per warehouse:

- *daily* = what customers kept over the last `sales_window_days` (90) --
  dispatches less sales returns, each net of its reversals, in stock units,
  dated up to today -- divided by the window. Orders nobody shipped are not
  demand.
- listed when available stock is at or below *daily* x (`lead_time_days` 7 +
  `safety_days` 7), the **reorder point**;
- suggested up to *daily* x (lead + safety + `cover_days` 30), less available
  and on order, **rounded up to whole units**. Cover 30 is "keep a month's
  stock and order back what sold".

A level typed on the stock row always wins over the derived one, as an Odoo
reordering rule or an ERPNext item reorder level does. The report rows carry
`basis` (LEVEL / SALES) and `average_daily_sales`; for a SALES row
`reorder_level` and `maximum_level` are the derived point and target. Lead time
is firm-wide until suppliers carry their own (row 3), and there is no MOQ or
order-multiple rounding until the supplier catalogue exists (rows 1-2).

## Requests for quotation (PG-8, backlog 86 #1, 2026-10-05)

`app/rfq`, routes under `/api/v1/rfqs`, migration `20261005_0309`. An RFQ
asks several suppliers for their prices on a list of products; its number
comes from its own series (`RFQ`, document framework).

- **Lifecycle.** `DRAFT` -> `SENT` -> `CLOSED`, or `CANCELLED` from either of
  the first two. The status moves only through `/send`, `/close`, `/cancel` and
  `/raise-orders`; `PUT /{id}` changes a draft only (lines, invited suppliers
  in `vendor_ids`, dates, notes) and leaves alone what it does not name.
- **Quotations.** One per RFQ and supplier, entered or replaced whole with
  `PUT /{id}/quotations/{vendor_id}` while the RFQ is `SENT`: per RFQ line a
  rate, a discount percent, a lead time and notes. A supplier who was not
  invited is refused, and so is any quote on a closed or cancelled RFQ.
- **Comparison.** `GET /{id}/comparison` lists every supplier's landed rate
  per line -- the rate after its discount, **before tax**: tax follows the
  product and the transaction rather than who quotes, and purchase lines carry
  no tax-inclusive flag, so it would not separate the quotes. Cheapest first
  (ties by lead time), every quote at the lowest rate marked `is_lowest`.
- **Choice.** `PUT /{id}/selections` replaces the whole list of choices, one
  quote per line; a line left out has none. A quote that is not the lowest
  needs a reason, which the line keeps; raising orders checks it again,
  because a quote edited after the choice can stop being the lowest.
- **Raise orders.** `POST /{id}/raise-orders` (needs `RFQ_MANAGE` and
  `PURCHASE_CREATE`) stages one draft purchase order per chosen supplier
  through `PurchaseService.stage_order`, each line at the quoted rate and
  discount, `reference_number` = the RFQ number and `external_reference` = the
  supplier's quote reference; records the order on the invited supplier's row,
  closes the RFQ and, when it was started from an approved requisition, marks
  that requisition ORDERED -- all in one commit.
- **From a requisition.** `POST /from-requisition/{requisition_id}` starts a
  draft RFQ from an **approved** requisition: its lines, and as suppliers the
  ones its lines name plus the products' preferred ones. One live RFQ per
  requisition.
- **Permissions.** `RFQ_VIEW` and `RFQ_MANAGE`, in the purchase group, so the
  purchase executive, the purchase manager and the firm administrator hold
  both.
- **On the desktop** (PR #1128). Buy > All Buy screens > Documents >
  *Requests for quotation* (`desktop/lib/ui/purchases/rfq_page.dart`): the
  list with a status filter, the request window (suppliers invited, lines),
  **Send**, **Enter quotes** (one supplier at a time), **Compare** with the
  lowest landed rate marked and a reason asked for any other choice, **Save
  selections** and **Raise orders**. An approved requisition has a **Create
  RFQ** action.
- **Not built.** Emailing the RFQ to the suppliers: the send-document service
  sends one document to one party with its own PDF, and an RFQ has neither a
  print layout nor a single recipient. Left for later.
- **QA.** TC-BUY-056 to TC-BUY-059 in `docs/qa/06_PURCHASING.md`.

## Rate contracts and blanket orders (PG-9, backlog 86 #2, 2026-10-05)

`app/rate_contracts`, routes under `/api/v1/rate-contracts`, migration
`20261005_0310`. A rate contract agrees with one supplier, for a period
(`valid_from` to `valid_to`), a rate, a discount percent and optionally a
contracted quantity per product; its number comes from its own series (`RC`,
document framework). The purchase orders priced from it are its releases.

- **Lifecycle.** `DRAFT` -> `ACTIVE` (`/approve`, which needs
  `PURCHASE_APPROVE`) -> `CLOSED` (`/close`), or `CANCELLED` (`/cancel`, with
  a reason) from draft or active. **`EXPIRED` is never stored**: an active
  contract whose `valid_to` has passed reads as `EXPIRED` and prices nothing;
  the list filters on it by date. `PUT /{id}` changes a draft only and leaves
  alone what it does not name; `DELETE /{id}` removes a draft only.
- **One contract per product and day.** Approving refuses a product already
  on another active contract with the same supplier for an overlapping period,
  naming it. The supplier's contracts are locked (`with_for_update`) first,
  because overlap is a fact about a set of rows that no key can express.
- **Pricing.** A blank price on an order line takes the contract's rate ahead
  of the supplier's price list and catalogue
  (`docs/PRICING_AND_PROMOTIONS.md`); the line records `rate_source =
  RATE_CONTRACT` and `rate_contract_line_id`.
- **Drawn is derived.** A contract line's `drawn_quantity` is the sum of the
  ordered quantity (free goods excluded) of the order lines naming it whose
  order is approved or later and not cancelled; `remaining_quantity` is
  contracted less drawn, never below zero. Nothing is stored, so cancelling a
  release gives its quantity back with nothing to reverse. An order closed
  short still counts its ordered quantity.
- **Over-drawing warns.** `PurchaseOrderResponse.rate_contract_warning` says
  which contracts the order takes past their quantity, counting itself while
  it is not yet approved -- so the preview, the draft and the approval all
  show it -- and the approval's timeline remark keeps it. It never refuses.
- **Releases.** `GET /{id}/releases` lists the order lines priced from the
  contract, oldest first, with `counts_as_drawn`.
- **Permissions.** `RATE_CONTRACT_VIEW` and `RATE_CONTRACT_MANAGE`, in the
  purchase group; approving takes `PURCHASE_APPROVE`.
- **On the desktop** (PR #1130). Buy > All Buy screens > Documents > *Rate
  contracts* (`desktop/lib/ui/purchases/rate_contract_page.dart`): the list
  with status and supplier filters, the contract window with drawn and
  remaining per line, **Approve**, **Close**, **Cancel** with a reason,
  **Delete** for a draft, and **Releases**. On the phase 2 purchase order a
  line priced from a contract carries a mark on its rate, and an order that
  over-draws shows the warning as a banner.
- **QA.** TC-BUY-060 to TC-BUY-062.

## The rest of backlog 86: where each feature lives (PG-1 to PG-14, 2026-10-05)

Fourteen purchasing features were built on 2026-10-05 (`docs/BACKLOG.md` §86,
`docs/BACKLOG_BUILD_PLAN.md`). RFQ and rate contracts have their own sections
above. The rest are one row each here: what it is, where it is kept and
reached, who may use it, and the document that holds its rule. The QA cases
are TC-BUY-029 to TC-BUY-090 in `docs/qa/06_PURCHASING.md`, written from the
code and not yet run by hand.

| Feature | What it is | Tables and columns | Routes | Permissions | The rule |
| --- | --- | --- | --- | --- | --- |
| **GST purchase register, HSN summary of purchases** (PG-1) | Approved and closed bills by tax head, and inward supplies folded by HSN and unit; approved debit notes and completed returns after billing are minus rows on their own dates | none: read from `purchase_invoice_line_taxes` on every call (`app/purchase_invoice/services/gst_purchase_register.py`) | `GET /purchase-invoices/reports/gst-register`, `/reports/hsn-summary` | `PURCHASE_VIEW` or `REPORT_VIEW` (Reports > Financial) | `docs/PURCHASE_TO_PAYMENT_FLOW.md`, *The GST purchase register and HSN summary* |
| **Payables by supplier and month** (PG-2) | What each supplier is owed by month, with Older, Credits and Outstanding, checked against control account 2100; an Owed / Paid switch | none: derived from `settlement_allocations`, returns, debit notes and advances (`app/purchase_invoice/services/payables_report.py`) | `GET /purchase-invoices/reports/payables` | `PURCHASE_VIEW` or `REPORT_VIEW`; Buy > Money > *Payables by Month* | `docs/PURCHASE_TO_PAYMENT_FLOW.md`, *What is owed, by supplier and month, against 2100* |
| **Cash purchase in one step** (PG-3) | Approving a bill may record its payment in the same commit | none new: an ordinary `settlements` row allocated to the bill | `POST /purchase-invoices/{id}/approve` with a `payment` block | `PURCHASE_APPROVE` and, for the block, `PAYMENT_CREATE` | `docs/PURCHASE_TO_PAYMENT_FLOW.md`, step 7 |
| **Attach the supplier's bill** (PG-4) | PDF, JPG or PNG up to 10 MB on a bill and on a goods receipt, at any status | `document_files`, `document_file_contents` (migration `20261005_0306`); the feature is `ATTACHMENTS` | `/purchase-invoices/{id}/files`, `/goods-receipts/{id}/files` (upload, list, content, delete) | viewing: the document's view code; adding and removing: `PURCHASE_CREATE` or `PURCHASE_UPDATE` on a bill, `PURCHASE_RECEIVE` on a receipt | `docs/PURCHASE_TO_PAYMENT_FLOW.md`, step 5; `docs/API_AND_PERSISTENCE_CONVENTIONS.md` |
| **TDS 194C / 194J worked out** (PG-5) | The supplier names its section; the bill proposes and posts the deduction at approval, a payment proposes it for money ahead of any bill, and it is deducted once | `tds_section_settings`; `vendors.default_tds_section`, `tds_individual_huf`, `tds_technical_services`; on the bill `tds_section`, `tds_base_amount`, `tds_proposed_amount`, `tds_amount` (migration `20261005_0307`) | `/finance/tds-sections/settings`, `/finance/tds-sections/suppliers/{vendor_id}`; `tds_amount` on the approve request | settings: `ACCOUNT_MANAGE`; the proposal: `ACCOUNT_VIEW`, `PAYMENT_VIEW` or `PAYMENT_CREATE` | `docs/LEDGER_POSTING_RULES.md`, *194C and 194J are worked out the way 194Q is* |
| **TCS charged by a supplier** (PG-6) | 206C(1H) collected on top of the bill: a rate, an amount or both; an asset, outside GST's taxable value | `tcs_rate_percent`, `tcs_amount` on the bill; control purpose `TCS_RECEIVABLE` (migration `20261005_0308`) | the bill's own create and update; `GET /purchase-invoices/reports/tcs-paid` | the bill's; the report `PURCHASE_VIEW` or `REPORT_VIEW` | `docs/LEDGER_POSTING_RULES.md`, *TCS a supplier charges the firm is an asset on the bill* |
| **Send the PO by WhatsApp** (PG-7) | The order's **Send** offers WhatsApp beside Email; the firm names the template for the event `PURCHASE_ORDER_SENT`; the order is then marked sent | none new: `messaging_outbox`, and `sent_via` on the order | `POST /messaging/send` with `PURCHASE_ORDER` | `DOCUMENT_SEND` | `docs/MESSAGING_FRAMEWORK.md` |
| **Serial numbers at receipt** (PG-10) | A serial-tracked receipt line names one serial per unit (typed, pasted or a range); completion creates the units; a purchase return names the units going back | `goods_receipt_line_serials` (migration `20261005_0311`), `serial_numbers`, `document_line_serials` | `serial_numbers` on the receipt and return lines; `POST /goods-receipts/serials/expand`; `GET /batch-serial/serials/{id}/trail` | the receipt's and the return's | `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`, *The trail starts at the receipt* |
| **Supplier free scheme on the item** (PG-11) | "Buy 10, get 2" for one supplier or all, of the same product or another; fills a blank free quantity on the order line, and offers another product as a gift line | `supplier_schemes` (migration `20261005_0312`); `scheme_id`, `scheme_name` on the order line | `/api/v1/supplier-schemes` | `SUPPLIER_SCHEME_VIEW`, `SUPPLIER_SCHEME_MANAGE` | below, *Supplier free schemes* |
| **Imports** (PG-12) | A bill and its payment in the supplier's currency with the exchange difference at payment; period-end revaluation; a Bill of Entry that lands customs duty on the stock and claims import IGST | `currency_code`, `exchange_rate`, `base_tax_total`, `base_grand_total` on the bill, `vendors.currency_code` (migration `20261005_0313`); `bills_of_entry`, `bill_of_entry_lines`, `bill_of_entry_documents`, `bill_of_entry_allocations` (migration `20261005_0314`) | the bill and `/payments` with a currency and rate; `POST /finance/fx-revaluation`; `/api/v1/bills-of-entry` | the bill's and the payment's; revaluation `JOURNAL_POST`; `BILL_OF_ENTRY_VIEW`, `BILL_OF_ENTRY_MANAGE`, posting and cancelling `PURCHASE_APPROVE` | `docs/LEDGER_POSTING_RULES.md`, the two sections on a bill in another currency and a Bill of Entry |
| **Fixed assets** (PG-13) | A bill line marked capital goods raises an asset instead of stock; a register, asset classes, depreciation runs, disposal, and the Income-tax block schedule | `asset_classes`, `fixed_assets`, `depreciation_runs`, `depreciation_run_lines` (migration `20261005_0315`); `is_capital_goods`, `asset_class_id` on the bill line | `/api/v1/fixed-assets` (`/classes`, `/depreciation-runs`, `/{asset_id}/dispose`, `/{asset_id}/schedule`, `/reports/it-block-schedule`) | `FIXED_ASSET_VIEW`, `FIXED_ASSET_MANAGE` (accounting group); a run, cancelling one and a disposal also need `JOURNAL_POST` | `docs/LEDGER_POSTING_RULES.md`, *A fixed asset is debited at cost, depreciated by run, and leaves at book value* |
| **Batch-wise PTR / PTS** (PG-14) | Price to retailer and to stockist on the batch, captured on the receipt line and charged by the customer's trade class | `batches.ptr`, `batches.pts`, `ptr` / `pts` on the receipt line, `customers.trade_class` (migration `20261005_0316`); feature `BATCH_PTR_PTS` | the receipt's and the batch's own | the receipt's and the batch's | `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`, *Batch-wise PTR / PTS*; `docs/PRICING_AND_PROMOTIONS.md` |

Four things about them that a reader of this file needs and the rule docs do
not say in one place:

- **Imports and capital goods go through the whole chain** (D-BUY-39,
  D-BUY-40, 2026-10-05), as well as on a bill typed alone.
  - *An import.* The purchase order carries `currency_code` and
    `exchange_rate` (rupees per unit; required for any currency but rupees,
    refused where the order is typed). Its lines are priced in that currency.
    A receipt values the stock in rupees at the order's rate. The bill is in
    the order's currency: one that names none takes the order's currency and
    rate ahead of the supplier's own default, and one in any other currency --
    a USD bill off a rupee order, or rupees off a USD order -- is refused
    naming the order, because it would post almost its whole value to price
    variance. A bill at another rate than the order's posts only the rate
    difference to price variance, through the same posting a bill typed
    alone uses. An edit that leaves the two fields out keeps them; neither
    can change once a receipt has valued goods at them.
  - *A machine.* `is_capital_goods` on the order line is taken by the
    receipt line (the receiver may set or clear it on a draft receipt).
    Completing the receipt moves no stock and accrues nothing for that line,
    and the line keeps the mark. The bill line billing it is capital goods --
    silence takes the mark and needs an asset class, unticking is refused --
    and approval capitalises it exactly as a bill typed alone does. A line a
    receipt has already taken **into stock** is still refused as capital
    goods at the bill, with a message saying to untick it, or to cancel the
    receipt and mark the line on the order or the receipt.
  - A purchase return naming a capital-goods line, off the receipt or off
    the bill, is **refused**: nothing entered stock, so a return has no
    movement to take out. The message says to claim the value with a debit
    note and dispose of the asset under Fixed Assets (D-BUY-41).
  - A debit note or a purchase return against a foreign-currency bill posts
    rupees at the bill's rate (D-BUY-41), and GSTR-2B, rule 37 and rule 42
    read such a bill in rupees (D-CMP-23); `docs/LEDGER_POSTING_RULES.md`.
- **What a bill owes is `grand_total + tcs_amount - tds_amount`**, in every
  place a payable is read: Record Payment, the payables report, *Paid now*.
- **Paid now, TDS and TCS are rupee matters.** A bill in another currency
  offers none of them, and is paid from Payments in its own currency.
- **Posting a Bill of Entry needs the linked receipts completed**: duty lands
  on goods received, and a line no linked receipt carries is an expense.

### Supplier free schemes (PG-11, backlog 86 #25 and #27)

`app/supplier_schemes`, routes under `/api/v1/supplier-schemes`, migration
`20261005_0312`. A scheme is a product, a buy quantity, a free quantity, an
optional other product given free, a period, and either one supplier or none
(every supplier of the product).

- **Same product.** A purchase order line priced inside the scheme's dates
  takes `floor(ordered / buy) x free` as its free quantity -- only where the
  line left it blank. A typed figure is kept and an explicit `0` refuses the
  scheme, the same two answers as a discount (`resolve_supplier_free_goods` in
  `app/core/utils/pricing.py`). The line records `scheme_id` and the label as
  it read then (`scheme_name`, such as `10+2`).
- **Another product.** The free goods go on a line of their own, nothing
  charged. The order preview offers it as a suggestion and the desktop adds
  the line once; saving never invents a line. A line with only free goods is
  priced live and kept (backlog 86 #27).
- **Which scheme.** A supplier's own scheme beats an all-suppliers one. Two
  active schemes of the same reach on one product may not overlap in dates;
  the check holds a lock on the product, because overlap is a fact about a set
  of rows.
- **Downstream.** The receipt and the bill raised from the line inherit its
  free goods. Free goods add units and no value: the receipt's cost per unit
  is the line's value before tax over accepted plus free.
- **On the desktop** (PR #1134). Buy > All Buy screens > Documents > *Supplier
  schemes*; on the phase 2 purchase order the side panel says "Scheme 10+2
  applied" for each line a scheme filled.
- **QA.** TC-BUY-066 to TC-BUY-069.

## Not built

- ~~The purchase order's received status~~ -- built: receiving moves the
  order to PARTIALLY_RECEIVED / RECEIVED (`PurchaseService`), corrected
  2026-09-28.
- ~~RFQ and Vendor Quotation~~ -- built 2026-10-05 (PG-8), server and
  desktop; see *Requests for quotation* above.
- **Left out of the fourteen features of backlog 86**: reading a supplier's
  bill into a draft (OCR); emailing an RFQ; a Bill of Entry in the GST
  purchase register and against GSTR-2B's import rows; purchase returns and
  debit notes in another currency; withholding on a payment abroad (section
  195); capitalising goods already in stock (mark the line capital goods
  on the order or the receipt instead, D-BUY-40); GST on the sale of an asset
  (raise a sales invoice); an Income-tax book posting.
- **Purchase analytics.** The fixed reports exist (register, pending,
  overdue, by vendor, by buyer, by product under
  `/api/v1/purchases/reports/*`, corrected 2026-09-28); an analysis by any
  combination follows `docs/BACKLOG.md` §62.
- **Multi-status list filtering.** `GET /api/v1/purchases` accepts one status
  per request, which is why the Purchase Orders "Open" segment filters
  `SUBMITTED` alone while the dashboard's Open card counts five statuses. See
  `desktop/docs/PURCHASE_NAVIGATION_UX.md`.

## Where the screens are

`desktop/docs/PURCHASE_NAVIGATION_UX.md` covers the navigation: five entries
under Purchases, the status bar inside Purchase Orders, and the same treatment
for Goods Receipts. The rule both follow is that **a document's status is a
view of one list, not a module of its own**.

---

## What each transition reaches outside its own module

*Moved out of `CLAUDE.md` on 2026-09-15 when that file passed the 150k-character limit.*

**Purchasing end to end** (`app/purchase`, `app/goods_receipt`, `app/purchase_invoice`, `app/purchase_return`, `app/settlements`) -- `docs/PURCHASE_FRAMEWORK.md` is the reference: the four documents, their lifecycles, and which transitions reach outside their own module. Only four do -- completing a goods receipt posts stock, cancelling a completed one **reverses both the stock and the journal** as of 2026-08-18, and **the journal follows the stock** as of 2026-08-22 -- the reversal credits inventory with what the movement actually removed, at the moving average, and books the difference from the receipt price to `PURCHASE_PRICE_VARIANCE`. Mirroring the original entry instead credited inventory with a number no movement ever removed and put a seeded store 2,287.42 out in one cancellation -- it reversed only the stock until then, so the GL's inventory balance drifted above the warehouse by the value of every cancelled receipt. Two traps live in that reversal and are worth knowing before writing another one: `reverse_entry` copies the source module and id onto the mirror it posts, so a lookup filtering only on POSTED finds the mirror next time and reverses the reversal (match `reversal_of_id IS NULL`), and **a receipt that has been invoiced cannot be cancelled at all** because the invoice already cleared the accrual -- that is a purchase return. approving a purchase invoice posts the journal, and completing a purchase return takes stock back off -- **and cancelling that return takes its journal back off too, as of 2026-08-22**: until then it reversed the stock and left the payable, the input tax and the inventory credit standing, the same defect `goods_receipt` carried until 2026-08-18 and nobody thought to look for in its mirror; everything else is paperwork and status. `docs/PURCHASE_TO_PAYMENT_FLOW.md` traces order to payment end to end with the ledger lines each step raises, and `docs/SALES_TO_RECEIPT_FLOW.md` does the same for the sale -- quotation, order, delivery note, invoice, receipt -- both driven against a running backend rather than read off the code. Three things to know about an order's state, all of them repaired on 2026-08-18 after being driven against a running server. **Receiving moves the order**: `GoodsReceiptService._resync_order_status` writes `PARTIALLY_RECEIVED` and `RECEIVED` as receipts complete and walks it back as they are cancelled, derived by summing the completed receipts rather than incremented. `PARTIALLY_ORDERED` and `ORDERED` are still declared and still unwritten, and orders received before that date were not backfilled. **Approval cannot be skipped** -- `approve` on a draft is refused with "Submit the order first", and `_assert_order_receivable` now refuses a receipt against anything that is not APPROVED, PARTIALLY_RECEIVED or RECEIVED. It did not: a draft order could be received against and the receipt completed, which posts stock and posts to the ledger, so the approval step was bypassable by any client that did not filter its own picker -- the desktop did, which is why it went unseen, and the unit suite could not catch it because its own fixtures received against a draft. And **an edit no longer decides the status**: see the full-dump trap below. Editing an APPROVED order withdraws the approval and returns it to DRAFT, on the record as `purchase.approval_withdrawn`; editing a received one is refused outright, because its lines are what stock was posted at.
