# Module status

What each module is for, what is built, and what is still open.

Compiled on **2026-09-05** from the running application and the four demo
firms, not from memory. Route and report counts are read off the OpenAPI
schema; table and row counts off the deployed schemas. Re-derive them rather
than trusting this file after a few months — a stale status line is worse than
no status line, because it talks the next reader out of checking. The finance
entry in `CLAUDE.md` claimed for months that automatic GL posting was not
built, long after eleven modules were posting, and it survived exactly because
nobody re-derived it.

| | |
| --- | ---: |
| Backend modules | 39 |
| API endpoints | 672 |
| Report endpoints | 57 |
| Desktop screens | 87 |
| Tables per firm store | 182 |
| Tests passing | 1,127 backend + 1,074 desktop |
| Migration head | `20260903_0127` |

## How to read this

A module is **built** when it has endpoints, a screen that reaches them, tests,
**and** seeded data that exercises it end to end. Anything short of that is
said plainly here, because the gap between "the code exists" and "somebody can
use it" is where nearly every defect in this project has lived — a route
declared below `/{id}`, a client method with no button, a report whose filter
no seeded row satisfies.

- **Built** — reachable, tested, exercised by the demo.
- **Partial** — works, but something named below is missing.
- **Open** — needs a decision, or is not started.

---

## Selling — quotation to cash

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Quotations `app/quotation` | 17 | 2 | Built | Offer, accept, convert. Expiry derives from `valid_until`, never a stored status. |
| Sales orders `app/sales_order` | 22 | 6 | Built | Status follows its deliveries. A hold is a flag, not a status, so part-shipped progress survives it. |
| Delivery notes `app/delivery_note` | 20 | 6 | Built | Moves stock and cost of goods sold. Inherits the order line's price rather than re-reading the masters. |
| Sales invoices `app/sales_invoice` | 18 | 6 | Built | Prints a real GST invoice with the CGST/SGST split and an HSN summary. |
| Sales returns `app/sales_return` | 18 | 4 | Built | Reverses stock, cost and the customer balance by the deltas the original row stored. |
| Credit notes `app/credit_note` | 9 | 3 | Built | Names the invoice **line**, so the tax reversed is the tax charged. Approval is a separate permission. |
| Proformas `app/proforma` | 8 | 2 | Built | Posts nothing, and draws its own `PI` series so GSTR-1's declared invoice range stays whole. |
| Receipts and refunds `app/settlements` | 15 | 0 | Built | Money in and out through one document. Allocating posts no journal — the receipt already did. |
| Customers `app/customers` | 24 | 0 | **Partial** | Statements and ageing reconcile to the account. Credit control ships in **warn** mode; no firm has chosen **block**. |
| Price lists `app/pricing` | 5 | 0 | Built | Quantity ladders. A customer's own list **replaces** the firm-wide one rather than amending it. |
| Promotions `app/promotions` | 14 | 3 | Built | Offers stack and compound; coupons, gifts and free shipping. A claim counts at approval, never while pricing. |
| Loyalty `app/loyalty` | 10 | 3 | Built | One ledger for points and cashback. Redeeming **settles** the bill, so the full GST is charged. |
| Commission `app/commission` | 13 | 0 | Built | Ladders, margin basis, caps and targets. A payout is snapshotted at accrual and posts on approval. |
| Territory and beats `app/sales` | 62 | 0 | Built | Routes, salesman coverage, beat plans, call lists. Nine plans a firm, weekly through monthly. |
| TCS 206C(1H) `app/tcs` | 4 | 0 | Built | Charged on the **receipt**, on the excess over the threshold only. Disabled by default. |

## Buying — order to payment

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Purchase orders `app/purchase` | 21 | 6 | Built | Approval cannot be skipped; status follows the receipts. Reports added 2026-09-04. |
| Goods receipts `app/goods_receipt` | 16 | 5 | Built | Posts stock and the ledger. A cancellation values the reversal from the **movement**, not the document. |
| Purchase invoices `app/purchase_invoice` | 16 | 5 | Built | Approval clears the accrual, after which the receipt can no longer be cancelled. |
| Purchase returns `app/purchase_return` | 18 | 6 | Built | Damaged and expired reports have rows only since 2026-09-04 — no seeded line carried the flags before. |
| Vendors `app/vendors` | 23 | 0 | Built | Categories and types reachable since the route-order fix. Child collections merge on a partial edit. |

## Stock — what is on the shelf

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Inventory `app/inventory` | 29 | 0 | Built | Summaries by firm, branch, warehouse and product; ledger, counts, transfers, write-offs. |
| Batches and serials `app/batch_serial` | 17 | 0 | **Partial** | Batch and expiry are exercised by two demo firms. **No firm serialises**, so that half runs on tests alone. |
| Products `app/products` | 17 | 0 | Built | Custom fields live in typed columns, so a list can filter and index on them. |
| Units and packaging `app/uom` | 29 | 0 | **Partial** | Conversions drive all seven document types. Packaging levels and barcode lookup have a screen and no seeded rows. |
| Branches and warehouses `app/branches` | 35 | 0 | Built | Imports stage and commit once, so a clash cannot half-apply a file. |

## Money — the books and the filings

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Finance `app/finance` | 33 | 0 | **Partial** | Chart of accounts, years, periods, journals, trial balance, P&L, balance sheet. **Eleven modules post automatically.** Cost and profit centres exist and are used by nothing. |
| GST returns `app/gst_returns` | 2 | 0 | Built | GSTR-1 and the outward half of 3B, derived on every read so a cancelled invoice drops out. |
| E-invoicing `app/einvoice` | 7 | 0 | **Partial** | Registration and e-way bills work in **sandbox**. Live filing needs GSP credentials and one `InvoiceRegistrationPortal`. |

## Configuration — how one firm differs from the next

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Business profiles `app/business` | 29 | 0 | **Partial** | **22 features declared, 6 of them flagged unbuilt.** Of the 16 that exist, 11 are gated (see `BUSINESS_PROFILE_FRAMEWORK.md`) and 3 are deliberately ungated pending a decision. Custom fields extend any module without a migration. |
| Tax framework `app/tax` | 52 | 0 | Built | Rules attach to the transaction, never the product. First match wins and evaluation stops. |
| Document framework `app/document_framework` | 17 | 0 | Built | Types, states, print templates and numbering. A firm administers its own series as of 2026-09-05. |
| Identity and roles `app/identity` | 25 | 0 | Built | 157 permission codes, all seeded, and all now visible to the guard that checks they are. |

## Platform — the parts a firm never sees

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Firms and tenancy `app/firms` | 6 | 0 | Built | Shared schema, dedicated schema, or dedicated database — possibly on another server. Provisioning is an explicit action. |
| Audit trail `app/common/audit` | 1 | 0 | Built | Append-only, enforced by a trigger in **every** schema. Per store, so no single query answers "everything that happened". |
| Diagnostics `app/diagnostics` | 3 | 0 | Built | A screenshot joins its traceback by request id, and a fault fingerprints on this codebase's frames rather than the ASGI plumbing. |
| Global search `app/search` | 1 | 0 | Built | Platform-owned definitions read the platform store; before that every Ctrl+K inside a firm answered 503. |

---

# What is pending, and why

Grouped by what is actually blocking each one. **Three of the four groups are
waiting on a decision rather than on code.**

## Deferred by the owner

Do not start either unprompted. Both sections exist so the thinking does not
have to be redone.

**Emailing a document to the party it names** (`docs/BACKLOG.md` §14). Most of
it exists: `GET /api/v1/sales-invoices/{id}/print` and its purchase twin
already return the finished PDF, and `document_states.allows_email` and
`document_timeline.email_recipient` are columns waiting for a writer. What does
not exist is everything about sending — no SMTP client, no mail configuration,
no notifications subsystem. Four questions decide it, none technical: which
address, whose outbox, what happens to a bounce, and whether a failed send
blocks the document.

**Licensing** (`docs/BACKLOG.md` §2). A `LICENSE_MANAGE` permission, a
`LICENSE_ADMIN` role and a `license_error` code exist and are unused — there is
no model, endpoint or screen. Five questions decide the shape: what is
licensed, what expiry does, phone-home or offline key, who issues one, and what
a firm sees as it approaches the limit.

## Waiting on a product decision

**Three features that work but are not gated.** Each is enforceable today;
enforcing it would take the feature away from firms currently using it, which
is a call about who should have it rather than a piece of work.

| Feature | Why it is still open |
| --- | --- |
| `TERRITORY` | Only AGENCY and WHOLESALE enable it, so gating it would take routes and beats away from PHARMACY, FOOD and RETAIL — all of which plausibly sell by territory on a distribution platform. The seeded profile assignment looks more wrong than the code does. |
| `APPROVAL_WORKFLOW` | Needs a product decision about which documents it governs before it can gate anything. |
| `MULTIPLE_WAREHOUSES` | Same shape: the flag exists, the behaviour it would switch off has not been agreed. |

**Three accounting questions deliberately left unanswered.** Each is defensible
as it stands and each would move real money if changed.

1. **Commission is measured on the document total, which includes tax.**
   Changing it moves every payout, past reports included.
2. **`additional_charges` sits outside the tax base.** Right for additions that
   genuinely are outside it; worth confirming against how firms use the field.
   Note that `freight_amount` is deliberately **inside** the base and reaches
   the lines, because a delivery charge is part of the value of the supply.
3. **A loyalty redemption settles the bill rather than discounting it**, so the
   full GST is charged on the supply. Treating it as a discount would reduce
   the taxable value and so the tax collected — a tax decision, and not one a
   module should take quietly.

## Declared, not built

Six industry features carry `business_features.is_implemented = false`, so the
service refuses to enable them and no profile advertises them. They are honest
placeholders rather than half-written code.

`IMEI` · `PRESCRIPTION_REQUIRED` · `RECIPE_MANAGEMENT` · `KITCHEN_MANAGEMENT` ·
`SERVICE_CONTRACTS` · `PROJECT_MANAGEMENT`

`COMMISSION` came off this list on 2026-09-03: `app/commission` had shipped ten
days earlier and the flag outlived the fact, so an administrator was being
refused a feature the platform had. **A flag recording what the codebase does
has to be revisited when the codebase does it**, and nothing but a survey finds
the next one.

## Built, but nothing exercises it

**This is the category that matters most.** Of 182 tables, 42 hold no live row
in any store. Most are attachments and notes nobody wrote, which is fine. These
five are not, and each is a code path the demo cannot reach:

| What | Table | Consequence |
| --- | --- | --- |
| Shortened sales chains | `sales_workflow_settings` | Every firm types all four documents, so `SalesChainService` — which raises the skipped ones for real, moving stock and cost — has never run on seeded data. |
| Credit blocking | `credit_control_settings` | No firm has a policy row, so only the default warn-at-80% path is exercised; `BLOCK` is untested outside unit tests. |
| Serial numbers | `serial_numbers`, `lots` | `products.track_serial` is false on every product in every store. |
| Packaging levels | `product_packaging_levels` | Screen, endpoints, barcode lookup and tests all exist; no seeded row reaches them. |
| Cost and profit centres | `cost_centers`, `profit_centers` | Present in finance with a `ledger_accounts.requires_cost_center` flag that no account sets. Nothing writes either table. |

Asking this question — *which columns does no live row populate?* — found four
defects in a single day on 2026-09-04:

- every purchase order carried a **null `buyer_id`**, so the platform-store
  read behind the by-buyer report was exercised by nothing;
- **zero coupons** in any store, so the whole claimed-by-name path was undriven;
- `purchase_return_lines.is_damaged` and `is_expired` false on every row, so
  two shipped reports **could only ever answer an empty grid**;
- a promotion seeded with no conditions matched every line of every document
  and, because a promotion outranks the tiers below it, **silently switched off
  three tiers of the pricing chain** — one line in 58 orders reached any of
  them.

The sweep is worth re-running whenever a feature lands.

---

## Where the ground truth is

Four demo firms trade three financial years across all three tenancy modes:
**MEDI01** and **FOOD01** share `firm_shared`, **WHOLE01** has its own schema,
**ELEC01** its own database. They agree line for line —

```
PO 32 | GRN 30 | PINV 30 | PRET 6 | PROMO 5 | IRN 17 | EWB 8 | QT 29
SO 58 | DN 58 | INV 49 | RCPT 37 | SRET 8 | CN 9 | PF 14 | TGT 2 | PAY 2
```

— which is what makes a divergence a signal worth chasing. WHOLE01 is the one
exception and it is explained: it carries a customer created by hand during
testing with no GST number, so four of its invoices cannot be registered and it
reads `IRN 13 | EWB 6`.

`scripts/verify_sample_data.py` checks five invariants in every store: stock
value against the inventory control account, every accounting period balancing,
customer outstanding against the receivable control account, every settlement
carrying its journal, and every approved invoice having posted. All five pass
in all three stores.

## See also

- `docs/MODULE_REVIEW_CHECKLIST.md` — the per-module review checklist and what
  each review found. 54 rows.
- `docs/BACKLOG.md` — the deferred items in full, with the questions each needs
  answered.
- `docs/SALES_FRAMEWORK.md`, `PURCHASE_FRAMEWORK.md`, `TAX_FRAMEWORK.md`,
  `UOM_FRAMEWORK.md`, `TERRITORY_FRAMEWORK.md`,
  `BUSINESS_PROFILE_FRAMEWORK.md` — the reference for each framework.
- `docs/SALES_TO_RECEIPT_FLOW.md`, `PURCHASE_TO_PAYMENT_FLOW.md` — the ledger
  lines each step of a document chain raises, driven against a running backend.
