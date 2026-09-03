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

Sales is five document modules, plus the masters, the pricing and the money
either side of them. Route counts are what the application serves today,
counted off the routers on 2026-08-24.

| Package | Documents | Routes | Desktop |
| --- | --- | ---: | --- |
| `app/quotation` | sales quotation | 17 | list, editor, lifecycle |
| `app/sales_order` | sales order | 17 | list, editor (raise and correct a draft), lifecycle |
| `app/delivery_note` | delivery note | 20 | list, editor, lifecycle |
| `app/sales_invoice` | sales invoice | 18 | list, editor (raise and correct), lifecycle, print |
| `app/sales_return` | sales return / credit note | 18 | list, editor, lifecycle |
| `app/sales` | territory, route, beat plan, geography | 63 | six screens |
| `app/customers` | customer, credit policy, receivables | 17 | list, editor, settings |
| `app/settlements` | receipt (money in) | 5 | settlements workspace |
| `app/pricing` | price list | 5 | list, editor |
| `app/commission` | commission rule, commission report | 6 | rates and collected, one page |

`app/settlements` is one implementation for money in and money out; a receipt
and a payment differ only in signs. It is documented with the purchase side.

### The tables sales owns

Every one is firm-owned, so it exists **once per store** — a query answers for
whichever schema the connection points at, and no query can span firms. Counts
are `ELEC01` after a standard three-year seed, given so a store that looks
wrong can be compared against one that is not.

| Document | Header | Lines | Also | ELEC01 |
| --- | --- | --- | --- | ---: |
| Quotation | `sales_quotations` | `sales_quotation_lines` | `_attachments`, `_notes` | 29 / 29 |
| Sales order | `sales_orders` | `sales_order_lines` | `_attachments`, `_notes` | 58 / 58 |
| Delivery note | `delivery_notes` | `delivery_note_lines` | `_attachments`, `_notes` | 58 / 58 |
| Sales invoice | `sales_invoices` | `sales_invoice_lines` | `_sources`, `_line_taxes`, `_accounting_events`, `_attachments`, `_notes` | 48 / 48 |
| Sales return | `sales_returns` | `sales_return_lines` | `_sources`, `_line_taxes`, `_attachments`, `_notes` | 8 / 8 |
| Receipt | `settlements` | `settlement_allocations` | — | 36 / 36 |

Four things that are easy to get wrong about this shape.

**Only the invoice and the return keep a stored tax breakup.**
`sales_invoice_line_taxes` and `sales_return_line_taxes` hold one row per
component per line — 96 rows against 48 invoice lines, because GST is CGST plus
SGST — so a bill reprints identically a year after the rate changed. The three
documents upstream re-resolve their tax on every read, which is right: an offer
and an order are not what anybody is charged.

**`_sources` exists only where a document bills another one.** An invoice line
and a return line each name the delivery note or invoice line they came from,
as a bare UUID with **no foreign key** — which is exactly why lines are
reconciled on their line number rather than deleted and re-inserted, and why
the three invoice modules, whose lines are terminal, are allowed to re-insert.

**What a customer owes is never stored on the invoice.** It is derived from
`settlement_allocations`, and the running balance lives in
`customer_receivable_transactions` (92 rows: one per approved invoice, one per
collection, one per completed return). A settlement is reversed rather than
edited, and the reversal puts the balance back by the **deltas stored on the
original row**, never by recomputing.

**`sales_orders.status` and `delivery_notes.status` are lifecycle state and
are not writable through an update body.** Both follow their downstream
documents — `_resync_order_status` derives the order's from the notes that
have left the warehouse, by summing rather than incrementing.

The masters either side: `customers` with `credit_limit`,
`default_discount_percent` and `credit_control_settings`; `products` with
`selling_price` and `mrp`; `price_lists` / `price_list_items`; and the
territory tables a sale is filed against. See
[`SALES_TO_RECEIPT_FLOW.md`](SALES_TO_RECEIPT_FLOW.md) for which of them each
step of a sale actually writes, measured rather than described.

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

**A firm chooses which of these stages its people type**, in
`sales_workflow_settings` — one row per firm, a boolean per skippable stage.
The documents always exist; the switch decides whether a person raises one or
`SalesChainService` raises it as the bill is saved. A firm with no row types
all four, which is how every firm behaved before the table existed.

| Firm | Quotation | Sales order | Delivery note | Invoice |
| --- | --- | --- | --- | --- |
| One person, counter sales | auto | auto | auto | **typed** |
| Hires a salesman | auto | **typed** | auto | **typed** |
| Hires a warehouse hand | auto | **typed** | **typed** | **typed** |
| Starts bidding for work | **typed** | **typed** | **typed** | **typed** |

A column per stage rather than one mode, because a firm changes shape and each
step should be a switch rather than a migration. **The invoice is always
typed** — it is what the customer receives, so there is nothing beyond it to
trigger it. What cannot be skipped is approval: that is where credit is
committed and where the journal is posted.

Two rules keep it honest. The switch governs **new** documents only, so
turning a stage on never strands work already in flight. And a synthesised
document is a real one — the same service call a person would have made — so
stock, cost, audit and every report are unchanged.

**Skipping a stage is not a way to bill goods that never moved.** Billing a
sales order directly is refused unless the firm's configuration ships it, in
which case the delivery note is raised and dispatched first.
`allow_direct_sales_order` used to be a boolean on the invoice that the caller
set to permit itself, which let a bill post revenue with no stock movement, no
cost of goods sold and a reservation left open for ever. The column survives as
a record of how a bill was raised; it is no longer an input.

**Stock moves at dispatch; money moves at invoice approval.** They are separate
events on purpose, which is why cost of goods sold belongs to the delivery note
and revenue to the invoice.

## Lifecycles

| Document | States | Notes |
| --- | --- | --- |
| Quotation | `DRAFT → SENT → ACCEPTED` / `DECLINED` / `CANCELLED` / `CONVERTED` | `EXPIRED` is **derived** from `valid_until`, never stored — nothing sweeps the table at midnight, and a job that had not run yet would let a stale quote through |
| Sales order | `DRAFT → APPROVED → PARTIALLY_DELIVERED → DELIVERED → CLOSED` / `CANCELLED` | the two middle states are derived from the dispatched notes, not incremented |
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
| Which stages are typed | `sales_workflow_settings`, per firm | Yes — a bare bill is refused unless the firm's configuration synthesises the documents behind it, and an order cannot be billed unless the bill ships it. `GET`/`PUT /api/v1/sales-orders/workflow-settings`, written with `SALES_MANAGE_SETTINGS` |
| Commission payouts | `commission_payouts`, per firm | Accrue → approve (posts) → pay (clears). `COMMISSION_PAY` to move the money, which `SALES_MANAGER` does not hold |
| Commission | `commission_rules` + `commission_rule_slabs`, per firm | Flat rate, a ladder, or an amount per unit; scoped to a product, a category or everything; paid on money collected or on invoiced value, with an optional floor, ceiling and target bonus |
| Targets | `sales_targets`, per firm | Reported, not enforced — `GET /api/v1/sales-targets/achievement`, measured on each target's own period and basis. `SALES_TARGET_MANAGE` to set one |
| Promotions | `promotions`, per firm | Yes — stacked in priority order while the document is priced, before tax. `GET`/`PUT /api/v1/promotions`, written with `PROMOTION_MANAGE` |
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

## 2. ~~A sales order cannot be raised directly from the desktop~~ — closed 2026-08-23

An order could only appear by converting a quotation, so a phone order had to
be typed as a quotation and immediately accepted — two documents, and an
acceptance the customer never gave. `POST /api/v1/sales-orders` had existed the
whole time with nothing on the desktop calling it, and the orphan-route guard
could not see it: the generic `documentPage` / `documentAction` helpers match
every two-segment sales route, so the create looked called.

**New Order** on the orders workspace opens a line editor of the same shape as
the quotation's (`SALES_CREATE`); **Edit** reopens a draft (`SALES_UPDATE`),
and only a draft — the service refuses anything past it, and an approved order
is what the warehouse picks against and what credit was committed on. A
non-draft opens read-only with a banner naming the status, rather than letting
somebody retype the lines and be refused.

**It captures a salesman**, which needed a decision first. Three endpoints
listed a firm's people, behind `TERRITORY_ASSIGN_SALESMEN`, `COMMISSION_VIEW`
and `USER_VIEW` — and the sales-order form holds none of the three, so a
fourth copy behind a fourth permission was the direction of travel.
`GET /api/v1/firm-members` replaced all three, gated on **membership of the
firm and nothing else**: a firm's own directory of names is not a privilege,
and what needs a permission is *acting* on a person — putting them on a route,
setting the rate they are paid. Those gates are unchanged.

Two things surfaced the moment a document actually carried a salesman.
`_validate_scope_references` in `sales_order` and `delivery_note` checked the
caller's salesman with `select(User)` on the **request** session, so raising
either document with one named answered 503 on every firm outside the platform
store — the sixth occurrence of that trap, and the second on this field after
the by-salesman reports the day before. It also accepted any user that existed
anywhere, so one firm could tag another firm's people on its own documents;
membership of *this* firm is what makes somebody its salesman.

Leaving the field blank is not automatically nobody: where the customer is on
a round, `_derived_salesman` supplies that round's salesman, and only where
they are not does the money land in the commission report's Unassigned bucket.
The form says exactly that. It offers every member and does not filter by who
covers the customer's round — the server refuses one who does not, naming the
reason, and filtering here would need the customer's assignments on every
keystroke and would still have to trust that refusal.

## 3. ~~A sales order's status never moves as it is delivered~~ — closed 2026-08-23

`SalesOrderStatus` declared four states and no service resynced it from
delivery notes, where the purchase side has had
`GoodsReceiptService._resync_order_status` since 2026-08-18. The quantities
were tracked — that is why the pending and back-order reports worked — but a
fully delivered order and one nothing had shipped against both read `APPROVED`.

`PARTIALLY_DELIVERED` and `DELIVERED` are written now, by
`DeliveryNoteService._resync_order_status` on dispatch. **Derived by summing
the notes that have left the warehouse**, never incremented: an incrementing
counter and a reversal are two chances to disagree. Only an order already in
the delivering part of its life is moved, so a DRAFT, CANCELLED or CLOSED order
is left where it is.

Building it surfaced the thing that would have broken. The gate on raising a
delivery note compared the **sales order's** status against `DeliveryNoteStatus`
members — which agreed only because both enums spell `APPROVED` and `CLOSED`
the same. Writing `PARTIALLY_DELIVERED` would have made it refuse every second
delivery, so a part-shipped order could never have been completed. A report
filter had the same confusion.

Existing orders are **not** backfilled, exactly as the purchase side did not.
Re-seeded demo data shows the statuses; orders created before this date stay
where they are.

### A question this raised and did not answer

The service refuses to cancel only a `CANCELLED` or `CLOSED` order, so a
`DELIVERED` one can still be cancelled — goods gone, order withdrawn, delivery
notes orphaned. That was already true and invisible: such an order read
`APPROVED`, which cancel has always allowed. Making the status visible makes
the question askable. The desktop gate lists the new statuses so it keeps
saying what the service does rather than quietly disabling a button the API
accepts; tightening the service is a product decision, not a bug fix.

## 4. ~~Only two documents can be printed~~ — closed 2026-08-23

`GET /purchases/{id}/print` and `GET /sales-invoices/{id}/print` were the whole
of it. Three more joined them, starting with the one a firm could not do
without: **the delivery challan** that travels with the goods, because
dispatching stock and having nothing to send with it is the problem.

A challan is not a bill and does not pretend to be. It carries no bank block,
no due date, no reverse-charge declaration and no HSN-wise summary, but it does
state the value of what is moving, because that is what makes it usable behind
an e-way bill. It names the vehicle and the driver — the two things a driver is
stopped and asked about — and prints the conventional three copies
(consignee / transporter / consignor) unless the firm renames them.

Building it extracted `app/document_framework/services/print_support.py`:
reading a firm's template and describing the firm and the customer as party
blocks were copied between the two existing print services, and three more
documents would have made four copies of each. Both existing services now use
it, with their sixteen tests as the check that nothing moved.

**The quotation and the credit note landed the same day**, which is what the
extraction was for. Five documents print now: purchase order, tax invoice,
delivery challan, quotation and credit note.

A quotation carries the one field no other document has — how long the prices
stand — because an offer without it is one the firm is still bound by next
year. A credit note is the customer's evidence that the money came back, and
states the reason the goods did.

### The credit note's tax breakup — closed the same day

It could state a tax total and no components, which under GST is not enough.
The invoice manages it only because `sales_invoice_line_taxes` stores the
breakup it charged (`20260822_0096`); a sales return line had no equivalent.

`sales_return_line_taxes` (`20260823_0101`) is the twin of that migration, and
`SalesReturnService._tax_amount` now keeps what the engine decided instead of
returning one number and discarding the rest — the same change the invoice made
a day earlier. Re-asking the engine at print time is what that storage exists
to prevent: rules are effective-dated, so it can answer differently from what
was actually credited.

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

## 6. ~~The product's selling price is never used~~ — closed 2026-08-23

`products.selling_price` and `products.mrp` were columns nothing read. The
product form captured them and the grid sorted on them; no document defaulted
a line's `unit_price` from either, so every price was typed again.

The quotation and sales-order editors — the only screens that type sales
lines — now start a line at the product's selling price and say what it lists
at, MRP included.
Choosing a different product reprices an untouched line; a price somebody has
typed survives, because refilling it would overwrite what they just agreed. A
revision counts its stored prices as typed, so re-opening an offer cannot have
the master rewrite a negotiated figure.

**Deliberately client-side, unlike the customer's standing discount**, which
the server applies. A discount is an arrangement: silence means "the usual
deal". A price is the central term of the sale, and a document that says
nothing about it is incomplete rather than ordinary — so `unit_price` stays
required on the API and an integrator must state one.

## 7. ~~There is no pricing beyond a single price per product~~ — closed 2026-08-23

`app/pricing` holds **price lists**: effective-dated arrangements scoped to one
customer, to a territory, or to the whole firm.

They hold **rates off the product's price**, not prices of their own, and that
is the decision the shape rests on: a firm revises a product's price once and
every arrangement built on it follows, where a list of absolute prices would
keep charging last year's figure until somebody edited every row.

Where it sits in the precedence, which is the part to know:

1. an explicit **amount** on the line,
2. else an explicit **percentage**,
3. else the **price list** — the most specific arrangement wins, customer over
   territory over firm-wide,
4. else the customer's **blanket rate**,
5. else nothing.

A list is more specific than the blanket rate, so it outranks it; a typed
figure outranks both, because a person deciding beats a table.

**Which is why no line editor may prefill the discount box.** The quotation
editor filled it with the customer's standing rate — and with a literal `0`
where they had none — on the reasoning that a salesman must see what is being
quoted. The reasoning is right and the implementation defeated price lists the
day they shipped: an explicit percentage outranks the list, so a customer on a
blanket 10% and a 15% list was quoted 10%, and a customer with no blanket rate
sent an explicit `0`, which refuses every arrangement — so **no price list
could reach a quotation raised from the desktop at all**. Driven against a
running backend: the same line resolved to 15% saying nothing and to nothing
saying `discount_percent: "0"`. Both editors now leave the box blank and say
what blank takes, and the running total says the rest is applied on save
rather than quoting a figure the form cannot stand behind. A product no
list mentions falls through to the blanket rate — which is why the resolver
answers `None` for silence rather than zero, and a list that deliberately puts
a product at nil blocks the blanket rate underneath.

Ranked in SQL by an explicit `case`, not by NULL ordering: PostgreSQL sorts
NULLs first in `DESC` and SQLite last, which is exactly how a firm-wide UOM
rule once outranked a product's own factor in production while the tests
stayed green.

**Sales › Price Lists** is where a firm agrees one (`PRICE_LIST_VIEW` to read,
`PRICE_LIST_MANAGE` to write). Every figure on it is a percentage and the
screen says so, because somebody expecting to type a price will otherwise type
one into a discount column. The scope is one segmented choice rather than two
pickers — the server refuses a list scoped to a customer *and* a territory, so
offering both would only produce a refusal somebody has to read. The rates are
**replaced** by what is saved rather than merged, which is why the editor
sends the version it read as `If-Match`: a lost race would otherwise discard
every rate somebody else had just entered. Territory-scoped lists are still
API-only; the screen agrees them with one customer or with everybody.

## 8. ~~No schemes or promotions~~ — the engine landed 2026-09-02

`app/promotions` is `app/tax`'s shape — a rule row, typed condition child rows,
action rows and an execution log — with one deliberate difference. **Tax stops
at the first matching rule; promotions stack.** Every matching offer applies, in
priority order, until one that refuses further stacking is reached, which is
what a firm means by running a customer discount and a seasonal offer together.

Two rules make stacking safe:

- **The order is total** — `priority ASC, code ASC, version_number DESC,
  created_at ASC`. With a stacking engine the order *is* the money, so the same
  document must always price the same.
- **Percentages compound on what is left, never add on the gross.** Two stacked
  ten percent offers take nineteen percent, not twenty. That is the ordinary
  retail meaning, and it also makes it arithmetically impossible for stacked
  benefits to exceed the line — which matters, because `resolve_line_discount`
  refuses a discount larger than the line and a promotion nobody could configure
  their way out of would make a document unsaveable rather than cheap.

It runs **before** tax and stores its result on the line, so a promotion reduces
the taxable value exactly as a bill discount does. Integration is one new tier in
the shared rule:

    explicit amount → explicit percent → promotion → price list → standing rate

A person deciding still beats a rule; an offer running today still beats a list
agreed once. A line somebody priced by hand is skipped entirely and the
execution log says so, rather than reporting a benefit the line never received.

**Resolved once, inherited thereafter.** A promotion is evaluated where the line
is first priced and carried forward as an explicit figure, so an offer that
expires between the order and the invoice does not change the bill.

**What phase 1 does not do**, and deliberately does not declare: coupons, usage
limits, customer groups, Buy X Get Y across *different* products, gifts,
loyalty, cashback and free shipping. The last three have no home in the data
model — there is no customer credit ledger and no freight field a "free
shipping" benefit could target — and declaring an action nothing reads is the
defect the tax review recorded twice over.

## 9. ~~No salesman commission~~ — the backend landed 2026-08-23

`app/commission` holds effective-dated rules — a percentage per salesman, with
a firm-wide default — and a report that answers, for a period, what each
salesman collected and earned.

**Earned on money actually collected, not on invoiced value.** That was the
decision the whole shape turned on, and it is why the report walks
`settlement_allocations` → settlement → invoice rather than reading invoices:
a reversed settlement must not pay commission, so only `POSTED` receipts count,
and an allocation whose invoice names no salesman is reported under
`Unassigned` rather than dropped.

Attribution is the **invoice's own** `salesman_id` — the document's tag, not
the customer's current territory assignment. What was true when the sale
happened is what the commission is on, the same reasoning that stops an invoice
re-reading a customer's discount.

Two things a firm should know before relying on it. **Refunds are not netted
off**: a refund returns an unallocated advance, so nothing ties it to an
invoice or a salesman — worth a decision if a firm refunds after paying.
And it **reports rather than pays**: no payout posts to the ledger, which is a
separate decision about which account it lands in.

**The demo exercises it as of 2026-08-23**, which it could not before. Every
store held zero salesman assignments while every customer sat on a round, so
no document could name a salesman at all; and every store held zero
settlements, so no money was ever collected. Commission is earned on money
collected by a named salesman, which made it the one feature the seed could
not show working. Two salespeople per firm now cover the rounds, three
invoices in four are collected, and each firm carries a firm-wide rate plus
one person on a better one — so the precedence a rule of one's own beats the
default is visible on screen rather than only described here.

**Sales › Commission** carries both halves: *Rates*, where the effective-dated
rules are agreed, and *Collected*, the report over a period
(`COMMISSION_VIEW` to read either, `COMMISSION_MANAGE` to change a rate). The
report names the Unassigned bucket rather than hiding it, since a total that
silently omits money collected against untagged invoices cannot be reconciled
against the cash book.

Two things the screen needed that were not there. `GET
/api/v1/commission/salesmen` lists the firm's people gated on
`COMMISSION_VIEW` — `users` lives only in the platform schema behind
`USER_VIEW`, and the territory module's twin is gated on
`TERRITORY_ASSIGN_SALESMEN`, so without an endpoint of its own the picker
could only offer people who already had a rule and a *new* rate could never be
agreed. And **the firm-wide default no longer pays the Unassigned bucket**: a
default is what a person with no rule of their own earns, not a rate on money
that named nobody. Driving a seeded store found it — every one of ELEC01's 49
invoices carries no salesman, so the whole default was being reported as
commission payable to nobody. The collected figure stays; only the payout is
zero.

## 9a. Commission is a ladder, not a single rate — landed 2026-09-03

`app/commission` held **one** flat percentage per salesman. That is one
arrangement of several, and the two most common in distribution were both
unexpressible: a slab scheme, and paying on invoiced value rather than on
money collected.

Four things are now the firm's to declare.

**A ladder.** `commission_rule_slabs` holds bands of value, each with its own
rate. A rule with no slabs pays its flat `percentage`, which is every rule
agreed before this existed and keeps working unchanged. A rule *with* slabs
ignores that column entirely — there is one answer to what a rule pays, and a
flat rate sitting beside a ladder that overrides it is the number somebody
eventually reads as the deal, which is why the list column shows the shape
rather than the field.

**How the ladder reads.** `slab_mode` is MARGINAL (each band at its own rate,
the way income tax reads) or WHOLE_AMOUNT (everything at the rate of the band
reached). Both are in ordinary use and they pay very differently — 120,000
against 2% to 100,000 and 3% above pays 2,600 one way and 3,600 the other — so
this is declared, never inferred. Bands are half-open: a rate quoted "from
100,000" pays at exactly 100,000.

**What the rate is of.** `basis` is COLLECTED (the default, and what this
module has always paid on) or INVOICED. A rule pays on one basis only, and the
overlap guard refuses a second live rule over the same person and days
*whatever its basis*, so a firm changing over replaces the rule rather than
quietly paying twice for one sale. The report shows both figures regardless,
because a firm paying one way still wants to see the other — and a row on an
INVOICED rule would otherwise show an earning with nothing behind it.

**A ceiling.** `max_commission_amount` caps what one rule pays one person for
one period, and is applied **after** the ladder: it limits what was earned,
not what was sold. Capping the value first would push the amount down a rung
and pay less than the ceiling the firm agreed.

Two rules the arithmetic turns on. **A ladder must be whole** — starting at
zero, meeting exactly, open-ended only at the top — because a gap is an amount
the rule cannot answer for and an overlap is two answers to one question. And
**each arrangement's ladder runs on its own subtotal**: the governing rule is
still resolved on each row's own date, so a rate change mid-period splits the
period rather than carrying the first window's volume into the second
window's thresholds.

Driven against WHOLE01, on its own schema, across all four shapes.

## 9c. Commission on what was sold — landed 2026-09-03

A rate was a statement about a whole document: 3% of everything, whoever sold
whatever. Firms do not work that way. `product_id` and `product_category_id`
make a rule a statement about **lines**, and `rate_type` PER_UNIT pays for
units rather than for value.

**Resolution is six rungs of specificity**, narrowest first: the person's own
rule for this product, then for its category, then their unscoped rule, then
the same three firm-wide. "3% on everything, 5% on the cold chain" is one
arrangement, and it only works if the narrower rule wins for the lines it
names while the broader one still covers the rest. Whose rule it is outranks
what it is about — a rate agreed with one person is a deal, and a firm-wide
rule that happens to name a product must not override it.

**An unscoped rule still measures exactly the document.** The report
apportions each invoice's own `grand_total` across its lines, using the same
`apportion` a bill discount is split with, so the shares sum to the invoice
and a rule matching every line measures precisely what it measured before
scoping existed. Deriving the share from the line's own net amount instead
would drift by whatever the header carries — tax, rounding, a bill-level
charge — and quietly change what every existing arrangement pays.

**On the collected basis a scoped rule takes its share of each receipt**, in
the same proportion, because a payment clears a share of every line it
settles. Half a bill collected against an invoice whose cold chain is 60% of
it earns the cold-chain rule 60% of that half.

Two refusals, both because the combination could not mean anything. A
**per-unit rate on the collected basis** — money collected has no cases in it.
And a **per-unit rate naming no goods** — it would add cases of biscuits to
litres of oil. A rule naming both a product and a category is refused too:
the product is the narrower of the two, so say that and drop the other.

**Open decision, deliberately not taken here:** commission is measured on the
document total, which includes tax. Whether a firm should pay commission on
tax it collects for the government is a question for the owner, not something
to change silently — changing it would move every existing payout.

## 9b. ~~Commission reports rather than pays~~ — closed 2026-09-03

`app/commission` answered what a period earned and stopped there, so the number
lived on a screen and never in the books. `commission_payouts` is the record of
a debt: **accrued** from the report, **adjusted** while it is still a draft,
**approved** into the ledger, **paid**, or **cancelled**.

**The report is read once, at accrual, and never again.** Everything
afterwards reads the stored row. The report walks live documents, so asking it
in September answers differently than it did in April — a settlement reversed,
an invoice cancelled, a rate corrected — and a payout that changes after it was
approved is one nobody can reconcile against the journal it posted.
`CustomerService.reverse_receivable_transaction` reads stored deltas for the
same reason.

**One live payout per person per overlapping period.** Two would pay the same
collections twice and nothing downstream could say which was real. A CANCELLED
payout holds no claim, which is what makes a period accrued at the wrong rate
correctable at all.

**The ledger.** Approval posts `Dr Commission Expense / Cr Commission Payable`;
payment posts `Dr Commission Payable / Cr` whichever cash or bank account the
money left. Two accounts rather than one, because an approved payout is a
liability that outlives the month it was earned in — booking the expense
straight against cash would say the firm owes nobody the moment it recognises
the cost. Both accounts are the firm's to nominate through
`firm_control_accounts` (`COMMISSION_EXPENSE`, `COMMISSION_PAYABLE`), the way
every other posting purpose is; the default chart carries `5600` and `2400` so
the first payout does not fail on an unmapped purpose.

Three smaller rules. An **adjustment needs a reason** and is only possible
while the payout is a draft — a number nobody can explain at the year end is
not an adjustment, and changing what was approved would leave the journal and
the record apart. **A paid payout cannot be cancelled**: the money has gone,
and undoing that is a payment the other way. And the **Unassigned bucket never
becomes a payout** — it stays in the report so the collections reconcile
against the cash book, and there is nobody to pay it to.

`COMMISSION_PAY` is a permission of its own and is deliberately **not** granted
to `SALES_MANAGER`. Whoever states a debt should not be the one who moves the
cash; a sales manager holding both could pay their own team, and on a
firm-wide rule, themselves.

**Sales › Commission › Payouts** carries the whole run: Accrue a period, then
Approve, Pay or Cancel per row.

## 9d. A floor, and a bonus for meeting a target — landed 2026-09-03

Two arrangements every distribution firm runs, neither of which could be
expressed.

**`minimum_amount` is a floor on the arrangement.** Below it the rule earns
nothing at all; at or above it, it pays on **all** of it. Deliberately not a
zero-percent bottom slab, which is a different deal: a ladder pays from the
first rupee once it is climbed, while "no commission below ten lakh a quarter"
pays nothing until the quarter is made. It is judged on what was sold, before
any rate is applied, because that is what the sentence is about.

**`bonus_percentage` is an extra percentage on the same value**, paid only
when the salesman's targets over the period were met. It is a field on the
rule rather than a second rule, because two live rules over one person's days
are refused — the overlap guard exists so a payout is never left to whichever
row a query returned first, and weakening it to allow a bonus rule would
reopen exactly that. The bonus is added **before** the cap, so a firm's
ceiling still holds.

**Targets over the window are judged taken together.** A year holding twelve
monthly numbers is met when the twelve achievements add up to the twelve
targets. Requiring every single month would make an annual bonus almost
impossible to earn; requiring only one would make it almost impossible to
miss. Each target is still measured over its own period and on its own basis
— that is `app/sales_targets`' rule and this only adds the two columns up.

**Somebody with no target earns no bonus, and has not failed.** The report
says `target_met: null` rather than false: nobody set them a number, so there
is nothing they missed, and paying the bonus there would hand it to everybody
the firm never measured.

## A line that is only a gift — fixed 2026-09-03

Nothing charged for, goods supplied free: `quantity` zero and `free_quantity`
two. It is the shape a "buy ten of this, get two of *that*" offer needs, and
it can be raised by hand today — the sales order and the delivery note both
accept it, and the note dispatches the goods.

The **invoice** did not. A remaining quantity of zero read as *fully billed*
in three places: the note-level filter hid the whole note, the per-line filter
dropped the line, and the free-goods inheritance pro-rated the gift by a
charged share of zero. Stock left the warehouse and the document the customer
reads said nothing about it — the same fault the ordinary case had until
2026-08-23, in the one shape nobody had tried.

Two rules now. Such a line is **owed until an invoice line references it**,
counted in rows rather than in quantity, because zero minus zero is zero
however many times the gift has been stated. And where the source line charged
for nothing, the invoice inherits the **whole** gift rather than a share of it:
there is no share to pro-rate by.

This is what "Buy X Get Y across different products" needed underneath it —
see below, where it landed.

## Buy X of one thing, get Y of another — landed 2026-09-03

`FREE_QUANTITY` and `FREE_PRODUCT` are not one benefit wearing two names. The
first gives **more of what was bought** and only ever changes a field on a line
that already exists. The second gives **something else**, which no line on the
document mentions — so the engine has nothing to adjust, and has to say *add
this* instead.

The engine answers with `gifts`, and the sales order turns each into a real
line: nothing charged for, goods supplied free. That line is appended after the
offers are read and **before anything is priced**, so it flows through
conversion, tax and totals exactly as a typed line does rather than down a
second path of its own to drift.

Three rules. The threshold is counted **across the lines the offer matched**,
not per line — ten bought as two lines of five is still ten, which is how
anybody ordering two pack sizes types it. An offer with **no** threshold gives
its gift once, because there the condition is on the document and the action
has nothing left to ask for. And a gift the caller already typed is **not
doubled**: entering the offer by hand and the engine finding it are the same
benefit, and what was asked for beats what was assumed.

The gift line **refuses every standing arrangement** rather than saying nothing
about them, because the line stores the rate it resolved and a bill for nothing
printing "7.5% discount" is a number nobody can explain. Making that true
turned up a hole in the shared rule: on a zero-value line the recorded rate was
read off a chain of `or`s, which is falsy for an explicit zero, so a line that
had *refused* every arrangement recorded the customer's standing rate anyway.
It reads the branch that was actually taken now.

Driven on WHOLE01: twenty bought earned two gifts, both dispatched, and the
bill came to 1,980.00 with the gift line stating two free units and costing
nothing.

## A document inherits the price it continues — fixed 2026-09-03

A delivery note ships at the order line's price, and an invoice bills at the
note line's, where the caller says nothing. That is the rule the discount and
the free goods already followed — *a note ships the deal the order struck*,
*an invoice inherits from the line it bills* — and the price was the one field
that did not.

`unit_price` on both line-write schemas is now `Decimal | None` with no
default. Silence means "whatever was agreed"; zero means goods given away.
They used to be the same value, so a caller that named a source line and
omitted the price got a note valued at nothing and a bill for **nothing** — no
refusal, and nothing on the document to say why.

Nothing was broken in practice: the desktop and the seeder both pass the
price. That is also why it survived, and the fixtures did the same, so every
test proved the number it had just supplied. It was found by driving the chain
with minimal payloads, and the fixtures now say nothing about the price where
the inheritance is what is under test.

## A credit note that reverses tax — landed 2026-09-03

A credit note already existed, as a row in `customer_receivable_transactions`
raised from the customers record. It reduced what the customer owed, booked
the whole figure to sales returns, and reversed **no output tax at all** — so
a firm agreeing a rate difference after invoicing credited the customer the
gross amount and went on declaring tax on a price nobody paid.

`app/credit_note` is the document that closes it, and it is deliberately
**not** a sales return. A return is goods coming back: stock moves, and cost
of goods sold is reversed at what the movement was worth. A credit note here
moves no stock at all.

**It always names the invoice and the lines it credits**, because only the
original line knows the rate the tax was charged at — and the rate is derived
from what that line was actually charged rather than read from a tax profile
that may since have been edited. An edit in September must not change what
comes off a March supply, which is the invoice's own inheritance rule one
document later.

Approving posts three legs — sales returns, output tax, receivable — **and**
moves the customer's balance. Both, or neither: a note that posted and left
the balance alone would drive the subsidiary ledger and the general one apart
by its value. Cancelling mirrors the journal and puts the balance back by the
deltas the original transaction stored.

**The cap counts credit notes only.** A line cannot be credited beyond what it
was charged, less what other live notes have already taken. A sales return
also credits the customer and is deliberately not netted off: a return may
have sourced from a delivery note, which cannot be mapped back to an invoice
line, and a cap that silently under-counts is worse than one that says what it
covers.

`CREDIT_NOTE_APPROVE` is separate from `CREDIT_NOTE_MANAGE` and not granted to
`SALES_MANAGER`. Drafting one is bookkeeping; approving it reverses tax the
firm has declared to the authority.

Driven against a seeded invoice: a line charged 3,946.88 with 710.44 of tax
gave an 18.00% rate, 100 credited reversed exactly 18.00, over-crediting was
refused naming both figures, and approving moved the customer from 11,904.64
to 11,786.64 before cancelling put it back.

## E-invoicing and e-way bills — landed 2026-09-03, in sandbox

`app/einvoice` registers an approved sales invoice with the Invoice
Registration Portal and raises the e-way bill for the goods it covers. Both
live in one module because they share one portal, one set of credentials and
one failure story.

**Sandbox is the mode today, and nothing can mistake it for a filing.** `mode`
is NOT NULL on both tables with **no server default** — a default is one
migration away from silently being LIVE — and the sandbox marks every
reference it mints (`SBX…`), so a number carried away from its row still says
what it is. The desktop shows the mode beside the reference everywhere. Live
filing raises rather than falling back: a firm that believes it is filing must
never be rehearsing instead.

**The payload is the part that had to be right**, and it needs no portal to
check. It is refused **locally, naming the field** — no GSTIN on the firm or
the customer, no HSN on a product — rather than sent to come back as a numeric
code somebody has to look up. The CGST/SGST versus IGST split is read off the
**two GSTINs' state codes**, so the document and the tax charged on it can
never disagree about the same supply; an inter-state supply taxed as local is
refused before anything is sent.

Three smaller rules. **One registration per invoice** and one bill per
invoice, by unique key: two references for one supply leave nothing to say
which the customer holds. **A refusal lands on the row**, not only in a log,
because the person who has to correct the invoice is looking at the invoice —
and a retry writes over the same row and counts the attempt. And **a
registration is withdrawn inside 24 hours**, judged in UTC; afterwards a
credit note is how a supply is corrected.

`EINVOICE_MANAGE` is not granted to `SALES_MANAGER`: reading what was
registered is part of running a sales desk, filing with the authority is not.

### What live filing still needs

The GSP credentials, and a decision about which provider. `portal_for` is the
one place to extend and `InvoiceRegistrationPortal` is the four methods a
provider has to answer. Nothing else in the module changes.

## GST returns — landed 2026-09-03

`app/gst_returns` answers what a firm declares for a period, and **stores
nothing**. A return is a view of the documents: the moment it were stored it
could disagree with them, so it is derived on every read from the invoices and
credit notes as they stand. A cancelled invoice simply drops out; a credit note
raised late appears in the month it was issued, not the month of the invoice it
credits.

`GET /api/v1/gst-returns/gstr1` fills the sections this system's data can
honestly fill — B2B, B2CL, B2CS, CDNR, HSN and DOCS — and
`GET /api/v1/gst-returns/gstr3b` gives the outward half of the summary. Both
are gated on `SALES_VIEW`: reading a return means reading every sale of the
period, which is the sales register's authority, not a new code nobody would
think to grant.

**A supply is placed by the tax it was charged, never by an address.** CGST
with SGST is only chargeable within one state and IGST only between two, so
the document settles the question — and for an unregistered buyer it is the
only thing that can, there being no GSTIN to read a state code from. The first
version read a `state_code` field the customer record does not carry, so every
B2CS row filed with a **blank** place of supply, which the portal rejects.
Where the tax says a border was crossed and the buyer is unregistered, the
invoice is named in `unplaced_invoices` rather than filed with a blank cell:
a rejection at upload with nothing to say which document caused it is the
worst of both.

**A credit note to an unregistered buyer is netted off its B2CS row**, not
filed in CDNR and not dropped. There is nobody to reverse a claim against it.
Dropped — which it was, on the belief that this system could not produce one
— 3B went on deducting a credit GSTR-1 never declared, and the two returns
could not be reconciled against each other.

**3B is aggregated from the documents, not parsed out of GSTR-1's answer.**
Parsing a report back out of its own JSON is how a summary drifts from the
detail it summarises; both read the invoices.

**Every figure that leaves the module is in rupees and paise.** Documents here
are priced to four decimals, no portal accepts that, and the rounding happens
once on the way out so the running totals behind it keep the scale they were
priced at. Rounding as they accumulate would let the HSN summary and the
invoice detail drift apart a paisa at a time.

Driven against a running backend across all four demo firms and all three
tenancy modes: each files at its own rate, and GSTR-1 net of credit notes
equals 3B's section 3.1(a) exactly for three of them and to a paisa for the
fourth, which is the residue of rounding each row independently.

### What the module deliberately does not answer

The inward half of 3B — inward supplies and input tax credit — is the
purchase side. It is reported as *"Not derived: the purchase side files this"*
rather than as a zero, because a zero reads as "no input credit claimed",
which is a different declaration. Nothing here files anything with the
authority either: this is what a firm files *from*.

## Tax collected at source — landed 2026-09-03

`app/tcs` implements section 206C(1H), and the one thing to understand before
changing any of it is that **the tax is charged on consideration received, not
on what was invoiced.** The statute says "at the time of receipt of such
amount", so the event that raises a liability is a receipt clearing, never an
invoice being approved. Putting it on the invoice — which is what makes it look
like just another tax line — collects it on money that may never arrive and
misses money that arrives against an older bill.

Everything else follows from that:

- **Only the excess counts.** The first ₹50 lakh a buyer pays in a financial
  year attracts nothing, so a receipt straddling that line is charged on the
  part above it. Charging the whole receipt is the obvious mistake and it
  over-collects by the entire remaining headroom.
- **The threshold is per buyer, per financial year**, judged on the *firm's*
  own year rather than an assumed April, and the running total is **summed from
  the receipts** rather than kept as a counter — a counter and a reversal are
  two chances to disagree, and disagreeing here means charging a buyer on money
  they got back. Refunds are netted off for the same reason.
- **A seller below the turnover threshold collects nothing at all**, and
  whether a firm is above it is a fact the firm *states*: its preceding year
  may predate its books here entirely, and a figure computed off a partial
  history would put a firm in or out of scope on data nobody migrated.
- **A buyer with no PAN on record is charged the higher rate.** That is section
  206CC rather than 1H, but it is the same collection and lives on the same
  settings row.
- **The tax raises what the buyer owes.** `Dr Accounts Receivable / Cr TCS
  Payable`, and a `TCS` receivable transaction beside it. Taking it out of the
  money received would leave the firm short by the tax on every collection and
  would say the buyer had settled something they were never billed for.
- **A reversed receipt reverses its collection**, mirrored rather than deleted:
  a quarterly return may already have reported it, and a row that vanished
  would leave that filing with nothing behind it.

`TCS Payable` is account **2500**, deliberately not 2200 — TCS is not GST, it
is filed on a different return on a different cycle, and netting the two would
put a quarterly payment inside a monthly one.

**Nothing is collected from anybody until a firm asks.** `is_enabled` defaults
false and `preceding_year_turnover` to zero, so the migration changes no
existing firm's behaviour. `TCS_MANAGE` is not granted to `SALES_MANAGER`, on
the same reasoning as the credit policy: the role a rule constrains must not be
able to switch it off.

`GET /api/v1/tcs/preview` answers what a receipt of a given size would attract
**before** it is taken, because the figure is needed when the money is asked
for rather than discovered afterwards — and it says *why* nothing is due, since
a bare zero cannot tell a buyer under the threshold from a firm that does not
collect at all.

### What the demo does with it

`generate_transaction_history.py` puts every firm in scope with the buyer
threshold scaled to **₹5,000**. A demo customer pays a few thousand rupees a
year, so at the statutory fifty lakh the mechanism could never fire and seeding
it would prove nothing. Only the two demo figures are scaled; the rate, the
excess-only rule and the per-buyer financial year are untouched. The four firms
report slightly different counts because a buyer crosses the threshold on their
own trading, which differs by tax rate and unit factor — the one number in the
tally that legitimately varies between them.

## Customer statements and receivables ageing — landed 2026-09-03

Two questions with different shapes, so two answers rather than one report
trying to be both. A **statement** is a movement — what the account stood at,
everything that happened to it in date order, what it stands at now
(`GET /api/v1/customers/{id}/statement`). An **ageing** is a position — which
bills are still unpaid and for how long (`GET /api/v1/customers/ageing`,
declared above `/{customer_id}` or FastAPI reads "ageing" as a customer id).

**The running balance is recomputed in date order, never read off
`outstanding_after`.** That column is a snapshot taken when the row was
written, in the order things were *recorded*; a statement is read in the order
things were *dated*. Money arriving against a bill raised last month is
recorded after it and dated before it, so believing the snapshot shows a
balance that never existed on any day. The opening balance is summed from the
deltas before the period — the same arithmetic that produced the current
balance, so the two cannot drift.

**What a bill still owes comes off the allocations**, because this repo
deliberately stores it nowhere, and a **reversed settlement cleared nothing**:
counting it would report a bill as paid that the firm has no money for. Age
runs from the invoice's own due date where it has one and from its date
otherwise — a bill with no terms is due when it is raised — and `as_of`
defaults to today in **UTC**.

**The ageing row reconciles against the account, and says how.** They are not
the same number: a credit note or a sales return reduces the account and sits
on no invoice, and tax collected at source raises it without being billed at
all. Driven against the demo, one customer's bills came to 27,150.98 while
their account stood at 21,230.48 — two reports about one customer disagreeing
by 5,920.50 with nothing to explain it. The row now carries
`account_balance`, `unapplied_credits` and `charges_not_billed`, and
`total_outstanding - unapplied_credits + charges_not_billed` is the account
balance exactly. The buckets always sum to `total_outstanding`; the last one is
open-ended, because a debt older than the final boundary still has to appear
somewhere.

An unapplied advance is reported **beside** the closing balance rather than
folded into it: netting them hides money the customer is entitled to have
applied.

## Proforma invoices — landed 2026-09-03

A buyer needs a document before the goods move: to open a letter of credit, to
get a payment approved, to clear customs. A quotation is an offer and a tax
invoice is a demand; the thing in between is a proforma, and `app/proforma` is
it.

**It posts nothing, and the absence is the design.** There is no
`journal_entry_id` and no `receivable_transaction_id` on either table, because
a proforma raises no revenue, no output tax, no receivable and no stock
movement. Adding either column later is the first step towards a document that
looks like a bill to the books as well as to the customer. The unit suite
proves the absence rather than trusting it: after issuing, it counts the
journal entries and the receivable rows and expects zero.

**Its number comes from its own series, never the tax invoice's.** GSTR-1's
DOCS section declares the invoice series a firm issued, so a proforma drawing
from that series would either leave a gap the return cannot explain or put a
number in it that was never a supply. `PROFORMA_INVOICE` is a document type of
its own with a `PI` prefix.

**Its lines are snapshotted from the sales order, not sent by the caller and
not read live.** A caller that could name its own lines would be stating a
price the order never agreed. Reading the order live would be worse: an order
can be edited afterwards -- withdrawing its own approval as it goes -- and a
document the customer is arranging payment against must not change underneath
them. Free goods are copied too; a proforma that dropped them would understate
what is being shipped.

**Once issued it cannot be edited.** A revision is a new proforma with
`supersedes_id` pointing back, not a rewrite of the old one. Withdrawing keeps
the row: the customer holds a copy, and a document that vanished leaves them
with a number this system cannot explain.

DRAFT → ISSUED → CANCELLED, and no approval step of its own — the order it
states was approved already, which is also why there are two permission codes
rather than three. `SALES_MANAGER` holds both: a proforma posts nothing, so
raising one is ordinary sales-desk work.

The demo issues one against every fourth order, because a proforma is what a
buyer asks for when they need a figure in advance, not something every sale
produces.

## Holding a sales order — landed 2026-09-03

A firm needs to say "not yet" to an order — a dispute, a document the customer
has not sent, a delivery they asked to defer — without unwinding it. The only
ways to stop one were to cancel it, which gives the stock back and ends the
deal, or to remember not to dispatch it.

**A hold is a flag, not a status, and that is the whole design.** An order that
is PARTIALLY_DELIVERED can be held, and releasing it has to put it back to
PARTIALLY_DELIVERED — not to APPROVED. Writing HOLD into `status` would destroy
the only record of how far the order had got, and the release would then have
to guess. Nothing is overwritten, so nothing has to be restored. That is the
same reasoning `update_order` was repaired on in 2026-08-18, where a status
written from a request body silently reset an approved order.

**The stock stays reserved.** Holding says "not yet", not "never": the goods are
still promised, and releasing them would let another order take them while this
one waits. Cancelling is the action that gives stock back.

**The hold stops something**, or it is a switch somebody flicks believing the
goods have stopped moving while they carry on out of the warehouse.
`DeliveryNoteService.stage_note` refuses a held order and **names the reason**,
because the person who hits the refusal is the one who has to get the hold
lifted. It is in `stage_note` rather than `create_note` so `SalesChainService`,
which raises notes itself when a firm has the delivery-note stage switched off,
is covered by the same line.

**The reason survives the release**, because "why was this held" is the question
asked afterwards, and an earlier release stamp is cleared when a new hold is
placed so the record never reads as released while it is held.

This is an operational stop, **not a credit control**. The credit control is
`credit_control_settings`, which warns and optionally refuses at approval; a
hold is for everything else. `SALES_APPROVE` covers both actions — deciding
whether an order goes out is the same authority as approving it in the first
place.

## What is still not built

**Margin-based commission.** `sales_invoice_lines` carries no cost, so a
margin would have to be reconstructed from the stock ledger's moving average
per movement — reachable, but a real piece of work and not something to
declare before it exists. It is the last item of the original incentive spec
with no code behind it.

## 10. ~~No sales targets or quotas~~ — landed 2026-09-03

`app/sales_targets` gives the by-salesman and by-territory reports the half
they were missing: they answered "how much" and never "how much against what".

Two things are configuration rather than a decision baked in. **`basis` is
INVOICED or COLLECTED**, because firms genuinely differ about what counts as
sold -- and commission here is earned on money collected, so a firm running
both can align them or not. And **the period is given as dates**, not derived
from a name: a firm's quarter does not always start where the calendar's does.

**Achievement is measured over the target's own period and on its own basis**,
never over the window a report asks for. A target for April is April's
achievement whether the report covers the month, the quarter or the year --
the window only chooses which targets are worth reporting. Measuring over the
window instead would answer a monthly target with a year of sales.

Attribution is the document's own `salesman_id`, the same rule commission
follows. A target beaten reports a shortfall of zero rather than a negative
number, which is a sentence nobody can read.

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
