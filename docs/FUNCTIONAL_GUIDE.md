# Functional guide, module by module

What each module is **for**, what you **configure** before using it, the
**workflow** it runs, **how to drive it** from the desktop, and the **tables**
it writes. No code walkthroughs — the file that maps a workflow onto a
permission and a table, so somebody can operate the platform or specify a
change to it.

Filled in one module at a time, and **complete as of 2026-09-16**: all 28
sections are written; section 29 (Branding) was added with release 1.3.0. The order below is the order a firm actually does things
in, which is **not** the code-dependency order in
[`LEARNING_PATH.md`](LEARNING_PATH.md): you cannot raise an invoice before
there is a tax rate, and you cannot set a tax rate before there is a firm.

**Brought up to release 1.3.0 on 2026-10-04.** Release 1.2.0 (the light menu,
Settings > Set up, favourites, My preferences and the whole backlog build) was
never shipped, so 1.3.0 is the first release after 1.1.0 and carries both it and
the agency's branding (section 29). Every "how to use it" path below is written
as the **1.3.0 menu** shows it; **What 1.3.0 changed in the menu** below the
module table translates an older path.

The backlog build of 2026-10-02 and 2026-10-03 (96 items in three waves) is
folded in as **What shipped on 2026-10-02 and 2026-10-03** below the module
table, with each item pointed at the section it extends; `BACKLOG_BUILD_PLAN.md`
section 4 holds the full record of each.

The purchasing and selling builds of **2026-10-05** (23 items, also part of
1.3.0) are folded in as **What shipped on 2026-10-05** below that, and at the
end of sections 15 and 16. They have not been through a full test suite, a CI
run or a hand test.

The eight sections finished on 2026-09-16 -- vendors, proforma invoices, credit
notes, TCS, GST returns, e-invoicing, inventory operations, and the reports /
search / audit / diagnostics group -- were written against the running system
and the modules' own source, which is where their "rules that bite" come from.
Two of them turned up findings rather than rules, both in vendors -- a `PUT`
that cleared what it did not name, and a category master with no in-use guard.
Both were fixed the same day and section 11 describes the fixed behaviour.

## Every section has the same six parts

| Part | Answers |
| --- | --- |
| **What it does** | The business job, in a paragraph |
| **Configure first** | What must exist before the module works, and what breaks if it doesn't |
| **Workflow** | The steps: who does it, what it changes, what status it lands in |
| **How to use it** | The desktop path and the actions on each screen |
| **Tables** | What is stored where, and which columns carry the meaning |
| **Rules that bite** | The refusals and defaults that surprise people |

Permission codes appear in the workflow tables. Endpoint tables are generated,
never typed: `uv run python scripts/dump_route_permissions.py --markdown <module>`.

**In a hurry?** [Runbook — a new firm, from nothing to trading](#runbook--a-new-firm-from-nothing-to-trading)
is the five steps that take an empty installation to a firm that can raise and
settle a document. **Settings › Platform › Firms › Firms › Set up** shows where a firm
stands on all of them and does two of them in place.

## The order

Re-measured 2026-09-05: **39 business modules**, **672 endpoints**, 126
migrations. Re-derive these rather than trusting them -- the counts in
`CLAUDE.md` were found to have drifted by a third on 2026-09-05, and
nothing about a document stops it happening here.

| Phase | # | Module | Done |
| --- | ---: | --- | --- |
| **A — Stand the firm up** | 1 | Firm setup and access | ✅ |
| | 2 | Business profile: what the firm may operate | ✅ |
| | 3 | Document numbering and lifecycle | ✅ |
| | 4 | Financial year and chart of accounts | ✅ |
| **B — Masters** | 5 | Branches and warehouses | ✅ |
| | 6 | Geography | ✅ |
| | 7 | Units and packaging | ✅ |
| | 8 | Tax setup | ✅ |
| | 9 | Products, attributes, batch and serial | ✅ |
| | 10 | Customers, groups and credit policy | ✅ |
| | 11 | Vendors | ✅ |
| | 12 | Territory, routes and beats | ✅ |
| | 13 | Price lists and discount rules | ✅ |
| | 14 | Promotions and coupons | ✅ |
| **C — Buying** | 15 | Purchase order → receipt → invoice → return | ✅ |
| **D — Selling** | 16 | Quotation → order → delivery → invoice → return | ✅ |
| | 17 | Proforma invoices | ✅ |
| | 18 | Credit notes | ✅ |
| **E — Money** | 19 | Receipts, payments and refunds | ✅ |
| | 20 | Loyalty and cashback | ✅ |
| | 21 | Commission, rules and payouts | ✅ |
| | 22 | Sales targets | ✅ |
| | 23 | Journals, ledgers and financial reports | ✅ |
| **F — Compliance** | 24 | Tax collected at source | ✅ |
| | 25 | GST returns | ✅ |
| | 26 | E-invoicing and e-way bills | ✅ |
| **G — Running it** | 27 | Inventory operations | ✅ |
| | 28 | Reports, search, audit and diagnostics | ✅ |
| **H — The agency** | 29 | Branding: the agency's name, tagline and logo | ✅ |

## What shipped after this guide was started

Eight backend modules landed between 2026-08-24 and 2026-09-03, after the order
above was first drawn. They are folded in as modules 14, 17, 18, 20, 22, 24, 25
and 26 rather than appended, because a firm meets them in the middle of what it
already does — a promotion prices an order, a credit note follows an invoice.

| Module | Routes | What it does | Where it surfaces |
| --- | ---: | --- | --- |
| `promotions` | 11 | Offers that stack, with coupons and a redemption ledger | Settings › Set up › Pricing › Promotions, coupon dialog |
| `loyalty` | 7 | Points a customer earns and spends, as one ledger | Settings › Set up › Pricing › Loyalty |
| `credit_note` | 6 | A document that reverses the tax it credits | Sell › Returns & notes › Credit Notes |
| `proforma` | 6 | A stated bill that posts nothing | Sell › All Sell screens › Documents › Proforma |
| `sales_targets` | 6 | What a firm expects to sell, and how it went | Sell › All Sell screens › Incentives › Targets |
| `einvoice` | 7 | Invoice registration and e-way bills, in sandbox | Accounts › All Accounts screens › Tax filing › E-Invoice |
| `tcs` | 4 | Tax collected at source, charged on the receipt | Accounts › All Accounts screens › Tax filing › TCS |
| `gst_returns` | 2 | GSTR-1 and 3B, derived on read and stored nowhere | Accounts › GST Returns |

**None of the eight is a business-profile capability**, and that is worth
knowing before anybody asks to switch one off for an industry. The module
catalogue names **workspaces** — `DASHBOARD`, `ADMINISTRATION`, `SETTINGS`,
`MASTERS`, `PRODUCTS`, `PURCHASES`, `SALES`, `INVENTORY`, `REPORTS`,
`ACCOUNTING`, plus `KITCHEN`, `RECIPES`, `PROJECTS` and `CONTRACTS` for four
industries — not backend packages. All eight live inside `SALES`, so a pharmacy
and an electronics distributor both get loyalty, promotions and TCS whether the
industry wants them or not. The catalogue is working as designed; the product
has simply outgrown its granularity.

A ninth module followed on 2026-10-02: `customer_debit_note` (more charged to a
customer on an invoice already raised, **Sell › Returns & notes › Customer Debit Notes**). It is folded
into module 18 beside the credit note it mirrors. The same day's GST work for
the sales and purchase chains is folded into modules 15, 16, 18 and 25.

## What shipped on 2026-10-02 and 2026-10-03

Ninety-six backlog items were built in three waves. Eight are new backend
packages, each with its own screen; the rest extend a module above. None of
the new packages is a business-profile capability (as with the eight above),
and a firm that does not use one simply never opens its screen. Route counts
are in `MODULE_STATUS.md`.

| Module | What it does | Where it surfaces | Main tables |
| --- | --- | --- | --- |
| `enquiry` | Leads and enquiries with follow-ups; **convert** stages the customer from the prospect and a quotation and commits once; won when the quotation becomes an order; lost with a reason from a fixed list. Numbered `ENQ`; the quotation's own permissions | Sell › All Sell screens › Documents › Enquiries | `enquiries`, `enquiry_lines`, `enquiry_follow_ups` |
| `approvals` | Up to three sign-off levels by document type, amount and role, over sales orders, sales invoices, purchase orders and purchase bills; bulk reject | Sell › All Sell screens › Documents › Approvals, Buy › All Buy screens › Documents › Approvals; Settings › Firm › Approval Levels | `approval_rules`, `approval_decisions` |
| `principal_claims` | What a principal owes: scheme redemptions at its share (the discount, and the free goods its offers gave at cost), free goods typed on bills of its products at cost, expiry write-offs and damaged returns, each source claimed once; and, as a claim of its own, a price cut on the stock in hand the day before it took effect (rate difference: old purchase rate less new, by product and batch); settled by its credit note or payment | Buy › All Buy screens › Money › Principal Claims | `principal_claims`, `principal_claim_lines`, `principal_claim_receipts` |
| `landed_costs` | Freight, duty and handling spread over completed receipts by value, quantity or weight; the on-hand share revalues stock, the rest goes to cost of goods sold | Buy › All Buy screens › Money › Landed Costs | `landed_cost_vouchers`, `landed_cost_charges`, `landed_cost_allocations` |
| `supplier_rebates` | Volume rebate agreements, accrued and reversed, settled by a party adjustment of kind `SUPPLIER_REBATE` | Buy › All Buy screens › Money › Supplier Rebates | `supplier_rebate_agreements`, `supplier_rebate_slabs` |
| `customer_rebates` | Turnover rebate agreements for a customer or a customer group, accrued and reversed, settled by a party adjustment of kind `CUSTOMER_REBATE`; no GST (SG-9) | Sell › All Sell screens › Documents › Customer Rebates (screen added 2026-10-05); the report *Customer rebate statement* | `customer_rebate_agreements`, `customer_rebate_slabs` |
| `bank_reconciliation` | Statements imported on the shared importer, matched to postings on the bank ledger, a reconciliation statement as on a date | Accounts › Bank Reconciliation | `bank_statements`, `bank_statement_lines`, `bank_reconciliation_matches` |
| `notifications` | The bell: derived on read, only what was read is stored | The bell on the menu bar | `notification_reads` |
| `report_layouts` | A person's saved layouts of the analysis screens | Sell › All Sell screens › Insight › Sales Analysis; Buy › All Buy screens › Insight › Purchase Analysis | `report_layouts` |

The settlements package also gained the **post-dated cheque** registers
(`post_dated_cheques`), **payment runs** (`payment_runs`) and **cheque
printing** (`cheque_layouts`); the finance package gained the **Tally export**
(`tally_ledger_mappings`), **TDS challans** (`tds_challans`), **TDS 194Q**,
**bank details** (`bank_account_details`), **ledger attachments**, the **cash
flow statement** and the **period-close checks**; purchase gained
**requisitions** (`purchase_requisitions`), **budgets** (`purchase_budgets`) and
**order revisions** (`purchase_order_revisions`); inventory gained **stock
transfers** (`stock_transfers`), **repacking** (`repacks`), **count plans**
(`count_plans`), **adjustment reasons and limits**
(`stock_adjustment_reasons`, `role_stock_adjustment_limits`,
`stock_adjustment_requests`) and **evidence files** (`stock_attachments`).

### Where each item sits in the sections below

**Section 10 (Customers).** A new outlet saves as `PENDING` when the firm
switches `new_outlets_need_approval` on and the person lacks `CUSTOMER_APPROVE`,
and nothing can be billed to it until it is approved (single or bulk).
Cash-discount days and percent sit on the customer, and the credit policy holds
the firm's terms, `overdue_interest_rate` and grace days, with a *Raise interest
debit note* action (`CUSTOMER_DEBIT_NOTE_MANAGE`; a draft, reason late-payment
interest). A **linked supplier** (`customers.linked_vendor_id`, same PAN, one
link each) gives a combined statement with a running net. Bank accounts are
masked to the last four and files are kept (`CUSTOMER_MANAGE_BANK_DETAILS`, held
by the firm administrator and not the sales manager or accountant). A duplicate
warning (same GSTIN, same last ten digits of phone, same name once punctuation
and trade words are set aside) precedes a save, and **merge** re-points every
column naming the duplicate in one transaction (refused when the duplicate has a
document in a locked financial year). Codes are issued from the `CUS`, `SUP` and
`PRD` series when left blank. A PAN check report lists missing or malformed PANs.

**Section 11 (Vendors).** A standing discount; the **catalogue** (their code,
price, pack size, minimum order, order multiple and lead time; importable); the
lead-time summary and its use in the expected date and in the sales-based
reorder point; a usual TDS section; ratings by people (1-5 per criterion, one
live rating per person, earlier ones kept); the **gifts** register
(`supplier_gifts`, `SUPPLIER_GIFT_MANAGE`) with the 194R summary; the linked
customer; the same duplicate warning and merge.

**Section 13 (Price lists).** **Price levels** (`price_levels`,
`product_price_levels`; a level on a customer or a group): the resolver reads
the list rate, then the level, then the product price, with the list's quantity
break. A price list can be scoped to a supplier, and product price revisions with
an effective date (`product_price_revisions`) are read from their date.

**Section 14 (Promotions).** The actions `BUY_X_GET_Y_DISCOUNT` and
`COMBO_PRICE`; festival **bonus points** (the largest multiplier that applies);
the conditions customer order count, days since last order, weekday and time of
day; **bulk coupon codes** (up to 5,000 single-use codes, all or none, with a
CSV export); **copy with new dates**; and the funding principal and its share,
which feed the principal claims.

**Section 15 (Buying).** Requisitions (`PURCHASE_REQUISITION_CREATE`, converted
to orders, raised from the below-reorder report); amendment of an approved order
with a revision list; supplier rates filling a blank price and discount; order
multiples and the policy that decides what a wrong multiple does; **quality
inspection** holding received goods in quarantine until decided
(`PURCHASE_INSPECT`); bill **tolerances** (`PURCHASE_APPROVE_OVER_TOLERANCE`);
**budgets** checked at approval (`PURCHASE_APPROVE_OVER_BUDGET`); free goods and
schemes on a receipt line; several receipts on one bill; a supplier's credit
applied against an opening bill; **payment runs** (approval needs
`PAYMENT_RUN_APPROVE`, which the cashier does not hold; one payment per supplier
by bank transfer, all or none; a generic NEFT file); and the supplier
performance and price-trend reports.

**Section 16 (Selling).** Several delivery notes on one bill, with a clash on
branch, salesman, territory or route refused by name; counter billing with a
scanner, split tenders (`sales_invoice_tenders`) and *Save & print*; the UPI QR
on a bill that still owes money; pick list and loading sheet from delivery
notes; reservation lapse and *Reserve again*; multi-level approval; WhatsApp
share by hand, reminders by statement of account, and sending other documents
by email (the messaging switches apply, except the hand share, which needs
none).

**Section 19 (Receipts, payments and refunds).** Payment mode and instrument
date on every settlement; the post-dated cheque registers (held, deposited,
cleared, bounced with return charges, cancelled while held); cheque printing.

**Section 23 (Journals, ledgers and financial reports).** The cash flow
statement; bank reconciliation; Tally export; firm bank details (the full number
to account managers and payment makers, the last four to everybody else); TDS
challans and 194Q; ageing bands per firm and the close checklist (listed, never
refusing); files on journals, receipts and payments. New control purposes:
`LANDED_COST_CLEARING`, `SUPPLIER_REBATE_RECEIVABLE`,
`PRINCIPAL_CLAIM_RECEIVABLE`, `CHEQUE_RETURN_CHARGES`, `TDS_INTEREST_AND_FEES`,
`GST_CASH_LEDGER`, `INTERNAL_USE`, `STAFF_WELFARE`, `SAMPLES_AND_DISPLAY` and
`PROMOTIONAL_EXPENSE`.

**Section 25 (GST returns).** A filed GSTR-1 is kept as a snapshot
(`gst_return_snapshots`) and later changes appear as amendments (B2BA, B2CLA,
CDNRA, B2CSA, documents added after filing), with 3B carrying the net; quarterly
(QRMP) filers get the IFF, PMT-06 deposits (`gst_cash_deposits`) and the
quarter's payment; the **GST checks** run before filing; rule 42
(`itc_common_reversals`; rule 43 is open); a **GSTIN per branch** scopes both
returns; warnings for a credit note after 30 November, a bill after its credit's
last date and a number longer than sixteen characters; and the tax rule is kept
on each line.

**Section 27 (Inventory operations).** Stock transfers as a document with
in-transit stock (dispatch, receive with damaged and missing, challan; refused
between two GSTINs); repacking; kits (`product_kit_components`: assemble,
disassemble, and assembled from components at dispatch); count plans by ABC
class with blind sheets; reasons, role limits and approval for large
adjustments; evidence files; incoming, outgoing and projected on availability;
the issue rule per product; expiry rules and returns due; reservations that
lapse; returns held until checked; stock alerts on Home; barcode labels;
discontinued and not-for-sale products; shelf life; internal-use, staff and
display issues.

**Section 28 (Reports, search, audit).** One search box on the audit trail;
trigram indexes behind search; sales analysis on an ordered basis, against last
year and with margin; purchase analysis with average rate and a rate-trend
screen; the PAN checks; the due lists; nightly retention after the backup.

**Section 9 (Products) and sections 2 and 5.** Principals and brands, price
history, kits, labels and the expiry, shelf-life and issue fields; **extra
fields on six documents** (quotation, order, delivery note, invoice, purchase
order, goods receipt), matched on the field's name as they carry forward and
printed when marked *Show on print*; a firm's own custom fields; features and
modules created at runtime reach every store (section 2); and the branch GSTIN
(section 5).

**Not built.** The 26Q FVU text file (the owner kept it for last), live
e-invoice and e-way bill through NIC or a GSP, real messaging sends, payment
links, a bank's own payment-run layout, rule 43, and the licence and installer
items; `BACKLOG_BUILD_PLAN.md` section 5.1 says what unblocks each.

## What shipped on 2026-10-05: the purchasing and selling builds

Twenty-three more items were built in one day: fourteen on the buying side
(PG-1 to PG-14, `BACKLOG.md` §86) and nine on the selling side (SG-1 to SG-9,
§87). They are part of release 1.3.0, which has not been distributed.
**None has been through a full test suite, a CI run or a hand test**: each was
merged on its own tests, so every statement about them in this guide is from
the code and is to be confirmed on a screen. The manual cases are TC-BUY-029 to
090 and TC-SELL-036 to 087 (`docs/qa/`). `PURCHASE_FRAMEWORK.md` and
`SALES_FRAMEWORK.md` are the references; the rules are in
`LEDGER_POSTING_RULES.md` and `SALES_CHAIN_RULES.md`.

Eight are new backend packages:

| Module | What it does | Where it surfaces | Main tables |
| --- | --- | --- | --- |
| `rfq` | A request for quotation to several suppliers, their quotes, a comparison by rate after discount, a choice per line (a reason off the lowest), and one draft purchase order per chosen supplier. `RFQ_VIEW`, `RFQ_MANAGE` | Buy › All Buy screens › Documents › Requests for quotation | `rfqs`, `rfq_lines`, `rfq_suppliers`, `supplier_quotations`, `supplier_quotation_lines` |
| `rate_contracts` | A rate, discount and optional quantity agreed with one supplier for a period; prices a blank order line ahead of the price list; drawn and remaining derived from approved orders; over-drawing warns. `RATE_CONTRACT_VIEW`, `RATE_CONTRACT_MANAGE`; approval `PURCHASE_APPROVE` | Buy › All Buy screens › Documents › Rate contracts | `rate_contracts`, `rate_contract_lines` |
| `supplier_schemes` | "Buy n, get m" of the same or another product, for one supplier or all, dated; fills a blank free quantity on the order line. `SUPPLIER_SCHEME_VIEW`, `SUPPLIER_SCHEME_MANAGE` | Buy › All Buy screens › Documents › Supplier schemes | `supplier_schemes` |
| `bill_of_entry` | The customs document of an import: duty and surcharge landed on the linked receipts' stock, IGST claimed, customs payable booked. `BILL_OF_ENTRY_VIEW`, `BILL_OF_ENTRY_MANAGE`; posting `PURCHASE_APPROVE` | Buy › All Buy screens › Documents › Bills of entry | `bills_of_entry`, `bill_of_entry_lines`, `bill_of_entry_documents`, `bill_of_entry_allocations` |
| `fixed_assets` | Asset classes, the register, depreciation runs, disposal and the Income-tax block schedule; an asset is raised by a bill line marked capital goods. `FIXED_ASSET_VIEW`, `FIXED_ASSET_MANAGE`; runs and disposal also `JOURNAL_POST` | Accounts › All Accounts screens › Fixed assets | `asset_classes`, `fixed_assets`, `depreciation_runs`, `depreciation_run_lines` |
| `collections` | Promises to pay with a derived status, the collection sheet and its PDF, the chase list; a collector on the customer. `RECEIPT_VIEW`, `RECEIPT_CREATE` | Sell › All Sell screens › Money › Collection Sheet, Payment Promises | `payment_promises` |
| `counter_shifts` | A cashier's till: an opening float, expected cash derived from the cash tenders, a counted close whose difference posts to *Cash Short and Over*. `SALES_INVOICE_CREATE` to open; the list `SALES_VIEW` | The counter bill's shift strip; Sell › All Sell screens › Documents › Counter Shifts | `counter_shifts` |
| `document_files` | The shared file store behind **Attachments** on the purchase bill, the goods receipt and the five sales documents: PDF, JPG or PNG up to 10 MB | The Attachments action and Files column of each list | `document_files`, `document_file_contents` |

`customer_rebates` (in the table above) gained its screen the same day.

The rest extend a section below:

**Section 9 (Products, batch and serial).** A goods receipt line for a
serial-tracked product names one serial per unit (`goods_receipt_line_serials`;
typed, pasted or a range), and completion creates the units and starts their
trail; a purchase return names the units going back. A batch carries `ptr` and
`pts` beside its MRP, captured on the receipt line (a batch number is required,
neither may exceed the MRP; feature `BATCH_PTR_PTS`). A product of type
`SERVICE` moves no stock anywhere in the sales chain.

**Section 10 (Customers).** One *Cash sale* customer per firm
(`customers.is_cash_sale`), made the first time a counter asks, which cannot be
deleted, given credit or a GSTIN, or made inactive. A **Collector**
(`customers.collector_id`); blank falls back to the account manager. A **Trade
class** (`RETAILER`, `STOCKIST`, `OTHER`) that chooses PTR or PTS for a blank
price off a batch.

**Section 11 (Vendors).** A **Currency** (`vendors.currency_code`, blank is
rupees) that starts the supplier's bills in it. The **Usual TDS section** now
takes 194C and 194J, with *Individual / HUF* and *Technical services (2%)*.

**Section 15 (Buying)** and **section 16 (Selling)** each end with a part
headed *Added on 2026-10-05*.

**Section 19 (Receipts and payments).** A payment may be recorded as its bill
is approved (*Paid now*, an ordinary payment needing `PAYMENT_CREATE`). A
payment in a foreign bill's currency posts the exchange difference to
*Exchange Gain/Loss*. A payment ahead of any bill proposes TDS under 194C or
194J. A promise to pay posts nothing.

**Section 23 (Journals and ledgers).** New control purposes, each seeded with
the chart and added to firms whose books are open only where missing:
`TCS_RECEIVABLE` (1430), `FIXED_ASSET_COST` (1500), `ACCUMULATED_DEPRECIATION`
(1590), `CUSTOMS_PAYABLE` (2800), `OTHER_CHARGES_RECOVERED` (4050),
`EXCHANGE_GAIN_LOSS` (4950), `ASSET_DISPOSAL_GAIN_LOSS` (4960),
`CUSTOMS_DUTY` (5220), `DEPRECIATION_EXPENSE` (6950) and
`CASH_SHORT_AND_OVER` (6960). *Revalue foreign payables* on Journal Entries
books the unrealised exchange difference at a period end and reverses it the
next day. TDS settings for 194C and 194J sit beside 194Q under Settings › Tax.

**Section 25 (GST returns).** GSTR-3B 4(A)(1) *Import of goods* reads posted
Bills of Entry. A charge on a sales bill is in GSTR-1 and 3B under its own SAC.

**Section 28 (Reports).** Reports › Financial gains *GST sales register*, *HSN
summary of sales*, *GST purchase register*, *HSN summary of purchases*, *TCS
paid to suppliers* and *Customer rebate statement*. Buy › All Buy screens ›
Money › *Payables by Month* is a screen of its own.

**Not built**: see the end of sections 15 and 16. The eight defects found
while the cases were written (D-BUY-35 to D-BUY-40, D-SELL-51, D-SELL-52)
and the five found after them (D-BUY-41 to D-BUY-43, D-CMP-23, D-UI-11) were
fixed on 2026-10-05.

## What 1.3.0 changed in the menu

Release 1.3.0 changed where every screen is reached, not what any of them does.
`APPLICATION_FEATURES_GUIDE.md` sections 2 and 12 describe it in full; this is
what a module section below needs.

- **The light menu.** Each of Sell, Buy, Stock, Accounts and Masters opens a
  short drop-down of daily screens; **All <Area> screens (N)** at its foot opens
  the rest under their group names (`Sell › All Sell screens › Insight › Sales
  Analysis`). The **Admin** area is gone from the bar. Reports is unchanged.
- **The Settings page** (the gear) is one tab: **Settings** (This PC and me,
  Firm, Selling, Buying, Stock, Tax, Business profile), **Set up** (Pricing,
  Territories & routes, Account structure, Party lists, Item lists, Locations)
  and **Platform** (People, Firms, Agency, System), as cards with a search box.
  It is built in the app from the permissions held; opening it asks the server
  nothing.
- **Favourites.** A star on every drop-down item; the list is on Home, first in
  Ctrl+K, and kept on the server with the person's preferences
  (`dashboard_layout`), so it follows them to another PC.
- **My preferences** (user menu, or Settings › This PC and me): start in firm,
  first screen, theme, text size (this PC only) and date format (default
  dd-MM-yyyy). One save of the changed fields.
- **The agency's branding** (module 29): the sign-in screen, the header and the
  first-run dialog.

An older path in this guide translates as:

| An older path says | In 1.3.0 |
| --- | --- |
| Administration › Users, Roles & Permissions, User Templates, User-Firm Assignments | Settings › Platform › People › Users, Roles, Permissions, User Templates, User-Firm Assignments |
| Administration › Firms, Masters › Firms | Settings › Platform › Firms › Firms |
| Administration › Business Profiles | Settings › Platform › Firms › Business Profiles |
| Administration › Feature Management, Module Configuration, Attribute Definitions, Mandatory Attributes, Profile Assignment, Industry Templates | Settings › Business profile › the same names |
| Settings › Audit Log(s), Diagnostics; Administration › Licensing | Settings › Platform › System › Audit Logs, Diagnostics, Licensing |
| Masters › Firm Settings, Financial Years; Settings › Numbering Series | Settings › Firm › Firm Settings, Financial Years, Numbering Series |
| Tax configuration, rules, simulator, log, settings | Settings › Tax › the same names |
| Sales › Proforma, Credit Notes, Debit Notes | Sell › All Sell screens › Documents › Proforma; Sell › Returns & notes › Credit Notes, Customer Debit Notes |
| Sales › GST Returns, GSTR-2B, E-Invoice, TCS | Accounts › GST Returns; Accounts › All Accounts screens › Tax filing › the rest (TCS settings: Settings › Selling › TCS Settings) |
| Sales workspace tabs: price lists, promotions, territories | Settings › Set up › Pricing, Territories & routes |
| Purchases workspace | Buy › Purchase Orders, Goods Receipts, Purchase Invoices; the rest under Buy › All Buy screens |
| Inventory › Inventory, Stock Ledger, Opening Stock, Physical Count | Stock › All Stock screens › Stock › Inventory; Stock › Stock Ledger; Stock › All Stock screens › Movements › Opening Stock; Stock › Physical Count |
| Finance › Journal Entries; Control Accounts, Cost and Profit Centres | Accounts › Journal Entries; Settings › Set up › Account structure |
| Masters › Branches, Warehouses | Unchanged (Masters drop-down) |
| Masters › Storage Areas, Branch Types, Warehouse Types; Geography masters | Settings › Set up › Locations › Storage Areas, Branch Types, Warehouse Types, Places |
| Masters › Vendor Categories, Vendor Types; Customer Groups | Settings › Set up › Party lists |

---

# 1. Firm setup and access

> [`ACCESS_CONTROL_FRAMEWORK.md`](ACCESS_CONTROL_FRAMEWORK.md) is the reference
> for the model behind this section: the two tiers of administrator, all 16
> seeded roles and 189 permission codes, how a role becomes a permission on a
> request, which modules each role is offered, and every setting a firm can
> change with the code that guards it. This section stays the **workflow**.

## What it does

The platform serves many firms from one installation. A **firm** is a trading
entity with its own customers, stock, documents and books; a **user** is a
person; a **membership** joins the two. Nothing else in the platform works
until all three exist, because every firm-owned screen is authorized twice —
once on what the user may do, once on which firm they may do it to.

Where a firm's data physically lives is also decided here, and **only** here:
a firm can share the common store, take a schema of its own, or take a whole
database of its own on another server. That choice is made when the firm is
created and cannot be changed afterwards, because nothing migrates rows
between stores.

## Configure first

Server-side, in `backend/config/.env` (prefix `AGENCY_`, environment variables
override the file). These decide what a new firm gets by default:

| Setting | Default | What it decides |
| --- | --- | --- |
| `AGENCY_TENANCY_SHARED_DATABASE_NAME` | `agency_platform` | The database shared-mode firms live in |
| `AGENCY_TENANCY_SHARED_SCHEMA_NAME` | `firm_shared` | The schema they share |
| `AGENCY_TENANCY_DEDICATED_SCHEMA_PREFIX` | `firm_` | Prefix for a schema-mode firm's own schema |
| `AGENCY_TENANCY_DEDICATED_DATABASE_PREFIX` | `erp_` | Prefix for a database-mode firm's own database |
| `AGENCY_TENANCY_CONNECTION_PROFILES` | *(empty)* | Named remote servers, as JSON: host, port, username, password. A firm naming one is built and served **on that server** |
| `AGENCY_JWT_ACCESS_TOKEN_MINUTES` | `15` | How long a session token lasts before the client silently refreshes |
| `AGENCY_JWT_REFRESH_TOKEN_DAYS` | `7` | How long "stay signed in" lasts |
| `AGENCY_SECURITY_MAX_LOGIN_ATTEMPTS` | `5` | Failed logins before the account locks |
| `AGENCY_SECURITY_LOCKOUT_MINUTES` | `15` | How long the lock holds |
| `AGENCY_SECURITY_PASSWORD_HISTORY_COUNT` | `5` | How many old passwords cannot be reused |
| `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` | — | The first platform admin's password. Staging and production **refuse to start** without it, or with the development JWT key |

An unknown `connection_profile` on a firm is refused when the firm is created,
not at first use — a typo would otherwise produce a firm that provisions
nothing and fails far from the request that caused it.

## Workflow

### A. Bring a firm into service

| # | Step | Who | Permission | Result |
| --- | --- | --- | --- | --- |
| 1 | Record the firm — name, code, GST, PAN, currency, financial-year start, and the storage choice | Platform admin | `PLATFORM-ADMIN` | Row in `firms` + intent in `firm_storage_mappings`. **Nothing is built yet** |
| 2 | Provision its storage (dedicated firms only) | Platform admin | `PLATFORM-ADMIN` | Database and/or schema created, migrations run, platform tables pruned, `provisioned_at` stamped |
| 3 | Assign a business profile | Platform admin | `PLATFORM_VIEW` + `FIRM_VIEW` | Decides which features and modules the firm operates (module 2) |

Step 1 records intent only, so a remote server that is slow or unreachable
cannot fail the creation of the firm record. Until step 2 succeeds the firm is
refused by name — *"Firm storage for 'X' has not been provisioned yet"* — and
the reason a build failed is kept on the record, not only in the logs.
**Re-running step 2 is the repair action**; every step is create-if-missing.

Shared-mode firms skip step 2 entirely, and asking for it is refused.

### B. Give somebody access

Three separate grants, held by different people on purpose:

| # | Step | Who | Permission | Grants |
| --- | --- | --- | --- | --- |
| 1 | Create the user account | User admin | `USER_CREATE` | Nothing yet — an account with no membership can sign in and open nothing |
| 2 | Assign roles | Role admin | `ROLE_ASSIGN` | *What* they may do — the permission codes behind those roles |
| 3 | Assign firms | User admin | `USER_UPDATE`, plus `USER_CREATE` in each firm named; a platform admin reaches every firm | *Whose data* they may do it to, and which firm opens by default (`is_primary`) |

### C. Sign in and pick a firm

| # | Step | Permission | Notes |
| --- | --- | --- | --- |
| 1 | Log in | *(open)* | Writes `login_history`; too many failures lock the account for the configured window |
| 2 | Choose a firm | authenticated | The client's firm switcher; every later request carries that firm's id |
| 3 | Work | per-screen code + membership | Both are checked. **A platform admin still has to pick a firm** to open firm-owned screens |
| 4 | Change password | authenticated | A user flagged to change their password fails **every** permission check until they do — so a forced reset locks the whole application, not just one screen. Otherwise it is **My profile › Change password** in the account menu, and it ends every session |
| 5 | Choose a primary firm | authenticated | **Primary firm** in the account menu, offered to somebody in more than one firm. The next sign-in lands there; the switcher is for the session only |
| 6 | See their own record | authenticated | **My profile**: the details held about them and every role they hold, read-only, without `USER_VIEW` |

## How to use it

| Task | Where |
| --- | --- |
| Create, edit, provision firms | **Settings › Platform › Firms › Firms** (`FIRM_VIEW`) |
| A firm's own details and preferences | **Settings › Firm › Firm Settings** (`FIRM_VIEW`) |
| Create, edit, delete users; unlock a login; assign roles in every firm or in one | **Settings › Platform › People › Users** (`USER_VIEW`) |
| Reset somebody's password, restore a deleted user | **Settings › Platform › People › Users**, platform administrators only |
| Your own profile, password | The account menu (top right), signed in |
| Your own start-in firm, first screen, theme, text size, date format | **User menu › My preferences**, or Settings › This PC and me |
| Define roles | **Settings › Platform › People › Roles** (`ROLE_VIEW`) |
| See the permission catalogue | **Settings › Platform › People › Permissions** (`PERMISSION_VIEW`) |
| Attach people to firms | **Settings › Platform › People › User-Firm Assignments** (`USER_VIEW` + `USER_UPDATE`, platform administrators only); a firm administrator uses **Users › Edit › Firms** or **Add existing user** |
| Read who changed what | **Settings › Platform › System › Audit Logs** (`AUDIT_LOG_VIEW`) |

The firm switcher lives in the shell header and lists only firms the signed-in
user is an active member of.

## Tables

All of these live in the **platform** schema only — no firm store holds a copy,
which is why a firm-owned screen cannot resolve a user's name without asking
the platform store for it.

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `firms` | The trading entity | `code`, `gst_number`, `pan_number` (unique among live rows only), `currency_code`, `financial_year_start`, `status`, `is_active` |
| `firm_storage_mappings` | Where that firm's data lives | `deployment_mode` (`SHARED`/`SCHEMA`/`DATABASE`), `database_name`, `schema_name`, `connection_profile`, `provisioned_at`, `provisioning_error` |
| `users` | People | `email` (unique among live accounts only), lock and password-change flags |
| `platform_admins` | Who is a platform administrator | — |
| `roles` | Named bundles of permission | system roles are immutable through the API |
| `permissions` | The permission catalogue | `code` — `DOMAIN_ACTION`, e.g. `CUSTOMER_VIEW` |
| `user_roles` | Which roles a person holds | — |
| `role_permissions` | Which codes a role grants | — |
| `user_firms` | **Membership** — whose data a person may touch | `is_primary` (the firm that opens by default), `is_active` |
| `user_preferences` | Per-user client settings | — |
| `refresh_tokens` | Live sessions | Pruned only by the retention job |
| `login_history` | Sign-in attempts | Pruned only by the retention job |
| `password_history` | Old passwords, to stop reuse | Pruned only by the retention job |

**The audit trail is per store, not central.** Firm administration writes to
`platform.audit_logs`; a firm's own work writes to that firm's store. No single
query can answer "everything that happened" across firms.

## Rules that bite

- **Storage routing is immutable.** An edit that changes deployment mode,
  schema, database or connection profile is refused. Omitting those fields
  means *keep what is stored*, not *reset to shared*.
- **Two firms may never share one database/schema pair** — soft-deleted firms
  included, because their data is still sitting there.
- **Soft delete releases the natural keys.** A deleted firm's `code`, GST and
  PAN become available again, and a deleted user's email can be re-onboarded.
- **A firm with users assigned cannot be deleted.** Remove the memberships
  first.
- **A permission code that is enforced but not seeded silently becomes
  platform-admin-only**, because the admin check short-circuits the lookup. If
  a role "has" a permission and the screen still refuses, this is why.
- **Three retention tables grow forever** unless `scripts/purge_retention.py`
  is scheduled (`docker compose --profile retention up -d`).

## Four permission rows worth questioning

Found by generating the endpoint table and reading the guard column against the
neighbouring rows. None has been driven against a running server, so each is a
question for whoever owns the module rather than a reported defect.

| Endpoint | Guard today | Why it looks wrong |
| --- | --- | --- |
| `POST /api/v1/permissions` | `PERMISSION_VIEW` | A **read** code on a write endpoint. `PERMISSION_CREATE` is seeded, and the alias binding it is declared in the router and used nowhere; the update and delete aliases are dead the same way |
| `GET /api/v1/roles/{id}/permissions` | `PERMISSION_ASSIGN` | Reading what a role holds needs the code for *granting* permissions, while reading the role itself needs only `ROLE_VIEW` |
| `GET /api/v1/users/{id}/firms` | `ROLE_VIEW` | A membership question answered behind a role code. The sibling `/users/{id}/roles` correctly takes `USER_VIEW or ROLE_VIEW` |
| `GET /api/v1/roles` | `PLATFORM-ADMIN` | The list is stricter than the `GET /roles/{id}` it lists |

Severity turns on who actually holds `PERMISSION_VIEW`: the seeded `VIEWER`
role explicitly excludes it, so the likely answer is "administrators only",
which makes the first row untidy rather than dangerous. Worth confirming rather
than assuming.

---

# Runbook — a new firm, from nothing to trading

Five steps. **Settings › Platform › Firms › Firms › select the firm › Set up** is the
panel that shows where a firm stands on every one of them -- storage, business
profile, books, tax, geography, branches and warehouses, people -- with
*Required* against the two the platform refuses to post without and
*Recommended* against the rest, and does four of them from the platform
side: **Provision storage**, **Open the books**, **Apply GST template**,
**Assign** a business profile and **Create head office and main warehouse**. Until 2026-09-08 step 4 had no screen at all,
and nothing said it was missing until a document refused to post; tax had
none either, and was five screens by hand. The same list is `GET /api/v1/firms/{id}/readiness` and
`scripts/check_firm_readiness.py`, from one implementation
(`app/firms/services/readiness.py`), so the screen and the shell cannot
disagree about what finished means.

## 1. Record the firm

**Settings › Platform › Firms › Firms › New** (platform admin), or `POST /api/v1/firms`.

Required: `name`, `code` (uppercase `A-Z0-9_-`, 2–50 characters), `country`
(2 letters), `currency_code` (3 letters), `financial_year_start`. GST, PAN,
address and contacts are optional. The desktop form pre-fills `IN` / `INR` and
the current financial-year start as **defaults, not decisions** — all three stay
editable.

The one choice that can never be changed afterwards is where the data lives:

| Mode | What the firm gets | Names derived as |
| --- | --- | --- |
| `SHARED` (the form's default) | The common store — nothing to build | `agency_platform` / `firm_shared` |
| `SCHEMA` | Its own schema in the shared database | `firm_<code>` |
| `DATABASE` | Its own database, optionally **on another server** | `erp_<code>` + schema `firm_<code>` |

The prefixes come from the `AGENCY_TENANCY_*` settings in module 1. Naming a
`connection_profile` puts the firm on that server; an unknown profile name is
refused **here**, not at first use, so a typo cannot produce a firm that
provisions nothing and fails far from the request that caused it.
`database_type` must match the platform dialect.

All five storage fields appear on the form under **Storage Mapping**, editable
while creating and read-only once the firm exists — which is exactly what the
service enforces.

Two refusals to expect: a duplicate `code`, GST or PAN among live firms; and a
database + schema pair another firm already claims, **soft-deleted firms
included**, because their data is still sitting there.

**Nothing has been built yet.** That is deliberate — a slow or unreachable
target server must not fail the creation of a firm record.

## 2. Provision the storage — dedicated firms only

**Settings › Platform › Firms › Firms › Provision** (the action appears for any firm that is not
SHARED, and stays enabled until its storage is ready), or
`POST /api/v1/firms/{id}/provision`.

It creates the database and/or schema, runs `alembic upgrade head` against it,
prunes the platform-only tables, and stamps `provisioned_at`.
Until that succeeds every request for the firm is refused by name — *"Firm
storage for 'X' has not been provisioned yet"* — and a failure is kept in
`provisioning_error` on the record rather than only in the log.

**Re-running is the repair action**, not a risk: every step is create-if-missing
and Alembic stops at head.

What the new store holds afterwards comes from the migrations themselves — the
business-profile catalogue, features and modules, units of measure, tax systems,
geography masters. There is no application-level seeding step; the provisioning
service's seed hook has no handler wired to it.

## 3. Assign a business profile

**Settings › Platform › Firms › Firms › Set up › Business profile row › choose
› Assign**, or **Settings › Business profile › Profile Assignment** (module 2). Decides the firm's features, modules and custom
fields. The panel reads the catalogue from the firm's **own** store
(`GET /api/v1/business-framework/firms/{id}/profiles`), which is why it works
from platform mode where the Profile Assignment screen needs some firm open.

Skip it and the firm falls back to the store's default profile (GENERIC); if the
store has no default either, **nothing is enforced at all**.

## 4. Open the books

**Settings › Platform › Firms › Firms › select the firm › Set up › Open the books**
(platform administrator), or `POST /api/v1/firms/{id}/open-books`. One
press gives the firm the default chart of accounts (24 accounts in five
groups), the financial year running now with twelve monthly periods, a
journal type and a voucher type, and a mapped control account for each of
the **24 posting purposes**. It is idempotent -- a second press creates
nothing and says the books were already open -- and it is audited as
`firm.books_opened`, with the year and the counts, on the platform trail.

The year opened is the one **today falls in**, aligned to the firm's own
year start: a firm set up in September with an April year end gets April to
March of the current year, and a firm founded years ago does not get its
founding year. `year_starts_on` on the request body opens a different one.
Refused, by name, for a dedicated firm whose storage has not been provisioned.

The chart is the one the demo firms are built with (`CHART` in
`app/finance/services/opening_setup.py`), a conventional distribution chart
and not a claim about any firm's conventions. A firm that wants a different
one builds it through the finance API and remaps its control accounts on
**Settings › Set up › Account structure › Control Accounts**: every purpose, the account it posts to, and
how many lines have posted there. A purpose with posted lines is **held** --
re-pointing it would leave two accounts each holding part of one story, so
the screen shows the count and no picker, and the API refuses by name; a
transfer entry and a new account from the next period is the way. Read with
`ACCOUNT_VIEW`, written with `ACCOUNT_MANAGE`, like the chart itself.

From a shell, `scripts/seed_finance_defaults.py --yes` still does the same
for every active firm at once, in each firm's own store; it is the same
seeder behind the same idempotency, and is what the demo data uses.

**Why this step is load-bearing.** `firm_control_accounts` is what tells posting
which ledger account is Inventory, Trade Receivables or Output Tax, and a
failed posting is allowed to fail the document action that triggered it, on
purpose — stock that moved with no accounting entry behind it is the gap that
rule closes.

So a firm that skips step 4 can enter masters and raise drafts, and then:

| Action | What happens |
| --- | --- |
| Dispatch a delivery note | Fails — no Cost of Goods Sold / Inventory accounts |
| Approve a sales invoice | Fails — no Receivables / Sales / Output Tax |
| Record a receipt | Fails — `settlements.journal_entry_id` is NOT NULL |
| Record a customer's opening balance | Refused outright — a balance nobody can book is one the firm should not be told it has recorded |

## 5. Give people access

Three grants, deliberately held by different people (module 1):

| Step | Where | Permission |
| --- | --- | --- |
| Create the account | **Settings › Platform › People › Users** | `USER_CREATE` |
| Assign roles — *what* they may do | **Settings › Platform › People › Roles** | `ROLE_ASSIGN` |
| Assign the firm — *whose data* | **Settings › Platform › People › User-Firm Assignments** (platform admin), or **Users › Edit › Firms** | `USER_UPDATE` plus `USER_CREATE` in the firm |

Mark one membership `is_primary`: that is the firm that opens by default. A
platform admin still has to pick a firm to open firm-owned screens.

## Then the masters, in this order

Each depends on the one before it:

1. **Branches**, then **warehouses** under them
2. **Units of measure** — check the profile defaults before products
3. **Tax** — the profile and its rates, before anything is priced
4. **Products**
5. **Customers** and **vendors** (credit policy with them)
6. **Territories and routes**, if the firm sells by round
7. **Price lists**

**Document numbering needs no setup.** Each module creates its document type,
states and numbering rule lazily on the first save, and the series can be edited
afterwards in **Settings › Firm › Numbering Series**.

## Checking it worked

| Check | Expect |
| --- | --- |
| The firm's storage is ready | `provisioned_at` set, `provisioning_error` empty |
| Its capabilities resolve | `GET /api/v1/business-framework/active-features` returns the profile's list, not an empty one |
| Finance is set up | `GET /api/v1/finance/ledger-accounts` returns the chart, and an accounting period covers today |
| A person can actually work | They can sign in, the firm appears in their switcher, and a firm-owned screen opens |

The end-to-end proof is raising one small sale — quotation to receipt — and
watching the receivable return to zero. `docs/SALES_TO_RECEIPT_FLOW.md` traces
exactly that, with the ledger lines each step raises.

## What this runbook says about the product

Two gaps were worth stating plainly rather than working around silently,
and both closed on 2026-09-08:

- ~~**Finance setup has no UI path.**~~ **Open the books** on the Firms
  setup panel is the UI path. What remains is narrower: a mapping, once
  made, can only be re-pointed through the API, and there is no screen for
  the 24 purposes. `docs/BACKLOG.md` §15.
- ~~**Nothing tells a firm it is missing.**~~ The setup panel does, before
  the first document: every step with done or missing, required or
  recommended, and the verdict *can post* or *cannot post yet*. The refusal
  at approval is unchanged; it is no longer the first anybody hears of it.

Two more closed the same day. **Tax has a template**: every tax table is
per firm, so a new firm has no system, no components, no profiles and no
rules, and until then the only thing that built a working GST setup was
`scripts/seed_tax_sample_data.py`. **Apply GST template** on the panel
(`POST /api/v1/firms/{id}/apply-tax-template`, `app/tax/services/gst_template.py`)
gives it the Indian GST system, CGST/SGST/IGST/CESS, the 0, 5, 12 and 18
percent slabs as local and interstate profiles plus exempt, the nine rules,
the reverse-charge services -- GTA 5% and legal services 18%, with four rules
created switched off (decision A29) -- and the country if the store has none -- a starting point, edited afterwards
on the tax screens, and the script now applies the same one. And **the
business profile is set from the panel**, from the firm's own catalogue, so
a brand-new firm no longer needs an established one open first.

The first branch and warehouse are the firm's own to name, so the panel
offers a **default** rather than deciding: **Create head office and main
warehouse** makes `HO` as the default branch and `MAIN` under it, renamed
afterwards on their own screens, and a firm that already named a branch gets
only the warehouse under it. What is left is who belongs to the firm, which
the panel names the screen for.

---

# 2. Business profile: what the firm may operate

## What it does

One installation serves a pharmacy, an electronics distributor and a food
wholesaler. They need different fields, different rules and different menus —
and none of that is hardcoded per industry. A **business profile** is a named
industry (PHARMACY, ELECTRONICS, WHOLESALE …) that switches on:

- **features** — optional capabilities such as expiry tracking, serial numbers,
  barcodes, warranty, drug licence;
- **modules** — which workspaces the firm operates and in what menu order;
- **custom fields** — extra fields on products, customers, vendors and other
  masters, and which of them are mandatory for a given product category.

A firm is assigned exactly one profile. Change the profile and the firm's
fields, menus and refusals change with it — no code change, no migration.

## Configure first

| Needs | Why |
| --- | --- |
| The firm exists and is provisioned (module 1) | The catalogue is read from the firm's own store |
| A **default profile** exists in that store | A firm with no assignment falls back to it. With no default either, **nothing is enforced at all** |
| The catalogue is migrated into **every** store | `business_profiles`, `business_features` and the rest are firm-owned tables, not platform ones |

**This is the trap that costs the most time.** The catalogue lives once per
firm store, so a query against `firm_shared` shows the two dedicated-store
firms as unassigned even when they are not, and a migration run only against
the platform schema leaves those stores without the catalogue entirely. Use
`scripts/migrate_all_stores.py`.

## Workflow

### A. Decide what an industry means

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Create or pick a profile | `PLATFORM-ADMIN` | Row in `business_profiles`; one is flagged the default |
| 2 | Switch its features on or off | `PLATFORM-ADMIN` | Rows in `profile_features`. A feature marked `is_implemented = false` is **refused** |
| 3 | Switch its modules on or off, set menu order | `PLATFORM-ADMIN` | Rows in `profile_modules` — two booleans: `is_enabled` (may use) and `is_visible` (appears in the menu) |

### B. Give a firm its industry

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Assign the profile to the firm | `PLATFORM-ADMIN` | Row in `firm_business_profiles`, written **into that firm's own store** |
| 2 | The firm's users sign in | — | `/active-features` and `/active-modules` answer what they may use |

### C. What the firm then experiences

| Situation | What happens |
| --- | --- |
| Reads anything | Always allowed. **The gates are write-only**, so switching a feature on can never hide data a firm already has |
| Writes to a feature-owned endpoint | Refused outright if the feature is off — e.g. batches and serials |
| Writes a feature-owned **field** on a shared resource | The write is refused only if it *populates* that field. Blank and unchanged always pass |
| Has no profile at all | Falls back to the platform default (GENERIC). A configuration gap is not treated as a decision |

The distinction in the middle two rows is the design: gating the whole endpoint
suits a feature that owns its resource, but most features are optional *fields*
on a resource every firm uses — gating the endpoint would stop a firm creating
products because it does not scan barcodes.

### D. Custom fields

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Define an attribute — name, data type, entity type, optionally scoped to one profile | `PLATFORM-ADMIN` | Row in `attribute_definitions` |
| 2 | Make it mandatory for a profile + product category | `PLATFORM-ADMIN` | Row in `category_attribute_rules` |
| 3 | Users fill it on the record | the module's own code | Value stored in that module's `*_attribute_values` table, in a typed column. Products, customers and vendors carry a **Custom fields** tab and branches and warehouses a section at the foot of the form; UOMs and tax profiles take `attributes` on the API and have no form for it yet |

**Mandatory is stated per profile and category, never globally.** Four
attributes were once globally mandatory, which asked a pharmacy for an IMEI and
an electronics distributor for an expiry date — and blocked product creation on
any freshly migrated database.

## How to use it

Under **Settings** (the gear), each needing `PLATFORM_VIEW`:

| Task | Where |
| --- | --- |
| Create industries, set what each enables | **Platform › Firms › Business Profiles** |
| The feature catalogue | **Business profile › Feature Management** |
| The module catalogue, menu order and visibility | **Business profile › Module Configuration** |
| Define custom fields | **Business profile › Attribute Definitions** |
| Make a field mandatory for a category | **Business profile › Mandatory Attributes** |
| Point a firm at an industry | **Business profile › Profile Assignment** (`FIRM_VIEW` + `PLATFORM_VIEW`) |
| The industry templates | **Business profile › Industry Templates** |

## What each profile enables today

Read live from `profile_features`:

| Profile | Features |
| --- | --- |
| PHARMACY | ATTACHMENTS, BARCODE, BATCH_TRACKING, DRUG_LICENSE, EXPIRY_TRACKING, MANUFACTURING_DATE, SHELF_LIFE |
| FOOD | ATTACHMENTS, BARCODE, BATCH_TRACKING, EXPIRY_TRACKING, MANUFACTURING_DATE, SHELF_LIFE |
| MANUFACTURING | APPROVAL_WORKFLOW, ATTACHMENTS, BARCODE, BATCH_TRACKING, MANUFACTURING_DATE, MULTIPLE_WAREHOUSES |
| WHOLESALE | ATTACHMENTS, BARCODE, BATCH_TRACKING, MULTIPLE_WAREHOUSES, TERRITORY |
| AGENCY | ATTACHMENTS, BARCODE, MULTIPLE_WAREHOUSES, TERRITORY |
| ELECTRONICS | ATTACHMENTS, BARCODE, SERIAL_NUMBER, WARRANTY |
| RETAIL | ATTACHMENTS, BARCODE, EXPIRY_TRACKING, QR_CODE |
| GARMENTS | ATTACHMENTS, BARCODE, QR_CODE |
| RESTAURANT | ATTACHMENTS, EXPIRY_TRACKING, SHELF_LIFE |
| GENERIC | ATTACHMENTS, BARCODE |
| SERVICE | APPROVAL_WORKFLOW, ATTACHMENTS |
| CUSTOM | *(none — configured per deployment)* |

Modules run 10–12 per profile: RESTAURANT and SERVICE add kitchen/recipes and
projects/contracts, ELECTRONICS and MANUFACTURING get 11, everyone else the ten
core workspaces.

**Eleven of twenty-one features are actually enforced.** `BATCH_TRACKING` and
`SERIAL_NUMBER` gate whole endpoints; `EXPIRY_TRACKING`, `MANUFACTURING_DATE`,
`SHELF_LIFE`, `WARRANTY`, `BARCODE`, `QR_CODE`, `DRUG_LICENSE`, `ATTACHMENTS`
and `VEHICLE_TRACKING` gate fields. `TERRITORY`, `APPROVAL_WORKFLOW` and
`MULTIPLE_WAREHOUSES` have working code and are deliberately ungated pending a
product decision — enforcing `TERRITORY` today would take routes away from
PHARMACY, FOOD and RETAIL, which plausibly sell by territory. Six of the
remaining codes have no backing code and stay `is_implemented = false`:
`IMEI`, `PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`,
`SERVICE_CONTRACTS` and `PROJECT_MANAGEMENT`.

## Tables

Every one is **firm-owned** — it exists once per store.

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `business_profiles` | The industries | `code`, `is_default` (the fallback for unassigned firms) |
| `business_features` | The capability catalogue | `code`, `default_enabled`, `is_implemented` |
| `business_modules` | The workspace catalogue | `code`, `default_enabled` |
| `profile_features` | Which features an industry enables | `is_enabled` (overrides `default_enabled`), `configuration` |
| `profile_modules` | Which modules an industry enables | `is_enabled`, `is_visible`, `display_order` |
| `firm_business_profiles` | **The assignment** — firm → industry | `is_active` |
| `attribute_definitions` | Custom field definitions | `entity_type` (`PRODUCT`, `CUSTOMER`, `VENDOR`…), optional profile scope, data type |
| `category_attribute_rules` | Which fields are mandatory | `business_profile_id` (**NULL = every profile**), `category_code`, `is_mandatory` |
| `business_profile_uom_defaults` | Default units per industry | `firm_id` **NULL = the profile-wide default**; a firm's own row wins |
| `<module>_attribute_values` | The values themselves | Typed columns — `value_text`, `value_number`, `value_date`, `value_boolean`, never JSON |

**How a capability is resolved:** firm → its assignment → else the default
profile → else enforce nothing. Then per catalogue entry: an explicit
`profile_features` / `profile_modules` row wins, otherwise the catalogue's
`default_enabled`.

## Rules that bite

- **The gates are write-only.** Safe methods always pass, so turning a feature
  on can never hide data.
- **A firm with no resolvable profile is never gated.** A configuration gap is
  not a decision.
- **`is_implemented = false` refuses enabling**, and it is deliberately *not*
  `is_active`: one is a fact about the codebase, the other an administrator's
  choice. Conflating them lets someone switch on a feature that does nothing.
- **Deleting a feature or module a profile still enables revokes the capability
  for every firm on that profile** — writes those firms made yesterday start
  being rejected.
- **The desktop's menu filtering is cosmetic, not a security boundary.** It
  hides entries; the server's `require_feature` / `require_module` is the
  boundary.
- **Mandatory attributes must be scoped.** A global `mandatory` flag asks every
  industry for every field.
- **Renaming the default profile once demoted it**, leaving the store with no
  default and therefore no gating at all for unassigned firms. Fixed, but it is
  the shape to watch when editing a profile.

### ~~One inconsistency worth fixing~~ — closed by #168

Kept because the shape recurs. `20260810_0059` cleared `is_implemented` for
seven codes with no backing code. That was true of `COMMISSION` when it was
written and stopped being true on 2026-08-23, when `app/commission` shipped
with effective-dated rates, a collection-based report, seeded permissions and a
desktop screen — and the flag outlived the fact, so `_reject_unimplemented`
went on refusing an administrator a feature the platform had.
`20260903_0107` flipped it.

**`is_implemented` is a claim about the codebase, so it goes stale the moment
the codebase moves and nothing re-checks it.** Six codes still carry
`false`; each is one shipped module away from repeating this. Whatever
implements one of them has to flip its flag in the same change, the way #168
had to be a separate repair.

---

# 3. Document numbering and lifecycle

## What it does

Every transactional document needs two things a firm cares about: a **number**
somebody can quote down the phone, and a **status** that decides what may still
be done to it. Both are configuration held per firm, not code — so one firm can
run `INV-000001` and another `SI/2026-2027/000001`, and neither needs a release.

The same module keeps the **timeline** — an append-only record of every state a
document passed through and who moved it — and the **print template** that
decides what the printed copy says.

## Configure first

**Nothing.** This is the one module that needs no setup: the first time a firm
saves a document of a given kind, its document type, its states and its default
numbering rule are created on the spot.

The one input it does read is the firm's `financial_year_start` (module 1),
which decides the financial-year label a number carries and when the sequence
resets.

## Workflow

### A. First save of a document kind, in a firm

| # | What happens | Result |
| --- | --- | --- |
| 1 | The module bootstraps its own document type | Row in `document_type_definitions` — one per firm per kind |
| 2 | It creates that type's states | Rows in `document_state_definitions`, one flagged the default |
| 3 | It creates a default numbering rule | Row in `document_numbering_rules` with the module's prefix |

Thirteen kinds bootstrap this way, each with its own prefix:

| Prefix | Document | Prefix | Document |
| --- | --- | --- | --- |
| `QT` | Quotation | `PO` | Purchase order |
| `SO` | Sales order | `GRN` | Goods receipt |
| `DN` | Delivery note | `PI` | Purchase invoice |
| `SI` | Sales invoice | `PR` | Purchase return |
| `SR` | Sales return | `PC` | Physical count |
| `RC` | Receipt | `PY` | Payment |
| `RF` | Refund | | |

### B. How a number is built

Either from a `format_pattern` if the rule has one, or by joining these parts
with the rule's `separator` (default `-`), skipping any that is switched off:

```
prefix  [company_code]  [branch_code]  [financial_year]  sequence  [suffix]
  SI                                       2026-2027      000010
                     →  SI-2026-2027-000010
```

`sequence_padding` decides the zeros (default 6). `include_company_code`,
`include_branch_code` and `include_financial_year` are the switches.

### C. How the sequence resets

The counter is kept per **scope signature** — `financial year | branch |
company` — so with `auto_reset` on, a new financial year starts again at 1 while
last year's numbers stay untouched. A firm numbering per branch gets an
independent run per branch, which is what a branch that files its own returns
needs.

### D. Manual numbers

Only if the rule sets `manual_allowed`. Then a caller may supply its own number
and the sequence is not consumed — for entering historical documents that
already have numbers on paper.

### E. Every move is recorded

Each transition appends to `document_lifecycle_events`: which document, from
which state to which, by whom, when. **Append-only** — the timeline is what the
document's history *is*, and `GET /documents/{id}/timeline` is what a screen
shows.

Worth knowing what this costs: sending a quotation, accepting it, approving a
delivery note and approving a sales return each write **nothing but** a
lifecycle event and an audit row. That is the difference between paperwork and a
movement.

### F. Printing

A firm can restyle what its documents say — the banner text (`TAX INVOICE` or
`BILL OF SUPPLY`, both real documents), an accent colour, a header note, whether
bank details appear. One template per firm per document type.

Five documents render today: purchase order, tax invoice, delivery challan,
quotation and credit note.

## How to use it

| Task | Where | Permission |
| --- | --- | --- |
| Change a prefix, padding, or what a number includes | **Settings › Firm › Numbering Series** | `SETTINGS_VIEW` to see; platform admin to change |
| See what the next number will look like before saving | `GET /numbering-rules/{id}/preview` | firm membership |
| Read a document's history | The document's timeline panel | firm membership |
| Restyle the printed copy | Print template per document type | firm membership |

**Reading is firm membership alone; changing is platform admin.** Numbering and
lifecycle shape every document a firm will ever raise, so the module is
deliberately readable by everyone in the firm and writable by nobody in it.

## Tables

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `document_type_definitions` | One row per firm per document kind | `code`, unique per firm |
| `document_state_definitions` | The states that kind can be in | `is_default`, `is_terminal`, `allows_edit`, `allows_print`, `allows_email`, `allows_export_pdf`, `sort_order`, `transition_rules` |
| `document_numbering_rules` | How the number is composed | `prefix`, `suffix`, `separator`, `sequence_padding`, `include_financial_year` / `_branch_code` / `_company_code`, `auto_reset`, `manual_allowed`, `format_pattern`, `is_default` |
| `document_number_sequences` | The live counter | `scope_signature` (`year\|branch\|company`), `next_sequence` |
| `document_lifecycle_events` | The timeline, append-only | from-state, to-state, actor, timestamp |
| `document_print_templates` | Per-firm print styling | `document_type`, `title_text`, `accent_color`, `header_note`, `show_bank_details`; one live row per firm per type |

## Rules that bite

- **A state is configuration; the transitions are not.** The states, their names
  and their edit/print flags live in the database, but which transition a
  service will actually perform is written in that service. Renaming a state in
  the table does not teach `approve` about it.
- **Nothing sweeps the tables.** A quotation's `EXPIRED` is derived from
  `valid_until` on read, never stored, precisely because a job that had not run
  yet would let a stale quote through.
- **The counter is per scope, so changing what a number includes changes which
  counter it uses.** Switching `include_branch_code` on mid-year starts a fresh
  run per branch rather than continuing the firm-wide one.
- **A number is reserved when the document is saved, not when it is approved.**
  A cancelled draft has consumed its number, which is normal for a
  numbering series but surprises people expecting no gaps.
- **Timeline events are append-only** and cannot be edited away, like the audit
  trail they sit beside.

### Two settings that do not do what they say

Both surfaced from the obvious question — *what can we configure this to
ignore?* The answer is: most of it, and then two things that look configurable
and are not.

**`auto_reset` is written and never read.** Its only reference outside the
model and schemas is the bootstrap setting it to `True`. The yearly reset is
not driven by that flag at all — it is driven by the scope signature, which is
built as `financial_year | branch | company` and **always** includes the year
label, whatever `include_financial_year` says:

```python
financial_year_label or str(document_date.year)
```

So setting `auto_reset = false` changes nothing, and a firm that wants one
continuous run — `SI-000001` through `SI-004312` across five years — cannot
have it.

**And the two settings interact badly.** Switch `include_financial_year` off
while the counter still resets per year, and the second year reissues the
first year's numbers: `SI-000001` in 2025-26 and `SI-000001` again in 2026-27.
**No document number column carries a unique constraint anywhere** — not
`invoice_number`, not `order_number`, not any sibling — so nothing rejects the
duplicate. Two invoices, same firm, same number, no error.

That combination is a defect rather than a gap: the configuration is offered,
it is reachable from **Settings › Firm › Numbering Series**, and taking it silently
corrupts the series.

**`manual_allowed` is unreachable.** The plumbing is complete — `reserve_number`
accepts a `manual_number` and correctly returns it without consuming the
sequence — but **no document module passes one**. The flag can be set and has no
path to a caller. The only client-supplied number anywhere is
`settlements.settlement_number`, which has its own handling and bypasses the
numbering rule. That matters for the case people want it for: entering
historical documents that already carry numbers on paper.

### What *can* be configured away, and does work

`include_financial_year`, `include_branch_code`, `include_company_code`,
`prefix`, `suffix` (all nullable), `separator` (any string, including empty),
`sequence_padding` (`1` gives `SI-1`), and `format_pattern`, which bypasses
composition entirely with `{prefix}`, `{sequence}`, `{financial_year}`,
`{branch_code}`, `{company_code}` and `{document_date}`. `INV/1`,
`2026-2027-000001` and a bare `000001` are all reachable today.

### Three tables nothing writes

`document_headers`, `document_lines` and `document_totals` are declared, exported
from the model package, and referenced by **no service, router, script or test**
— every concrete module keeps its own header and line tables instead. They are a
generic document store that was designed and then not used.

They cost nothing at runtime, and they mislead: somebody reasonably reads the
schema, finds a "documents" table, and looks there for a sales order that will
never be in it. Either wire them up or drop them; leaving three empty tables
named after the module's central concept is the expensive option.

---

# 4. Financial year and chart of accounts

## What it does

Holds the books. A **financial year** divided into **accounting periods** says
when a document may be posted; a **chart of accounts** says where the money
lands; and the **control-account mapping** translates "this is a sales invoice"
into "debit 1100, credit 4000 and 2200".

Nothing here is optional decoration. Documents post through one service that
**refuses rather than guesses**, and a refused posting fails the document action
that triggered it — so an unfinished setup here does not produce wrong books, it
stops the firm trading.

## Configure first

| Needs | Why |
| --- | --- |
| The firm, provisioned (module 1) | The books live in the firm's own store |
| Its `financial_year_start` | The year and its twelve periods are built from that date |

Then four things must exist before **any** document can post:

1. a **journal type**,
2. a **voucher type**,
3. an **open accounting period covering the document's date**,
4. a **control account for every purpose that posting touches**.

Each missing one produces a message naming it — *"No open accounting period
covers 2026-08-28"*, *"This firm has no ledger account configured for:
INVENTORY, COST_OF_GOODS_SOLD"*. Gaps in the mapping are reported **all at
once** rather than one refusal at a time.

**The whole set is created by `scripts/seed_finance_defaults.py --yes`** — see
the runbook. The mapping in particular has no endpoint and no screen.

## Workflow

### A. Open the year

| # | Step | Endpoint | Permission |
| --- | --- | --- | --- |
| 1 | Create the financial year | `POST /finance/financial-years` | `FINANCIAL_YEAR_CREATE` |
| 2 | Create its periods (twelve monthly, by convention) | `POST /finance/accounting-periods` | `FINANCIAL_YEAR_CREATE` |
| 3 | Close or reopen a period | `PATCH /finance/accounting-periods/{id}` | `FINANCIAL_YEAR_CLOSE` |

A period is `OPEN`, `CLOSED` or `LOCKED`. Only `OPEN` accepts postings.
**A locked period accepts exactly one edit: being reopened.**

Periods are numbered and coded **within their year**, not within the firm — the
seeder writes `P01`…`P12` every year, so scoping the code to the firm would have
stopped a firm ever holding a second year, and with it year-end, comparatives
and prior-year reporting.

### B. Build the chart

| # | Step | Endpoint | Permission |
| --- | --- | --- | --- |
| 1 | Account groups | `POST /finance/account-groups` | `ACCOUNT_MANAGE` |
| 2 | Ledger accounts | `POST /finance/ledger-accounts` | `ACCOUNT_MANAGE` |
| 3 | Cost and profit centres (optional) | `POST /finance/cost-centers`, `/profit-centers` | `ACCOUNT_MANAGE` |
| 4 | Journal and voucher types | `POST /finance/journal-types`, `/voucher-types` | `ACCOUNT_MANAGE` |
| 5 | **Map the control accounts** | *(script only)* | — |

The seeded chart is a conventional distribution chart, not a claim about any
firm's conventions. A firm that wants a different one builds it through the API
and remaps its control accounts — changing a code or a name is an edit to seed
data, not a migration.

### C. Post by hand

| # | Step | Endpoint | Permission |
| --- | --- | --- | --- |
| 1 | Draft a journal entry | `POST /finance/journal-entries` | `JOURNAL_CREATE` |
| 2 | Post it | `POST /finance/journal-entries/{id}/post` | `JOURNAL_POST` |
| 3 | Reverse it | `POST /finance/journal-entries/{id}/reverse` | `JOURNAL_REVERSE` |

**A posted entry is reversed, never edited or deleted.** The reversal is a
mirror entry linked to the original, so both stay on the record.

### D. Read the books

| Report | Endpoint | Permission |
| --- | --- | --- |
| Trial balance | `GET /finance/trial-balance` | `TRIAL_BALANCE_VIEW` |
| General ledger for one account | `GET /finance/general-ledger/{id}` | `LEDGER_VIEW` |
| Profit and loss | `GET /finance/profit-loss` | `PROFIT_LOSS_VIEW` |
| Balance sheet | `GET /finance/balance-sheet` | `BALANCE_SHEET_VIEW` |
| Account summaries | `GET /finance/account-summaries` | `LEDGER_VIEW` |

## The default chart

**24 accounts in 5 groups**, seeded by `CHART` in
`app/finance/services/opening_setup.py` -- re-derive this table from there
rather than trusting it. It said nineteen until 2026-09-16, which was true when
written: commission, TCS and loyalty each brought accounts of their own when
those modules shipped, and nothing updated the count.

The **Purpose** column is what document posting actually looks up -- an account
with no purpose mapped is invisible to it.

| Code | Account | Type | Purpose |
| --- | --- | --- | --- |
| 1000 | Cash | Asset | `CASH` |
| 1010 | Bank | Asset | `BANK` |
| 1100 | Trade Receivables | Asset | `ACCOUNTS_RECEIVABLE` |
| 1200 | Inventory | Asset | `INVENTORY` |
| 1300 | Input Tax | Asset | `INPUT_TAX` |
| 2100 | Trade Payables | Liability | `ACCOUNTS_PAYABLE` |
| 2200 | Output Tax | Liability | `OUTPUT_TAX` |
| 2300 | Goods Received Not Invoiced | Liability | `GOODS_RECEIVED_NOT_INVOICED` |
| 2400 | Commission Payable | Liability | `COMMISSION_PAYABLE` |
| 2500 | TCS Payable | Liability | `TCS_PAYABLE` |
| 2600 | Loyalty Payable | Liability | `LOYALTY_PAYABLE` |
| 3000 | Opening Balance Equity | Equity | `OPENING_BALANCE_EQUITY` |
| 4000 | Sales | Income | `SALES_REVENUE` |
| 4100 | Sales Returns | Income | `SALES_RETURNS` |
| 4200 | Discount Received | Income | `DISCOUNT_RECEIVED` |
| 4900 | Rounding | Income | `ROUNDING` |
| 5000 | Purchases | Expense | `PURCHASE_EXPENSE` |
| 5100 | Purchase Returns | Expense | `PURCHASE_RETURNS` |
| 5200 | Cost of Goods Sold | Expense | `COST_OF_GOODS_SOLD` |
| 5300 | Discount Allowed | Expense | `DISCOUNT_ALLOWED` |
| 5400 | Purchase Price Variance | Expense | `PURCHASE_PRICE_VARIANCE` |
| 5500 | Inventory Adjustment | Expense | `INVENTORY_ADJUSTMENT` |
| 5600 | Commission Expense | Expense | `COMMISSION_EXPENSE` |
| 5700 | Loyalty Expense | Expense | `LOYALTY_EXPENSE` |

Groups: `CA` Current Assets, `CL` Current Liabilities, `REV` Revenue, `EXP` Direct Expenses, `EQ` Equity. A firm set up from 2026-10-02 also has `CA-CASH` *Cash-in-Hand* (1000) and `CA-BANK` *Bank Accounts* (1010) inside Current Assets (decision A22); an older firm has cash and bank directly in `CA`.

**`2300` and `5400` are the two people ask about.** *Goods Received Not
Invoiced* holds the accrual between a receipt and the bill for it. *Purchase
Price Variance* takes the difference when goods leave stock at a different
average from what a document said they cost — which is what stops a reversal
putting the ledger out against the warehouse.

A purpose must resolve to an account of the right classification: mapping
revenue onto an expense account is refused at mapping time rather than
discovered in a report.

## How to use it

| Task | Where |
| --- | --- |
| Open and close years and periods | **Settings › Firm › Financial Years** |
| Post and reverse journal entries | **Accounts › Journal Entries** |
| Trial balance, P&L, balance sheet, ledger statement | **Accounts › Trial Balance, Profit & Loss, Balance Sheet, Ledgers**; Cash Flow under **All Accounts screens › Statements** |
| Map control accounts | **Settings › Set up › Account structure › Control Accounts** (`ACCOUNT_VIEW` to read, `ACCOUNT_MANAGE` to write) |
| Cost centres and profit centres | **Settings › Set up › Account structure › Cost Centres**, **Profit Centres**. An account's *Requires a cost centre* / *Requires a profit centre* flag on the chart makes a journal line on it name one |

## Tables

All firm-owned, in the firm's own store.

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `financial_years` | The year | `starts_on`, `ends_on`, `is_active`, `is_locked` |
| `accounting_periods` | Its periods | `period_number` and `code` unique **per year**, `status` (`OPEN`/`CLOSED`/`LOCKED`) |
| `account_groups` | Classification for rollups | `code`, `account_type` |
| `ledger_accounts` | The chart | `code`, `account_type`, group |
| `firm_control_accounts` | **Purpose → account** | `purpose`, `ledger_account_id`. No API, no screen |
| `journal_types`, `voucher_types` | Required references for any posting | `code` |
| `journal_entries` | The entry | date, status, `reversal_of_id` |
| `journal_lines` | Its legs | account, debit, credit, narration |
| `gl_postings` | The ledger itself | what reports read |
| `ledger_balances` | Running balances | — |
| `customer_ledgers`, `vendor_ledgers` | Party sub-ledgers | — |

## Rules that bite

- **A posting failure fails the document.** Dispatch, invoice approval, receipts
  and returns all refuse rather than proceed unposted. That is deliberate: stock
  that moved with no accounting entry behind it is the gap the rule closes.
- **A date with no open period stops everything dated in it** — including
  backdated documents, which is what a firm building history hits first.
- **A posted entry is reversed, never edited.** Reversals are linked, and a
  lookup that filters only on POSTED will find the mirror and reverse the
  reversal; the reversal chain must be excluded explicitly.
- **The balance check and the stored lines must round the same way.** Checking
  a document balanced at four decimals while storing legs at two once allowed
  lines a cent apart with `is_balanced` true — and `gl_postings` copies line
  amounts straight through.
- **A ledger statement is dated by the journal date, not by when it was
  posted.** It was ordered by the wall clock at posting once, which puts a
  backdated entry in the wrong place.
- **Twelve periods is a convention, not a rule.** The seeder writes twelve
  monthly ones; the API will create any periods you ask for.

### The gap, stated once

`firm_control_accounts` is the only table in this module with no endpoint and no
screen, and it is the one without which nothing posts. Financial years, periods,
groups, accounts, journal and voucher types are all creatable through the API,
so a firm can be fully set up in every visible respect and still be unable to
approve an invoice. Either the mapping needs a screen, or provisioning should
seed it — and a readiness check on the firm would say which of the four
preconditions is missing before somebody discovers it at dispatch.

---

# 5. Branches and warehouses

## What it does

The firm's physical shape. A **branch** is a place that trades — it has an
address, a GST registration, working hours and a manager. A **warehouse** sits
under a branch and is a place that holds stock. Inside a warehouse, **storage
nodes** describe zones, racks and bins as a tree.

This matters beyond the address book: **every stock movement names a
warehouse**, and documents are filed against a branch. Nothing can be received,
dispatched, counted or transferred until at least one of each exists.

## Configure first

| Needs | Why |
| --- | --- |
| The firm, provisioned | Both are firm-owned |
| Geography masters (module 6) | Address fields are keys — country, state, district, city, postal code, locality — not free text |
| Branch and warehouse **types** (optional) | Classification only; a branch with no type is fine |

## Workflow

### A. Set up the places

| # | Step | Endpoint | Permission |
| --- | --- | --- | --- |
| 1 | Create branch types, if you classify branches | `POST /branch-types` | `BRANCH_UPDATE` |
| 2 | Create the branch | `POST /branches` | `BRANCH_CREATE` |
| 3 | Create warehouse types, if you classify warehouses | `POST /warehouse-types` | `WAREHOUSE_UPDATE` |
| 4 | Create warehouses under the branch | `POST /warehouses` | `WAREHOUSE_CREATE` |
| 5 | Describe the inside of a warehouse | `POST /warehouses/storage-nodes` | `STORAGE_AREA_MANAGE` |

A branch carries `code` (unique per firm), display name, the six geography
keys, address lines, timezone, currency, `gst_registration`, PAN, a licence
number, `working_hours` as JSON, and `is_default`.

A warehouse carries its branch, code, the same geography keys, `capacity` and
`capacity_unit`, `is_default`, and **ten capability flags** — temperature
controlled, cold storage, hazardous storage, and whether it has receiving,
dispatch, returns, inspection and packing areas and a loading dock.

### B. Bulk work

Both entities support the same six: `bulk-delete`, `bulk-restore`,
`bulk-status`, `duplicate`, `import` and `export`. Import **stages the whole
file and commits once**.

### C. Retire a place

| # | Step | Refused when |
| --- | --- | --- |
| 1 | Delete a warehouse (`WAREHOUSE_DELETE`) | It still holds stock — `current_quantity` or `reserved_quantity` is non-zero on any inventory record |
| 2 | Delete a branch (`BRANCH_DELETE`) | It still has live warehouses under it |
| 3 | Restore either (`*_RESTORE`) | — |

Both are soft deletes, and both refusals live **in the service**, which is the
only place they can: a soft delete never reaches the database's referential
check.

## How to use it

In the **Masters** drop-down, and under Settings for the set-up lists:

| Task | Where | Permission |
| --- | --- | --- |
| Branches | **Masters › Branches** | `BRANCH_VIEW` |
| Warehouses | **Masters › Warehouses** | `WAREHOUSE_VIEW` |
| Zones, racks and bins | **Settings › Set up › Locations › Storage Areas** | `STORAGE_AREA_MANAGE` |
| Classification | **Settings › Set up › Locations › Branch Types**, **Warehouse Types** | `BRANCH_VIEW` / `WAREHOUSE_VIEW` |
| What this deployment can do | Not offered in the menu: its screen was a placeholder with nothing to change | `BRANCH_VIEW` |

## Tables

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `branches` | Places that trade | `code` (unique per firm), six geography keys, `gst_registration`, `working_hours` (JSON), `is_default`, `status` |
| `warehouses` | Places that hold stock | `branch_id`, `capacity` + `capacity_unit`, `is_default`, ten capability flags, `status` |
| `warehouse_storage_nodes` | Zones, racks, bins | `parent_id`, `node_type`, `path` (materialised), `sort_order` |
| `branch_types`, `warehouse_types` | Classification | `code` |
| `branch_attribute_values`, `warehouse_attribute_values` | Custom fields (module 2) | Typed value columns |

## Rules that bite

- **Only one default branch and one default warehouse per firm.** The service
  demotes the incumbent and flushes *before* promoting the new one, and a
  partial unique index (`UQ_branches_default_active`,
  `UQ_warehouses_default_active`) holds the rule at the database.
- **An import stages and commits once.** Both import endpoints used to loop
  over the single-row create, which commits — so a batch whose fifth row
  clashed returned 409 with the first four already written, and the corrected
  file then failed on those four as duplicates. The import was impossible to
  complete. The dialog says which behaviour you get, because the first question
  after a failure is whether half of it went in.
- **The bulk endpoints are a second implementation.** All six once wrote no
  audit rows at all and skipped the delete guards their single-row twins
  enforced. Review both paths whenever either changes.
- **An update sends only what changed.** `BranchUpdate` / `WarehouseUpdate` are
  partial: one rename once cleared the branch's street lines, city, default
  flag and GST registration, and all ten warehouse capability flags, because
  the form does not edit those and the write model dumped defaults over them.
- **`ondelete="RESTRICT"` on the geography keys is not a guard.** Those masters
  are soft-deleted, so a "deleted" city stays wired to every branch naming it
  while vanishing from the list. The refusal has to be in the geography
  service (module 6).
- **A literal path must be declared before `/{id}`.** `GET /branches/export`
  and `GET /warehouses/export` were both read as an id and answered 422 —
  unreachable from the day they were written, and now guarded by a test.

### The settings screen is a capability report, not settings

`GET /branch-warehouse/settings` stores nothing and reads nothing. It returns
fourteen booleans **hardcoded in the router**, telling a client which
capabilities this deployment actually has, so a screen does not offer features
that cannot work. Every flag was once `True`, including five with no
implementation anywhere.

Which makes it the same shape as `business_features.is_implemented`: **a claim
about the codebase that goes stale the moment the codebase moves.** It has,
already — `stock_transfer_ready` still reads `False` with a comment saying *"No
transfer service or endpoint exists"*, and `POST /api/v1/inventory/transfers`
now moves stock between warehouses under `INVENTORY_ADJUST`, writing
`TRANSFER_OUT` and `TRANSFER_IN` movements. The capability shipped; the flag
was not flipped, so any client trusting this response hides a feature the
platform has.

`inter_branch_transfer_ready`, `rfid_ready`, `iot_ready` and
`warehouse_automation_ready` still read `False`, and those four are still true.

---

# 6. Geography

## What it does

One set of place masters that every address-carrying module names, so a city
means the same thing to a customer, a vendor, a branch and a warehouse.

```
geo_countries → geo_states → geo_districts → geo_cities
                                          → geo_postal_codes → geo_localities
```

Per firm store. Each of the four modules carries the same six keys, and
`GeoAreaPicker` is the **one** control that fills them — use it rather than a
fifth copy of the cascade.

## Configure first

Nothing. The masters are seeded, and a firm can add to them.

## Workflow

Settings › Set up › Locations › Places. Add a country, then its states, then
districts, then cities. A postal code hangs off a city; a locality off a postal
code.

## Rules that bite

1. **Customers are the odd one out, and the reason there is a migration.**
   They had free text and no keys where the other three had keys and no form.
   `20260816_0094` added the keys beside the text and backfilled only
   unambiguous matches.
2. **The keys are the truth; the text is derived from them.** `city`, `state`,
   `country` and `postal_code` are NOT NULL and every report reads them, so a
   row whose `city` says one thing and whose `city_id` says another leaves
   nothing to say which a report should believe. `CustomerService._apply_place`
   derives the text from the keys. An address naming no place keeps the text it
   was given.
3. **`ondelete="RESTRICT"` is not a guard here.** Every foreign key into the six
   tables is RESTRICT, which reads like protection — but these tables are
   soft-deleted, and a soft delete never reaches the database's referential
   check. A "deleted" city would stay wired to every branch naming it and
   simply vanish from the list. The refusal lives in the service, and it looks
   at the level below **and** at everything outside the module: addresses,
   branches, warehouses, route profiles.
4. **Two traps live in the picker itself**, both found by testing rather than
   by reading. A stored id that is not in the loaded list must stay as an item
   of its own, or `DropdownButtonFormField` asserts and the form saves as
   blank. And a rung must be loaded from the **new** selection rather than from
   `widget.value`, which the parent has not rebuilt yet in the frame the choice
   was made — choosing a country loaded no states at all, and shipped that way
   because the first two screens' tests only ever chose one rung.

---

# 7. Units and packaging

## What it does

A product is bought in one unit, held in another and sold in a third. This
module holds the units, the factors between them, and the packaging hierarchy a
scanner reads.

## The seven slots a product carries

| Slot | What it is for |
| --- | --- |
| `base_uom_id` | The unit everything converts through |
| `inventory_uom_id` | What the shelf is counted in |
| `purchase_uom_id` | What a purchase order is written in |
| `sales_uom_id` | What a sales document is written in |
| `minimum_sales_uom_id` | The smallest a customer may buy |
| `default_receiving_uom_id` | What a goods receipt defaults to |
| `default_dispatch_uom_id` | What a delivery note defaults to |

## Configure first

UOM groups and their units, then conversion rules. A product with no factor
between its purchase and inventory units cannot be received.

## How a factor is found

Effective-dated rules, resolved in a stated order: **the product's own rule
before the firm-wide one**, ranked explicitly rather than by NULL sort.

**Eight document modules call `convert_quantity` per line** — purchase, goods
receipt, purchase invoice, purchase return, sales order, delivery note, sales
invoice, sales return — plus `inventory`. They take a `factor = 1`
short-circuit only when the units match.

`quotation` deliberately does not convert: it moves no stock, and the
conversion happens when it becomes an order, because `convert_quotation` builds
that order through `SalesOrderService.create_order`.

## Packaging and barcodes

`product_packaging_levels` describes a carton holding a strip holding a piece,
each level carrying its own `barcode`, `gtin`, `ean` and `upc`.
`GET /barcode-lookup` resolves a code across all four columns and then the
product's own barcode, and answers with the product **and how many base units
one scan is**.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Units, groups, conversion rules | **Settings › Set up › Item lists › Units of Measure, UOM Groups, Conversion Rules** |
| Packing hierarchy and barcodes | **Settings › Set up › Item lists › Packaging Types, Packaging Levels** |

## Tables

`uoms` · `uom_groups` · `uom_group_units` · `uom_conversion_rules` ·
`packaging_types` · `product_packaging_levels` · `uom_industry_templates` ·
`business_profile_uom_defaults` · `uom_attribute_values`

## Rules that bite

1. **Never let NULL ordering pick a row.** PostgreSQL sorts NULLs first in
   `DESC`, SQLite last — so `ORDER BY product_id DESC` made a firm-wide rule
   outrank a product's own factor **in production** while the unit suite saw
   the right answer. Rank on `case((col.is_(None), 1), else_=0)`.
2. **A conversion rule's revision is `version_number`, not `version`.**
   `version` is the concurrency counter, and `uom.ConversionRule` was renamed
   in `20260809_0055` after the ORM was found moving the revision on every
   save. The rename also found a second copy of the resolver in `app/inventory`
   matching a line's stored revision against the *counter*, which agreed only
   until somebody edited a rule.
3. **A packaging level's barcode columns were read by nothing** until
   `/barcode-lookup` shipped — the framework documentation described a scanner
   that had no implementation behind it.

---

# 8. Tax setup

## What it does

What a document is taxed, decided by rules rather than by a rate on a product.
Systems hold components, components make profiles, and rules choose which
profile applies to a given line of a given document.

## The shape

| Layer | What it is |
| --- | --- |
| `tax_systems` | GST, VAT — a country's regime |
| `tax_components` | CGST, SGST, IGST, CESS — what gets charged |
| `tax_profiles` | A named bundle of components with effective-dated rates |
| `tax_rules` | Which profile applies, given the document |

## Configure first

A country mapped to a tax system, then components, then at least one profile,
then a rule that reaches it. A product carries `tax_profile_group_code` — not a
profile — and the rule matches on it.

## How a rate is chosen

ACTIVE rules ordered `priority ASC, code ASC, version_number DESC`, and **the
first match wins and evaluation stops**. This is the opposite of promotions,
which stack.

**Rules attach to the transaction, never to the product.** The product
contributes `tax_profile_group_code`, `product_category_id` and `product_type`
to the matching context; everything else comes from the document.

## A rule's scope is a filter; its **action** is the answer

The distinction that costs an afternoon if you have it backwards. A rule's
`country_id`, `business_profile_id` and `tax_profile_id` are **scope filters** —
"only consider me when this is already the context". They do not decide
anything. What a matching rule *does* is its `actions`:

| Action | Effect |
| --- | --- |
| `APPLY_TAX_PROFILE` | Charge this profile instead of the one in context |
| `APPLY_TAX_COMPONENT` | Add one component |
| `OVERRIDE_COMPONENT_PERCENTAGE` | Same component, different rate |
| `EXEMPT_TAX` · `ZERO_RATED` | Nothing charged, and they are not the same thing on a return |
| `REVERSE_CHARGE` | The buyer accounts for it; reported separately, never added to the total |
| `INPUT_CREDIT_ALLOWED` · `INPUT_CREDIT_BLOCKED` | Whether the tax can be reclaimed |

So an interstate rule scoped to the IGST profile never fires: the document
arrives carrying the *product's* profile, not the one you hope to end at. The
rule matches on the transaction and **switches** the profile with
`APPLY_TAX_PROFILE`. Driven on 2026-09-16, the wrong shape silently charged an
interstate sale CGST+SGST — right total, wrong components, and a GST return
that files them in the wrong boxes.

**The simulation says why.** Every response carries a `decisions` array: one
entry per rule considered, with `matched` and a reason —
*"Tax profile did not match the rule scope."*, *"transaction_type failed
EQUALS."* Read it before changing a rule; it is the difference between
debugging and guessing.

## `simulate` is the calculation, not a preview

All the transactional modules call `TaxRuleService.simulate` once per line
while building a document, on their own session — so **it must never commit**.
The `/simulate` endpoint owns that.

It also derives `country_id` from the applied profile's tax system and
`business_profile_id` from the firm's assignment, because no document sends
either and rules scoped that way would otherwise never match.

**`total_tax_amount` is only what the counterparty is billed.** Tax
`included_in_price` and tax under `REVERSE_CHARGE` are reported separately in
`inclusive_tax_amount` and `reverse_charge_tax_amount`, and must not be added
to a document total.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Tax systems, components, rates | **Settings › Tax › Tax Configuration** |
| Rules, trying one, what a calculation decided | **Settings › Tax › Tax Rules, Rule Simulator, Execution Log** |
| Tax defaults; GST documents (dispatch policy, e-invoice route, return filing) | **Settings › Tax › Tax Settings, GST Documents**; **TDS on Purchases (194Q)** |

## Tables

`tax_systems` · `tax_components` · `tax_profiles` · `tax_profile_components` ·
`tax_country_mappings` · `tax_rules` · `tax_rule_conditions` ·
`tax_rule_actions` · `tax_rule_execution_logs` · `tax_settings` ·
`tax_profile_attribute_values` · `tax_migration_mappings`

`tax_rule_execution_logs` grows fastest of anything in the platform — one row
holding three JSON documents per document line — and is pruned per firm store
by `scripts/purge_retention.py`.

## Rules that bite

1. **A flag the engine records has to change an outcome.**
   `included_in_price` and `REVERSE_CHARGE` were stored, returned in the
   response and read by nobody, so configuring either silently produced wrong
   money.
2. **A scope filter must be satisfiable by the callers that actually exist.**
   Rules can be scoped by country; no document sends one; country-scoped rules
   therefore never fired until `simulate` began deriving it.
3. **A product seeded before its firm had a tax profile keeps a NULL
   `tax_profile_group_code`**, matches no rule, and is **billed with no tax at
   all**. WHOLE01's toothpaste did exactly that for two financial years —
   37,105 of supplies — and nothing said so until a GST return reported a
   nil-rated row nobody had asked for.
4. **A rule is superseded, not edited**, and carries `version_number`. A
   document priced in March must still be explicable in September.

---

# 9. Products, attributes, batch and serial

## What it does

What the firm buys and sells, what industry-specific facts it records about
each, and — where the industry needs it — which physical batch or serial each
unit came from.

## Configure first

UOM groups and conversion rules, a product category, and a tax profile group.
A product saved without a factor between its units cannot be received.

## Custom fields, not columns

A module gains industry-specific fields through `AttributeService`, **never** by
adding columns. An `AttributeDefinition` targets an `entity_type` and is
optionally scoped to one business profile, so a pharmacy firm carries fields a
food firm does not.

**The catalogue is shared; value storage is per module.** Each module owns a
small table extending `AttributeValueBase` — `product_attribute_values` is the
reference — keeping a real foreign key to the owning record and its own
indexes.

**Values live in typed columns** (`value_text`, `value_number`, `value_date`,
`value_boolean`) so list filters and reports can index and query them. A
`products.category_attribute_values` JSON blob existed until 2026-08-09 and
could not be filtered.

Read attributes for a list of records with `values_for_many`, **never per row**.

## Tracking flags

`track_batch` · `track_expiry` · `track_lot` · `track_serial` ·
`track_manufacturing_date` · `track_warranty` · `require_batch_on_receipt` ·
`require_batch_on_issue` · `require_serial_on_receipt` ·
`require_serial_on_issue` · `allow_negative_stock` · `allow_fraction` ·
`allow_decimal`

Several are gated by the business profile: setting `track_expiry` on a firm
whose profile does not enable `EXPIRY_TRACKING` is refused **when the field is
populated**, not when the endpoint is called — blank and unchanged always pass,
so a firm cannot be stopped from creating a product because it does not scan
barcodes.

## Batch, lot and serial

`batches` records a physical intake — a number, a manufacturing date, an
expiry. A traced product may only be **issued from a batch**, and dispatch
takes the batch nearest expiry first.

**No demo firm serialises.** `serial_numbers` and `lots` hold no rows in any
store, so that half of the module runs on unit tests alone.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Products | **Masters › Products** |
| Categories, brands, principals | **Settings › Set up › Item lists › Product Categories, Principals, Brands** |
| Custom fields and which are mandatory | **Settings › Business profile › Attribute Definitions, Mandatory Attributes**; a firm's own: **Settings › Firm › Custom Fields, Custom Field Rules** |
| Batches, lots, serials, expiry | **Stock › Batches, Expiry Monitor**; **All Stock screens › Tracking** |

## Tables

`products` · `product_categories` · `product_attribute_values` ·
`product_media` · `batches` · `lots` · `serial_numbers`

## Rules that bite

1. **No attribute is mandatory for every firm.** `20260801_0011` seeded four
   attributes with `mandatory = True` and no scope, which asked a pharmacy for
   an IMEI and an electronics distributor for an expiry date — and
   `AttributeService` refuses the write, so it **blocked product creation on
   any freshly-migrated database**. `20260815_0087` clears it. Where an
   attribute really is required, say so in `category_attribute_rules`, scoped
   to a business profile and a category.
2. **A master field added later never reaches a store already seeded.** The
   batch flags were the first instance, the HSN code the second,
   `tax_profile_group_code` the third. Expect another every time a master gains
   a field the demo needs.
3. **`ondelete="RESTRICT"` will not stop a soft delete.** The refusal has to
   live in the service.

---

# 10. Customers, groups and credit policy

## What it does

Who the firm sells to, what they owe, what they have been promised, and how far
they are allowed to go. Four things live here that look like one: the customer
record, their **commercial segment**, their **receivable ledger**, and the
firm's **credit policy**.

## Configure first

| Needs | Why |
| --- | --- |
| Geography masters | An address names real places, not free text |
| A chart of accounts and an open period | An opening balance **posts**, and is refused if it cannot |
| Customer groups (optional) | The last tier of the discount chain |

## Workflow

| Step | Permission | Result |
| --- | --- | --- |
| Create | `CUSTOMER_CREATE` | A customer, optionally with an opening balance |
| Edit | `CUSTOMER_UPDATE` | Partial: what is not sent is left alone |
| Import | `CUSTOMER_IMPORT` | Staged, and committed **once** |
| Credit policy | `CUSTOMER_MANAGE_SETTINGS` | The firm's rule, not one customer's |

`CUSTOMER_MANAGE_SETTINGS` is deliberately **not** granted to `SALES_MANAGER`.
The role the limit constrains must not be able to switch it off.

## The receivable ledger

Every movement of what a customer owes is a row in
`customer_receivable_transactions`, typed:

| Type | Raises or lowers | Note |
| --- | --- | --- |
| `OPENING_BALANCE` | raises | Posts `Dr Accounts Receivable / Cr Opening Balance Equity` |
| `INVOICE` | raises | |
| `RECEIPT` | lowers | Splits into balance and advance when it overpays |
| `ADVANCE_RECEIPT` | — | Money held against nothing yet |
| `ADVANCE_APPLY` | lowers | **Posts no journal** — the money already moved |
| `CREDIT_NOTE` | lowers | |
| `REFUND` | raises | |
| `TCS` | **raises** | The buyer owes it *on top of* what they just paid |
| `LOYALTY` | lowers | Credit already owed, spent — the firm has been paid |

**A statement recomputes its running balance in date order.** The stored
`outstanding_after` is a snapshot taken in the order things were *recorded*; a
statement is read in the order things were *dated*. Money arriving against last
month's bill is recorded after it and dated before it, so the stored figure
shows a balance that never existed on any day.

**An ageing row reconciles against the account and says how.** The bills and
the balance are not the same number — a credit note reduces the account and
sits on no invoice, while TCS raises it without being billed. The report shows
`total_outstanding − unapplied_credits + charges_not_billed` and that equals the
balance exactly.

## Credit policy

Per firm, in `credit_control_settings`: `enforcement` is `OFF`, `WARN` or
`BLOCK`, with a warn and a block percentage. A firm with **no row warns at 80%
and never blocks**, which is why shipping this stopped nobody trading.

Checked at two points, both where credit is committed: **sales order approval**
and **sales invoice approval**. Exposure is
`current_outstanding − unapplied_advance + the document being saved`.

`GET /customers/{id}/credit-status?amount=` answers before a document is saved,
rather than reporting the breach after.

**A `credit_limit` of zero means unset, not "no credit".**

**The desktop warns and never blocks.** A client that blocked on its own would
enforce a rule the firm may not have chosen, and could be bypassed by any other
client. It also stays silent when the server would refuse anyway, because the
refusal carries the same sentence.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Customers | **Masters › Customers** |
| Customer groups | **Settings › Set up › Party lists › Customer Groups** |
| Credit policy | **Settings › Selling › Credit Control** (`CUSTOMER_MANAGE_SETTINGS`) |
| Statements and ageing | **Sell › Customer Statements** |

## Tables

`customers` · `customer_addresses` · `customer_contacts` ·
`customer_attribute_values` · `customer_groups` ·
`customer_receivable_transactions` · `credit_control_settings`

## Rules that bite

1. **An update is partial, and it has to be.** `addresses` and `contacts` are
   **replaced**, not merged, so reconciling a collection the caller never sent
   soft-deleted every row in it. Both are guarded on `model_fields_set` now,
   and `opening_balance` is read from the dumped values with the row as its
   fallback — reading it off the model made an omission mean zero, which the
   balance-reset guard then acted on.
2. **The place keys are the truth; the text is derived from them.** `city`,
   `state`, `country` and `postal_code` are NOT NULL and every report reads
   them, so a row whose `city` says one thing and whose `city_id` says another
   leaves nothing to say which a report should believe.
3. **`customer_type` is a legal classification** — INDIVIDUAL or BUSINESS.
   Hanging a price or an offer on it was never possible; `customer_groups` is
   the firm's own segmentation.
4. **Deleting a group somebody is in is refused in the service.**
   `ondelete="RESTRICT"` is not a guard on a soft-deleted table — a retired
   group would otherwise stay on every customer's record while vanishing from
   every list.
5. **Import stages and commits once.** Looping over a committing create meant a
   batch whose fifth row clashed returned 409 with the first four already
   written, and the corrected file then failed on those four as duplicates.

---

# 11. Vendors

## What it does

The other side of the customer: who the firm **buys** from. A vendor record
carries the identity a purchase document needs (name, code, GSTIN, PAN), the
people and places to send an order to, and the bank account a payment settles
into. Four modules point at it — `purchase_orders`, `goods_receipts`,
`purchase_invoices` and `settlements` — so a vendor is created once and named
for the life of a purchase.

It is deliberately the same shape as a customer: one header row with child
collections beside it, custom fields through `AttributeService`, and the same
import, export, duplicate, bulk and restore actions. Where the two differ is
what they carry, not how they behave, so a screen learned on one is a screen
learned on both.

## Configure first

| Thing | Needed for | What happens without it |
| --- | --- | --- |
| Nothing at all | A vendor | A vendor with a code and a name is valid |
| **Vendor categories** | Grouping and reporting | The field stays empty; nothing refuses |
| **Vendor types** | Distinguishing a manufacturer from a stockist | The field stays empty; nothing refuses |
| **Geography masters** | Addresses that report by place | The address keeps its text and reports by nothing |
| **A business profile with `DRUG_LICENSE`** | Recording a drug licence on a tax row | The field is refused — see rule 3 |

Both masters are optional and both are `RESTRICT`-ed from the vendor, so one
in use cannot be removed.

## Workflow

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Create the vendor — code, name, display name, and whether they are GST registered | `VENDOR_CREATE` | Row in `vendors`, status `ACTIVE` |
| 2 | Add contacts, addresses, bank accounts, tax rows, attachments, notes | `VENDOR_UPDATE` | Child rows, each soft-deleted on its own |
| 3 | Fill the firm's custom fields | `VENDOR_UPDATE` | Rows in `vendor_attribute_values`, typed |
| 4 | Buy from them | `PURCHASE_*` | The vendor id is stamped on the order and travels to the receipt, the bill and the payment |

Retiring one is a soft delete (`VENDOR_DELETE`) and `POST /{id}/restore` brings
it back with its children, because the children were never hard-deleted either.

## How to use it

| Task | Where |
| --- | --- |
| Create, edit, retire, restore, duplicate vendors | **Masters › Vendors** (`VENDOR_VIEW`) |
| Group them | **Settings › Set up › Party lists › Vendor Categories** (`VENDOR_MANAGE_CATEGORIES` to write) |
| Manufacturer, stockist, importer… | **Settings › Set up › Party lists › Vendor Types** (same code) |
| Import a list, export the grid | The toolbar (`VENDOR_IMPORT`, `VENDOR_EXPORT`) |
| Change many at once — status, category, profile | The grid's bulk actions (`VENDOR_UPDATE`) |

Endpoint table, generated rather than typed:

```powershell
uv run python scripts/dump_route_permissions.py --markdown vendors
```

## Tables

All in the firm's own store.

| Table | Holds |
| --- | --- |
| `vendors` | The header: code, names, category, type, business profile, status, GST registration, GSTIN, PAN, licence and registration numbers, contact details |
| `vendor_categories`, `vendor_types` | The two optional masters, `RESTRICT`-ed from the header |
| `vendor_contacts` | People, with their own phone and email |
| `vendor_addresses` | Places, carrying the same six geography keys every address-bearing module uses |
| `vendor_bank_accounts` | Where a payment goes |
| `vendor_tax_details` | Registration rows — and the drug licence, which is why it is checked per row |
| `vendor_attachments`, `vendor_notes` | Documents and free text |
| `vendor_attribute_values` | The firm's custom fields, in typed columns rather than JSON |

`business_attributes` on the header is a JSON column and is **not** the custom
fields mechanism; industry-specific fields belong in `vendor_attribute_values`
through `AttributeService`, where a list filter can index them.

## Rules that bite

1. **Code and GSTIN are unique per firm, not globally.** `UQ_vendors_firm_code`
   and `UQ_vendors_firm_gstin` are composite with `firm_id`, so two firms may
   each have a `V001`, and one firm may not. The service checks first for the
   message and the database constraint catches the race — both paths answer
   *"Vendor code or GSTIN already exists in this firm."*
2. **A `PUT` leaves alone what it does not name, and an explicit `null`
   still clears.** Both halves of the request now read silence the same way.
   Until 2026-09-16 the header did not: `_vendor_values` dumped the whole
   write model, so a payload naming only a phone number also set `gstin`,
   `pan` and `website` back to null -- the trap that wiped a product's tax
   group and units the day before, and the convention in
   [`API_AND_PERSISTENCE_CONVENTIONS.md`](API_AND_PERSISTENCE_CONVENTIONS.md).
   Create is unchanged: there a default really is the value to store.
   The **collections** have always worked this way and are guarded
   separately -- each is touched only when the caller actually sent it
   (`is not None`), so a client that does not manage contacts cannot erase
   them by omission. A submitted collection is reconciled row by row, and a
   row that has gone answers *"A vendor contact no longer exists."* rather
   than being silently re-created.
3. **A drug licence is a feature-gated field, not a feature-gated vendor.** A
   firm whose profile lacks `DRUG_LICENSE` still keeps vendors — it simply has
   no business recording a licence number against one. The check runs over
   **every submitted tax row** (`tax[0].drug_license`, `tax[1]…`), because the
   number lives on the tax rows rather than on the header. A firm with no
   resolvable profile is never gated: a configuration gap is not a decision.
4. **A category or type a live vendor still names cannot be retired.**
   *"This category is used by 3 vendor(s) and cannot be deleted. Move them to
   another category first."* Both keys carry `ondelete="RESTRICT"`, which
   reads like protection and is not: these masters are soft-deleted, and a
   soft delete never reaches the database's referential check -- the trap
   geography documents in section 6. So the refusal lives in the service,
   where products have had one since they were written. It counts **live**
   vendors: a retired vendor does not hold its category open. Added
   2026-09-16, when writing this section found vendors to be the one master
   module without it.
5. **Deleting a vendor does not delete their history.** Purchase orders,
   receipts, invoices and settlements hold the vendor id and go on naming it.
   That is the point of a soft delete: the documents stay readable and the
   vendor stops appearing in pickers.

---

# 12. Territory, routes and beats

## What it does

Who calls on which shop, when. A firm-configurable hierarchy of places, the
rounds a salesman walks, and the plan that turns a round into today's call
list.

## The hierarchy is the firm's own

`sales_hierarchy_levels` defines the levels; the demo firms run **Region →
Territory → Route**. A node becomes a **route** when it has a
`territory_route_profile`, which carries the working days the round is walked.

## Configure first

Hierarchy levels, then nodes, then a route profile on the leaves, then customer
and salesman assignments.

## The three keys on a customer assignment

`territory_customer_assignments` carries the customer, the route, and a
`visit_sequence` — the shop's position on the round.

**`PUT /{id}/customers` replaces the whole list**, with position in the list as
the sequence, so membership and order travel together. Omitting `is_primary`
means *leave it alone*: sending it back would demote the round somebody chose
and collide with the one-primary-per-shop key.

## How a beat plan becomes a call list

Three conditions decide whether a plan calls anybody, and **all three must
hold**:

1. the recurrence hits that date (weekly, fortnightly, monthly),
2. the route's effective window is in force on that date, and
3. **the route works that weekday**.

The call list returns **every** plan with an `occurs` flag and a `reason`, not
just the due ones — so a plan that does not fire says why rather than
disappearing.

A plan may name its own stops in `sales_beat_plan_customer_stops`, which is
**additive**: a plan listing none falls back to the customers on its territory
in `visit_sequence` order. That is the ordinary case and needs no rows at all.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Territories, route types, routes | **Settings › Set up › Territories & routes › Territories, Route Types, Route Builder** |
| Beat plans, call lists, coverage | **Sell › All Sell screens › Field sales** |

## Tables

`sales_hierarchy_configs` · `sales_hierarchy_levels` · `sales_territories` ·
`sales_route_types` · `territory_route_profiles` · `territory_working_days` ·
`territory_customer_assignments` · `territory_salesman_assignments` ·
`sales_beat_plans` · `sales_beat_plan_customer_stops`

## Rules that bite

1. **A partial unique index cannot be `DEFERRABLE`, so a swap must release
   before it reassigns.** `UQ_territory_customer_assignments_sequence_active`
   keeps two shops off one stop number, and PostgreSQL checks it per statement
   — so reassigning row by row collided the moment two rows exchanged values,
   which is exactly what dragging one stop above another does. `set_customers`
   clears the numbers it is about to hand out, flushes, then writes them, and
   clears **only** the ones actually moving.
2. **A screen that replaces a whole list must prove it read that list first.**
   Both territory screens clear the pane **before** the read rather than after
   it succeeds, and refuse to save until the pane provably holds the selected
   route — without that, a failed read left the previous route's shops on
   screen and one Save wrote them over a different round.
3. **A route's effective window is enforced**, judged on the document's own
   date. It decides both whether a beat plan calls the round and whether a
   document may be tagged with it.
4. **A salesman must cover the customer's territory.** `_validated_salesman`
   refuses anybody who does not — and until the demo put salespeople on rounds,
   *every* attempt to name a salesman was refused on every customer of every
   firm, which is how three `select(User)` defects survived months of green
   tests.
5. **`TERRITORY` is deliberately ungated.** Only AGENCY and WHOLESALE enable
   the feature, so enforcing it would take routes and beats away from PHARMACY,
   FOOD and RETAIL. The seeded assignment looks more wrong than the code does.

---

# 13. Price lists and the discount chain

## What it does

What a customer pays off a product, before any offer is applied. A price list
is a **ladder of quantity breaks**, scoped to one customer, one territory, or
the whole firm, and effective-dated.

## Configure first

Products, and customers or territories if the list is to be scoped. Nothing
else — a firm with no price list simply resolves the tier below.

## How a rate is found

`PriceListResolver` is built **once per document**, not per line: the lists
that could apply depend on the customer, the territory and the date, none of
which change between lines.

Then `rate_for(product, quantity)` takes the **highest break at or below** the
line's quantity. Breaks of 0, 50 and 200 price a line of 120 at the 50.

**A more specific list replaces the ladder rather than merging into it.** A
customer's own arrangement *is* the arrangement, not an amendment to the
firm-wide one — merging would silently give them breaks nobody agreed with
them.

**`None` is not zero.** A product no list mentions falls through to the
customer's blanket rate; a product a list deliberately puts at **zero** does
not.

## Where it sits in the chain

Fourth of six. Below anything typed and below a promotion, above the customer's
standing rate and their segment's:

```
explicit amount → explicit percent → promotion → PRICE LIST →
customer's standing rate → customer group rate
```

**A promotion outranks it**, which is the thing to remember when a list appears
not to work. An unconditional offer means the list is never consulted at all.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Price lists and price levels | **Settings › Set up › Pricing › Price Lists, Price Levels** |
| The lowest price, each role's discount limit | **Settings › Selling › Price Floor, Discount Limits** |

## Tables

`price_lists` · `price_list_items`

The unique key is `(list, product, min_quantity)`. It was `(list, product)`
until quantity breaks existed, which meant a list could hold only one row per
product — the whole limitation the ladder removes.

## Rules that bite

1. **No line editor may prefill the discount box.** Filling it turns an
   inherited arrangement into an override, and a literal `0` refuses every
   arrangement. The quotation editor filled it with the customer's standing
   rate — so **no price list could reach a quotation raised from the desktop at
   all**, from the day price lists shipped.
2. **A list outside its effective window does not apply**, judged on the
   document's date.
3. **Rank on an explicit `case`, never on NULL ordering.** PostgreSQL sorts
   NULLs first in `DESC` and SQLite last, so a firm-wide rule outranked a
   product's own factor in production while the unit suite saw the right
   answer.

---

# 14. Promotions and coupons

## What it does

Offers the firm is running: what they give, who qualifies, whether they stack,
and what each one has cost. Modelled on `app/tax` — a rule, typed condition
rows, action rows and an execution log — with one deliberate difference.

**Promotions stack; tax does not.** The tax engine breaks at the first match.
The promotion engine applies **every** matching offer in `priority ASC, code
ASC, version_number DESC, created_at ASC` order, until one with
`allow_stacking = false` is applied, which ends evaluation.

## What an offer can give

| Action | Parameters | What it changes |
| --- | --- | --- |
| `LINE_DISCOUNT_PERCENT` / `_AMOUNT` | percent / amount | The line's resolved discount |
| `BILL_DISCOUNT_PERCENT` / `_AMOUNT` | percent / amount | The document's bill discount, then apportioned |
| `FREE_QUANTITY` | buy, free | More of **the same** product — adjusts the line |
| `FREE_PRODUCT` | product, quantity | A **different** product — **emits a new line** |
| `FREE_SHIPPING` | none | Sets `freight_amount` to nothing |

`FREE_PRODUCT` emits a line because there is no line to adjust. The gift is
appended **before anything is priced**, so it flows through conversion, tax and
totals exactly as a typed line does — and it sets `discount_percent` to an
**explicit zero**, because silence would let the customer's standing rate
resolve and a bill for nothing would print a discount percentage.

`FREE_SHIPPING` takes no parameter: a partial waiver is `BILL_DISCOUNT_AMOUNT`,
which already exists. It waives the charge whole or not at all, so two offers
cannot waive it twice.

## What an offer can ask about

`customer_id` · `customer_group_id` · `branch_id` · `territory_id` ·
`route_id` · `salesman_id` · `product_id` · `product_category_id` ·
`product_type` · `line_quantity` · `line_gross` · `document_gross` ·
`transaction_type` · `transaction_date`

Every one is satisfiable by a document that actually exists. The tax module's
lesson is that **a scope filter nothing satisfies never fires** — tax rules can
be scoped by country, no document sends one, so country-scoped rules never
matched anything.

## Stacking, precisely

**Percentages compound on what is left, never add on the gross.** Two stacked
10% offers take 19%, not 20%. That is the retail meaning, and it is also the
only basis on which stacked benefits cannot exceed the line — which matters,
because `resolve_line_discount` refuses a discount above the line and a
promotion configuration must not be able to make a document unsaveable.

**A stacking engine must collapse to one live version per `version_group_id`.**
Superseding leaves the predecessor ACTIVE, and tax survives that only by
stopping at the first match. Copying its query verbatim hands the customer the
same offer twice.

## Claims

`promotion_redemptions` has three states and they are not the same fact:

| State | When | Counts against a limit |
| --- | --- | --- |
| `PENDING` | The document is priced | **No** |
| `CLAIMED` | The document is **approved**, under a row lock | **Yes** |
| `REVERSED` | The document is cancelled | No |

Booking at approval rather than while pricing is load-bearing: pricing runs on
the caller's session and **must never commit**, so a counter incremented there
would either publish a half-written order or count a draft nobody approved.

Two behaviours follow, both deliberate. An offer already exhausted is **not
quoted at all**, so nobody is promised a price the approval would refuse. And
two documents priced while it still had room race at approval, where the loser
is **refused by name** rather than silently repriced.

## Coupons

A coupon is a way of *reaching* an offer, not a second kind of one — the
benefit, the conditions and the stacking rule stay on the promotion.
`sales_orders.coupon_code` sits on the order rather than the quotation, because
the order is what gets approved.

**An unrecognised code leaves the order saveable and simply gives nothing.** A
typo in a field that gives money away must not refuse a sale.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Offers, coupons, copy with new dates, try offers | **Settings › Set up › Pricing › Promotions** |
| How several matching offers combine | **Settings › Selling › Sales Stages** |

## Tables

`promotions` · `promotion_conditions` · `promotion_actions` ·
`promotion_coupons` · `promotion_redemptions` · `promotion_execution_logs`

`version_number` is the published revision; `version` is the concurrency
counter and must not be reused for it.

`promotion_execution_logs` grows fastest of anything here — one row holding
three JSON documents per document line — and is pruned by
`scripts/purge_retention.py`.

## Rules that bite

1. **An offer's identity is its `version_group_id`, not the row.** An ACTIVE
   promotion is superseded rather than edited, so anything identifying it by
   row id breaks the moment somebody changes it — and changing it is the
   routine act, because there is no other way. Three checks did: a coupon was
   orphaned by any edit, `max_redemptions` reset to zero so an exhausted
   campaign came back to life, and retiring an offer left its codes live and
   pointing at nothing.
2. **`evaluate` never commits.** The `/simulate` endpoint owns that.
3. **A line somebody priced by hand is skipped, and the trace says so.** A log
   reporting a benefit the line never received is a lie told to the person
   asking why the price is what it is.
4. **A blanket offer switches off every tier beneath it.** Not a small
   discount — a decision that no price list, standing rate or segment rate will
   ever be consulted. Nothing in the engine can tell the firm did not mean it.

---

# 15. Buying — purchase order to payment

## What it does

Four documents move goods from a supplier onto the shelf and the money out of
the bank. Only three of the transitions reach outside their own module;
everything else is paperwork and status, and knowing which is which is most of
understanding this chain.

| Document | What it changes outside itself |
| --- | --- |
| Purchase order | Nothing. It records an intention. |
| **Goods receipt** | **Posts stock, and posts to the ledger** |
| **Purchase invoice** | **Posts the payable and the input tax** |
| **Purchase return** | **Takes stock back off, and reverses its journal** |

## Configure first

| Needs | Why | What breaks without it |
| --- | --- | --- |
| A branch and a warehouse | Every line lands somewhere | The order cannot be saved |
| A vendor | Who is supplying | Same |
| A product with its UOM slots | The order is in purchase units, the shelf in inventory units | Conversion fails on the line |
| A tax profile on the product's group | The line has to be taxed | The document totals with no tax and nobody is told |
| An open accounting period | The receipt posts into it | The receipt completes and the posting is refused |
| Numbering series for all four | Each takes its own number | The first document of the kind fails |

## Workflow

### A. Raise and approve the order

| Step | Who | Result |
| --- | --- | --- |
| Create | `PURCHASE_CREATE` | `DRAFT` |
| Submit | `PURCHASE_UPDATE` | `SUBMITTED` |
| Approve | `PURCHASE_APPROVE` | `APPROVED` |

**Approval cannot be skipped.** `approve` on a draft is refused with *"Submit
the order first"*, and a receipt is refused against anything that is not
`APPROVED`, `PARTIALLY_RECEIVED` or `RECEIVED`. Until 2026-08-18 a draft could
be received against and the receipt completed — which posts stock and posts to
the ledger — so the approval step was bypassable by any client that did not
filter its own picker.

**Editing an approved order withdraws the approval** and returns it to `DRAFT`,
recorded on the timeline as `purchase.approval_withdrawn`. Editing a received
one is refused outright: its lines are what stock was posted at.

`PARTIALLY_ORDERED` and `ORDERED` are declared and **no order header ever
takes either**. A header only moves through `DRAFT`, `SUBMITTED`,
`APPROVED`, `PARTIALLY_RECEIVED`, `RECEIVED`, `CANCELLED` and `CLOSED`.
Worth knowing before reading the code: `PurchaseOrderStatus.ORDERED` **is**
assigned — to `purchase_order_lines.status`, which is a different column
sharing the same enum. A grep for the name finds it and looks like a
contradiction.

### B. Receive the goods

Completing a goods receipt posts stock and the ledger, and moves the order:
`_resync_order_status` writes `PARTIALLY_RECEIVED` and `RECEIVED` as receipts
complete, and walks it back as they are cancelled. It is **derived by summing
the completed receipts**, not incremented — an incrementing counter and a
reversal are two chances to disagree.

**Cancelling a completed receipt reverses both the stock and the journal**, and
the journal follows the stock: it credits inventory with what the movement
actually removed, at the moving average, and books the difference from the
receipt price to `PURCHASE_PRICE_VARIANCE`. Mirroring the original entry
instead credited inventory with a number no movement ever removed, and put a
seeded store 2,287.42 out in a single cancellation.

### C. Bill it

Approving a purchase invoice posts the payable, the input tax and the
inventory clearing. **After that the receipt can no longer be cancelled** — the
invoice already cleared the accrual, and a purchase return is the way.

**Input credit is decided per bill line.** Each line carries *Eligible*,
*Blocked (s.17(5))* or *Ineligible*, defaulting from the product or the expense
account, then from a tax rule's *Input credit blocked*, and changeable on the
line. Only an eligible line's tax goes to input tax (1300); the tax on a blocked
or ineligible line is a cost of buying and is posted to **5450 Input Tax Not
Claimable**. GSTR-3B reports blocked credit in 4(A)(5) and reverses it in
4(B)(1), and credit ineligible for any other reason in 4(D)(2).

**A supplier has a GST type** — Regular, Composition, Unregistered, Overseas or
SEZ — set on the supplier. Only a *declared* Composition, Unregistered or
Overseas supplier is billed no GST and gives no credit; a supplier with no type
set is taxed by the rules as before, because a GSTIN nobody typed in does not
make a supplier unregistered. Reverse charge still applies to any of them.

**GSTR-2B** (the portal's file of what suppliers reported) is imported under
**Accounts › All Accounts screens › Tax filing › GSTR-2B Reconciliation** and matched to the firm's approved bills by supplier
GSTIN, bill number and date, with a ₹1 tolerance. Each document reads Matched,
Different, In 2B only or In books only. By default 3B keeps claiming **every**
bill and lists what 2B lacks; a firm can switch to claiming **matched bills
only**.

### D. Send goods back

Completing a purchase return takes stock off and reverses the payable, the
input tax and the inventory credit. A return (or a debit note) off a bill the
firm paid **reverse charge** on takes its share of that reverse-charge tax off
as well, rather than leaving the self-assessed tax standing. Cancelling that
return takes its journal back off too. Until 2026-08-22 it reversed the stock and left the payable
standing — the same defect `goods_receipt` carried until 2026-08-18, in its
mirror, which nobody thought to look for.

A line can be flagged **damaged**, **expired** or **scrap**, and the damaged
and expired reports filter on exactly those flags.

## How to use it

**Buy › Purchase Orders**, then **Goods Receipts** and **Purchase Invoices**
(all in the Buy drop-down; **Returns & notes** opens Purchase Returns and Debit
Notes). New → lines → Submit → Approve. Receive from the order's own dialog;
bill from the receipt; return from the receipt. Requisitions, Approvals and
Quality Inspection are under **Buy › All Buy screens › Documents**; the
purchase-side money screens (Payment Runs, Post-dated Cheques, Supplier Gifts,
Supplier Rebates, Principal Claims, Landed Costs) under **Money**; Purchase
Settings, Approval Limits and Purchase Budgets under **Settings › Buying**.

Six reports: register, orders not yet received, overdue, and by supplier, by
buyer and by product.

## Added on 2026-10-05 (backlog 86, PG-1 to PG-14)

Built and merged on their own tests; **not yet through a full suite, CI or a
hand test**. Screens new to the menu: **Requests for quotation, Rate
contracts, Supplier schemes** and **Bills of entry** under **Buy › All Buy
screens › Documents**, **Payables by Month** under **Money**, and **Fixed
assets** under **Accounts › All Accounts screens**.

| Feature | How to use it | Its rules |
| --- | --- | --- |
| **Request for quotation** | New → products and invited suppliers → **Send** → **Enter quotes** per supplier → **Compare** → choose a quote per line → **Save selections** → **Raise orders**. An approved requisition has **Create RFQ** | Compared on the rate after discount, before tax. A choice off the lowest needs a reason. One draft order per chosen supplier; the RFQ then closes. Raising orders needs `RFQ_MANAGE` and `PURCHASE_CREATE`. Emailing it is not built |
| **Rate contract** | New → supplier, period, product, rate, optional quantity → **Approve**. Then leave the price blank on an order line for that supplier | The contract's rate ranks above the supplier's price list. Drawn is the ordered quantity on approved orders, never stored. Over-drawing warns and never refuses. An active contract past its last day reads expired and prices nothing. Overlap for one product and supplier is refused at approval |
| **Supplier scheme** | New → supplier (or all), product, buy quantity, free quantity, optional free product, dates. Then raise an order | A same-product scheme fills a **blank** free quantity; a typed figure is kept and 0 refuses it. Another product is offered as a gift line, added once. The supplier's own scheme beats an all-suppliers one. The receipt and bill inherit the free goods |
| **Serials at receipt** | On a serial-tracked receipt line open **Serials**: type, paste, or **Fill a range** | One serial per unit (accepted plus free) before the receipt completes. A serial is unique in the firm, case ignored. Cancelling the receipt removes the units unless one has moved |
| **PTR and PTS** | On a batch receipt line type PTR and PTS beside the MRP; set **Trade class** on the customer | Needs the feature `BATCH_PTR_PTS` (Pharmacy, Food, Wholesale). A batch number is required; neither rate may exceed the MRP. A blank sales price ranks: typed, price list, batch rate, price level, product |
| **Attachments** | **Attachments** on a purchase bill or a goods receipt | PDF, JPG or PNG, 10 MB, at any status. Removing one is audited. OCR is not built |
| **Paid now** | In the bill's Approve dialog tick **Paid now** → method, amount, reference, date → **Approve and pay** | One commit: the bill approves and an ordinary payment is allocated to it. Needs `PAYMENT_CREATE`. More than the bill owes is refused |
| **TDS 194C / 194J** | Set the supplier's **Usual TDS section**; thresholds and rates under **Settings › Tax › TDS on purchases (194Q, 194C, 194J)**. Approve the bill: the dialog shows the proposal and an override box | Posted at approval. A payment ahead of any bill proposes it instead; it is deducted once. What a bill owes is its total plus TCS less TDS |
| **TCS on a purchase** | Type a **TCS rate** or **TCS amount** on the bill | A rate alone is worked on the total including GST; a typed amount wins. Outside GST. Posts Dr TCS Receivable (1430) at approval |
| **PO by WhatsApp** | **Send** on the order → WhatsApp | Messaging, the channel and the template for *Purchase order sent to the supplier* must be set. Template only, no PDF. The order is marked sent |
| **Imports** | Give the supplier a **Currency**; raise the order with **Currency** and **Exchange rate**, receive it, and bill the receipt (or type the bill alone, in that currency with its rate); pay it from Payments in the currency | Lines and totals as typed; stock and the journal in rupees, the receipt at the order's rate and the bill at its own. A bill is in its order's currency: another is refused, and another rate posts only the difference to price variance. An order's currency and rate cannot change after a completed receipt. No TCS, TDS or Paid now. The payment's rate against the bill's posts the exchange gain or loss. Rupees are refused against a foreign bill |
| **Bill of Entry** | New → link the bills and receipts → per line the assessable value and the duty rates or amounts → **Post** | Basic duty and surcharge (10% of the duty by default) land on the linked receipts' stock; a line no receipt carries is an expense. IGST and cess are input tax. The linked receipts must be completed. Cancel reverses |
| **Fixed assets** | Tick **Capital goods** on the order line (or the receipt line), then pick an asset class on the bill line; or tick it on a bill typed alone; or type an opening asset in the **Asset register**. **Depreciation runs** → run a period. **Dispose** on an asset | The line debits the asset account instead of stock, one asset per line. A line marked on the order or the receipt is received without entering stock; a line a receipt already took into stock is refused at the bill. A run is pro rata by days, one journal, forward only, the latest cancellable. Disposal books the gain or loss. The Income-tax block schedule posts nothing |
| **GST purchase register, Payables by Month** | Reports › Financial; Buy › All Buy screens › Money | Read on every call, nothing stored. Debit notes and returns after billing are minus rows. Payables are checked against control account 2100 |

**Two things that bite.** A machine must be marked **Capital goods** on the
order or the receipt **before** the receipt is completed: once a receipt has
taken a line into stock the bill refuses to capitalise it. And capital goods
cannot go back as a purchase return -- they never entered stock -- so claim
their value with a debit note and dispose of the asset under Fixed Assets.
A debit note or a purchase return against a foreign-currency bill is typed
in the bill's currency and posts rupees at the **bill's** rate, not the
day's (D-BUY-41); the registers, purchase analysis, GSTR-2B matching, rule
37, rule 42 and GSTR-3B all show such a bill in rupees at that rate.

**Not built:** OCR of a supplier's bill; emailing an RFQ; a Bill of Entry in
the GST purchase register and against GSTR-2B; returns and debit notes in
another currency; withholding on a payment abroad (section 195); capitalising
goods already in stock; GST on the sale of an asset; recurring bills, job work,
drop-ship, consignment and a supplier credit limit.

## Tables

`purchase_orders` · `purchase_order_lines` · `purchase_order_history` ·
`purchase_notes` · `purchase_attachments` · `purchase_delivery_schedules`
`goods_receipts` · `goods_receipt_lines` · `_notes` · `_attachments`
`purchase_invoices` · `_lines` · `_sources` · `_accounting_events` · `_notes` ·
`_attachments`
`purchase_returns` · `_lines` · `_sources` · `_accounting_events` · `_notes` ·
`_attachments`

Added 2026-10-05: `rfqs` · `rfq_lines` · `rfq_suppliers` ·
`supplier_quotations` · `supplier_quotation_lines` · `rate_contracts` ·
`rate_contract_lines` · `supplier_schemes` · `goods_receipt_line_serials` ·
`bills_of_entry` · `bill_of_entry_lines` · `bill_of_entry_documents` ·
`bill_of_entry_allocations` · `tds_section_settings` · `document_files` ·
`document_file_contents`; fixed assets keep `asset_classes` · `fixed_assets` ·
`depreciation_runs` · `depreciation_run_lines`.

Lines are reconciled on their **line number**, not deleted and re-inserted.
Downstream documents record `source_document_line_id` as a bare UUID with no
foreign key, so re-inserting lines silently leaves those references dangling.

## Rules that bite

1. **A status is not writable through the update body.** `update_order` read
   `data.status` until 2026-08-18, and the write schema defaults it to `DRAFT`
   — so a client that said nothing about the status silently reset an approved
   order, and a partially-received one that nothing could then move back.
2. **An invoiced receipt cannot be cancelled.** The refusal names the invoice.
3. **A reversal is valued from the movement, never from the document.** Goods
   arrive at one average and leave at another; mirroring an entry across that
   gap is what puts a store out.
4. **`reverse_entry` copies the source module and id onto the mirror it
   posts**, so a lookup filtering only on `POSTED` finds the mirror next time
   and reverses the reversal. Match `reversal_of_id IS NULL`.
5. **A traced product may only be issued from a batch**, so a return of one has
   to name the batch going back.
6. **A purchase return line must name a warehouse** — it does not fall back to
   the header's, where `sales_return` does. Such a return could be raised and
   approved and then never completed.

---

# 16. Selling — quotation to cash

## What it does

Five documents take an offer to money in the bank. The chain is longer than the
buying one and the rules are subtler, because a price agreed at one step must
survive to the next.

| Document | What it changes outside itself |
| --- | --- |
| Quotation | Nothing. It commits nothing and reserves nothing. |
| Sales order | **Reserves stock**; claims any promotion at approval |
| **Delivery note** | **Moves stock, and posts cost of goods sold** |
| **Sales invoice** | **Posts revenue, receivable and output tax** |
| **Sales return** | **Takes stock back, credits the customer** |
| Receipt | **Posts cash and clears the receivable** |

**A firm chooses which of the first three its people type**, per stage, in
`sales_workflow_settings`. A firm with no row types all four.
`SalesChainService` raises whatever is switched off by driving the same
services a person would, so **the documents are real**: stock still leaves at
dispatch and cost of goods sold still belongs to the delivery note.

## Configure first

Everything the buying chain needs, plus a customer, and — if the firm uses them
— price lists, customer groups, promotions and a loyalty scheme. None of those
is required; all of them change the price.

## The price, and how it survives the chain

This is the part worth reading twice. **A line discount is resolved in one
place**, `resolve_line_discount`, and six tiers are ranked:

| Rank | Tier | Where it comes from |
| ---: | --- | --- |
| 1 | An explicit **amount** | Typed on the line |
| 2 | An explicit **percentage** | Typed on the line |
| 3 | A **promotion** | The offers in force on the document's date |
| 4 | A **price list** | The customer's own, else the territory's, else the firm's |
| 5 | The customer's **standing rate** | `customers.default_discount_percent` |
| 6 | Their **segment's** rate | `customer_groups.default_discount_percent` |

Three things follow that surprise people.

**`None` and `0` are different answers.** Saying nothing takes whatever
arrangement applies; sending zero refuses every one of them for this line. That
is why no line editor prefills the discount box: filling it turns an inherited
arrangement into an override, and a literal `0` turns it off.

**A blanket offer switches off every tier beneath it.** An unconditional
promotion is not a small discount — it is a decision that no price list, no
standing rate and no segment rate will ever be consulted. Nothing in the engine
can tell that the firm did not mean it.

**A downstream document inherits, it does not re-resolve.** The delivery note
ships the order line's price; the invoice bills the note's. Re-deciding one
document later is how an agreement gets quietly rewritten — an offer that
expires between the order and the invoice must not change the bill.

## Workflow

### A. Offer

**Rate includes GST.** The quotation and the sales order each carry a *Rate
includes GST* switch, defaulting in the editor from the firm's setting. Sent by
nobody it is **off** — a converted quotation, a counter bill and an import all
hand over rates already before tax. The line keeps the rate as typed beside the
pre-tax figure and the editor shows it back as typed. A quotation typed at shelf
prices becomes an order typed at them, read back to pre-tax at the order's date,
so the customer is billed what was quoted. Bills raised from an order print only
the pre-tax rate.

Quotation: `DRAFT` → `SENT` → `ACCEPTED` → `CONVERTED`, or `DECLINED`.
Expiry is derived from `valid_until` and nothing writes an `EXPIRED` status.
An expired quotation cannot be accepted or converted. Converting twice is
refused by name.

### B. Order

`DRAFT` → `APPROVED` → `PARTIALLY_DELIVERED` → `DELIVERED`.

Approval reserves stock, claims any promotion under a row lock, and checks the
credit policy. **A hold is a flag, not a status** — an order that is
`PARTIALLY_DELIVERED` can be held, and releasing it must put it back where it
was, so nothing is overwritten and nothing has to be restored. **The stock
stays reserved** while held: holding says "not yet", not "never".

### C. Dispatch

The delivery note moves stock and posts cost of goods sold, and moves the
order — derived by summing the notes that have left the warehouse.

A note line carries **two quantities and they are not interchangeable**:
`current_delivery_quantity` is what the customer is charged for, and
`delivered_quantity` is that plus free goods converted into inventory units.
The second is right for stock, because all of it left. **Only the first is a
billing cap.**

**Every delivery note states why the goods are going out** — a *reason*: Sale
(the default), Van or route sale, On approval, Quantity not known, Job work, or
Other with words. It prints on the challan. A transfer between branches is a
stock transfer, not a delivery note, so it is not a reason.

**Dispatch before an invoice is a firm policy** (Settings › Tax › GST
Documents): **Off** says nothing, **Warn** (the default) lets a Sale note go and
records the warning on the dispatch, **Block** refuses and points at *Dispatch
and invoice*. A van or route sale is not judged unless the firm switches on
*route sales need the invoice first*. **Dispatch and invoice** is one action
that dispatches the note and raises and approves its invoice together, so the
invoice exists at removal.

**Batches are confirmed on the delivery note.** Each line opens with the
batches the order reserved (earliest expiry first), and a **batch picker** lists
every batch of the product in the warehouse — expiry, days left, and available
(on hand less what is reserved for other orders). A line may split across
batches and the challan prints one row per batch. The server checks product,
warehouse, expiry on the document date and availability, and records a skip of
the earliest-expiry order in the audit trail.

### D. Bill

`DRAFT` → `APPROVED`. Approval posts revenue net of discount, the receivable
and the output tax, and snapshots what the goods cost onto
`sales_invoice_lines.cost_amount` for any margin-based commission.

### E. Money

A receipt splits when it is recorded: `min(amount, outstanding)` comes off the
balance and the excess becomes an unapplied advance. Allocating that advance
later **posts no journal** — the money already moved; only the part that became
an advance moves the balance.

Reversing a settlement puts the balances back **by the deltas stored on the
original row**, never recomputed: a receipt of 500 against an outstanding 300
splits into 300 and 200, and only that row remembers the split.

## How to use it

**Sell** drop-down, one tab per document: **Quotations, Sales Orders, Delivery
Notes, Sales Invoices** and **Returns & notes** (Sales Returns, Credit Notes,
Customer Debit Notes); Enquiries, Proforma and Approvals under **All Sell
screens › Documents**; which stages the firm types under **Settings › Selling ›
Sales Stages**. The invoice can be raised from the billable-notes picker; the order carries deposits and promotion claims in its
own dialog.

## Added on 2026-10-05 (backlog 87, SG-1 to SG-9)

Built and merged on their own tests; **not yet through a full suite, CI or a
hand test**. Screens new to the menu: **Counter Shifts** and **Customer
Rebates** under **Sell › All Sell screens › Documents**, **Collection Sheet**
and **Payment Promises** under **Money**, and **Transporters** under
**Settings › Set up › Territories & routes**.

| Feature | How to use it | Its rules |
| --- | --- | --- |
| **GST sales register, HSN summary of sales** | Reports › Financial | Read through GSTR-1's own readers, so they agree with the return. Credit notes, completed returns and late cancellations are minus rows on their own dates; a customer debit note is a plus row. `SALES_VIEW` or `REPORT_VIEW` |
| **Walk-in cash sale** | On the counter bill choose **Walk-in**; type the buyer's name and phone | One *Cash sale* customer per firm. The bill must be paid in full to be approved. No loyalty points; B2C. A buyer's name is refused on any other customer's bill |
| **Service invoice** | Put a product of type *Service* on any sales document | Billed with its SAC. No reservation, no dispatch movement, no cost of goods sold, never a back order. It still rides the whole chain |
| **Other charges** | On the sales bill, **Other charges** → **Add charge**: name, amount, tax profile, SAC | Up to ten. Taxed by the profile each names; none means no tax. Credited to *Other Charges Recovered* (4050). In GSTR-1, 3B, the register, the e-invoice and the print. Not carried from the order; cannot be credited |
| **Transporters, freight terms** | Keep carriers under Transporters; on the delivery note pick **Carrier (master)** and **Freight** | The note copies the carrier's name, GSTIN or TRANSIN and mode where they were left blank; what is typed wins; the master never rewrites a note. An inactive carrier is refused. Freight terms print and move no money. Read `SALES_VIEW`, keep `SALES_UPDATE` |
| **Attachments** | **Attachments** on the quotation, order, delivery note, invoice and return lists | PDF, JPG or PNG, 10 MB. Each document keeps its own. Viewing takes the document's view code, adding and deleting its update code |
| **Hold and recall** | On the counter bill **Hold (F8)** with a note; **Recall** to bring one back | A hold is a flag on a draft, not a status. A held bill is never approved, singly or in bulk. Nothing moves in stock |
| **Counter shift** | **Open shift** with a float; bill; **Close shift** with the counted cash | One open shift per cashier. Expected cash is the float plus the cash tenders whose receipts stand, derived on every read. The difference posts to *Cash Short and Over* (6960); exact posts nothing. Closed by its cashier or a holder of `SALES_APPROVE`. Optional |
| **Collection follow-up** | Set **Collector** on the customer; open **Collection Sheet**; record a promise from a bill's row; follow them in **Payment Promises** | A promise posts nothing. Pending, due today, kept, broken or withdrawn is derived from the receipts between the day taken and the day promised. Withdrawn, never edited. Refused on a draft, on a bill that owes nothing, for more than it owes |
| **Customer rebate** | **Customer Rebates** → an agreement for a customer or a group, a period and slabs → after the period, **accrue** → settle against bills | Turnover is derived from the documents GSTR-1 counts. The slab reached rates the whole turnover. Accrued once: Dr Rebates Allowed (5310), Cr Customer Rebates Payable (2900). Settled only by a party adjustment of kind `CUSTOMER_REBATE`. No GST. One live agreement per customer per overlapping period. Agreeing takes `SALES_APPROVE`; settling `PARTY_ADJUSTMENT_MANAGE` |

**Two things to know.** A bill paid at the counter is stamped with the open
shift of the cashier who **made** it: `CASHIER` and `BILLING_EXECUTIVE` cannot
approve, so a manager approves their bills, and the bill still lands in the
cashier's shift. The approver's own shift takes it only when the maker has
none open. And *Settle against bills* on Customer Rebates is shown on
`PARTY_ADJUSTMENT_MANAGE` alone, so a `SALES_MANAGER` is not offered it;
`FIRM_ADMIN` and `FIRM_MANAGER` are.

**Not built:** a counter refund against a bill, a count by denomination and a
hand-over of a shift; a promise for the account as a whole from the screen,
the promise on the customer statement and a reminder from a broken promise;
changing the carrier of a note already raised; a rebate settled by a GST
credit note or paid out in money; and rows 10 to 31 of `BACKLOG.md` §87 (van
sales, export and SEZ, warranty, packing slip, bill of supply and the rest).

## Tables

`sales_quotations` · `_lines` · `_notes` · `_attachments`
`sales_orders` · `_lines` · `_notes` · `_attachments` · `sales_workflow_settings`
`delivery_notes` · `_lines` · `_notes` · `_attachments`
`sales_invoices` · `_lines` · `_line_taxes` · `_sources` · `_accounting_events`
`sales_returns` · `_lines` · `_line_taxes` · `_sources`
`gst_compliance_settings` (the firm's dated GST document settings)

Added 2026-10-05: `sales_invoice_charges` · `transporters` ·
`payment_promises` · `counter_shifts` · `customer_rebate_agreements` ·
`customer_rebate_slabs` · `document_files` · `document_file_contents`.

`sales_invoice_line_taxes` is what makes a printed tax invoice possible: a line
kept a single `tax_amount` until 2026-08-22, so the CGST/SGST split a tax
invoice must state existed only in a prunable log.

## Rules that bite

1. **A bill charges for what was sold, not for what left the warehouse.** A
   note dispatching 12 with 1 free had all 12 billed and offered a thirteenth.
2. **A gift line is owed until an invoice line references it**, counted in rows
   and never in quantity — zero minus zero is zero however often it is stated.
3. **A discount on the whole document reaches the lines, and therefore the
   tax.** It is apportioned across the lines in proportion to what each is
   worth *after* its own discount, stored on the line, and the rounding
   residual goes to the largest line so the shares sum exactly.
4. **Freight is inside the taxable value**; `additional_charges` is outside it.
5. **A credit note reverses tax on the base the invoice taxed** — charges and
   freight included.
6. **A chain of committing services is not a transaction.** Compose the
   `stage_*` methods and commit once; `begin_nested` does not help, because
   `Session.commit()` commits the outermost transaction.
7. **Credit limits warn, and block only if a firm asks.** A `credit_limit` of
   zero means unset, not "no credit".

---

# 17. Proforma invoices

## What it does

A bill that is not a bill: what an order **will** be charged, stated in
advance. A buyer often needs a document before the goods move — to open a
letter of credit, to get a payment approved internally, to clear customs, to
release funds against an advance. A quotation is an offer and a tax invoice is
a demand; the proforma is the thing in between.

It is raised from an **approved sales order** and states that order's lines,
prices and tax. It moves no stock, raises no revenue and creates no
receivable.

## Configure first

| Thing | Needed for |
| --- | --- |
| An **approved** sales order | There is nothing else to state |
| A `PROFORMA_INVOICE` document type with its own numbering series | The number on the document |

Tax setup matters only in that the proforma repeats what the order computed;
it runs no tax engine of its own.

## Workflow

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Raise it against an approved order | `PROFORMA_MANAGE` | `DRAFT`, numbered from the proforma series |
| 2 | Correct it while it is still yours | `PROFORMA_MANAGE` | Still `DRAFT` |
| 3 | Issue it | `PROFORMA_MANAGE` | `ISSUED`, and now frozen |
| 4 | Replace it, if terms change | `PROFORMA_MANAGE` | A new proforma whose `supersedes_id` points at the old one |
| 5 | Cancel it | `PROFORMA_MANAGE` | `CANCELLED`; nothing to unwind, because nothing posted |

The sales chain is untouched by all of this. The order proceeds to delivery
and a tax invoice exactly as it would have.

## How to use it

**Sell › All Sell screens › Documents › Proforma** (`PROFORMA_VIEW`). Two reports sit beside the register:
**Register** lists what was issued over a period, and **Outstanding** lists
proformas that have not yet turned into an invoice — the follow-up list for
whoever is chasing an advance.

```powershell
uv run python scripts/dump_route_permissions.py --markdown proforma
```

## Tables

| Table | Holds |
| --- | --- |
| `proforma_invoices` | Header: the order it states, its own number (unique per firm), `valid_until`, status, and `supersedes_id` |
| `proforma_invoice_lines` | The stated lines, with the prices and tax the order carried |

**Neither table has a `journal_entry_id` or a `receivable_transaction_id`, and
that absence is the design** — see rule 1.

## Rules that bite

1. **A proforma posts nothing, and there is deliberately nowhere to record
   that it did.** No revenue, no output tax, no receivable, no stock movement.
   The columns are missing on purpose: adding either one later is the first
   step towards a document that looks like a bill to the books as well as to
   the customer.
2. **Its number comes from its own series, never the tax invoice's.** GSTR-1's
   DOCS section declares the invoice series a firm issued, so a proforma
   drawing from that series would either leave a gap the return cannot explain
   or put a number in it that was never a supply.
3. **Once issued it cannot be edited** — *"Only a draft proforma can be
   changed. Once it has gone to the customer, raise a replacement instead."*
   The customer may already be arranging payment against that number, and a
   document that quietly changed under them is worse than a second one that
   says it replaces the first.
4. **Only an approved order can be stated** — *"A draft is not a deal and a
   cancelled one has been called off."* An order with no lines is refused too:
   there is nothing to state.

---

# 18. Credit notes

## What it does

Money credited to a customer **without goods coming back** — a rate agreed
after invoicing, a quality allowance, a billing error. It always names the
invoice it credits, and it reverses that invoice's **tax** along with its
value.

This is deliberately **not** a sales return. A return is goods coming back:
stock moves, the warehouse counts them, and cost of goods sold is reversed at
what the movement was worth. A credit note moves no stock at all. Conflating
the two would put a stock movement behind a rate correction, which is the
shape of defect that leaves a warehouse disagreeing with its own ledger.

**Why the module exists.** A credit note already existed as a row in
`customer_receivable_transactions`, raised from the customers router. It
reduced what the customer owed, booked the whole figure to sales returns — and
reversed **no output tax at all**. A firm that agreed a rate difference after
invoicing credited the customer the gross amount and went on declaring tax on
a price nobody paid.

## Configure first

| Thing | Needed for |
| --- | --- |
| An **approved** sales invoice | The document being credited, and the rates to reverse at |
| Open books with `OUTPUT_TAX`, `SALES_RETURNS` and `ACCOUNTS_RECEIVABLE` mapped | The journal the approval posts |
| A `CREDIT_NOTE` document type and series | The number |

## Workflow

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Raise it against an approved invoice, line by line, with a reason | `CREDIT_NOTE_MANAGE` | `DRAFT`; nothing has posted |
| 2 | Correct it | `CREDIT_NOTE_MANAGE` | Still `DRAFT` |
| 3 | Approve it | `CREDIT_NOTE_APPROVE` | Posts the journal, reduces the receivable, stamps `journal_entry_id` and `receivable_transaction_id` |
| 4 | Cancel it | `CREDIT_NOTE_APPROVE` | Reverses what it posted |

Approving is a separate permission from raising on purpose: whoever states
that the firm owes money back should not be the only person who agrees it.

## How to use it

**Sell › Returns & notes › Credit Notes** (`CREDIT_NOTE_VIEW`; customer debit notes beside it). Three reports: **Register**,
**By customer**, and **By reason** — the last is the one that tells a firm
whether it is crediting for quality, for pricing, or for its own billing
mistakes.

```powershell
uv run python scripts/dump_route_permissions.py --markdown credit_note
```

## Tables

| Table | Holds |
| --- | --- |
| `credit_notes` | Header: `sales_invoice_id` (required), reason, status, and the `journal_entry_id` / `receivable_transaction_id` stamped at approval |
| `credit_note_lines` | One line per invoice line credited, carrying the rate that invoice charged |

## Rules that bite

1. **It always names the invoice it credits, and the line it credits.** Tax
   has to be reversed at the rate that **was charged**, not at today's rate,
   and only the original line knows what that was — the same reasoning that
   stops an invoice re-reading a customer's discount. It is also what a GST
   credit note has to state. A line naming no invoice line is refused: *"A
   credit note line must name a line of the invoice it credits."*
2. **You cannot credit more than was charged.** The cap is per line and counts
   what earlier notes already took: *"A credit note cannot credit more than
   the line was charged: X charged, Y already credited."* The invoice line is
   **locked while the cap is read**, so two notes racing cannot both see the
   same headroom — a sum guarded by a read is not guarded at all (see
   [`API_AND_PERSISTENCE_CONVENTIONS.md`](API_AND_PERSISTENCE_CONVENTIONS.md)).
3. **Only an approved invoice can be credited** — *"A draft is not a sale, and
   a cancelled one has already been undone."*
4. **Only a draft can be changed** — *"Cancel this one and raise another."*
   Once it has posted, editing it would rewrite a journal that has already
   been declared.
5. **A credit note for nothing cannot be approved.** Zero value, zero tax,
   nothing to post.
6. **It is not a sales return, and the two are not interchangeable.** If goods
   are physically coming back, raise a sales return so the stock moves and the
   cost is reversed at what the movement was worth.

## The debit note to a customer

The credit note turned the other way: **more** charged on an invoice already
raised — a price that rose after billing, a short-billed quantity, an extra
charge. **Sell › Returns & notes › Customer Debit Notes**, `/api/v1/customer-debit-notes`, number prefix
`SDN` (`DN` is the delivery note's).

- It names an **approved** invoice and the lines being charged more, moves no
  stock, and is taxed **at the rate each line was charged**, split into
  CGST/SGST/IGST the way the invoice was.
- It has **no cap**, because a price can rise by whatever is agreed. The control
  is approval: `CUSTOMER_DEBIT_NOTE_APPROVE` is a separate permission, not given
  to the sales manager.
- Approval posts Dr receivable, Cr sales revenue and output tax per head, and
  raises the customer's balance by the same rounded figure.
- It is **owed on the invoice**: a receipt allocated to the invoice settles it,
  and it ages from the invoice's due date.
- Cancelling is refused once money received on the invoice has met it. An
  invoice with a live debit note cannot be cancelled.
- GSTR-1 files it in CDNR with note type `D`; GSTR-3B adds it under
  `debit_notes_added`.

---

# 19. Receipts, payments and refunds

## What it does

Money in and money out, through **one** document. A receipt from a customer and
a payment to a vendor differ only in signs.

`settlements.journal_entry_id` is **NOT NULL**, because the defect this module
exists to close is a settlement that never reached the ledger.

## Workflow

| Step | Permission | Result |
| --- | --- | --- |
| Record a receipt | `RECEIPT_CREATE` | Posts cash and clears the receivable |
| Record a payment | `PAYMENT_CREATE` | Posts the payable and the money out |
| Allocate an advance | `RECEIPT_CREATE` | Decides which invoice a credit belongs to |
| Reverse | `RECEIPT_CREATE` | A mirror journal cancels it |

## How a receipt splits

A receipt of 500 against an outstanding 300 splits **when it is recorded**:
`min(amount, outstanding)` comes off the balance and the excess becomes an
unapplied advance.

**Applying that advance later posts no journal.** The receipt already debited
cash and credited receivables, and the invoice already debited receivables; the
allocation only decides which invoice the credit belongs to, and a journal
would count the money twice.

**Only the part that became an advance moves the balance.** Posting
`ADVANCE_APPLY` for the whole allocation double-counts — the first version did,
and a deposit taken while the customer already owed something (the ordinary
case) was refused outright with *"exceeds unapplied advance"*.
`_advance_part_of` reads the split off the receipt's own receivable row and
subtracts what earlier allocations used, or the last of an advance is stranded
for ever.

## Reversal

A settlement is **reversed, never edited or deleted**. A mirror journal cancels
it, the allocations stop clearing invoices but still record what they had
cleared, and the customer's balances go back **by the deltas stored on the
original row** — never recomputed, because only that row remembers the split.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Receipts, customer statements | **Sell › Receipts**, **Sell › Customer Statements** |
| Payments, supplier statements | **Buy › Payments**, **Buy › Supplier Statements** |
| Refunds, post-dated cheques | **Sell › All Sell screens › Money › Refunds, Post-dated Cheques**; **Buy › All Buy screens › Money › Post-dated Cheques** |
| Payment runs | **Buy › All Buy screens › Money › Payment Runs** |

## Tables

`settlements` · `settlement_allocations`

What an invoice still owes is derived from `settlement_allocations`, **never
stored on the invoice**.

## Rules that bite

1. **`CustomerService.post_receivable_transaction` moves a balance without
   writing a journal.** It is the older, lower-level path, and the two books
   drift by every rupee recorded through it. Record money through
   `/api/v1/receipts` and `/api/v1/payments`.
2. **`settlements.sales_order_id` is a note, not a ring-fence.** Cancelling the
   order does not make the deposit vanish.
3. **The direction check is `SettlementDirection.RECEIPT`, not `"IN"`.** The
   first TCS version compared against a string the column never holds, so it
   collected nothing anywhere and only the tests said so.

---

# 20. Loyalty and cashback

## What it does

One ledger for every movement of credit a customer holds. What a firm calls the
scheme — points, cashback — is a matter of the conversion rate, not of the
model.

## The design turns on the tax

**A redemption settles the bill; it does not discount it.** The supply is worth
what it is worth and the full GST is charged. Treating it as a discount would
reduce the taxable value and so the tax collected — a decision about tax, and
not one this module makes quietly.

## What each movement does

| Kind | Points | Journal |
| --- | --- | --- |
| `EARNED` | + | `Dr Loyalty Expense / Cr Loyalty Payable` |
| `REDEEMED` | − | `Dr Loyalty Payable / Cr Accounts Receivable`, **and** a `LOYALTY` receivable row |
| `EXPIRED` | − | `Dr Loyalty Payable / Cr Loyalty Expense` for the share that lapsed |
| `ADJUSTED` | ± | **Nothing** — it corrects a count, not a transaction |
| `REVERSED` | ± | Mirrors what it reverses |

**Points cost the firm money when earned, not when spent**, so a scheme's cost
lands in the month it was incurred.

**Redeeming needs both legs.** The journal alone moves the control account
while the customer's own balance stays put, so the two books drift by every
redemption — `verify_sample_data.py` caught that within minutes of the seed
running.

## Expiry

A sweep, not a background job, and it **names the entry it takes**, so it can
be run twice safely.

**Points expire out of what is left of a batch.** Spending is allocated
**oldest batch first**, so a customer with one lapsing batch and one fresh one,
who spent the older one's worth, keeps the fresh one in full. `expire` wrote
back the *whole* earned entry until 2026-09-03, so a batch already spent lapsed
a second time and left customers on **negative points** — the balance is a sum
over the ledger with no floor, and the sweep was the only way below zero.

`expiry_months` NULL means points **never expire**. Zero would mean they expire
the day they are earned.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| The scheme (earn rate, value of a point, expiry) | **Settings › Selling › Loyalty Scheme** |
| Balances and movements | **Settings › Set up › Pricing › Loyalty** |

## Tables

`loyalty_entries` · `loyalty_settings`

The balance is **the sum of the ledger and never a column**.

## Rules that bite

1. **A redemption is refused rather than trimmed.** More than the balance is an
   error, not a smaller redemption.
2. **`redeem` holds the customer with `with_for_update`.** It reads a *sum* and
   then inserts, so no row is updated and no version can conflict — two
   requests that both read before either commits would both pass.
3. **`expire` takes an `actor_id`**, because a journal with no author is one
   nobody can ask about.

---

# 21. Commission, rules and payouts

## What it does

What a salesman earns, and the document that pays it. A rule is an arrangement
that outlives any one year — which is why commission rules are **not** cleared
by a history reset.

## A rule is four decisions, not one rate

| Decision | Values | Note |
| --- | --- | --- |
| `basis` | `COLLECTED` / `INVOICED` | A rule pays on **one** of them |
| `measure` | `VALUE` / `MARGIN` | Margin pays on the money less what the goods cost |
| `rate_type` | `PERCENT` / `PER_UNIT` | PER_UNIT multiplies **quantity** and ignores slabs |
| `slab_mode` | `MARGINAL` / `WHOLE_AMOUNT` | Declared, never inferred — they pay very differently |

A rule with **slabs ignores `percentage` entirely**, so never show that column
beside a ladder. A ladder must start at zero, meet exactly, and be open-ended
only at the top.

`minimum_amount` earns **nothing at all** below it and pays on **all** of it
above — deliberately not a zero-percent bottom slab, which pays from the first
rupee once the ladder is climbed and is a different deal.

`bonus_percentage` is paid only when the salesman's targets over the period
were met, and is added **before** the cap so a firm's ceiling still holds.

`max_commission_amount` is applied **after** the ladder, so it caps what was
earned rather than what was sold.

## Six rungs of specificity

A rule may name a product or a category, making it a statement about **lines**
rather than about the document. Resolved per line:

1. the person's own **product** rule
2. the person's own **category** rule
3. the person's own **unscoped** rule
4. the firm-wide product rule
5. the firm-wide category rule
6. the firm-wide unscoped rule

**Whose rule it is outranks what it is about** — otherwise a firm-wide rule
naming a product would override a rate somebody negotiated.

**An unscoped rule must keep measuring exactly the document**: the report
apportions each invoice's `grand_total` across its lines with the same
`apportion` the bill discount uses, so the shares sum to the invoice. Deriving
a share from the line's own `net_amount` would drift by whatever the header
carries.

## The payout

`DRAFT` → `APPROVED` → `PAID`, or `CANCELLED`.

**The report is read once, at accrual, and never again.** It walks live
documents, so re-reading would answer differently after a settlement is
reversed or a rate corrected — and the journal posted at approval would then
disagree with the record beside it.

Approval posts `Dr COMMISSION_EXPENSE / Cr COMMISSION_PAYABLE`; payment posts
`Dr COMMISSION_PAYABLE / Cr` the money account. Two purposes, because an
approved payout is a liability that outlives the month it was earned in.

**`COMMISSION_PAY` is separate from `COMMISSION_MANAGE`** and not granted to
`SALES_MANAGER`: whoever states a debt must not be the one who moves the cash.

## How to use it (1.3.0 menu)

**Sell › All Sell screens › Incentives › Commission** (rates, collected, payouts).

## Tables

`commission_rules` · `commission_rule_slabs` · `commission_payouts`

## Rules that bite

1. **One live payout per person per overlapping period, held by the database.**
   `_assert_period_is_free` selects and `accrue` inserts with nothing between
   them, so two requests that both check before either commits both passed —
   leaving one salesman holding two live payouts for one month, which pays the
   same collections twice. `UQ_commission_payouts_period_active` is the guard.
2. **A journal reference is unique**, so the accrual, the payment and the
   reversal need distinct ones (`...`, `...-PAY`, `...-REV`) or an approved
   payout can never be paid.
3. **NULL cost is not zero.** An invoice raised straight off an order has no
   dispatch behind it, so nothing moved and nothing was costed — and zero would
   say the goods were free, which on a margin rule pays commission on the whole
   sale price. Such a line contributes nothing.
4. **A sale below cost earns nothing, not a negative.** Clawing it back off
   other sales is an arrangement nobody asked for.
5. **Commission is earned on net sales -- tax and freight earn nothing.** A
   bill contributes its taxable value net of discounts, without its tax or its
   freight; a receipt contributes the same share of that base as it is of the
   bill. Decided by Claude, industry standard, 2026-09-24. Payouts accrued
   before then keep what they were paid on.

---

# 22. Sales targets

## What it does

What a firm expects a salesman to sell over a period, and how it went. Small,
and it exists mostly to answer one question for commission: were the targets
met?

**Targets over a window are judged taken together** — the achievements summed
against the targets summed. Requiring every month makes an annual bonus
unearnable; requiring one makes it unmissable.

**Somebody with no target reports `target_met: null`, not false**, and earns no
bonus: nobody set them a number, so there is nothing they failed.

`sales_targets` · permissions `SALES_TARGET_VIEW` / `SALES_TARGET_MANAGE`.

Seeded targets are **reset with the history**, because a target derived from
what was sold would otherwise be measured against sales that no longer exist.

## How to use it (1.3.0 menu)

**Sell › All Sell screens › Incentives › Targets**.

---

# 23. Journals, ledgers and financial reports

## What it does

The books. A chart of accounts, financial years and periods, the journal every
posting module writes to, and the statements read off it.

## Automatic posting is built

**Eleven modules post** through `DocumentPostingService`: `delivery_note`,
`sales_invoice`, `sales_return`, `credit_note`, `goods_receipt`,
`purchase_invoice`, `purchase_return`, `settlements`, `loyalty`, `tcs` and
`commission`.

Which account each leg lands in is per firm, in `firm_control_accounts`, keyed
by purpose — `ACCOUNTS_RECEIVABLE`, `INVENTORY`, `OUTPUT_TAX`,
`PURCHASE_PRICE_VARIANCE`, `LOYALTY_PAYABLE`, `COMMISSION_PAYABLE`,
`TCS_PAYABLE` and the rest, 24 in all.

The predecessor guessed accounts by name and was removed on 2026-08-09; see git
history for its rules.

## Configure first

A financial year with its periods, a chart of accounts, and a control account
for every purpose the firm's modules will post to. **A document that cannot
find its control account is refused rather than posted to a guess.**

## Rules that bite

1. **A ledger leg facing stock is valued from the movement; a leg facing a
   counterparty is valued from the document.** Every forward posting already
   did this; all three reversals broke it and were fixed on 2026-08-22.
2. **`reverse_entry` copies the source module and id onto the mirror**, so a
   lookup filtering only on POSTED finds the mirror next time and reverses the
   reversal. Match `reversal_of_id IS NULL`.
3. **A closed period refuses a posting**, which is what makes it a close.
4. **Cost and profit centres exist and are used by nothing.**
   `ledger_accounts.requires_cost_center` is a flag no account sets.

## How to use it (1.3.0 menu)

| Task | Where |
| --- | --- |
| Journal entries, expenses, ledgers, bank reconciliation | **Accounts** drop-down |
| Trial balance, profit and loss, balance sheet | **Accounts** drop-down; Cash Flow under **All Accounts screens › Statements** |
| Chart of accounts, opening balances, party adjustments, contra vouchers, Tally export | **Accounts › All Accounts screens › Books** |
| Control accounts, cost and profit centres | **Settings › Set up › Account structure** |

## Tables

`financial_years` · `accounting_periods` · `account_groups` ·
`ledger_accounts` · `ledger_balances` · `journal_types` · `journal_entries` ·
`journal_lines` · `gl_postings` · `voucher_types` · `firm_control_accounts` ·
`cost_centers` · `profit_centers` · `customer_ledgers` · `vendor_ledgers`

---

# 24. Tax collected at source

## What it does

Section 206C(1H): what a seller collects from a buyer **on the money the buyer
pays**. It is unlike every other tax in this system, and the difference decides
the whole design — the statute says *"at the time of receipt of such amount"*,
so the event that raises a liability is a **receipt**, never an invoice being
approved.

Putting it on the invoice — which is what makes it look like just another tax
line — collects it on money that may never arrive, and misses money that
arrives against an older bill.

## Configure first

**Settings › Selling › TCS Settings** (`TCS_MANAGE`), per firm:

| Setting | Means |
| --- | --- |
| `is_enabled` | Whether this firm collects at all. **A seller below the turnover threshold collects nothing** — and whether a firm is above it is a fact the firm *states*, because its preceding year may predate its books here |
| `threshold_amount` | The per-buyer, per-year floor (₹50,00,000 under 1H) |
| `rate_percent` | The rate on the excess |
| `rate_without_pan_percent` | The higher rate for a buyer with no PAN |
| `section_code` | Which section this row is for |

The books need `TCS_PAYABLE` mapped — account **2500**, deliberately not 2200
Output Tax: TCS is not GST, it is filed on a different return on a different
cycle, and netting the two would put a quarterly payment inside a monthly one.

## Workflow

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | State the firm's position and rates | `TCS_MANAGE` | Row in `tcs_settings` |
| 2 | Preview what a receipt would collect | `TCS_VIEW` | Nothing stored — a calculation |
| 3 | Record a receipt | `RECEIPT_*` | If the buyer is past the threshold, a `tcs_collections` row and a credit to TCS Payable |
| 4 | Read what has been collected | `TCS_VIEW` | The register, per buyer and period |

## How to use it

**Accounts › All Accounts screens › Tax filing › TCS** (`TCS_VIEW`) — settings, a preview calculator, and the
collections register.

```powershell
uv run python scripts/dump_route_permissions.py --markdown tcs
```

## Tables

| Table | Holds |
| --- | --- |
| `tcs_settings` | One row per firm per section: enabled, threshold, both rates |
| `tcs_collections` | What was collected, against which receipt and which buyer, in which financial year |

## Rules that bite

1. **It is charged on the money, not on the bill.** The receipt is the taxable
   event. A bill that is never paid collects nothing; a payment against a
   two-year-old bill collects at today's rules.
2. **Only the excess counts.** The first ₹50,00,000 a buyer pays in a financial
   year attracts nothing, and a receipt straddling that line is charged **on
   the part above it and no more** — not on the whole receipt.
3. **The threshold is per buyer, per financial year, and it resets.** The
   running total is scoped to both and is **derived by summing the
   collections**, never held as a counter. A counter and a reversal are two
   chances to disagree.
4. **The financial year is the firm's own**, not the calendar year and not
   April-to-March by assumption.
5. **A buyer with no PAN is charged the higher rate**, which is why the setting
   is two rates rather than one.
6. **A firm below the turnover threshold collects nothing at all**, and that is
   a statement the firm makes — the platform cannot derive it from books that
   may not go back far enough.

---

---

# 25. GST returns

## What it does

What a firm has to declare for a period, read off what it actually sold.
Two reads: **GSTR-1** (outward supplies, section by section) and **GSTR-3B**
(the summary).

**The returns store nothing.** A return is a *view of the documents*, and
the moment it were stored it could disagree with them — a cancelled invoice, a
credit note raised late, an amended rate. So it is derived on every read, from
the invoices and credit notes as they stand.

The sections are the ones this system's data can honestly fill:

| Section | What it carries |
| --- | --- |
| **B2B** | Supplies to a customer carrying a GSTIN, invoice by invoice |
| **B2CL** | Inter-state supplies to an unregistered customer above the invoice-wise threshold |
| **B2CS** | Everything else unregistered, summarised by place of supply and rate — net of credit notes issued to those buyers in the period |
| **CDNR** | Credit notes **and debit notes** (note type `D`) against registered customers |
| **HSN** | What was sold, by HSN code and rate |
| **DOCS** | The document series issued |

## Configure first

| Thing | Needed for |
| --- | --- |
| The firm's own GSTIN | Placing the supplier, and deciding what is inter-state |
| Customers' GSTINs where they have one | The B2B / B2CS split |
| `hsn_code` on products | The HSN section |
| Tax rules that actually charged the documents | Everything — the return reads what was charged |
| A proforma series separate from the invoice series | DOCS declaring a clean series (see section 17) |

## Workflow

There is no workflow to speak of, and that is the design: pick a period and
read. `GET /api/v1/gst-returns/gstr1` and `/gstr3b`, both `SALES_VIEW`.
Filing itself happens on the portal — this produces the figures.

Around the two reads sit a few things that *are* stored, because they record
what people did rather than what the documents say: the **GST payments** a firm
records, the **filings** somebody marks as done (`gst_return_filings`), and the
**GSTR-2B imports** with their match results. The **tax calendar** on Home reads
them: for each of the last three months, GSTR-1 (due the 11th), GSTR-3B (due the
20th) and, for a month that collected any, the TCS deposit (due the 7th), each
marked done, due or late. It covers monthly filers only. GSTR-3B also reports
blocked and ineligible input credit and the debit notes added (see modules 15
and 18).

## How to use it

**Accounts › GST Returns** (`SALES_VIEW`); the rest of tax filing (GSTR-2B Reconciliation, Rule 37, Rule 42, GST checks, GST Payment, PMT-06 deposits, TDS Challans, Bank Details) under **Accounts › All Accounts screens › Tax filing**; the GST settings under **Settings › Tax › GST Documents**.

```powershell
uv run python scripts/dump_route_permissions.py --markdown gst_returns
```

## Tables

The two returns own no table: they read sales invoices, credit notes, debit
notes, customers and products, and return a computed document. The module's own
tables are `gst_payments`, `gst_return_filings`, `gstr2b_imports` and
`gstr2b_documents`.

## Rules that bite

1. **A supply is placed by the tax it was charged.** The document settles the
   place of supply, and for an unregistered buyer nothing else can — there is
   no GSTIN to read a state code from.
2. **An invoice that cannot be placed is reported, not filed.** Where the tax
   says a border was crossed and the buyer is unregistered, the invoice lands
   in `unplaced_invoices` rather than being filed with a blank cell the portal
   would reject. **Read that list every period** — it is the module telling you
   its input is wrong, not its output.
3. **3B is aggregated from the documents, not parsed out of GSTR-1's JSON.**
   Deriving one return from another's serialised output makes a formatting
   change into an accounting change.
4. **A credit note to an unregistered customer is netted off its B2CS row**,
   not filed in CDNR. There is nobody to reverse a claim, and the section has
   no room for a number nobody reads.
5. **Every figure that leaves here is in rupees and paise.** Documents are
   priced to four decimals and no portal accepts that, so the rounding happens
   **once, on the way out** — the running totals behind it keep the scale they
   were priced at.
6. **This module and `app/einvoice` split a line's tax through the same
   `split_components`**, so what is filed and what was registered can never
   disagree about which bucket a component belongs in.

---

---

# 26. E-invoicing and e-way bills

## What it does

What the government portal gave back for an invoice, and for its movement. An
e-invoice is registered with the Invoice Registration Portal, which returns an
**IRN**; an e-way bill is raised from that same registration for the goods it
covers.

Two registrations, one module, because they share one portal, one set of
credentials and one failure story.

**Today the only portal implemented is the sandbox.** That is a statement about
the codebase, not about the design — see rule 1, which is the rule this whole
module is shaped around.

## Configure first

| Thing | Needed for |
| --- | --- |
| An **approved** sales invoice | There is nothing to register otherwise |
| The firm's GSTIN, and the buyer's where they have one | The payload the portal validates |
| `hsn_code` on every product on the invoice | The same |
| The firm's e-invoice **mode** | Which portal is talked to — `SANDBOX` rehearses, `LIVE` files |

## Workflow

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Register an approved invoice | `EINVOICE_MANAGE` | Row in `einvoice_registrations` with the IRN, the acknowledgement and the **mode it was made in** |
| 2 | Generate the e-way bill for it | `EINVOICE_MANAGE` | Row in `eway_bills`, with transport mode and vehicle |
| 3 | Cancel either, with a reason | `EINVOICE_MANAGE` | Withdrawn, reason recorded |
| 4 | Read the register | `EINVOICE_VIEW` | What is registered, and in which mode |

## How to use it

**Accounts › All Accounts screens › Tax filing › E-Invoice** (`EINVOICE_VIEW`); the route and dates under **Settings › Tax › GST Documents**.

```powershell
uv run python scripts/dump_route_permissions.py --markdown einvoice
```

## Tables

| Table | Holds |
| --- | --- |
| `einvoice_registrations` | The IRN, acknowledgement number and date, the signed payload, the status, and `mode` |
| `eway_bills` | The bill number, validity, transport mode and vehicle, against the registration |

## Rules that bite

1. **A sandbox registration must never read as a filing.** A sandbox
   registration is a rehearsal: no return was filed, no IRN exists at the
   authority, and the number on it means nothing outside this database. So
   `mode` is **NOT NULL with no server default** — a default is one migration
   away from quietly becoming `LIVE` — and the reference the sandbox mints is
   **prefixed** so it cannot be mistaken even out of context. A row that could
   not say which it was would be a document somebody eventually presents at a
   check post.
2. **`portal_for("LIVE")` raises rather than falling back to the sandbox.** A
   firm that has switched to LIVE and has no credentials must be told loudly:
   silently rehearsing while somebody believes they are filing is the worst
   outcome this module has available.
3. **Cancelling requires a reason** — *"Say why the registration is being
   withdrawn."* — and so does cancelling an e-way bill. The portal asks; so
   does this.
4. **An e-way bill needs a live registration.** *"This invoice has no live
   registration."* The bill is raised from the registration, not from the
   invoice directly.
5. **Transport mode is a closed list** — ROAD, RAIL, AIR or SHIP.
6. **This module and `app/gst_returns` split a line's tax through the same
   `split_components`**, so what is registered and what is filed cannot
   disagree about which bucket a component belongs in.

---

---

# 27. Inventory operations

## What it does

What the warehouse holds, what it is worth, and every movement that got it
there. Most stock movement is a *consequence* of a document — a goods receipt
brings stock in, a delivery note takes it out — and this module is the other
half: the movements a firm makes **about** its stock rather than about a trade.
Opening balances, adjustments, transfers, write-offs, quarantine and physical
counts.

It also owns the two reads everything else asks: **what is on hand** (by firm,
branch, warehouse or product) and **how it got that way** (the stock ledger).

## Configure first

| Thing | Needed for |
| --- | --- |
| A branch and a warehouse | Stock has to be somewhere (section 5) |
| Products, with their stock flags | `require_batch_on_issue` decides whether a dispatch may leave a batch unnamed |
| Open books with `INVENTORY`, `INVENTORY_ADJUSTMENT`, `COST_OF_GOODS_SOLD` and `OPENING_BALANCE_EQUITY` mapped | Every movement posts |
| UOM setup | A line entered in cases and stocked in pieces |

## Workflow

**Opening stock** is a document, not a field:

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Open a batch and enter lines (or import XLSX) | `OPENING_STOCK_CREATE` / `INVENTORY_IMPORT` | `DRAFT` — nothing has moved |
| 2 | Edit while draft | `OPENING_STOCK_UPDATE` | Still draft |
| 3 | Post it | `OPENING_STOCK_CREATE` | Stock exists, valued, against Opening Balance Equity |

**A physical count** is a document too, and for the same reason — the sheet is
filled in over hours by people walking a warehouse, and posted once at the end.
An endpoint that applied counted quantities immediately would lose everything
the moment somebody closed a laptop.

| # | Step | Permission |
| --- | --- | --- |
| 1 | Open a count | `INVENTORY_ADJUST` |
| 2 | Record what was found, line by line | `INVENTORY_ADJUST` |
| 3 | Post it — every difference becomes an adjustment | `INVENTORY_ADJUST` |
| 4 | Or cancel it | `INVENTORY_ADJUST` |

**The single movements** — `POST /adjustments`, `/transfers`, `/write-offs`,
`/quarantine` — each move stock between buckets or locations and each post a
journal.

## How to use it

| Task | Where |
| --- | --- |
| What is on hand | **Stock › Stock Summary**, and **Stock › All Stock screens › Stock › Inventory** (`INVENTORY_VIEW`), with by-firm, by-branch, by-warehouse and by-product reads |
| How it got there | **Stock › Stock Ledger** (`INVENTORY_LEDGER_VIEW`) and **All Stock screens › Stock › Transactions** (`INVENTORY_TRANSACTION_VIEW`) |
| Opening balances | **Stock › All Stock screens › Movements › Opening Stock** |
| Adjust, transfer, write off, quarantine | **Inventory**, each its own action (`INVENTORY_ADJUST`); large adjustments wait under **All Stock screens › Movements › Adjustment Approvals** |
| Stock transfers, repacking | **Stock › Stock Transfers**; **All Stock screens › Movements › Repacking** |
| Batches, expiry, lots, serial numbers | **Stock › Batches**, **Expiry Monitor**; **All Stock screens › Tracking › Lots, Serial Numbers** |
| The firm's stock rules | **Settings › Stock** (Inventory Settings, Adjustment Reasons, Adjustment Limits, Batch Rules) |
| Count the shelves | **Stock › Physical Count** |

```powershell
uv run python scripts/dump_route_permissions.py --markdown inventory
```

## Tables

| Table | Holds |
| --- | --- |
| `inventories` | The current position: one row per firm/branch/warehouse/node/product/batch, with **seven** quantity buckets — current, reserved, available, blocked, damaged, quarantine, in-transit |
| `inventory_transactions` | Every movement, with the before and after of each bucket |
| `stock_ledger_entries` | The ledger view of those movements, with `average_cost_after` |
| `product_valuations` | The moving weighted-average cost, one row per **firm and product** |
| `opening_stock_batches`, `opening_stock_lines` | The opening-balance document |
| `physical_counts`, `physical_count_lines` | The counting sheet |

## Rules that bite

1. **Valuation is per `(firm, product)`, deliberately not per location.** A
   per-warehouse average turns every stock transfer into a cost-movement
   problem, and a per-bin average is noise. The costing method is stored so a
   firm can move to FIFO later without the table changing shape.
2. **Available is not current.** Reserved stock is still current and is not
   available; a dispatch allocates from **available**. Seven buckets exist
   because a warehouse really does distinguish them, and a screen that reads
   the wrong one tells the truth about the wrong question.
3. **A dispatch never takes an expired batch.** "Earliest expiry first", read
   literally, hands the customer the batch that went out of date last month —
   which is what it did until 2026-09-16. Expired stock is dropped from the
   candidates and a resulting shortfall **names the batch and its date**,
   because the screen still shows that stock as on hand. Expiry is judged on
   the **document's own date**, so replaying history posts what it posted then.
4. **No bucket may go negative** — *"<bucket> quantity cannot become
   negative."* — and the scope checks are real: a branch that is not the
   firm's, a warehouse that is not the branch's, and a product that is not the
   firm's are each refused by name.
5. **A movement is reversed once.** *"This inventory movement was already
   reversed."* — and a reversal takes the journal off with the stock.
6. **A leg facing stock is valued from the movement, not from the document.**
   Goods arrive at one average and leave at another; mirroring a document's
   value across that gap puts the store out. The difference lands in Purchase
   Price Variance (see section 4).
7. **Opening stock posts to Opening Balance Equity**, not to purchases. It is
   a statement of where the firm started, not something it bought.

---

---

# 28. Reports, search, audit and diagnostics

## What it does

The four things that are *about* the platform rather than part of any trade:
what happened (reports), finding a record (search), who changed what (audit),
and what broke (diagnostics).

**Reports are not a module.** There is no `app/reports` package: each module
publishes its own reports under its own router — 57 report routes across the
tree — and the desktop gathers them into one workspace through
`report_catalog.dart`, which lists **56 reports** (re-count it rather than
trusting that number).

## Configure first

Nothing, for any of the four. They read what the other modules wrote. What
does matter is that a report is only as good as the masters behind it: a
by-territory report needs territories assigned, an HSN summary needs HSN codes
on products.

## Workflow

None of these has a workflow. They are reads, with two exceptions worth
knowing:

- **Diagnostics accepts a write from the client** — `POST /client-errors`,
  authenticated and no permission code, because the desktop reports its own
  crashes. Reading them needs `DIAGNOSTICS_VIEW`.
- **The audit trail is append-only at the database level**, enforced by the
  `TR_audit_logs_append_only` trigger, and every schema owns its own copy of
  that trigger and the function it calls.

## How to use it

| Task | Where | Permission |
| --- | --- | --- |
| Every report the signed-in user may open | **Reports** | per report |
| Find a record across modules | The shell's global search | firm scope; results are filtered by what you may see |
| Who changed what | **Settings › Platform › System › Audit Logs** | `AUDIT_LOG_VIEW` |
| What the client crashed on | **Settings › Platform › System › Diagnostics** | `DIAGNOSTICS_VIEW` |

```powershell
uv run python scripts/dump_route_permissions.py --markdown search
uv run python scripts/dump_route_permissions.py --markdown diagnostics
```

## Tables

| Table | Holds |
| --- | --- |
| `audit_logs` | Every mutation: actor, entity, action, before and after. **Per store**, not central |
| `error_reports` (diagnostics) | Client crashes, grouped by fingerprint, with their occurrences |

Search and reports own no tables — both read the modules'.

## Rules that bite

1. **The audit trail is per store, not central.** Platform administration
   writes to `platform.audit_logs`; every firm-owned mutation writes to that
   firm's own store, because `record_audit` runs on whichever session `get_db`
   resolved. That is deliberate — a DATABASE-mode firm's history has to live
   inside its own database for the isolation guarantee to hold. **No single
   query can answer "everything that happened"**; a cross-firm view iterates
   the stores.
2. **A firm's trail is its own store plus the platform rows that belong to
   it.** `AuditLogReader.list_events_with` merges on the **read** — exactly
   once per store, with the same filters on both, and never merging a store
   with itself, which a one-schema unit suite would otherwise do. Only
   `tests/integration/` can see that class of bug.
3. **`GET /api/v1/audit-logs` reads one trail, chosen by firm context.** No
   `X-Firm-ID` plus platform authority gives the platform trail; `X-Firm-ID`
   gives that firm's. Date filters are inclusive UTC calendar days.
4. **Audit rows cannot be edited or deleted**, by trigger. Anything that
   shapes a firm store must leave both the trigger and its function alone —
   `prune_platform_objects` once dropped the function `CASCADE`, which took
   every dedicated store's trigger with it and left the trail rewritable.
5. **Search is permission-filtered per module, not once at the top.** A user
   who may see customers but not products gets customers back and no products
   — not an empty result and not a 403.
6. **A report needs its own entry in `report_catalog.dart` to be reachable.**
   The orphan-route guard matches path *shapes*, so a sibling's entry makes an
   unlisted report look reachable; `tests/unit/test_reports_have_a_screen.py`
   asks it both ways. A report nobody can open is how whole features have gone
   missing here.

---

---

# 29. Branding: the agency's name, tagline and logo

## What it does

The agency that bought the product has a **name, a tagline and a logo**. They
lead the sign-in screen and the header of every screen, so every PC shows the
same, and the product's own name stays beside them, quietly. Sign-in happens
before a firm is chosen, so the record sits above the firms: **one live row per
installation, in the platform store**, with no `firm_id`. No row means *not yet
given*: the desktop then falls back to the name in `desktop/config/branding.json`
and the agency's initials.

**Our product's identity is a different thing and comes from a different
place.** The product and company names, tagline, logos, support details (phone,
WhatsApp, hours, email, website; blank in 1.3.0, an empty row is hidden) and
the eight strengths on the sign-in panel come only from `config/branding.json`,
which the package builds and every installer replaces. The agency can never
change them from the app. Backlog 71; `docs/BRANDING_AND_NAMES.md` section 8 is
the record of what was built.

It is not a business-profile capability and a firm cannot switch it off.

## Configure first

Nothing. An installation with no branding works as it always did, showing
Agency Platform's own name. The record is given in one of three ways (the
workflow below), by somebody holding `PLATFORM_SETTINGS`, which only the
platform tier holds.

## Workflow

| Step | Who | Result |
| --- | --- | --- |
| **Fresh server install**: the Branding page after *This PC* (agency name, tagline, logo file; all optional) | Whoever installs | Setup writes the values as UTF-8 JSON to a temporary file (never on a command line), passes `-BrandingFile` to `server_setup.ps1`, which runs **`agency-server set-branding --file`** once the server answers `/health`, then deletes the file. It saves through the same service as the Settings screen, so it is audited. The page is not shown for an app-only PC, an upgrade or a repair |
| A logo the server refuses | — | **A branding problem never fails an install**: the name is saved, the logo is skipped and a warning goes to the install log; the logo can be added later. A tagline or logo without a name is refused at Next |
| **First sign-in** while branding is not set | A platform administrator, or a holder of `PLATFORM_SETTINGS` | *Set up your agency* opens once, after sign-in: name, tagline, logo, live preview. **Skip for now** is kept per user (workspace state `phase2.first_run`, `agency_skipped`) and Home then shows a *Finish setting up* card until it is given. A firm administrator never sees either |
| **Any time** | `PLATFORM_SETTINGS` | **Settings › Platform › Agency › Branding**: one form; Save, **Remove logo** |
| Read it | Anyone, signed out | The sign-in screen reads name, tagline and whether there is a logo, then the logo only when this PC's cached copy is of another version |

An upgrade leaves the record **empty**: no Branding page is shown on an upgrade,
so the first administrator to sign in is asked *Set up your agency*.

The endpoints, all under `/api/v1/branding` (a platform path):

| Route | Who | Does |
| --- | --- | --- |
| `GET /api/v1/branding` | anyone, signed out | `is_set`, name, tagline, colour, `has_logo`, `version` (also the `ETag`) |
| `GET /api/v1/branding/logo` | anyone, signed out | the image, `image/png` or `image/jpeg`; 404 when none |
| `PUT /api/v1/branding` | `PLATFORM_SETTINGS` | replace name, tagline, colour; the first save creates the record |
| `PUT /api/v1/branding/logo` | `PLATFORM_SETTINGS` | multipart `file`; PNG or JPG by its bytes, not its name; at most 1 MB |
| `DELETE /api/v1/branding/logo` | `PLATFORM_SETTINGS` | remove the logo; initials show instead |

## How to use it

| Task | Where |
| --- | --- |
| Give or change the name, tagline, logo | **Settings › Platform › Agency › Branding** (`PLATFORM_SETTINGS`; no firm needed) |
| Give it on a new PC | The installer's Branding page; or `agency-server set-branding --file branding.json` on the server PC |
| See it | The sign-in screen (logo or initials, name, tagline; the strengths panel at the left; **More help**); the header, before Home; the window title **<agency> > <firm>** |
| See the changes made | **Settings › Platform › System › Audit Logs**, no firm chosen |

The form takes the agency name (required), tagline and logo (PNG or JPG), shows a
live preview of the sign-in card and the top of every screen, and lists our
product, company and logo read-only. There is **no accent-colour box**: the
stored colour is sent back unchanged. Save shows *Saved.* and the header changes
at once, with no read.

## Tables

`agency_branding`, **platform store only** (migration `20261004_0300`), plus the
`BaseEntity` columns:

| Column | Holds |
| --- | --- |
| `branding_key` | Always `AGENCY`; exists only so a unique index can hold *one live row* |
| `agency_name` | Required, up to 150 characters |
| `tagline` | Up to 200 characters |
| `accent_color` | `#RRGGBB` or none; stored, not yet asked or applied |
| `logo`, `logo_content_type` | The image itself (so every PC reads the same one from the server) and `image/png` or `image/jpeg` |

Audit actions, in the platform trail: **`agency_branding.created`** (the first
save), **`agency_branding.updated`** and **`agency_branding.logo_changed`** (the
type and size, never the image).

## Rules that bite

- **One live row is held by the database, not by a read.**
  `UQ_agency_branding_key_active` is a unique index on the constant key where
  `is_deleted = false`; two first saves at once cannot both find none and insert.
- **The logo's type is read from its bytes, never its file name**: a text file
  renamed `.png` is refused (*The logo must be a PNG or JPG image.*). At most 1
  MB, an over-size one is refused naming its size. **A logo needs the name to be
  given first.** The server does not check the logo's shape; the screens fit it
  into a square.
- **Every write honours `If-Match`** with the `ETag` it was given, so two PCs
  editing at once: the second is refused with the somebody-else-saved message
  and keeps what was typed. The desktop sends `PUT`/`DELETE` of the logo only
  when the logo changed.
- **Reading is public, writing is not.** `GET` needs no sign-in because the
  sign-in screen shows the agency; every write needs `PLATFORM_SETTINGS`. The
  route is a platform path, so it never needs an `X-Firm-ID`.
- **The desktop holds a copy.** The last answer is kept per server on the PC, so
  the sign-in screen opens at once and survives a server that is not answering
  (the agency's own logo from the last visit, or Agency Platform's own on a PC
  that never had one). When a PC holds *no* copy the first-run dialog asks the
  server once before opening, because an empty form saved without a version
  would otherwise replace the agency's branding.
- **A branding problem must never fail an install.** The installer path
  reports what it skipped and carries on.
- **Not built:** Help > About, first-run steps 2 to 4, the "PRACTICE" mark, the
  accent colour in use, and support details (blank by design).
