# The sales module

What the platform can sell with, what decides the money on a line, and — in the
last section — what is missing, checked rather than assumed.

Two documents already cover parts of this and are not repeated here:

- **`docs/SALES_TO_RECEIPT_FLOW.md`** traces one sale from quotation to receipt
  with the ledger lines each step raises, driven against a running backend. Read
  that for *what happens*; read this for *what exists*.
- **`docs/TERRITORY_FRAMEWORK.md`** covers routes, beats and call lists.

---

## The module map

Sales is five document modules, plus the masters and the money either side of
them. Route counts are what the application serves today.

| Package | Documents | Routes | Desktop |
| --- | --- | ---: | --- |
| `app/quotation` | sales quotation | 16 | list, editor, lifecycle |
| `app/sales_order` | sales order | 17 | list, lifecycle — **no editor** |
| `app/delivery_note` | delivery note | 19 | list, editor, lifecycle |
| `app/sales_invoice` | sales invoice | 18 | list, editor (raise and correct), lifecycle, print |
| `app/sales_return` | sales return / credit note | 17 | list, editor, lifecycle |
| `app/sales` | territory, route, beat plan, geography | 63 | six screens |
| `app/customers` | customer, credit policy, receivables | 17 | list, editor, settings |
| `app/settlements` | receipt (money in) | 5 | settlements workspace |

`app/settlements` is one implementation for money in and money out; a receipt
and a payment differ only in signs. It is documented with the purchase side.

## The chain

```
Quotation ──convert──▶ Sales Order ──▶ Delivery Note ──▶ Sales Invoice ──▶ Receipt
   offer                 promise          goods move        money owed      money in
 nothing moves      stock reserved      stock leaves      revenue booked   receivable
                    credit committed    COGS booked       tax charged        cleared
                                                                    │
                                                        Sales Return ◀┘
                                                     goods back, credit note
```

Every step is optional except the one that commits what you need: a firm can
raise an order without a quotation, and an invoice without a delivery note
(`allow_direct_sales_order`). What cannot be skipped is approval — that is where
credit is committed and where the journal is posted.

**Stock moves at dispatch; money moves at invoice approval.** They are separate
events on purpose, which is why cost of goods sold belongs to the delivery note
and revenue to the invoice.

## Lifecycles

| Document | States | Notes |
| --- | --- | --- |
| Quotation | `DRAFT → SENT → ACCEPTED` / `DECLINED` / `CANCELLED` / `CONVERTED` | `EXPIRED` is **derived** from `valid_until`, never stored — nothing sweeps the table at midnight, and a job that had not run yet would let a stale quote through |
| Sales order | `DRAFT → APPROVED → CLOSED` / `CANCELLED` | see the gap list: nothing moves it as deliveries happen |
| Delivery note | `DRAFT → APPROVED → DISPATCHED → COMPLETED → CLOSED` / `CANCELLED` | `DISPATCHED` is where stock leaves, and is deliberately terminal for cancellation |
| Sales invoice | `DRAFT → APPROVED → CLOSED` / `CANCELLED` | approval posts the journal and commits credit |
| Sales return | `DRAFT → APPROVED → COMPLETED → CLOSED` / `CANCELLED` | `COMPLETED` puts stock back and raises the credit note |

Lifecycle states are configuration in `app/document_framework`, not enums the
code branches on — but the status values above are what the services write.

## What decides the money on a line

One rule, in `app/core/utils/pricing.py`, called by every sales and purchase
document. `docs/SALES_TO_RECEIPT_FLOW.md` is the reference; in short:

1. an explicit **amount** beats
2. an explicit **percentage**, which beats
3. the customer's **standing rate** (`customers.default_discount_percent`),
4. which beats nothing.

`None` and `0` are different answers — saying nothing takes the arrangement,
sending zero refuses it for that line.

A discount on the **whole bill** is resolved separately, comes off what the
lines already discounted to, and is apportioned across them and stored on each,
so it reduces the taxable value rather than being subtracted after tax.

**`free_quantity`** is goods given away: outside the gross and outside the tax
base, but real stock leaving the warehouse, and stated on the bill.

Tax comes from `app/tax` — the rule engine is called once per line while the
document is built, on the document's own date.

## Configuration that changes how sales behave

| Concern | Where | Enforced? |
| --- | --- | --- |
| Credit limits | `credit_control_settings`, per firm | Yes — `OFF` / `WARN` / `BLOCK` at sales order and sales invoice approval. A firm with no row warns at 80% and never blocks |
| Territory and route | `app/sales` | A route's effective window decides whether a document may be tagged with it, judged on the document's own date |
| Tax | `app/tax` profiles and rules | Yes, per line |
| Units and packaging | `app/uom` | Yes — every line converts, with a `factor = 1` short-circuit |
| Industry features | `app/business` | `EXPIRY_TRACKING`, `BATCH_TRACKING`, `SERIAL_NUMBER`, `WARRANTY`, `BARCODE`, `ATTACHMENTS` and others gate fields on sales documents |
| Document numbering | `app/document_framework` | Per firm, per document type |
| Print layout | `document_print_templates` | Per firm, per document type — invoice only today |

## Permissions

Seeded in `app/identity/system_seed.py`. Firm-owned, so every one is checked
together with active `UserFirm` membership for the `X-Firm-ID` header.

`SALES_VIEW`, `SALES_CREATE`, `SALES_UPDATE`, `SALES_APPROVE`, `SALES_CANCEL`,
`SALES_IMPORT`, `SALES_EXPORT`, `SALES_RETURN`, plus the three narrower creates
`SALES_QUOTATION_CREATE`, `SALES_ORDER_CREATE`, `SALES_INVOICE_CREATE`, and the
two roles `SALES_EXECUTIVE` and `SALES_MANAGER`.

Customer-side: `CUSTOMER_VIEW/CREATE/UPDATE/DELETE/RESTORE/IMPORT/EXPORT/SUPPORT`
and `CUSTOMER_MANAGE_SETTINGS`. The last is deliberately **not** granted to
`SALES_MANAGER`: the role a credit limit constrains must not be able to switch
it off.

## Reports

Twenty-four report endpoints, all reachable from the Reports workspace:

| Module | Reports |
| --- | --- |
| Quotation | conversion, register |
| Sales order | register, pending, back-orders, by-customer, by-salesman, by-territory |
| Delivery note | register, pending, partial, by-route, by-salesman, by-warehouse |
| Sales invoice | register, summary, pending, overdue, reconciliation, customer-outstanding |
| Sales return | register, reconciliation, by-customer, by-product |

Every module also has `/import`, for a staged batch that commits once — an
import whose fifth row clashes must not leave the first four written.

Two inconsistencies in that surface, both cosmetic and both real: the sales
invoice exports at `/export/csv` where the other four use `/export`, and it is
the only one of the five with no `/summary` — its workspace cards read
`/reports/summary` instead.

---

# What is missing

Checked on 2026-08-23 against the route table, the desktop tree and the models,
not from memory. Ordered by what it costs a firm. The first was closed the same
day and is kept here, struck through, because the reasoning is worth keeping.

## 1. ~~A sales invoice cannot be raised from the desktop~~ — closed 2026-08-23

This was the largest gap in the module. There was no invoice editor, no "bill
this delivery note" action, and no call to `create('sales-invoices', …)`
anywhere in `desktop/lib`, so a firm using only the desktop could quote, order
and dispatch and then not bill — while `POST /api/v1/sales-invoices` worked and
`SALES_INVOICE_CREATE` sat seeded with no screen checking it.

**New Invoice** on the sales invoice workspace now opens an editor that bills a
delivery note. It is backed by `GET /api/v1/sales-invoices/billable`, which
answers with the documents that still have something left to bill and, per
line, what is dispatched, what earlier invoices already took, and what remains.
That endpoint exists because a client cannot work the remainder out for itself:
one that guessed would offer paperwork the save then refuses, and on a firm
with 58 delivery notes and 49 invoices that is a refusal nine times in ten.

The remaining quantity is derived through the same helper `create_invoice`
uses, so the number offered is the number the save accepts. Cancelling an
invoice puts its quantity back on the list.

The list carries **two** kinds of source: dispatched delivery notes, and
approved sales orders that nothing has shipped against. An order drops off the
moment it has any delivery note, and that rule is load-bearing rather than
tidy: `_already_invoiced_quantity` is keyed on the source **line** id, and an
order line and the delivery line raised from it are different ids — so
offering both would let each be billed in full and no guard anywhere would
notice the customer had been charged twice.

A **draft** can also be reopened and corrected, against `PUT
/api/v1/sales-invoices/{id}` — a route that existed and which nothing called,
so a mistyped draft could only be cancelled and re-raised. Editing is refused
once the invoice is approved: the journal is posted and the customer owes the
money, so a correction is a cancellation and a fresh bill. While editing, a
line may keep what the draft already bills **plus** whatever is still unbilled
elsewhere — the draft's own quantity counts against the source line and would
otherwise be subtracted from the number the user is allowed to keep.

## 2. A sales order cannot be raised directly from the desktop

Same shape, smaller cost. An order can only appear by converting a quotation,
so a phone order has to be typed as a quotation and immediately accepted.
`POST /api/v1/sales-orders` exists and the history generator uses it.

Partly relieved on 2026-08-23: an approved order can now be **billed**
directly, so a firm that invoices before dispatch is no longer stuck. Raising
the order still needs a quotation.

## 3. A sales order's status never moves as it is delivered

`SalesOrderStatus` declares `DRAFT`, `APPROVED`, `CANCELLED`, `CLOSED` and
nothing else, and no service resyncs it from delivery notes. The purchase side
does exactly this — `GoodsReceiptService._resync_order_status` writes
`PARTIALLY_RECEIVED` and `RECEIVED` and walks them back on cancellation.

The quantities *are* tracked, which is why the pending and back-order reports
work; it is the status that is static. A fully delivered order and one nothing
has shipped against both read `APPROVED`.

## 4. Only two documents can be printed

`GET /purchases/{id}/print` and `GET /sales-invoices/{id}/print` are the whole
of it. Missing, in the order a distribution firm would want them:

- **A delivery challan.** Goods travelling without paperwork is the problem;
  this is the document that should accompany them.
- **A quotation.** An offer that cannot be sent to the customer as a document.
- **A credit note** for a sales return.

The renderer (`app/sales_invoice/services/invoice_pdf.py`) and the per-firm
template table are general enough to serve all three.

## 5. Optimistic concurrency stops before the invoice

| Module | Accepts `If-Match` | Publishes `version` |
| --- | --- | --- |
| Quotation | yes | yes |
| Sales order | yes | yes |
| Delivery note | yes | yes |
| Sales invoice | yes | yes |
| Sales return | yes | yes |

**Closed 2026-08-23.** Two people editing the same draft invoice was
last-one-wins, silently, and the sales return was the odder case: it published
a version a client could read and accepted no precondition built from it. Both
now accept `If-Match` and answer an `ETag`, and the invoice publishes its
`version` on the response the way the other three sales documents do. Closing
it was a precondition for the invoice editor rather than a tidy-up — the update
replaces the whole line collection, so a lost race costs every line somebody
entered.

## 6. The product's selling price is never used

`products.selling_price` and `products.mrp` are columns nothing reads. No
document defaults a line's `unit_price` from the product; every price is typed,
including in the quotation editor, which is the only screen that types lines.

This is the cheapest of these to close and the most immediately visible.

## 7. There is no pricing beyond a single price per product

No price lists, no rate contracts, no customer- or territory-specific pricing,
and no effective-dated price changes — `price_list`, `rate_contract` and their
spellings appear nowhere in `app/`. The customer's standing discount percentage
is the only per-customer pricing the platform has.

## 8. No schemes or promotions

"Buy 10, get 1 free" and "5% off over ₹50,000 on a line" are conditions on a
line with actions on a line — the same shape `app/tax` already implements as an
effective-dated, priority-ordered, first-match-wins rule engine with an
execution log. `free_quantity` and the discount fields are the *result* such a
rule would write; today somebody types them by hand on every document.

Whatever is built must run **before** tax and store its result on the line, for
the same reason the bill discount does.

## 9. No salesman commission

`COMMISSION` is a declared business feature carrying `is_implemented = false`,
which the service refuses to enable. Territory already records which salesman
owns a customer and which round a document was filed against, so the data a
commission run needs is being captured.

## 10. No sales targets or quotas

Nothing to measure the by-salesman and by-territory reports against.

## 11. Sending a bill by email is on the backlog

Deliberately deferred (2026-08-22). The invoice renders to a PDF the desktop
can print; nothing sends it.

---

## Deliberate boundaries, not gaps

Worth stating so they are not "fixed" by mistake:

- **Custom attributes target master data, not documents.** `AttributeEntityType`
  covers products, customers, vendors, branches, warehouses and tax profiles.
  A sales document gains fields by industry gating, not by attributes.
- **`EXPIRED` is derived, not stored** — see the lifecycle table.
- **No `DELETE` on orders, delivery notes or invoices.** Cancel is the reverse,
  and it reverses the stock and the journal with it. Quotations and sales
  returns can be deleted only while `DRAFT`.
- **The desktop warns on credit and never blocks.** A client that blocked on its
  own would enforce a rule the firm may not have chosen, and any other client
  could bypass it. The server's refusal is the boundary.

## Where the code is

| Concern | File |
| --- | --- |
| The five services | `backend/app/{quotation,sales_order,delivery_note,sales_invoice,sales_return}/services/` |
| Discounts and free goods | `backend/app/core/utils/pricing.py` |
| Credit control | `backend/app/customers/services/credit_control.py` |
| Ledger posting | `backend/app/finance/services/document_posting.py` |
| Invoice PDF | `backend/app/sales_invoice/services/invoice_pdf.py` |
| Territory | `backend/app/sales/` |
| Desktop screens | `desktop/lib/ui/{quotations,sales,delivery_notes,sales_returns}/` |
| Traced flow | `docs/SALES_TO_RECEIPT_FLOW.md` |
| Demo data | `backend/scripts/generate_transaction_history.py` |
