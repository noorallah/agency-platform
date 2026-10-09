# Market comparison: what the Agency Platform does, and what it is missing

The owner asked: *"Compare our product's functions and use cases with other
tools in the market; list what we are missing."* This document answers that
for the customer we sell to -- an Indian distributor, agency, wholesaler or
stockist, usually GST-registered, often with salesmen on routes -- and turns the
answer into a prioritised list. It builds on `docs/BACKLOG.md` §42 (the first
comparison, 2026-09-18), and adds Vyapar, Odoo and ERPNext, a full feature
matrix, and a launch-oriented priority order.

Written 2026-09-26. **Rows touched by the 2026-10-02 work** (GSTR-2B, input
credit, debit notes, reorder suggestions, batch choice on a sale) say so in
their own cell; the rest is as of the 26th and is not re-derived here.

**How to read the claims.**

- **Our product**: every "Yes" or "Partial" for the Agency Platform comes from
  the docs named in each row (`MODULE_STATUS.md`, `FUNCTIONAL_GUIDE.md`,
  `BACKLOG.md`, `DEFECTS.md`, `UI_PHASE_2_DESIGN.md`,
  `PROFIT_AND_LOSS_GUIDE.md`), with a few spot checks of `backend/app`. Where
  the docs say nothing, the cell says "not found in our docs" rather than
  guessing.
- **Competitors**: capabilities are from general product knowledge and the
  sources listed in BACKLOG §42. Products change between releases and many
  features sit in a higher plan, a paid add-on or a separate product (Zoho
  Payroll, Marg eOrder, ERPNext HRMS). **Re-check a competitor claim before it
  goes into a sales conversation.** No prices or version numbers are given on
  purpose.
- "Odoo/ERPNext" is one column: they are the broad open-source ERPs. Where the
  two differ it says so.

Marks: **Yes** -- built and usable. **Partial** -- exists with a named gap.
**No** -- not offered. **Sandbox** -- works against a test portal only.
**Add-on** -- a separate paid product or app from the same vendor.

---

## 1. Feature matrix

### Sales and billing

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Quotation, sales order, delivery note, invoice | Yes (full chain, each stage switchable per firm) | Yes | Yes | Yes | Yes | Yes | Yes |
| Proforma invoice | Yes (own `PI` series, posts nothing) | Yes | Yes | Yes | Yes | Yes | Yes |
| Sales returns and credit notes | Yes (credit note names the invoice line) | Yes | Yes | Yes | Yes | Yes | Yes |
| Debit note to a customer | Yes (2026-10-02: against the invoice, taxed at each line's rate, owed on the invoice; approval is a separate permission; GSTR-1 note type D) | Yes (against a bill reference) | Yes | Yes | Partial | Yes | Yes |
| Rate typed with GST included (quotation, order, bill) | Yes (2026-10-02: a switch on each, kept as typed) | not re-checked | not re-checked | not re-checked | not re-checked | not re-checked | not re-checked |
| Delivery challan with a reason (sale, route sale, on approval, job work) and a dispatch-before-invoice rule | Yes (2026-10-02: reason prints on the challan; policy Off / Warn / Block; *Dispatch and invoice* in one action) | not re-checked | not re-checked | not re-checked | not re-checked | not re-checked | not re-checked |
| Order hold, back orders, part delivery | Yes | Partial | Yes | Yes | Partial | Yes | Yes |
| Credit limit control | Yes (warn or block, per firm) | Yes | Yes | Yes | Partial | Partial | Yes |
| GST invoice print, A4 / A5 | Yes (CGST/SGST split, HSN summary, copies) | Yes | Yes | Yes | Yes | Yes | Yes |
| Thermal (80 mm) bill | Yes (built 2026-09-26) | Yes | Yes | Yes | Yes | Partial | Yes (POS) |
| Counter / POS billing mode | Partial (phase 2 "daily screens" target: 3 lines in 30 s, keyboard only) | Partial | Yes | Yes | Yes | Add-on (Zoho POS) | Yes |
| Barcode scan on billing | Partial (`/barcode-lookup` resolves packaging barcodes; scan-to-line in billing not found in our docs) | Yes | Yes | Yes | Yes | Yes | Yes |
| Barcode label printing | No (not found in our docs) | Partial | Yes | Yes | Yes | Partial | Yes |
| Recurring invoices | No | Partial | Partial | No | No | Yes | Yes |

### Purchasing

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PO, goods receipt, purchase invoice, return | Yes (approval cannot be skipped) | Yes | Yes | Yes | Yes | Yes | Yes |
| Skip stages for a small firm | No (sales has stage switches; purchasing does not -- BACKLOG §38) | Yes (voucher directly) | Yes | Yes | Yes | Yes | Partial |
| Damaged / rejected / expired on receipt and return | Yes (with reports) | Partial | Yes | Yes | Partial | Partial | Yes |
| Reorder alert and suggested PO | Yes (suggestion from typed levels, raised as draft POs; 2026-10-02: or from the last 90 days' sales -- lead + safety days, plus cover -- a typed level always wins) | Partial | Yes | Yes | Partial | Yes | Yes |
| Landed cost (freight / clearing added to stock cost) | No (§42.12) | Partial | Partial | Partial | No | Yes | Yes |

### Inventory

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Multi-branch, multi-warehouse | Yes | Yes (godowns) | Yes | Yes | Partial | Yes | Yes |
| Batch, expiry, earliest-expiry-first | Yes (2026-10-02: a batch picker on the delivery note, one challan row per batch) | Yes | Yes | Yes (pharma strength) | Yes | Yes | Yes |
| Serial numbers with warranty dates | Yes (seeded on ELEC01 only) | Partial | Yes | Yes | Yes | Yes | Yes |
| UOM conversions, packaging levels | Yes (all document types; carton/strip/piece with own barcodes) | Yes | Yes | Yes | Partial | Yes | Yes |
| Transfers, adjustments, write-offs, physical count | Yes | Yes | Yes | Yes | Partial | Yes | Yes |
| Stock valuation / ageing / slow-moving reports | Yes (valuation as on a day with the books beside it, bank stock statement, ageing with turnover, slow-moving, dead stock; corrected 2026-10-08, `docs/qa/INVENTORY_MARKET_GAPS_2026-10-08.md`) | Yes | Yes | Yes | Partial | Yes | Yes |
| Kits / composite items | Yes (assembled, taken apart, assembled at dispatch; repacking) | Partial (BOM) | Yes | Partial | No | Yes | Yes |
| Bill of materials / manufacturing | No (not in scope) | Yes | Yes | Partial | Partial | Partial | Yes |

### Pricing and schemes

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Price lists with quantity ladders, per-customer lists | Yes | Yes (price levels) | Yes | Yes | Partial | Yes | Yes |
| Trade schemes, free goods | Yes | Partial | Yes | Yes | Partial | No | Yes |
| Stacking promotions, coupons, gifts, free shipping | Yes (claim counted at approval under a lock) | No | Partial | Partial | No | No | Yes (Odoo); Partial (ERPNext pricing rules) |
| Loyalty points and cashback | Yes (one ledger; redemption settles the bill) | No | Partial | Partial | Partial | No | Yes |
| Scheme claims back to the principal | No (§42.7) | No | Partial | Yes | No | No | No |

### Field sales

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Territories, routes, beat plans, call lists | Yes (62 routes; weekly to monthly plans) | No | Partial | Yes (with eOrder) | No | No | Partial (ERPNext territory tree; no beat plans) |
| Salesman commission and targets | Yes (ladders, margin basis, caps; payout posts to ledger) | No | Partial | Partial | No | No | Partial (ERPNext sales partner commission) |
| Salesman mobile app: order booking at the outlet | No (Android APK is a desktop-layout preview -- §42.6, §48) | No | Add-on | Add-on (eOrder) | Partial | Partial (Zoho apps) | Partial |
| Offline collections, GPS, visit check-in | No (§39) | No | Partial | Add-on | No | No | Partial |

### Accounting and GST compliance

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Double-entry ledger, automatic posting | Yes (11 modules post; five invariants verified per store) | Yes | Yes | Yes | Partial | Yes | Yes |
| Trial balance, P&L, balance sheet | Yes (P&L one month + YTD; range is §50) | Yes | Yes | Yes | Yes | Yes | Yes |
| Day book, cash book, bank book, cash flow | No (not found in our docs) | Yes | Yes | Yes | Yes | Yes | Yes |
| Cost / profit centres | Yes (screens and journal picker) | Yes | Yes | Partial | No | Partial | Yes |
| Expense entry without writing a journal | No (P&L guide §5) | Yes (payment voucher) | Yes | Yes | Yes | Yes | Yes |
| GSTR-1 and GSTR-3B | Yes (derived live; 3B includes ITC from approved bills, per-line eligibility -- blocked s.17(5) credit in 4(A)(5)/4(B)(1), ineligible in 4(D)(2); debit notes in CDNR) | Yes | Yes | Yes | Yes | Yes | Yes (India localisation) |
| GSTR-2A / 2B reconciliation | Yes (2026-10-02: import the 2B file, match with a Rs 1 tolerance, claim all bills or matched only; no live portal fetch) | Yes | Yes | Yes | Partial | Yes | Partial (ERPNext India Compliance) |
| Tax calendar (what is due, late, done) | Yes (2026-10-02: on Home, GSTR-1, 3B and TCS deposit; monthly filers only; "filed" is marked by a person) | not re-checked | not re-checked | not re-checked | not re-checked | not re-checked | not re-checked |
| Upload / file returns to the portal | No (figures only; filing on the portal) | Yes | Yes | Yes | Partial | Yes | Partial |
| E-invoice (IRN) | **Sandbox** (live needs a GSP) | Yes | Yes | Yes | Yes | Yes | Yes (via GSP apps) |
| E-way bill | **Sandbox**, raised from the e-invoice only | Yes | Yes | Yes | Yes | Yes | Yes |
| TCS 206C(1H) | Yes (on the receipt, excess only) | Yes | Yes | Yes | Partial | Yes | Partial |
| TDS, incl. 194Q | No (§42.4) | Yes | Yes | Yes | Partial | Yes | Yes |
| Multi-currency, forex revaluation | Partial (`currency_code` fields only; no rates or revaluation found) | Yes | Yes | Partial | No | Yes | Yes |
| Payroll | No | Yes | Yes | Add-on | No | Add-on | Yes (Odoo, ERPNext HRMS) |
| Budgets | No (not found in our docs) | Yes | Yes | No | No | Yes | Yes |

### Payments and banking

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Receipts, payments, refunds, advances, allocation | Yes (reversal restores exact deltas) | Yes | Yes | Yes | Yes | Yes | Yes |
| Customer statement and ageing | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Vendor ageing | Partial (vendor outstanding report; no vendor ageing route found) | Yes | Yes | Yes | Yes | Yes | Yes |
| Pay an expense account from Payments | No (suppliers only -- P&L guide §5) | Yes | Yes | Yes | Yes | Yes | Yes |
| Bank reconciliation (statement import) | No (§42.2) | Yes | Yes | Yes | Partial | Yes | Yes |
| Connected banking / bank feeds | No | Partial (some banks) | Partial | Partial | No | Yes | Partial |
| Post-dated cheque register, bounce handling | No (bounce = reverse the receipt -- §42.3) | Yes | Yes | Yes | Yes (cheque tracking) | Partial | Partial |
| Cheque printing | No (not found in our docs) | Yes | Yes | Yes | No | Partial | Partial |
| UPI QR / payment link on invoice | No (§42.10) | Yes | Yes | Yes | Yes | Yes | Partial |
| Payment reminders to customers | No (§42.1) | Partial | Yes | Yes | Yes | Yes | Yes |

### Reporting and analytics

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Operational registers and exception reports | Yes (56 in the report catalogue) | Yes | Yes | Yes | Yes | Yes | Yes |
| Drill-down from a figure to the vouchers | Partial (phase 2 §9 item 3, not yet decided) | Yes (a Tally hallmark) | Yes | Yes | Partial | Yes | Yes |
| Period choice on financial reports | Partial (one month; §50) | Yes | Yes | Yes | Yes | Yes | Yes |
| Export to Excel / PDF | Yes (grid export; invoice PDF) | Yes | Yes | Yes | Yes | Yes | Yes |
| Role-based home / dashboard | Partial (phase 2 Home built; gadgets §49) | Partial | Partial | Yes | Yes | Yes | Yes |
| Custom report builder | No | Partial (TDL) | Partial | No | No | Yes | Yes |

### Platform: multi-firm, users, audit, backup

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Many firms in one installation | Yes (shared schema, own schema or own database, even another server) | Yes | Yes | Yes | Yes | Yes (orgs) | Yes |
| Roles and fine-grained permissions | Yes (189 codes, 16 seeded roles) | Partial | Yes | Yes | Partial | Yes | Yes |
| Audit trail | Yes (append-only by DB trigger in every store) | Yes (edit log) | Yes | Yes | Partial | Yes | Yes |
| Firm admin can read own audit trail | Partial (`AUDIT_LOG_VIEW` is platform-side only -- BACKLOG "Also open") | Yes | Yes | Yes | Yes | Yes | Yes |
| Industry profiles, custom fields | Yes (22 features, typed custom fields) | Partial (TDL) | Partial | Partial (pharma/FMCG editions) | No | Yes | Yes |
| Scheduled backup and restore | **No** (D-QA-4; half built on a branch -- §45, §35) | Yes | Yes | Yes | Yes (cloud/drive) | Yes (vendor-hosted) | Partial (hosted yes; self-hosted is yours) |
| Licensing and activation | No (§2, deferred) | Yes | Yes | Yes | Yes | Yes | n/a |
| In-app update notice | No (§43) | Yes | Yes | Yes | Yes | n/a (cloud) | n/a |

### Integrations and mobile

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Email a document | No (§14, deferred by owner) | Yes | Yes | Yes | Yes | Yes | Yes |
| WhatsApp / SMS sharing | No (§42.1) | Yes | Yes | Yes | Yes | Yes | Partial |
| Import masters from a file | Partial (server imports exist; desktop file import only for inventory -- §46) | Yes (Excel) | Yes | Yes | Yes | Yes | Yes |
| Migrate from Tally / Busy | No (§36, §42.11) | n/a | Yes (from Tally) | Yes (from Tally) | Yes (from Tally) | Yes | Partial |
| Access from outside the office | Partial (HTTPS to a self-hosted server -- §1; no cloud) | Partial (remote access) | Partial | Partial | Yes (cloud sync) | Yes | Yes |
| Phone app | No (APK is a preview; phone layout parked -- §48) | Partial (reports) | Yes | Yes | Yes (mobile-first) | Yes | Yes |
| Customer / vendor portal | No (§42.14) | No | No | Partial (retailer app) | Partial (online store) | Yes | Yes |
| Open API for integrations | Yes (672 REST endpoints) | Partial (XML/ODBC) | Partial | Partial | No | Yes | Yes |
| Marketplace / courier integrations | No (§42.15) | No | No | Partial | Partial | Yes | Yes |

### Usability and keyboard

| Capability | Agency Platform | Tally Prime | Busy | Marg | Vyapar | Zoho | Odoo/ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Keyboard-first entry | Partial (phase 2: Ctrl+K / Alt+G, Alt+area letters; Tally voucher keys F5-F9 still "to agree") | Yes | Yes | Yes | Partial | Partial | Partial |
| Global search for screens and records | Yes (Ctrl+K) | Yes (Go To) | Partial | Partial | Partial | Yes | Yes |
| Create a missing master inside a document | Partial (planned in phase 2 §4.6) | Yes (Alt+C) | Yes | Yes | Yes | Yes | Yes |
| Live pricing while typing, as saved | Yes (server `preview` endpoints price every line) | Yes | Yes | Yes | Yes | Yes | Yes |
| Indian formats (lakh grouping, amount in words) | Partial (amount in words on bills; lakh grouping is phase 2 §9 item 8) | Yes | Yes | Yes | Yes | Yes | Partial |
| In-app help (F1), onboarding checklist | Partial (firm readiness panel; F1 help is phase 2 §9 item 12) | Yes | Yes | Yes | Yes | Yes | Yes |

---

## 2. Where we are ahead

Only claims the docs support. The honest caveat first: **Odoo and ERPNext match
or exceed us on breadth**; our lead is against the desktop Indian tools a
distributor usually buys (Tally, Busy, Marg, Vyapar), and on correctness and
isolation rather than on feature count.

| Area | What we do | Who else does it |
| --- | --- | --- |
| Field sales | Territories, routes with effective windows, salesman coverage, beat plans (weekly to monthly) and daily call lists in the core product (`TERRITORY_FRAMEWORK.md`) | Marg only with its eOrder add-on; Tally, Vyapar, Zoho none |
| Promotion engine | Offers that stack and compound, coupons, gifts, free shipping; one identity per offer across edits; a claim counted at approval under a lock so two orders cannot both take the last unit of an offer | Odoo; Tally/Busy/Marg have schemes and free goods, not a stacking engine |
| Loyalty | Points and cashback on one ledger, expiry by batch with its cost reversed, redemption settling the bill so the full GST stands | Odoo, ERPNext; the Indian desktop tools mostly lack it |
| Commission and targets | Rule ladders, margin basis, caps, per-date rule resolution, payouts snapshotted and posted to the ledger, pay permission separate from manage | Largely absent from Tally, Vyapar, Zoho; partial elsewhere |
| Server-priced documents | Every line is priced by the server as it is typed (`/preview` endpoints) -- what is shown is exactly what is stored; one discount resolver for every sales and purchase document | Unusual; most tools price on the client |
| Per-firm storage isolation | A firm can live in the shared schema, its own schema, or its own database on another server; routing fixed at creation | Tally/Busy keep one data folder per company; cloud tools are multi-tenant but not per-firm databases |
| Audit trail | Append-only, enforced by a database trigger in every store, kept inside the firm's own store | Tally's edit log (mandated since 2023) is comparable in purpose; ours is enforced by the database |
| Configurable sales chain | Each stage (quotation, order, delivery note) switchable per firm; switched-off stages are raised by the same services so stock still leaves at dispatch | Competitors let you skip stages by typing a direct voucher, which loses the chain |
| Books that reconcile | Stock value = inventory control account, receivables = control account, every period balances -- checked per store by `verify_sample_data.py` | Not a published guarantee elsewhere |
| GST returns never stale | GSTR-1 and 3B derived on every read, so a late credit note or cancellation is always reflected | Most tools also compute on read; the gain is that nothing can drift |
| Fine-grained access | 189 permission codes; credit policy cannot be changed by the sales manager it constrains; commission payment separate from commission setup | Busy/Zoho/Odoo comparable; Tally and Vyapar coarser |
| Industry profiles and typed custom fields | 22 declared features gate fields per industry; custom fields in typed, indexable columns | Odoo/ERPNext (custom fields); Tally needs TDL |

---

## 3. What we are missing

Effort: **S** about a week or less, **M** two to four weeks, **L** more than a
month or a separate product. Estimates are rough and assume one developer with
the existing frameworks.

### 3.1 Must have for launch in India

These are the items a distributor compares on in the first demo, or the ones
that lose data or money if absent.

| # | Item | What it is | Who has it | Why it matters to a distributor | Effort | Our reference |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | **Scheduled backup and restore** | Daily `pg_dump` of every store, retention, restore procedure; a manual "back up now" | All seven | A disk failure today loses everything. Non-negotiable for software installed on a customer's own PC | S (half built) | D-QA-4, BACKLOG §45, §35 |
| M2 | **Live e-invoice and e-way bill** | A GSP connection behind the existing `InvoiceRegistrationPortal`; standalone e-way bills for transfers and non-invoice movements | All except basic Vyapar plans | Mandatory above the turnover threshold; a firm that must register IRNs cannot bill with us today | M (plus a GSP contract) | MODULE_STATUS "E-invoicing: Partial" |
| M3 | **Share bills by WhatsApp and email; payment reminders** | Send the invoice PDF and statement; reminders before and after due date | All seven | The first thing a customer notices missing; collections run on WhatsApp | M | BACKLOG §14 (deferred), §42.1, phase 2 §9 item 2 |
| M4 | **Expenses screen and indirect expenses** | Pick an expense, amount and "paid from" and the journal is made; an Indirect Expenses group; Payments able to pay an expense account | All seven | Rent, fuel, salaries and freight need an accountant's journal permission today; P&L cannot show net profit the Indian way | S | PROFIT_AND_LOSS_GUIDE §5 |
| M5 | **Bank reconciliation with a PDC register** | Import a statement, match to receipts and payments, cleared date; post-dated cheques held until their date, bounce with charges | Tally, Busy, Marg, Zoho, Odoo/ERPNext; Vyapar (cheques) | The accountant's weekly work; Indian distribution still runs on dated cheques | M | BACKLOG §42.2, §42.3 |
| M6 | **Import masters and opening position from a file, and from Tally** | Templates, preview with row errors, all-or-nothing, update by code; Tally masters and balances | Busy, Marg, Vyapar import from Tally; all import Excel | Every customer is leaving another tool; onboarding must be a day, not a project | M (files) / L (Tally) | BACKLOG §46, §36, §42.11 |
| M7 | **TDS, especially 194Q** | Deduction on the excess over Rs 50 lakh per seller per year; TDS on rent and contractors; certificates | Tally, Busy, Marg, Zoho, Odoo/ERPNext | Most distributors cross 194Q with their principal; an auditor asks for it | M (mirrors the TCS engine) | BACKLOG §42.4 |
| M8 | **GSTR-2B reconciliation** (**built 2026-10-02**: import and match; claim all or matched only) | Import the portal's 2B JSON, match to purchase invoices, show credit at risk | Tally, Busy, Marg, Zoho | Input tax credit is only claimable on what suppliers filed | M | BACKLOG §42.5 |
| M9 | **Day book, cash and bank books, period-range reports** | The standard Indian books; P&L and trial balance for a year, a quarter or chosen months; drill-down to vouchers | All seven | The first reports an owner or CA opens; one-month P&L is not enough for year-end | S-M | BACKLOG §50; phase 2 §9 item 3; day/cash book not found in our docs |
| M10 | **Fast counter billing with barcode** | Scan or type a code to add a line, save-print-next in one key, keyboard only | Busy, Marg, Vyapar, Odoo; Tally partially | Retail and cash-and-carry counters judge software on seconds per bill | M | UI_PHASE_2_DESIGN §4.6 (target set, not yet measured) |
| M11 | **Licensing** | Activation, expiry, what a firm sees near its limit | All commercial tools | Needed to sell the product at all, though not a customer feature | M | BACKLOG §2 (deferred by owner) |

### 3.2 Should have

Differentiators for our target segment, or gaps a customer raises in the first
months of use.

| # | Item | What it is | Who has it | Why it matters | Effort | Our reference |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | **Salesman mobile app** | Order booking at the outlet, stock and scheme check, receipts, visit check-in; offline with sync | Marg (eOrder), DMS apps, Busy add-on | The feature distributors compare field-sales products on; our routes and beats are desktop-only today | L (separate product) | BACKLOG §42.6, §39, §48 |
| S2 | **Scheme claims to the principal** | Sum promotion cost per principal per period, raise a claim, settle it | Marg, DMS apps | How an agency earns back what it passes on; the figures already exist in the promotion ledger | M | BACKLOG §42.7 |
| S3 | **Reorder suggestion to a purchase order** (**built**: from typed levels, and from sales as of 2026-10-02) | "Raise a PO for everything below reorder, up to maximum" | Busy, Marg, Zoho, Odoo/ERPNext | Turns an existing column into a saved afternoon a week | S | BACKLOG §42.9 |
| S4 | **UPI QR on the invoice** | Static QR from the firm's UPI ID and the amount | Tally, Busy, Marg, Vyapar, Zoho | Faster collection with no gateway and no internet | S | BACKLOG §42.10 |
| S5 | **Stage switches for purchasing** | Record a supplier bill without a typed PO and GRN | All the Indian desktop tools (direct purchase voucher) | A one-person firm types three documents for one bill today | M | BACKLOG §38 |
| S6 | **Landed cost** | Spread a transporter's or clearing agent's bill over the goods received | Zoho, Odoo/ERPNext; partial in Tally/Busy | Without it stock cost and margin are understated | M | BACKLOG §42.12 |
| S7 | **Stock ageing, slow-moving and dead-stock reports; vendor ageing** | Standard inventory and payables analysis | All seven | Pharma and FMCG distributors manage near-expiry and dead stock weekly | S | Not found in our report catalogue |
| S8 | **Barcode label printing** | Print product and shelf labels with price and MRP | Busy, Marg, Vyapar, Odoo | Needed once barcode billing (M10) exists | S | Not found in our docs |
| S9 | **Firm administrator can read their own audit trail** | A firm-scoped audit permission | All seven | On a product installed at the customer, the owner not seeing his own history looks backwards | S (decision first) | BACKLOG "Also open", audit trail entry |
| S10 | **A user's default branch and warehouse; financial-year scope** | Documents open with the user's branch; lists bounded to the current year | Tally (company period), Busy, Zoho | Fewer wrong-warehouse documents (D-QA-17); faster lists after year two | S each | BACKLOG §44, §37 |
| S11 | **Cheque printing** | Print a payment cheque on bank stationery | Tally, Busy, Marg | Common for supplier payments | S | Not found in our docs |
| S12 | **Approvals and notifications** | A bell: "3 orders waiting for you" | Zoho, Odoo/ERPNext; partial elsewhere | Approval is mandatory on POs, so approvers need to be told | M | UI_PHASE_2_DESIGN §9 item 15 |
| S13 | **Update notice and self-update** | Tell administrators a new version is out and apply it overnight | Tally, Busy, Marg | Keeps installed copies current without a visit | M | BACKLOG §43 |

### 3.3 Nice to have

| # | Item | Who has it | Why it can wait | Effort | Our reference |
| --- | --- | --- | --- | --- | --- |
| N1 | Payroll | Tally, Busy, Odoo/ERPNext; Zoho and Marg as add-ons | Distributors often use a separate payroll tool or a CA; integrate or export rather than build | L | not found in our docs |
| N2 | Multi-currency with exchange rates and revaluation | Tally, Busy, Zoho, Odoo/ERPNext | Only importers need it; currency fields already exist | M | `currency_code` on firm and invoice only |
| N3 | Customer and vendor portal | Zoho, Odoo/ERPNext | Needs the server reachable from outside -- a hosting decision first | L | BACKLOG §42.14 |
| N4 | Kits and composite items | Zoho, Busy, Odoo/ERPNext | Promotions already give free goods, covering most gift packs | M | BACKLOG §42.13 |
| N5 | Connected banking / bank feeds | Zoho; Tally for some banks | Statement import (M5) gives most of the value | L | BACKLOG §42.2 |
| N6 | Payment gateway links | Tally, Zoho, Vyapar | The UPI QR (S4) covers counter collection | M | BACKLOG §42.10 |
| N7 | Recurring invoices | Zoho, Odoo/ERPNext | Suits rent and subscriptions more than trading | S | BACKLOG §42.15 |
| N8 | Budgets and variance | Tally, Busy, Zoho, Odoo/ERPNext | Owners of small distributors rarely set formal budgets | M | not found in our docs |
| N9 | Custom report builder | Zoho, Odoo/ERPNext | Grid export to Excel serves most ad-hoc needs | L | -- |
| N10 | Geography auto-fill (districts, cities, pin codes) | Most cloud tools via pin-code lookup | States are seeded; the rest is typing | M | BACKLOG §41 |
| N11 | Home gadgets by role; phone layout | Zoho, Odoo, Marg | Home is built and approved for now | M each | BACKLOG §49, §48 |
| N12 | BOM, job work, marketplace and courier integrations | Busy (BOM, job work); Zoho (courier, Shopify, Amazon) | Outside the distributor profile | L | BACKLOG §42.15 |
| N13 | Declared industry features: IMEI, prescription, recipe, kitchen, service contracts, projects | Various vertical products | Not our segment. The placeholders were withdrawn on 2026-10-08 (migration `20261008_0353`), so nothing is declared and unbuilt any more | varies | `BUSINESS_PROFILE_FRAMEWORK.md` |

### 3.4 Found on a second pass, 2026-09-27

Owner, 2026-09-27: "any features we are missing compared to the market?"
Each "not found" was checked by searching `backend/app` for the tables or
columns the feature would need. The first three were planned the same day
in the backlog.

| # | Item | What it is | Who has it | Why it matters | Priority | Effort | Our reference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| G1 | **Trade licences** | Firm, branch, customer and vendor licences with validity; goods that need one; a sale check | Marg, Busy (pharma), pharma and agri DMS | A pharma wholesaler may sell only to licensed buyers | **High** (by trade) | M | BACKLOG §54 |
| G2 | **PAN / TAN checks and TDS both ways** | PAN from GSTIN, TAN on firm and customers, TDS deducted on payments and receipts | Tally, Busy, Zoho | Firms holding a TAN cannot record a deduction today | **High** | S + M | BACKLOG §53, §53.1 (extends M7) |
| G3 | **Extra fields on documents** | A firm's own fields on orders, deliveries, invoices (vehicle, PO reference, site) | Tally (UDFs), Busy, Zoho (custom fields) | Masters take custom fields; documents do not | Medium | M | BACKLOG §52 |
| G4 | **Export to Tally** | Vouchers and masters as Tally XML, for the firm's CA | Marg, Busy, most DMS apps | Most CAs keep the books in Tally; a distributor on another tool sends them its data every month | **High** | M | none -- M6 is the other direction |
| G5 | **Batch-wise MRP and rates** | Each batch carries its own MRP and rates (PTR, PTS in pharma); billing and printing take the batch's | Marg, Busy | Pharma and FMCG receive the same product at a new MRP; one MRP per product (`products.mrp`) cannot hold both | **High** (pharma/FMCG) | M | none |
| G6 | **Last rate while billing** | The rate and discount this customer last got for this product (and the last purchase rate) shown on the line | Tally, Busy, Marg, Vyapar | Used on nearly every bill; prevents quoting a regular customer a different price | Medium | S | none |
| G7 | **Picking list and loading sheet** | One sheet per van or route: everything to load for the day's deliveries, by product and batch | Marg, Busy, DMS apps | How a distributor's godown actually dispatches; per-delivery notes alone mean picking the same product ten times | Medium | S | none (delivery notes carry the vehicle number) |
| G8 | **Debit note to a supplier** (`app/debit_note` now exists, and 2026-10-02 added the mirror to a customer) | Rate difference, shortage or a scheme owed, without goods going back -- the mirror of a credit note | Tally, Busy, Marg, Zoho | Only a purchase return reduces a supplier bill today, which forces a fake stock movement | Medium | S | none; credit notes are sales-side only |
| G9 | **Cash discount and interest on overdue** | A discount for paying early; interest charged on overdue bills at the firm's rate | Tally (interest), Busy, Marg | Common credit terms ("2% if paid in 7 days"; 18% on overdue) | Medium | S-M | none |
| G10 | **Expiry and breakage claims to the principal** | Stock expired or broken in the market, returned or claimed from the company for credit | Marg, pharma and FMCG DMS | A real cost for pharma and FMCG distributors; the figures are partly in sales and purchase returns | Medium | M | extends S2 |
| G11 | **GSTR-9 annual return; composition-scheme parties** | The annual return from the year's documents; a bill of supply for a firm under composition, and composition customers treated as such | Tally, Busy, Marg, Zoho | Year-end compliance; small firms under composition cannot use the product | Low-Medium | M | none |
| G12 | **Returnable containers** | Crates, cans, cylinders issued and returned per customer, with deposits | Busy, beverage and dairy DMS | Only for beverage, dairy and gas distributors | Low (by trade) | M | none |
| G13 | **Invoices printed in Hindi or a regional language** | Party names and item names in a second language on print | Busy, Vyapar, Marg | Asked for by some rural and semi-urban distributors | Low | S-M | none |

**Where they fit in section 4:** G2 before go-live (the two TDS accounts
and TAN); G1 before go-live for a pharma firm; G4 and G5 with the first
update; G6, G7 and G8 are small and can ride with whatever release is next.

---

## 4. Recommended order for the next items

Ordered by risk first, then by what loses a sale in the first demo, then by
reuse of engines already built.

1. **Scheduled backup (M1).** Half built on `fix/d-qa-4-daily-backup`; finish
   the live run and the restore procedure. Everything else is moot if a
   customer loses a year of data.
2. **Expenses screen and indirect expenses (M4).** Small, and without it a
   firm's P&L is incomplete by rent and salaries every month.
3. **Share by WhatsApp and email, with reminders (M3).** The PDFs exist; the
   four questions in BACKLOG §14 need the owner's answer (which address, whose
   outbox, bounces, whether a failed send blocks). Most visible gap in a demo.
4. **File import with templates (M6, first half).** Products, then customers,
   then vendors, per BACKLOG §46. A customer cannot start without their
   masters.
5. **Bank reconciliation with post-dated cheques (M5).** One screen, the
   accountant's weekly work.
6. **Live e-invoice and e-way bill through a GSP (M2).** Mostly a commercial
   step (choose a GSP, get credentials) plus one portal class; the sandbox path
   already proves the flow.
7. **TDS 194Q and GSTR-2B matching (M7, M8).** What the auditor asks about;
   TDS mirrors the TCS engine, 2B needs only a JSON import.
8. **Day book, cash book and period-range reports (M9)**, together with
   BACKLOG §50, since both change the report period chooser.

After these: counter billing speed with barcode (M10) as phase 2's daily
screens are finished, then scheme claims (S2) and reorder suggestions (S3),
which reuse data we already hold. The salesman mobile app (S1) is our natural
differentiator but is a separate product and deserves its own decision.

---

## 5. Uncertain claims about our own product

Flagged so they are checked before this document is used externally:

- **GSTR-3B input tax credit.** `MODULE_STATUS.md` (compiled 2026-09-05) says
  3B covers the outward half only; `backend/app/gst_returns/services/gstr_service.py`
  now builds table 4 (ITC claimed, reversed, net) from approved bills
  (D-CMP-20). The matrix follows the code; `MODULE_STATUS.md` is stale here.
- **Barcode scanning in billing.** `/barcode-lookup` exists; whether any billing
  screen adds a line from a scan was not found in our docs.
- **Day book, cash book, cash flow, stock ageing, vendor ageing.** No route or
  catalogue entry was found; they may exist under another name.
- **Keyboard voucher keys (F5-F9)** are "an option to agree" in the phase 2
  design, not confirmed as built.
- **Grid export to Excel** is inferred from the fixed defect BACKLOG §31.5
  ("Export said success and saved nothing -- fixed"), not from a feature doc.
- **Remote access** rests on BACKLOG §1 (HTTPS anywhere, HTTP only on a private
  network); how a customer would expose the server safely is not documented.
