# Purchasing: the workflow, and what it touches

How a firm buys — from raising an order to paying the supplier — and which
other modules each step depends on.

Verified against the code and the running backend on 2026-08-18. Every status,
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

**Only three transitions do anything outside their own module**, and knowing
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

### The four statuses nothing sets

`PurchaseOrderStatus` also declares `PARTIALLY_ORDERED`, `ORDERED`,
`PARTIALLY_RECEIVED` and `RECEIVED`. **No code moves an order into any of
them.** `GoodsReceiptService` never imports `PurchaseService`, and completing a
receipt leaves the order exactly where it was.

So an order that has been received in full still reads **APPROVED**. The
`ORDERED` value that does appear in `purchase_service.py` is a *line* status,
not the order's.

Two consequences worth knowing before relying on them:

- the Purchase Orders status bar offers no Received segment, because there
  would never be a row in it;
- "what is still outstanding" is computed from the receipts themselves
  (below), never read off the order.

Advancing the order alongside its receipts is a real gap, not a subtlety. It
needs a decision about who owns the transition — the receipt, or a service
above both.

### What a line carries

Product, ordered quantity, free quantity, unit price, discount, tax profile,
purchase UOM and inventory UOM, warehouse and storage node, batch and expiry
requirements, remarks. Header carries vendor, branch, warehouse, buyer,
purchase type, currency, expected delivery and the document number.

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
   against that order. Over-receipt is refused unless the receipt sets
   `allow_over_receipt`, and then only up to `over_receipt_percent`;
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

> CLAUDE.md still says automatic GL posting from invoices is not built. That is
> out of date for this module: `post_purchase_invoice` exists and runs on
> approval.

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
this is for services and expenses rather than goods.

---

## Not built

- **The purchase order's received status.** Described above. The enum values
  exist; nothing sets them.
- **RFQ and Vendor Quotation.** No model, table, service, endpoint or API
  client method for either. The Sourcing group in the sidebar is the extension
  point; both open a placeholder.
- **Purchase analytics.** No `/api/v1/purchases/reports/*` endpoints. The
  Analytics entry is a placeholder; the reports catalogue's "Purchase" section
  is populated entirely by goods-receipt endpoints.
- **Multi-status list filtering.** `GET /api/v1/purchases` accepts one status
  per request, which is why the Purchase Orders "Open" segment filters
  `SUBMITTED` alone while the dashboard's Open card counts five statuses. See
  `desktop/docs/PURCHASE_NAVIGATION_UX.md`.

## Where the screens are

`desktop/docs/PURCHASE_NAVIGATION_UX.md` covers the navigation: five entries
under Purchases, the status bar inside Purchase Orders, and the same treatment
for Goods Receipts. The rule both follow is that **a document's status is a
view of one list, not a module of its own**.
