# Backlog build plan: what each open item needs

**Date: 2026-10-02.** The owner asked: *"To fix them, what is needed, one by
one."* This document answers that for every open item in `docs/BACKLOG.md`,
plus the one open defect (D-PERF-1 in `docs/DEFECTS.md`). The backlog says
*what* each item is and why; this says *what it takes*.

**The rule it follows** (owner, 2026-10-02): *"If something you can fix as per
standards of marketplace tools by comparing, I am ok; if any major input is
needed from me then put it as open."* So every question that Tally, Zoho Books,
ERPNext, Marg or Busy settle between them is answered here as **Decided by
standard**, and the item is **Claude alone**. Only major inputs -- a contract
or account, money, a CA's or lawyer's sign-off, hardware, branding, or
something the owner has already parked -- are put to the owner.

## How to read it

- **Section 1** is one table of every item, by area: what it is, whether it
  needs anything from the owner, how big it is, and who can do it.
- **Section 2** lists the few things only the owner can provide.
- **Section 3** lists every question settled by market standard, one line
  each, so the owner can overrule any of them in one sitting.
- **Section 4** is the detail per item: what gets built, in which module and
  screen, what it waits on. **Where an entry has no "Needs from the owner"
  line, the answer is nothing**: the item follows the standard named for it
  in section 3. Paths named there exist today unless the entry says "new".
- **Section 5** is what is parked or waiting, and the items whose status was
  unclear, each with a recommendation.
- **Section 6** is a build order in waves.

**Effort:** **S** under a day; **M** two to five days; **L** one to two weeks
or more. All screen work goes into the phase 2 desktop only (`desktop/lib/phase2`
and the `desktop/lib/ui` screens it reuses -- the `*_phase2.dart` editors), as
the owner ruled on 2026-09-27.

**Counts.** 96 open items to build: **36 S, 48 M, 12 L**. **All 96 are
Claude alone** -- none needs the owner before work can start, though eight
need something from the firm or its CA before they are *used* (a bank's file
format, a cheque leaf, a printer, a CA's check of a rate), each named in its
entry. 22 items are parked or waiting on the owner (section 5.1). Checked
against the code on 2026-10-02, **six listed items turned out to be built
already** and are not counted: §34 system-numbered stock movements, §31.16,
§31.17's partial search, §8's slim report rows, §31.7's interstate question,
and optimistic concurrency on UOM, tax and batch (section 5.3).

---

## 1. Summary

| Id | Ref | Item | Needs from owner | Effort | Who |
| --- | --- | --- | --- | --- | --- |
| **Selling** | | | | | |
| SEL-1 | §58 items 2, 4 | Several delivery notes on one bill: pick the customer first, tick the notes, refuse a mix on screen -- **built 2026-10-03** (A54) | Nothing | S | Claude alone |
| SEL-2 | §60 row 4 | Offer: buy 2, second at 50% off | Nothing | M | Claude alone |
| SEL-3 | §60 row 5 | Offer: combo price (shampoo + soap for 150) | Nothing | M | Claude alone |
| SEL-4 | §60 row 6 | Offer: double loyalty points during a festival | Nothing | S | Claude alone |
| SEL-5 | §60 row 7 | Offer: 500 single-use coupon codes at once, exported to a file | Nothing | S | Claude alone |
| SEL-6 | §60 row 8 | Offer only for a first order, or for customers not billed in 90 days | Nothing | M | Claude alone |
| SEL-7 | §60 row 9 | Offer only on certain weekdays or hours | Nothing | S | Claude alone |
| SEL-8 | §60 row 10 | Copy last Diwali's offers with new dates | Nothing | S | Claude alone |
| SEL-9 | §64 row 1 | Special rate per customer, and named price levels (Retail, Wholesale, Dealer) | Nothing | M | Claude alone |
| SEL-10 | §67 row 1 | Enquiries and leads before the quotation | Nothing | L | Claude alone |
| SEL-11 | §42.7, §60 row 11, §55 G10 | Claims to the principal: scheme, expiry and breakage | Nothing | L | Claude alone |
| SEL-12 | §55 M10 | Fast counter billing with a barcode scanner | Nothing (a scanner to test with) | M | Claude alone |
| SEL-13 | §55 G7 | Picking list and loading sheet by van or route | Nothing | M | Claude alone |
| SEL-14 | §55 G9 | Cash discount for early payment; interest on overdue bills | Nothing | M | Claude alone |
| SEL-15 | §75 row 11 | A new outlet added by a salesman waits for office approval | Nothing | M | Claude alone |
| **Buying** | | | | | |
| BUY-1 | §61 item 1 | Free goods meant for customers: a "free issue only" product and a "given free / sample" issue | Nothing | M | Claude alone |
| BUY-2 | §61 items 2, 3 | Supplier gifts for the firm or owner: a register, its journal, the 194R total | Nothing | M | Claude alone |
| BUY-3 | §65 row 4 | Supplier rates: a supplier's standing discount and price list | Nothing | M | Claude alone |
| BUY-4 | §69 row 1 | Supplier catalogue: supplier's name and code per product, price history, pack | Nothing | M | Claude alone |
| BUY-5 | §69 row 2 | Minimum order quantity and order multiple warned on the order | Nothing | S | Claude alone |
| BUY-6 | §69 row 3 | Supplier lead time fills the expected date and is measured | Nothing | S | Claude alone |
| BUY-7 | §68 row 3 | Purchase requisition (indent) from a store, approved, turned into orders | Nothing | M | Claude alone |
| BUY-8 | §68 row 5 | Amending an approved purchase order, with revision numbers | Nothing | M | Claude alone |
| BUY-9 | §68 row 6 | Received goods held until a quality check passes | Nothing | M | Claude alone |
| BUY-10 | §68 row 7 | A bill that differs from order or receipt beyond a tolerance is held | Nothing | M | Claude alone |
| BUY-11 | §68 row 9 | Payment run: pay many suppliers' due bills at once, bank upload file | Nothing (the firm's bank's file format to finish it) | M | Claude alone |
| BUY-12 | §68 row 11 | Supplier performance: on time, short, rejected, price trend | Nothing | M | Claude alone |
| BUY-13 | §69 row 8 | Volume rebates from suppliers | Nothing | M | Claude alone |
| BUY-14 | §69 row 9 | Purchase budget by branch, category and month | Nothing | M | Claude alone |
| BUY-15 | §69 row 10 | Users rate suppliers (opinion, kept apart) | Nothing | S | Claude alone |
| BUY-16 | §42.12 | Landed cost: freight and loading added to the stock's cost | Nothing | L | Claude alone |
| BUY-17 | §36 | Supplier credit from a return set against an opening bill -- **built 2026-10-03** (A52) | Nothing | S | Claude alone |
| **Stock** | | | | | |
| STK-1 | §70 row 1 | A stock transfer as a document: dispatch, in transit, receive | Nothing | L | Claude alone |
| STK-2 | §70 row 2 | A GSTIN per branch, and transfers between GSTINs as tax invoices | Nothing | L | Claude alone |
| STK-3 | §70 row 3 | Issue stock for internal use, staff or display -- **built 2026-10-03** (A61) | Nothing | S | Claude alone |
| STK-4 | §70 row 4 | Repacking: a 25 kg bag into 25 one-kg packs | Nothing | M | Claude alone |
| STK-5 | §70 row 7 | Expiry rules per product: stop selling, alert, return to supplier | Nothing | M | Claude alone |
| STK-6 | §70 row 8 | Planned and blind stock counts, with variance approval | Nothing | M | Claude alone |
| STK-7 | §70 row 11 | Adjustment reasons as a list the firm keeps | Nothing | M | Claude alone |
| STK-8 | §70 row 12 | Large adjustments and write-offs need approval | Nothing | M | Claude alone |
| STK-9 | §70 row 13 | Photos and documents on adjustments, write-offs, counts | Nothing | S | Claude alone |
| STK-10 | §70 row 14 | Incoming and outgoing beside available stock -- **built 2026-10-03** (A60) | Nothing | S | Claude alone |
| STK-11 | §70 row 15 | Issue rule per product: earliest expiry, first in, or pick by hand | Nothing | S | Claude alone |
| STK-12 | §70 row 16 | Reservations that lapse after N days | Nothing | M | Claude alone |
| STK-13 | §70 row 17 | Returned goods held until checked | Nothing | S | Claude alone |
| STK-14 | §70 row 18 | Stock alerts and the inventory dashboard | Nothing | M | Claude alone |
| STK-15 | §42.13 | Kits and combo packs | Nothing | L | Claude alone |
| STK-16 | §55 S8 | Barcode label printing | Nothing (label size and printer to test) | S | Claude alone |
| STK-17 | §75 row 5 | Discontinued products, and products never for sale -- **built 2026-10-03** (A58) | Nothing | S | Claude alone |
| STK-18 | §75 row 6 | Shelf life on the product fills a batch's expiry -- **built 2026-10-03** (A59) | Nothing | S | Claude alone |
| **Accounts** | | | | | |
| ACC-1 | §42.2 | Bank reconciliation from the bank's statement file | Nothing (a sample statement helps) | L | Claude alone |
| ACC-2 | §42.3 | Post-dated cheque register: held, deposited, cleared, bounced | Nothing | M | Claude alone |
| ACC-3 | §74.1 row 12 | How money moved: UPI, cheque, NEFT, card, cash, with number and date -- **built 2026-10-02** (A49) | Nothing | S | Claude alone |
| ACC-4 | §74.1 row 13 | The firm's bank details printed on bills; account numbers masked | Nothing | M | Claude alone |
| ACC-5 | §74.1 row 14 | Checks before closing a month -- **built 2026-10-02** (A50) | Nothing | S | Claude alone |
| ACC-6 | §74.1 row 16 | Ageing buckets set per firm; due today and this week -- **built 2026-10-03** (A51) | Nothing | S | Claude alone |
| ACC-7 | §53.1 | TDS challan screen; a supplier's usual TDS section | Nothing | M | Claude alone |
| ACC-8 | §42.4 | TDS 194Q worked out automatically past ₹50 lakh per supplier | Nothing (CA confirms the rate at hand-over) | M | Claude alone |
| ACC-9 | §74 row 5 | Cash flow statement | Nothing | M | Claude alone |
| ACC-10 | §74 row 7 | Scanned bill or letter attached to a journal, receipt or payment | Nothing | M | Claude alone |
| ACC-11 | §75 row 4 | A customer who is also a supplier, as one party | Nothing | M | Claude alone |
| ACC-12 | §55 S11 | Cheque printing | Nothing (a cheque leaf to align) | S | Claude alone |
| **GST** | | | | | |
| GST-1 | §77 row 12 | Warn on a credit note after 30 November -- **built 2026-10-02** (A46) | Nothing | S | Claude alone |
| GST-2 | §77 row 13 | GST document numbers kept to 16 characters -- **built 2026-10-02** (A47) | Nothing | S | Claude alone |
| GST-3 | §78 row 7 | Warn on a supplier bill entered after its credit's last date -- **built 2026-10-02** (A48) | Nothing | S | Claude alone |
| GST-4 | §78 row 9 | Common credit reversal for a firm with exempt sales (rules 42/43) | Nothing (CA confirms at hand-over) | M | Claude alone |
| GST-5 | §74.1 row 9 | GST checks before filing: an exception list | Nothing | M | Claude alone |
| GST-6 | §74.1 row 10 | A filed return's figures kept as filed; later changes as amendments | Nothing | L | Claude alone |
| GST-7 | §74.1 row 11 | Quarterly filers (QRMP) | Nothing | M | Claude alone |
| GST-8 | §74.1 row 15 | The tax rule that applied, kept on each line | Nothing | M | Claude alone |
| **Masters and configuration** | | | | | |
| MST-1 | §75 row 1 | Principal (company) and brand masters | Nothing | M | Claude alone |
| MST-2 | §75 row 7 | New rates from a future date, with rate history | Nothing | M | Claude alone |
| MST-3 | §75 row 8 | Warn on duplicate parties; merge two into one | Nothing | L | Claude alone |
| MST-4 | §75 row 9 | Attachments and a bank account on the customer | Nothing | S | Claude alone |
| MST-5 | §75 row 10 | Customer, supplier and product codes issued automatically | Nothing | S | Claude alone |
| MST-6 | §52 | Extra fields on documents, not only on masters | Nothing | L | Claude alone |
| MST-7 | §17 | Features and modules created at runtime reach every store | Nothing | S | Claude alone |
| MST-8 | §16 | A firm configures its own custom fields | Nothing | M | Claude alone |
| **Reports** | | | | | |
| RPT-1 | §62 remainder | Sales analysis: filters, orders basis, margin, compare, chart, export, saved layouts | Nothing | M | Claude alone |
| RPT-2 | §66 remainder | Purchase analysis: the same, plus receipt basis, average rate, rate trend | Nothing | M | Claude alone |
| **Platform** | | | | | |
| PLT-1 | §56 A | Bulk reject, and approval in several levels | Nothing | L | Claude alone |
| PLT-2 | §55 S12 | Notifications: the bell | Nothing | M | Claude alone |
| PLT-3 | §56 C | Fast global search (trigram indexes) | Nothing | S | Claude alone |
| PLT-4 | §56 C | GSTR-1, GSTR-3B and outstanding reports under 3 seconds | Nothing | M | Claude alone |
| PLT-5 | §56 C | Back-dated entries carried forward in one statement | Nothing | M | Claude alone |
| PLT-6 | §56 C | Old login and log records pruned by default | Nothing | S | Claude alone |
| PLT-7 | D-PERF-1 | The 38 routes past their time target on WHOLE01 | Nothing | M | Claude alone |
| PLT-8 | §31.17 rest | One search box on the audit trail spanning who and what | Nothing | S | Claude alone |
| PLT-9 | §31 leftovers | Phase 1 leftovers: payload guard on the phase 2 editors, "Line 1" labels, price-list counts | Nothing | S | Claude alone |
| PLT-10 | §3 | The stray `installer/` folder | Nothing | S | Claude alone |
| PLT-11 | §53 item 4 | Report: parties with no PAN, and PAN that does not match the GSTIN -- **built 2026-10-03** (A53) | Nothing | S | Claude alone |
| **Messaging and integration** | | | | | |
| MSG-1 | §51 A2 | Share a document on WhatsApp by hand -- **built 2026-10-03** (A56) | Nothing | S | Claude alone |
| MSG-2 | §51 A3 | UPI QR code on the printed bill -- **built 2026-10-03** (A55) | Nothing | S | Claude alone |
| MSG-3 | §51 A4 | Payment reminder by hand from the overdue list and statement -- **built 2026-10-03** (A57) | Nothing | S | Claude alone |
| MSG-4 | §51 | Send documents other than the invoice by hand | Nothing | M | Claude alone |
| MSG-5 | §55 G4 | Export to Tally (vouchers and masters, XML) | Nothing (the CA's Tally to check an import) | L | Claude alone |

---

## 2. Needs the owner (major inputs only)

None of these blocks an item in section 1. Each unblocks something in
section 5.1, or is needed before a built feature is switched on for a firm.

1. **E-invoicing route for the first firm that must e-invoice live (§77
   row 8).** Which route -- Direct NIC with the firm's own API credentials, or
   a GSP (Masters India or ClearTax) -- and the contract and credentials for
   it. *Recommended:* Direct NIC for a firm above ₹5 crore that can register
   for API access itself (no fee); a GSP only if the firm already has one.
2. **Messaging accounts (A13).** A real SMTP mailbox, a WhatsApp Cloud API
   account and an SMS (DLT-registered) account to prove the built messaging
   against the real thing; it stays off until then.
3. **Payment links (§51 B4).** Whether to offer them, and a Razorpay or
   Cashfree merchant account to build against. *Recommended:* after go-live,
   once a firm asks; the UPI QR (MSG-2) covers most of the need for free.
4. **Facts about the go-live firms**, which decide whether three parked items
   are built at all: does any firm (a) sell exempt goods or use the
   composition scheme (bill of supply, §77 row 14), (b) import goods (bill of
   entry, §78 row 8, §68 row 13), (c) need a rate contract or RFQ (§68 row 12,
   §65 row 14, §69 row 11)?
5. **The CA's sign-off at hand-over** on A5, A8, A9, A20, A31, and on the
   rates built in ACC-8 (194Q) and GST-4 (rules 42/43). Also the owner's OK
   on A43, A44, A45 (built 2026-10-02).
6. **Already parked by the owner**, unchanged here: licensing and update
   delivery (B11: §2, §43); the next phase -- portal, salesman app, field
   collections, phone layouts (B7: §42.14, §42.6, §39, §48); sign-in,
   branding, menu and dialog review (B9: §71-73, after the Jugnix trademark is
   filed); a spare PC for the clean-machine installer test and the `.ico`
   (B10: §3, §47).
7. **For testing only, not for building:** a barcode scanner (SEL-12), a
   label printer or label sheet size (STK-16), a cheque leaf from the firm's
   bank (ACC-12), a sample statement and the bulk-payment upload format from
   the firm's bank (ACC-1, BUY-11).

---

## 3. Decided by market standard

Each answer below is what the named tools do. The owner may overrule any one;
otherwise it is built as written.

| Item | Decided | As in |
| --- | --- | --- |
| SEL-1 | Customer first, then a tick list of that customer's dispatched notes with something left to bill | Tally, Zoho, ERPNext |
| SEL-2 | "Buy X get Y at N% off" discounts the cheapest qualifying units, repeating per set bought | Zoho, Odoo, Shopify |
| SEL-3 | A combo price is apportioned over the combo's lines by their value, so each line keeps its own GST | Busy, Tally schemes |
| SEL-4 | Festival points are a multiplier on the earn rate for the offer's dates; their cost is booked when earned, as today | Zoho, Vyapar loyalty |
| SEL-5 | Codes are random, 8 characters, single-use each, exported as CSV; a batch can be voided whole | Shopify, Zoho |
| SEL-6 | Eligibility is worked out at pricing from the firm's own invoices (first order; not billed in N days) | Shopify, Odoo |
| SEL-7 | Weekday and time window, judged on the document's own date and the time it was raised, in IST | Odoo POS, Marg |
| SEL-8 | Copying makes drafts with new dates; nothing goes live until approved | Zoho, Odoo |
| SEL-9 | Named price levels on the product; a customer or group is given one; a rate on a price list beats the level, which beats the product's price | Tally price levels, Busy, Marg |
| SEL-10 | Enquiry -> quotation; a prospect becomes a customer only on conversion | Zoho CRM-lite, ERPNext Lead/Opportunity |
| SEL-11 | A claim is raised per principal per period from offers marked "principal funded", plus expiry and breakage returns; settled by the principal's credit note or a receipt | Marg, DMS apps |
| SEL-12 | A scan adds a line or adds 1 to the same product's line; one key saves, prints and starts the next; tender split cash / UPI / card | Marg, Busy, Vyapar |
| SEL-13 | Pick list sums products and batches over the chosen notes; loading sheet lists drops in route order per vehicle | Marg, DMS apps |
| SEL-14 | Cash discount is a receipt deduction to "discount allowed" with no GST change unless agreed on the bill; overdue interest is shown on the statement at the firm's rate and raised as a customer debit note only when the user chooses | Tally interest, Zoho |
| SEL-15 | Optional per firm; a pending outlet takes orders but cannot be invoiced or given credit until approved | DMS apps, ERPNext |
| BUY-1 | Same-item free quantity stays as today; a different free item is "free issue only" stock; giving it away posts promotional expense at cost | Tally, Busy, Marg |
| BUY-2 | Gifts are not stock; the journal depends on who keeps it (asset, expense or drawings) against "Other income - supplier incentives"; no input credit; 194R total per supplier per year against ₹20,000 | Accounting standard practice |
| BUY-3, 4 | Supplier price per supplier and product with effective dates and quantity breaks, history kept; a supplier's standing discount; ranked in the one pricing resolver | Zoho, ERPNext Item Price |
| BUY-5 | Warn by default and suggest the rounded quantity; a firm may switch to refuse; never changed silently | ERPNext, SAP |
| BUY-7 | Requisition -> approve -> convert into orders grouped by preferred supplier | ERPNext Material Request |
| BUY-8 | Amending makes revision n, keeps every earlier revision, and needs re-approval when the total rises past the approver's limit | ERPNext amend, SAP |
| BUY-9 | Optional per product or category; the receipt lands in quarantine until released or rejected | ERPNext Quality Inspection |
| BUY-10 | Firm tolerance as a % and an amount; beyond it the bill is held for approval naming the lines | SAP, ERPNext over-billing allowance |
| BUY-11 | A run picks bills due by a date, is approved once, records each payment, and exports a bank file through the same field mapping as imports | Tally e-payments, Zoho |
| BUY-13 | Rebate agreement with slabs on purchase value per period; accrued as a receivable from the supplier at period end; claimed by debit note | SAP, ERPNext |
| BUY-14 | Budget per branch, category and month; warn when exceeded, never block by default | Zoho, ERPNext |
| BUY-15 | 1-5 stars on price, quality, delivery, support, labelled as opinion | Procurement suites |
| BUY-16 | A landed cost voucher spreads a freight or clearing bill over completed receipts by value (or quantity / weight); stock still on hand is revalued, the sold share goes to cost of goods sold | Zoho, ERPNext Landed Cost Voucher |
| STK-1 | Two steps, dispatch then receive, with stock in transit between; within one GSTIN on a delivery challan | Zoho transfer orders, Tally |
| STK-2 | A GSTIN per branch; a transfer between two GSTINs is a taxable supply raised as a tax invoice | CGST Act (distinct persons) |
| STK-3 | Reasons Internal use, Staff, Display / demo, each to its own expense account | Tally, Busy |
| STK-4 | Repacking consumes the source, produces the target, carries the cost across, books wastage to loss | Tally / Busy stock journal, Marg |
| STK-5, 11, 12, 13 | Firm defaults with product or category overrides; lapsing reservations and held returns are off until switched on | ERPNext, Zoho |
| STK-6 | Cycle counts by ABC class or bin; blind count optional; variance above a limit needs approval | ERPNext, SAP |
| STK-7, 8 | A reason master mapped to accounts; approval by role limit on value, the same rules as discount and purchase limits | ERPNext |
| STK-10 | Incoming = open purchase orders not yet received; outgoing = open sales orders not yet reserved | Zoho, ERPNext |
| STK-15 | A kit is a product with components; selling it moves the components; an assembled pack is made by repacking | Zoho composite items |
| STK-16 | PDF labels on A4 sheets and 50 x 25 mm thermal rolls; Code 128; name, MRP, price | Marg, Busy |
| STK-17 | A Discontinued status refused on purchase orders and still sold; a Not-for-sale flag never on a sales document | ERPNext, Zoho |
| ACC-1 | Statement import (CSV / Excel through the field mapping); match by amount, date within 3 days and reference; cleared date on the receipt or payment; a reconciliation statement | Tally, Busy, Zoho |
| ACC-2 | A cheque dated ahead is held, not posted, until its date; deposit, clear and bounce; a bounce reverses and may carry a charge | Busy, Tally |
| ACC-4 | Bank details on the firm's bank accounts printed on bills; any account number masked to the last four digits except for roles that pay | Zoho, banking apps |
| ACC-5 | Warn by default; a firm may switch to refuse | ERPNext, Zoho period close |
| ACC-7 | A challan (CIN, BSR code, date) gathers the month's deductions and posts Dr TDS payable / Cr bank; the supplier carries a default section | Tally, Zoho |
| ACC-8 | ₹50 lakh per supplier per financial year; 0.1% on the excess, on the bill (credit) or the payment, whichever first; rate and threshold in settings | Tally, Zoho, Busy |
| ACC-9 | Indirect method from the same balances | Tally, Zoho |
| ACC-11 | Link a customer to a supplier record; one combined statement; set-off already built | Tally, Zoho |
| ACC-12 | CTS-2010 cheque layout with a per-bank offset setting | Tally cheque printing |
| GST-4 | Rule 42 monthly on common credit, true-up at year end; report by default, posting optional, as rule 37 | Tally, Zoho |
| GST-6 | Marking a return filed freezes its figures; a later change to that period goes to the next return's amendment tables | Tally, ClearTax |
| GST-7 | Filing frequency on the firm; GSTR-1 quarterly with optional IFF; due 22nd / 24th by state | GST law, Tally |
| MST-1 | A principal (company) master linked to its supplier; brands under it | Marg "company", Busy |
| MST-2 | A scheduled rate revision with an effective date; history kept | Tally "applicable from" |
| MST-3 | Warn on create by name, phone, GSTIN; merge moves every reference and is refused across a locked year | Zoho merge contacts |
| MST-5 | Optional automatic code from a series; typing stays allowed | ERPNext naming series |
| MST-6 | Header fields first, carried down the chain where the same field exists, printable, filterable | Zoho custom fields |
| MST-8 | `firm_id` on the attribute tables, shared rows copied per firm, firm administrator manages definitions and mandatory rules; profile change stays a platform action (B2) | Zoho, ERPNext |
| PLT-1 | Reject needs a reason; approval rules by amount with up to three levels | Zoho approvals |
| PLT-2 | A server-side notification list, polled by the desktop: approvals waiting, refused sends, stock alerts | Zoho, ERPNext |
| PLT-6 | Retention on by default (the existing 30 / 90 day rules), run daily by the installed server | Every hosted product |
| MSG-1 | Open WhatsApp at the party's number with the message typed, the PDF saved for the user to attach | Vyapar |
| MSG-2 | `upi://pay` QR for the amount due, from the firm's UPI ID | Tally, Vyapar |
| MSG-5 | TallyPrime XML import format: masters and vouchers for a date range, ledgers mapped per firm | Busy, Marg exporters |

---

## 4. The items, one by one

### Selling

#### SEL-1. Several delivery notes on one bill: customer first (§58 items 2, 4)
- **What it is:** when billing, choose the customer, tick their delivered notes, and be told on screen if two notes cannot share a bill.
- **Needs from the owner:** nothing (section 3).
- **What gets built:** desktop only. Replace the *Also bill* menu in `desktop/lib/ui/sales/sales_invoice_editor_phase2.dart` (and its twin `purchase_invoice_editor_phase2.dart`) with a customer-first tick list (number, date, order, amount left), refusing notes that differ in branch, salesman, territory or route by name. The server already refuses the same mix. Widget test for both editors.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A54, D-SELL-44): the invoice editor asks for the **customer** first (only those with notes to bill) and opens a tick list of their notes -- number, date, order, left to bill before tax; a customer with one note has it ticked without asking. A note of another branch, salesman, territory or route cannot be ticked beside those already ticked and says which field and which note it clashes with. The supplier bill does the same with the **supplier** and their receipts (branch is the only field a receipt can clash on). One shared dialog, `desktop/lib/phase2/source_tick_dialog.dart`. `GET /sales-invoices/billable` now names each note's branch, order, salesman, territory and route (one read per kind for the page). The server compared each later note only with the first, so a first note naming no salesman let two different salesmen through; it now compares with the first note that names one (D-SELL-44). No migration. Tests: `test_sales_invoice_module.py` (two new), `sales_invoice_several_notes_test.dart`, `purchase_bill_several_receipts_test.dart`.

#### SEL-2. Offer: buy X get Y at a discount (§60 row 4)
- **What it is:** "buy 2, the second at 50% off".
- **What gets built:** a new `PromotionActionType` in `backend/app/promotions/schemas/promotion.py`, valued in `promotion_service.py` beside `FREE_QUANTITY`; no migration (actions are rows). Promotion dialog (`desktop/lib/ui/pricing/promotion_dialog.dart`) gains the benefit; *Try offers* shows it. Tests: pricing, best-offer valuation, the cap.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### SEL-3. Offer: combo price (§60 row 5)
- **What it is:** a set price for a set of products bought together.
- **What gets built:** a new action type naming the set and its price; the engine finds complete sets on the document and apportions the saving over their lines by value (as `apportion` does for bill discounts) so tax stays per line. Dialog: a product multi-pick with quantities. Tests: partial sets, two sets, tax per line.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### SEL-4. Offer: festival bonus loyalty points (§60 row 6)
- **What it is:** double (or any multiple of) loyalty points for the offer's dates.
- **What gets built:** an action type carrying a multiplier, read by `backend/app/loyalty/services/loyalty_service.py` where points are earned at invoice approval. Dialog field. Tests: earn doubled only inside the dates; reversal on cancel.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### SEL-5. Bulk single-use coupon codes (§60 row 7)
- **What it is:** generate 500 codes for a campaign and hand them out as a file.
- **What gets built:** `POST /promotions/{id}/coupons/generate` (count, prefix) in `backend/app/promotions/api/router.py` using `coupon_crud.py`, each code single-use; a CSV export; *Generate codes* and *Export* on the coupon screen (`coupon_dialog.dart`). No migration (codes are coupon rows).
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### SEL-6. Customer eligibility conditions (§60 row 8)
- **What it is:** an offer only for a customer's first order, or for customers not billed in N days.
- **What gets built:** new `PromotionField` keys derived while pricing (count of the customer's approved invoices; days since the last one), read in one query per document. Condition picker on the dialog. Tests for each, and that a draft does not count as an order.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### SEL-7. Day and time conditions (§60 row 9)
- **What it is:** "weekends only", "4-6 pm".
- **What gets built:** `PromotionField` keys for weekday and time of day, from the document date and its creation time in IST. Dialog conditions. Tests at the edges of the window.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### SEL-8. Offer templates (§60 row 10)
- **What it is:** copy last year's offers with new dates.
- **What gets built:** `POST /promotions/copy` (ids, new from / until) creating drafts; *Copy...* on `desktop/lib/ui/pricing/promotion_page.dart` for the ticked rows. Tests: copies are drafts, the originals untouched.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### SEL-9. Special rates per customer and named price levels (§64 row 1)
- **What it is:** "Anand pays 80 for detergent"; Retail / Wholesale / Dealer rates.
- **What gets built:** migration: a fixed `rate` on `price_list_items` beside `discount_percent` (`backend/app/pricing/models/price_list.py`); a new price-level master and product rates per level; a level on the customer and customer group. Ranked in `backend/app/core/utils/pricing.py` (list rate > level > product price). Product editor (`product_editor_phase2.dart`) gets a rates-per-level grid; customer editor a level picker; price list dialog a Rate column. Tests: ranking, a typed rate still wins, documents inherit.
- **Depends on:** nothing; combines with MST-2. **Effort / Who:** M, Claude alone.

#### SEL-10. Enquiries and leads (§67 row 1)
- **What it is:** record an enquiry before quoting, follow it up, and see why deals were lost.
- **What gets built:** a new `app/enquiry` module in the five layers: enquiry with lines, prospect details, expected value, salesman, next follow-up, status Open / Quoted / Won / Lost with reason; numbering through the document framework; *Convert to quotation* calling `backend/app/quotation`; a prospect becomes a customer on conversion. Migration yes. Permissions seeded in `app/identity/system_seed.py`. Phase 2: Sell > Enquiries list and editor, a "follow-ups due" list. Tests and `docs/SALES_CHAIN_RULES.md`.
- **Depends on:** nothing. **Effort / Who:** L, Claude alone.

#### SEL-11. Claims to the principal (§42.7, §60 row 11, §55 G10)
- **What it is:** what the company owes the agency for schemes passed on, and for expired or broken stock, raised as a claim and tracked till settled.
- **What gets built:** a *principal funded* flag and principal on a promotion; a new claim document per principal and period, its lines gathered from promotion cost (redemptions and free goods, already ledgered), expiry write-offs and damaged returns; statuses Raised / Part settled / Settled; posts Dr claims receivable / Cr promotional expense (new control purpose), settled by receipt or the principal's credit note. Migration yes. Phase 2 screen under Buy > Claims; printable claim statement. Tests.
- **Depends on:** MST-1 (principal master). **Effort / Who:** L, Claude alone.

#### SEL-12. Fast counter billing with barcode (§55 M10)
- **What it is:** a counter bill where scanning adds the item, one key saves and prints, and the next bill opens.
- **What gets built:** the phase 2 bill (`sales_invoice_editor_phase2.dart`) already finds a product by barcode; add a scan field that adds a line or adds 1, save-print-new on one key, the thermal print (`thermal_pdf.py`) as the counter's default, and a tender split (cash / UPI / card) on *Received now* (§64 row 5). A batch-tracked product takes FEFO as today. Widget tests with a simulated scanner (keystrokes ending in Enter).
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### SEL-13. Picking list and loading sheet (§55 G7)
- **What it is:** what the storeman picks and what goes on each van, by route.
- **What gets built:** two PDFs beside `backend/app/delivery_note/services/challan_print_service.py`: a pick list summing products and batches over the chosen notes, and a loading sheet per vehicle with customers in route order (`visit_sequence`) and amounts to collect. Delivery note list: tick notes, *Pick list*, *Loading sheet*. No migration.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### SEL-14. Cash discount for early payment; interest on overdue (§55 G9)
- **What it is:** "2% off if paid in 10 days", and interest charged on late bills.
- **What gets built:** migration: cash-discount days and % on payment terms / the customer; Record Receipt offers it as a *discount allowed* deduction when inside the window (deductions already exist on receipts). An interest rate per firm; the customer statement (`backend/app/customers/services/statement_service.py`) shows interest accrued per overdue bill; *Raise interest debit note* uses `backend/app/customer_debit_note`. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### SEL-15. New outlet pending office approval (§75 row 11)
- **What it is:** a shop a salesman adds can take orders, but is not billed on credit until the office approves it.
- **What gets built:** a `PENDING` member of `CustomerStatus` (`backend/app/customers/schemas/customer.py`) and a firm setting; invoice and credit sale refused for a pending customer by name; *Approve* single and bulk (`run_each` in `bulk_actions.py`); a permission seeded with its migration. Customer list filter. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

### Buying

#### BUY-1. Free goods for customers (§61 item 1)
- **What it is:** promotional stock that can be received, given away and counted, but never sold at a price.
- **What gets built:** migration: a *free issue only* flag on products and a scheme name on goods receipt lines; sales screens refuse a price on such a product; new stock issue reasons *Given free to customer* and *Sample* (beside `WriteOffReason` in `backend/app/inventory/schemas/inventory.py`) naming the customer and posting to a *Promotional expense* control purpose at cost. A report: received per supplier and scheme, given per customer, on hand. Tests as listed in §61.
- **Depends on:** STK-7 if done first (the reason becomes a master row). **Effort / Who:** M, Claude alone.

#### BUY-2. Supplier gifts register, journal, 194R (§61 items 2, 3)
- **What it is:** a TV or gold coin from a supplier recorded once, with the right journal and the tax total.
- **What gets built:** a new register table (date, supplier, item, value, kept by firm / used up / owner, linked purchase); saving posts one journal by who keeps it through `document_posting.py`; a third receipt line kind *Gift, not stock* creating a register row instead of stock; a per-supplier, per-year total against ₹20,000 with any 194R TDS (`backend/app/finance/tds.py` already lists 194R). Migration yes. Phase 2 screen under Buy. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### BUY-3. Supplier rates (§65 row 4)
- **What it is:** a supplier's standing discount and price list fill the order line.
- **What gets built:** migration: `standing_discount_percent` on vendors; price lists with a supplier scope (purchase side) in `backend/app/pricing`; the purchase branch of `backend/app/core/utils/pricing.py` ranks them as sales does. Vendor editor field; price list dialog's purchase mode. Tests mirroring the sales ranking.
- **Depends on:** nothing; BUY-4 extends it. **Effort / Who:** M, Claude alone.

#### BUY-4. Supplier catalogue (§69 row 1)
- **What it is:** per supplier and product: their name and code, price with history, pack size, minimum order, lead time.
- **What gets built:** a new supplier-product table (dated rows, never overwritten); the purchase order line fills supplier code, rate and pack from it; *Catalogue* tab on the vendor editor and import through `app/common/file_import.py`. Migration yes. Tests.
- **Depends on:** BUY-3. **Effort / Who:** M, Claude alone.

#### BUY-5. Minimum order quantity and order multiple (§69 row 2)
- **What it is:** ordering 115 against a minimum of 100 in multiples of 20 warns and suggests 120.
- **What gets built:** check in `backend/app/purchase/services/purchase_service.py` from the catalogue row; a firm setting warn / refuse; reorder rounding (`reorder.py`) uses it; the order editor shows the suggestion. Tests.
- **Depends on:** BUY-4. **Effort / Who:** S, Claude alone.

#### BUY-6. Lead time used and measured (§69 row 3)
- **What it is:** the expected date fills from the supplier's lead time, and actual delays are recorded.
- **What gets built:** expected delivery default from the catalogue row; actual lead time derived per receipt; reorder planning (`reorder.py`, which already has a firm-wide `lead_time_days`) prefers the supplier's. Tests.
- **Depends on:** BUY-4. **Effort / Who:** S, Claude alone.

#### BUY-7. Purchase requisition / indent (§68 row 3)
- **What it is:** a branch or storeman asks for goods; once approved it becomes one or more orders.
- **What gets built:** a requisition document (lines, needed by, approval) in `backend/app/purchase` or its own module, numbered by the document framework; *Convert to orders* grouping by preferred supplier (`products.preferred_vendor_id`); the reorder screen can raise one. Migration yes. Phase 2 list and editor under Buy. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### BUY-8. Purchase order amendment (§68 row 5)
- **What it is:** change an approved order formally: revision number, what changed, reprinted as "Amendment 1".
- **What gets built:** migration: `revision_number` and a revisions table holding each earlier version; *Amend* on an approved order, re-approval through `approval_limit.py` when the total rises; the print (`purchase_print_service.py`) names the amendment. Tests: receipts against the order survive, quantities never drop below received.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### BUY-9. Quality inspection hold (§68 row 6)
- **What it is:** for pharma or food, received stock is unusable until checked.
- **What gets built:** an *inspection required* flag on product / category (migration); `goods_receipt_service.py` posts such lines into quarantine (the quarantine hold already exists in inventory); an inspection screen to pass (release) or reject (return or write-off). Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### BUY-10. Bill match tolerances holding the bill (§68 row 7)
- **What it is:** a supplier bill priced or counted beyond the agreed tolerance waits for approval.
- **What gets built:** firm tolerance (% and amount) in purchase settings (`workflow_settings_service.py`, migration); the purchase invoice approval in `backend/app/purchase_invoice` compares to receipt and order, refuses without a permission and names the lines; bulk approval reports it per row. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### BUY-11. Payment run and bank bulk file (§68 row 9)
- **What it is:** pay all bills due by Friday across suppliers in one go, and upload one file to the bank.
- **What gets built:** a payment-run document (date, chosen bills, approval) that records one payment each through `backend/app/settlements/services/settlement_service.py`; export of a bank file from `vendor_bank_accounts` in a generic NEFT layout, mapped to a bank's columns with the import field mapping (`backend/app/imports`). Migration yes. Phase 2 screen under Buy > Money. Tests.
- **Needs from the firm, to finish:** its bank's bulk-upload format.
- **Depends on:** ACC-4 (masking: only a paying role sees full numbers). **Effort / Who:** M, Claude alone.

#### BUY-12. Supplier performance (§68 row 11)
- **What it is:** which supplier delivers late, short or bad, and at what price trend.
- **What gets built:** a report grouped in SQL over receipts and order lines (`line_quantities.py` already derives received / rejected / returned per line): on time %, short %, rejected %, average rate by month. Entry in `desktop/lib/ui/reports/report_catalog.dart`. No migration.
- **Depends on:** BUY-6 makes on-time sharper (works on the order's expected date without it). **Effort / Who:** M, Claude alone.

#### BUY-13. Supplier volume rebates (§69 row 8)
- **What it is:** "2% back on the year's purchases over 10 lakh", tracked and claimed.
- **What gets built:** a rebate agreement (supplier, period, slabs); purchases counted from approved bills; at period end an accrual Dr rebate receivable / Cr purchase rebates; claimed by a supplier debit note (`backend/app/debit_note`). Migration yes. Phase 2 screen. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### BUY-14. Purchase budget (§69 row 9)
- **What it is:** a spending budget by branch, category and month, shown and warned on the order.
- **What gets built:** a budget table; used = approved orders in the period; the order editor shows used / available; warn at approval, optional approval when exceeded. Migration yes. Settings > Buying screen. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### BUY-15. Supplier rating by people (§69 row 10)
- **What it is:** users score suppliers, kept apart from the computed figures.
- **What gets built:** a rating table (user, supplier, five criteria, remark, date); averages on the vendor editor (`vendor_editor_phase2.dart`). Migration yes. Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### BUY-16. Landed cost (§42.12)
- **What it is:** freight, loading or clearing paid to a third party is added to the goods' cost, so margins are right.
- **What gets built:** a landed cost voucher naming completed receipts and a service bill (expense / purchase invoice without source); apportion by value, quantity or weight; revalue the stock still on hand and post the sold share to cost of goods sold, through `inventory_service.py` and `document_posting.py`. Migration yes. Phase 2 screen under Buy. Tests: average cost moves, the journal balances, a cancel reverses both books.
- **Depends on:** nothing. **Effort / Who:** L, Claude alone.

#### BUY-17. Supplier credit against an opening bill (§36)
- **What it is:** a return's credit can be set against a bill brought over from the old software.
- **What gets built:** `backend/app/settlements/services/supplier_credits.py` accepts a vendor opening bill as a target beside purchase invoices; the opening bill's derived outstanding includes it; the apply dialog lists opening bills. Tests. Migration only if the allocation table needs the opening-bill reference.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A52): `supplier_credit_applications.vendor_opening_bill_id` (migration 0239; `purchase_invoice_id` nullable, a check holds exactly one); `apply_supplier_credit` takes an opening bill instead of refusing it; `opening_bill_payments` counts the credit, so Record Payment, the opening bill list and the vendor delete guard follow; cancelling an opening bill withdraws the credit set against it. The desktop apply dialog already listed opening bills ("(opening)"), so it needed no change. Tests in `test_supplier_credit_opening_bill.py`.

### Stock

#### STK-1. Stock transfer as a document (§70 row 1)
- **What it is:** a numbered, multi-line transfer with a printed challan, dispatched and then received at the other end, with shortages recorded.
- **What gets built:** a transfer document (lines, from / to, status Draft / Dispatched / Received); dispatch moves stock to `in_transit_quantity` (already on inventory records), receive moves it in and records short or damaged; challan print. Migration yes. Phase 2 list and editor under Stock. Tests including batches and value.
- **Depends on:** nothing; STK-2 adds the tax-invoice case. **Effort / Who:** L, Claude alone.

#### STK-2. Branches with their own GSTIN (§70 row 2)
- **What it is:** a firm registered in two states uses each branch's GSTIN on its documents; a transfer between them is a tax invoice.
- **What gets built:** migration: a GSTIN on branches (`backend/app/branches/models/branch_warehouse.py`); every print, GSTR-1/3B (`gstr_service.py`), e-invoice payload and e-way bill read the document's branch GSTIN; returns filter by GSTIN; an inter-GSTIN transfer raised as a sales invoice to the other branch with input credit there. Tests across returns.
- **Depends on:** STK-1. **Effort / Who:** L, Claude alone.

#### STK-3. Issue for internal use (§70 row 3)
- **What it is:** stock taken for the office, staff or display, booked to the right expense.
- **What gets built:** reasons *Internal use*, *Staff*, *Display / demo* with control purposes in `opening_setup.py` (backfilled by migration); the write-off action in `stock_action_dialog.dart` offers them. Tests.
- **Depends on:** nothing (or STK-7, which turns reasons into a master). **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A61): `WriteOffReason` gains `INTERNAL_USE`, `STAFF` and `DISPLAY`; each posts to its own expense through new purposes `INTERNAL_USE` (6900 *Stock Used in Business*), `STAFF_WELFARE` (6910 *Staff Welfare*) and `SAMPLES_AND_DISPLAY` (6920 *Samples and Display*), indirect expenses seeded by `opening_setup.py` and given to existing firms by migration 0243 (only where missing, never overwriting). `post_stock_adjustment` takes the expense purpose; damage, expiry and loss stay on *Inventory Adjustment*. The write-off dialog offers the three. Tests: `test_stock_issue_reasons.py`, `stock_action_dialog_test.dart`.

#### STK-4. Repacking and bulk breaking (§70 row 4)
- **What it is:** turn one product into another -- a 25 kg bag into 25 packs -- carrying the cost and recording wastage.
- **What gets built:** a repack document: consume lines and produce lines, cost carried in proportion, wastage to a loss account; one transaction through `inventory_service.py`. Migration yes. Phase 2 screen under Stock. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### STK-5. Expiry rules per product (§70 row 7)
- **What it is:** per product: when to stop selling, when to alert, when to send back to the supplier.
- **What gets built:** migration: three day counts on product / category overriding the firm's `batch_sale_settings`; the batch picker and dispatch (`batch_sale_policy.py`) use them; the expiry monitor lists "return to supplier now". Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### STK-6. Count planning (§70 row 8)
- **What it is:** cycle counts on a schedule, blind counts, and approval of large differences.
- **What gets built:** ABC class on inventory (computed from sales value), a count plan (class or bin, frequency), a blind option hiding system quantity on the sheet, and a variance limit needing approval in `physical_count_service.py`. Migration yes. `physical_count_page.dart`. Tests.
- **Depends on:** STK-8 for the approval rule. **Effort / Who:** M, Claude alone.

#### STK-7. Adjustment reasons as a master (§70 row 11)
- **What it is:** the firm keeps its own list of reasons, each tied to an account.
- **What gets built:** a reason table seeded with today's DAMAGE / EXPIRY / LOSS and the new ones (STK-3, BUY-1); every adjustment and write-off names one; the journal uses its account. Migration yes, with backfill. Settings > Stock screen. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### STK-8. Approval for large adjustments (§70 row 12)
- **What it is:** above a value per role, an adjustment waits for a manager.
- **What gets built:** role value limits on the same pattern as `role_discount_limits` and `approval_limit.py`; adjustments above it saved as pending, approved singly or in bulk. Migration yes. Tests.
- **Depends on:** STK-7. **Effort / Who:** M, Claude alone.

#### STK-9. Evidence on adjustments (§70 row 13)
- **What it is:** photos and documents attached to adjustments, write-offs, counts and transfers.
- **What gets built:** an attachments table for stock movements and counts in the shape of `delivery_note_attachments`; upload in the stock dialogs. Migration yes. Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### STK-10. Incoming and outgoing on availability (§70 row 14)
- **What it is:** beside available, how much is on order from suppliers and promised to customers.
- **What gets built:** two derived figures in the stock summary of `inventory_service.py` (open purchase order lines not received; open sales order lines not reserved), grouped in SQL; shown on the stock screen and the sales order line. No migration. Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A60): `app/inventory/services/pipeline.py` derives **incoming** (approved purchase orders less completed receipts, in stock units) and **outgoing** (APPROVED / PARTIALLY_DELIVERED sales order lines less what left the warehouse less what is still reserved), per warehouse and product, one grouped read per table; reorder planning now uses the same incoming derivation, still counting drafts. `GET /inventory/summary/by-product` and `/by-warehouse` carry `incoming_quantity`, `outgoing_quantity` and `projected_quantity` (available + incoming - outgoing); by-product also lists a product with no stock row but open orders. The order preview's line carries both for the warehouse it ships from. Desktop: a *Product stock* table on Stock Summary (the by-product route gained its screen) and Incoming / Outgoing / Projected columns there and on *Warehouse stock*; the order editor's side panel shows both under Stock. No migration. Tests: `test_stock_pipeline.py`, `inventory_sections_test.dart`.

#### STK-11. Issue rule per product (§70 row 15)
- **What it is:** per product: earliest expiry first, first received first, or the person picks.
- **What gets built:** a product / category setting (migration); allocation in `batch_serial_service.py` follows it; "person picks" refuses silent allocation at dispatch (the §79 picker already exists). Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### STK-12. Reservations that lapse (§70 row 16)
- **What it is:** stock held for an order that never ships is released after N days.
- **What gets built:** a firm setting (off by default); a pass on the server's existing timer (the messaging worker's loop in `backend/app/messaging/services/outbox_worker.py` shows the pattern) releases them and flags the order; audit row. Migration for the setting. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### STK-13. Returned goods held until checked (§70 row 17)
- **What it is:** a customer return goes to quarantine until someone checks it.
- **What gets built:** a firm setting (off by default); `backend/app/sales_return` posts restock quantities to quarantine when on; release through the existing quarantine release. Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### STK-14. Stock alerts and the inventory dashboard (§70 row 18)
- **What it is:** warnings for low, out, over maximum, near expiry, pending transfers and counts, and Home figures for stock.
- **What gets built:** an alerts query in `inventory_service.py` feeding Home's *To do* (`desktop/lib/phase2/home_page.dart`) and, once built, the bell; an inventory turnover figure per product in the stock ageing report (`stock_ageing.py`). No migration.
- **Depends on:** PLT-2 for the bell (works on Home without it). **Effort / Who:** M, Claude alone.

#### STK-15. Kits and combo packs (§42.13)
- **What it is:** a gift pack stocked or sold as one item made of others.
- **What gets built:** a component list on a product of type kit (migration); selling a kit dispatches its components in proportion, the invoice shows the kit; an assembled kit is made by a repack (STK-4). Product editor *Components* tab. Tests through order, note, invoice, return.
- **Depends on:** STK-4. **Effort / Who:** L, Claude alone.

#### STK-16. Barcode label printing (§55 S8)
- **What it is:** print price and barcode labels for products or a received batch.
- **What gets built:** a label PDF service (Code 128, name, MRP, price, batch and expiry if tracked) for A4 label sheets and 50 x 25 mm thermal rolls; *Print labels* on the product list and the goods receipt. No migration.
- **Needs from the firm, to test:** its label size or printer. **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### STK-17. Discontinued and not-for-sale products (§75 row 5)
- **What it is:** a discontinued product is no longer bought but still sold until gone; packing material is never sold.
- **What gets built:** `DISCONTINUED` in `ProductStatus` (`backend/app/products/schemas/product.py`) refused on purchase orders; a *not for sale* flag refused on sales documents (migration). Product editor. Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A58): `DISCONTINUED` sells (`SELLING_STATUSES` in `app/products/services/trading_status.py`) and is refused on a purchase order by name; reorder planning now lists only ACTIVE products, so it is not suggested. `products.not_for_sale` (migration 0241, all stores) refuses the product on every new sales line -- quotation, sales order and the bare bill the chain turns into one -- whatever its status; it is still bought. Product editor: the status lists carry DISCONTINUED and a *Not for sale* switch sits beside *Allow negative stock*. Tests: `test_product_discontinued.py`, `phase2_product_form_test.dart`.

#### STK-18. Shelf life on the product (§75 row 6)
- **What it is:** a product's shelf life fills each batch's expiry from its manufacturing date.
- **What gets built:** migration: shelf life days on products (batches already carry `shelf_life_days` in `backend/app/batch_serial/models/batch_serial.py`); the receipt fills expiry when only a manufacturing date is typed. The customer's minimum remaining life is already built (§79). Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A59): `products.shelf_life_days` (1-3650, migration 0242, all stores; gated on the SHELF_LIFE feature like the product's other optional fields). A goods receipt line typed with a manufacturing date and no expiry is stored with expiry = manufacturing date + shelf life (`expiry_from_shelf_life` in `batch_serial_service.py`); a typed expiry stands; nothing is filled where the firm's profile does not enable EXPIRY_TRACKING, since the batch would then refuse it. The batch a receipt creates now keeps its manufacturing date and shelf life, each where the firm's profile has that feature (`feature_enabled` in `app/business/gating.py`). Product editor: *Shelf life (days)* beside *Track expiry*. Tests: `test_product_shelf_life.py`, `phase2_product_form_test.dart`.

### Accounts

#### ACC-1. Bank reconciliation (§42.2)
- **What it is:** tick the bank statement against receipts and payments, and print what is still unmatched.
- **What gets built:** a statement import through `app/common/file_import.py` with the field mapping of `backend/app/imports`; statement lines matched to settlements and contra vouchers by amount, date within 3 days and reference; a cleared date on settlements (migration); match / unmatch by hand; a bank reconciliation statement report. Phase 2 screen under Accounts. Tests.
- **Depends on:** ACC-3 helps matching. **Effort / Who:** L, Claude alone.

#### ACC-2. Post-dated cheque register (§42.3)
- **What it is:** a cheque dated ahead is held until its date, then deposited, cleared or bounced.
- **What gets built:** cheque date and status on settlements (migration); a PDC is recorded but not posted until deposit; bounce reverses through the existing reversal and can add a charge via a customer debit note; a PDC register report and a "due to deposit today" list. Tests.
- **Depends on:** ACC-3. **Effort / Who:** M, Claude alone.

#### ACC-3. Payment mode on receipts and payments (§74.1 row 12)
- **What it is:** record whether money came by UPI, cheque, NEFT, card or cash, with its number and date.
- **What gets built:** migration: a mode, instrument number and date on settlements beside `SettlementMethod` (`backend/app/settlements/models/settlement.py`); `record_settlement_dialog.dart` fields; the day / cash / bank books (`books_register.py`) and the collection report show the mode. Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.
- **Built 2026-10-02** (A49): `settlements.payment_mode` and `instrument_date` (migration 0236); cash and bank books gain *Mode* and *Instrument*; collections by mode read the mode; tests in `tests/unit/test_settlement_payment_mode.py`.

#### ACC-4. Firm bank accounts and masking (§74.1 row 13)
- **What it is:** the firm's bank name, account and IFSC printed on bills; others' account numbers show only the last four digits.
- **What gets built:** bank details on the firm's bank ledger accounts (migration) and a "pay to" block in `invoice_print_service.py`; masking in the vendor and customer bank responses unless the caller holds a paying permission. Tests that the full number never leaves the server otherwise.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### ACC-5. Checks before closing a month (§74.1 row 14)
- **What it is:** before a month closes, list what is unfinished.
- **What gets built:** a pre-close check in `backend/app/finance/services/finance_service.py`: draft journals and documents dated in the month, approved documents without a journal, unallocated receipts, GST return not marked filed (`gst_return_filings`), and unreconciled bank lines once ACC-1 exists. Warn by default, refuse by firm setting (migration for the setting). Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.
- **Built 2026-10-02** (A50): `app/finance/services/period_close_checks.py`; `period_close_settings` (migration 0237); `GET /finance/accounting-periods/{id}/close-checks`, `GET`/`PUT /finance/period-close-settings`; the Financial years screen lists before closing. Unreconciled bank lines join when ACC-1 is built. Tests in `tests/unit/test_period_close_checks.py`.

#### ACC-6. Ageing buckets per firm; due lists (§74.1 row 16)
- **What it is:** a firm chooses its ageing columns, and sees what falls due today and this week.
- **What gets built:** buckets per firm replacing the fixed `BUCKET_BOUNDS` in `statement_service.py` (migration for the setting); "due today / this week" filters on the receivable and payable due lists. Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

- **Built 2026-10-03** (A51): `app/finance/services/ageing_settings.py`; `ageing_settings` (migration 0238); `GET`/`PUT /finance/ageing-settings`; the customer and vendor ageing both read the firm's bands (the vendor ageing row now carries `buckets` instead of four fixed columns); `GET /sales-invoices/reports/due` and `/purchase-invoices/reports/due?days=` (0 = today, 7 = the week ahead); the bands are set on the Financial years screen. Tests in `test_customer_statement.py` and `test_stock_and_vendor_ageing.py`.

#### ACC-7. TDS challan screen; a supplier's default section (§53.1)
- **What it is:** record the TDS deposit as a challan, and stop typing the section on every payment.
- **What gets built:** a challan document (CIN, BSR, date, period, section) that gathers the deductions it pays and posts Dr TDS payable / Cr bank; migration; a default TDS section on vendors filling payments and expenses. Phase 2 screen under Accounts > Tax filing. The 26Q export (`tds_return.py`) then names the challan per deduction. Tests.
- **Depends on:** nothing. Unblocks the 26Q FVU file (section 5.1). **Effort / Who:** M, Claude alone.

#### ACC-8. TDS 194Q worked out automatically (§42.4)
- **What it is:** past ₹50 lakh of purchases from one supplier in a year, the 0.1% TDS is suggested on the bill or payment.
- **What gets built:** firm settings for the 194Q threshold and rate (migration); a running total per supplier per financial year summed from bills, never a counter; the payment and bill suggest the deduction on the excess with section 194Q; a register of 194Q per supplier. Tests at the threshold edge. Today a deduction is typed by hand (`backend/app/finance/tds.py`).
- **Needs from the CA, at hand-over:** confirm the rate and threshold as the current Finance Act has them. **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### ACC-9. Cash flow statement (§74 row 5)
- **What it is:** where cash came from and went, for a bank loan file.
- **What gets built:** a report by the indirect method in `backend/app/finance` from the trial balance movements (profit, change in receivables, payables, stock, then investing and financing by account group); phase 2 report beside the P&L. No migration. Tests that it reconciles to the change in cash and bank.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### ACC-10. Attachments on journals, receipts and payments (§74 row 7)
- **What it is:** the scanned bill or letter kept with the entry.
- **What gets built:** attachment tables for journal entries and settlements in the shape of `purchase_invoice_attachments` (migration), sharing the expense module's storage; upload and view on the phase 2 journal and receipt screens. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### ACC-11. Customer and supplier as one party (§75 row 4)
- **What it is:** link the shop that buys from us and sells to us, and see one statement.
- **What gets built:** migration: a linked vendor on the customer; a combined statement from both statement services; the set-off in `backend/app/party_adjustments` preselects the link. Customer and vendor editors show it. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### ACC-12. Cheque printing (§55 S11)
- **What it is:** print the payee, amount and words on a cheque leaf.
- **What gets built:** a cheque PDF on the CTS-2010 layout with per-bank X / Y offsets stored on the firm's bank account; *Print cheque* on a bank payment. No migration beyond the offsets.
- **Needs from the firm, to test:** a cheque leaf. **Depends on:** ACC-4. **Effort / Who:** S, Claude alone.

### GST

#### GST-1. Credit note after 30 November warns (§77 row 12)
- **What it is:** tax on a credit note for a past year's sale can no longer be reduced after 30 November; the screen says so.
- **What gets built:** a warning at credit note and sales return approval naming the date (s.34(2)), in `backend/app/credit_note/services/credit_note_service.py` and the sales return service. Tests.
- **Effort / Who:** S, Claude alone.
- **Built 2026-10-02** (A46): `app/tax/services/gst_time_limits.py` (shared with GST-3), `time_limit_warning` on the credit note and sales return responses; tests in `tests/unit/test_gst_time_limits.py`.

#### GST-2. 16-character document numbers (§77 row 13)
- **What it is:** a GST invoice number may not be longer than 16 characters.
- **What gets built:** a check on numbering rules for GST document types in `backend/app/document_framework`, refusing a pattern whose longest number passes 16 (r.46(b)); the numbering editor (`numbering_series_editor.dart`) shows the length. Tests.
- **Effort / Who:** S, Claude alone.
- **Built 2026-10-02** (A47, D-TAX-3): the platform's own default was 19 characters, so the defaults changed too -- `short_financial_year` on the series (migration 0235), `app/document_framework/services/gst_numbering.py`; tests in `tests/unit/test_gst_document_numbers.py`.

#### GST-3. Supplier bill after the credit's last date (§78 row 7)
- **What it is:** credit for a year must be claimed by 30 November after it; a later bill is warned.
- **What gets built:** a warning at purchase invoice approval when the supplier's date belongs to a year whose 30 November has passed (s.16(4)), in `backend/app/purchase_invoice`. Tests.
- **Effort / Who:** S, Claude alone.
- **Built 2026-10-02** (A48): `credit_time_limit_warning` on the bill response (helper in `app/tax/services/gst_time_limits.py`); tests in `tests/unit/test_gst_time_limits.py`.

#### GST-4. Common credit reversal, rules 42/43 (§78 row 9)
- **What it is:** a firm with exempt sales gives back the share of common input credit that relates to them.
- **What gets built:** a monthly calculation in `backend/app/gst_returns/services` (beside `rule37.py`): common credit x exempt turnover / total turnover, with the year-end true-up; Report (default) or Report and post, as rule 37; GSTR-3B 4(B)(1). Migration for the setting and the reversal rows. Tests.
- **Needs from the CA, at hand-over:** confirm the turnover definitions used. **Effort / Who:** M, Claude alone.

#### GST-5. GST checks before filing (§74.1 row 9)
- **What it is:** a list of what is wrong in a return period before it is filed.
- **What gets built:** an exceptions endpoint in `backend/app/gst_returns`: bad GSTIN checksum or state, missing or short HSN for the firm's turnover, missing place of supply, e-invoice required but not registered, a credit note with no invoice; each row opens its document. Phase 2 screen under GST. Tests per check.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### GST-6. Filed figures kept; changes as amendments (§74.1 row 10, remainder)
- **What it is:** once a return is marked filed, its figures stop changing; a later edit shows up in the next return as an amendment.
- **What gets built:** *Mark filed* (already in `tax_calendar.py`) also snapshots the GSTR-1 lines it reported (migration); GSTR-1 compares current documents with the snapshot and puts changes in B2BA / CDNRA / B2CSA for the next period; 3B states differences. Tests across a filed month.
- **Depends on:** nothing. **Effort / Who:** L, Claude alone.

#### GST-7. Quarterly filers, QRMP (§74.1 row 11)
- **What it is:** small firms file GSTR-1 and 3B quarterly and pay monthly.
- **What gets built:** filing frequency on the firm's GST settings (migration); GSTR-1 for a quarter with the optional IFF in months 1-2; 3B quarterly; due dates 22nd / 24th by state in `tax_calendar.py`; PMT-06 payments in months 1-2 in `gst_payment_service.py`. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

#### GST-8. Tax rule kept on each line (§74.1 row 15)
- **What it is:** a reprint years later can say which tax rule applied, even after the logs are purged.
- **What gets built:** migration: rule code and version on every line-tax table (sales and purchase invoices, orders, returns, notes), written from `TaxRuleService.simulate`'s result; shown on the line's tax detail. Tests.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

### Masters and configuration

#### MST-1. Principal and brand (§75 row 1)
- **What it is:** tie each product to its brand and each brand to the company (and supplier) whose agency the firm holds.
- **What gets built:** principal and brand masters (migration), principal linked to a vendor; `products.brand` (free text) backfilled into brand rows; principal-wise filters on sales analysis, stock and reports. Masters screens in phase 2. Tests.
- **Depends on:** nothing. Unblocks SEL-11. **Effort / Who:** M, Claude alone.

#### MST-2. Price revision with an effective date (§75 row 7)
- **What it is:** "new rates from the 1st", kept with history.
- **What gets built:** a dated price table for selling and purchase price (migration); `pricing.py` reads the rate in force on the document date; a revision import by file; the product editor shows history. Tests at the changeover date.
- **Depends on:** best with SEL-9 (levels carry dates too). **Effort / Who:** M, Claude alone.

#### MST-3. Duplicate check and merge (§75 row 8)
- **What it is:** warn about a second "Sri Balaji Stores", and merge two records of one party.
- **What gets built:** a similarity check on create (name, phone, GSTIN) in the customer and vendor services; a merge that re-points every document, balance, route membership and attribute to the survivor in one transaction, refused across a locked year, audited. Every referencing table found from metadata, not a hand list. Tests.
- **Depends on:** nothing. **Effort / Who:** L, Claude alone.

#### MST-4. Customer attachments and bank account (§75 row 9)
- **What it is:** KYC copies, agreements and a bank account on the customer.
- **What gets built:** copy `vendor_attachments` and `vendor_bank_accounts` (`backend/app/vendors/models/vendor.py`) for customers (migration); tabs on `customer_editor_phase2.dart`; masking per ACC-4. Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### MST-5. Codes from a series (§75 row 10)
- **What it is:** customer, supplier and product codes issued automatically, as documents are.
- **What gets built:** series for the three masters through the document framework, as `movement_numbering.py` did for stock movements; a blank code means "issue one"; typing still allowed. The phase 2 editors show "issued on save". Tests.
- **Depends on:** nothing. **Effort / Who:** S, Claude alone.

#### MST-6. Extra fields on documents (§52)
- **What it is:** a firm adds its own fields (site name, buyer's PO) to orders, notes and invoices without a new release.
- **What gets built:** document types added to `AttributeEntityType` (`backend/app/business/models/framework.py`) and `AttributeService` called from each document service, header first; carried down the chain where the same field exists; a *print* flag read by the print services; list filter. *Additional details* section on the phase 2 editors. Tests per document.
- **Depends on:** MST-8. **Effort / Who:** L, Claude alone.

#### MST-7. Features and modules created at runtime reach every store (§17)
- **What it is:** a new feature or module made by the platform administrator works in every firm, not just one store.
- **What gets built:** extend `backend/app/business/services/profile_replication.py` (profiles already replicate) to features and modules, reporting each store written or failed. Tests.
- **Effort / Who:** S, Claude alone.

#### MST-8. A firm configures its own custom fields (§16)
- **What it is:** a firm administrator adds fields to their own products and customers, without touching another firm's.
- **What gets built:** migration: nullable `firm_id` on `attribute_definitions` and `category_attribute_rules`, shared rows copied per firm, code unique per firm among live rows; `attribute_service.py` scoped to the caller's firm; two permission codes seeded and granted to `FIRM_ADMIN` with a migration; the tabs leave the platform view. Lifecycle guards are already built (B2). Integration test across two firms in `firm_shared`.
- **Depends on:** nothing. **Effort / Who:** M, Claude alone.

### Reports

#### RPT-1. Sales analysis, the rest (§62)
- **What it is:** filters on the screen, orders booked as a basis, margin, compare with last year, chart, export, saved layouts.
- **What gets built:** filter pickers and the rest in `desktop/lib/ui/sales/sales_analysis_page.dart` (the server already takes the filters); an orders basis and a margin figure (cost from dispatches, behind a cost permission) in `backend/app/sales_invoice/services/sales_analysis.py`; saved layouts per user (migration). Home gadgets stay with §49 (parked). Tests.
- **Effort / Who:** M, Claude alone.

#### RPT-2. Purchase analysis, the rest (§66)
- **What it is:** the same for purchases, plus the received and ordered bases, average rate and a rate trend per product.
- **What gets built:** the shared `AnalysisPage` widget gains the same; server bases over goods receipts and orders; a rate trend report. Tests.
- **Depends on:** RPT-1 (shared widget). **Effort / Who:** M, Claude alone.

### Platform

#### PLT-1. Bulk reject and multi-level approval (§56 A)
- **What it is:** reject many documents at once with a reason, and approval chains by amount.
- **What gets built:** *Reject* through `run_each` (`backend/app/document_framework/services/bulk_actions.py`) where a document has a reject transition; approval rules (document type, amount band, level 1-3, role) in a new table (migration), consulted by the approval services that already judge role limits; the pending-approvals list per user. Tests.
- **Depends on:** PLT-2 to tell the approver. **Effort / Who:** L, Claude alone.

#### PLT-2. Notifications: the bell (§55 S12)
- **What it is:** a bell on the phase 2 bar listing what waits for the user.
- **What gets built:** a notifications table per store (migration) and `GET /me/notifications` with mark-read; written by approvals waiting, refused messages, stock alerts; the desktop polls each minute; a bell in `desktop/lib/phase2/app_menu_bar.dart`. Tests.
- **Effort / Who:** M, Claude alone.

#### PLT-3. Trigram search (§56 C)
- **What it is:** the Ctrl+K search answering under a second on a large firm.
- **What gets built:** a migration enabling `pg_trgm` and GIN trigram indexes on the searched name and number columns (PostgreSQL only, skipped on SQLite), applied to every store; re-time with `scripts/time_routes.py`. Integration test that the index is used.
- **Effort / Who:** S, Claude alone.

#### PLT-4. GSTR-1 / 3B and outstanding under 3 s (§56 C)
- **What it is:** the month's returns and the receivables reports open in under 3 seconds on a big firm.
- **What gets built:** move GSTR-1 / 3B arithmetic from Python into grouped SQL in `gstr_service.py`; the outstanding reports read allocations grouped in SQL rather than per bill. Re-time on PERF01 (`docs/PERFORMANCE_AT_VOLUME.md`). Tests that figures are unchanged.
- **Effort / Who:** M, Claude alone.

#### PLT-5. Set-based back-dated carry (§56 C)
- **What it is:** an entry dated in the past updates later balances in one step, not month by month.
- **What gets built:** replace the loop in the journal engine's carry into later periods (`backend/app/finance/services/journal_engine.py`) with one set-based `UPDATE`; integration test on PostgreSQL.
- **Effort / Who:** M, Claude alone.

#### PLT-6. Retention on by default (§56 C)
- **What it is:** old login records, refresh tokens and tax logs are pruned automatically.
- **What gets built:** the installed server runs `agency-server purge-retention` daily (`backend/app/cli.py`), as the scheduled backup does; a firm or the platform can switch it off. `docs/RELEASE_BUILD.md` updated.
- **Effort / Who:** S, Claude alone.

#### PLT-7. D-PERF-1: 38 slow routes on WHOLE01
- **What it is:** some screens are slower than their target on a two-year firm.
- **What gets built:** re-time on an idle machine first (the run had 1.4 GB free); then the worst: `firm-profile-assignments` (15 s), `geo/localities` (9 s), `gst-returns/calendar` (4.8 s), `delivery-notes` (3.9 s), `balance-confirmations`, `control-accounts`, `goods-receipts`; `account-summaries` has no screen. Each fixed by grouping in SQL or paging; `quick-check` again.
- **Effort / Who:** M, Claude alone.

#### PLT-8. One search box on the audit trail (§31.17, rest)
- **What it is:** type part of a name or action and find the entries.
- **What gets built:** a `search` filter in `backend/app/common/audit/services/reader.py` across action, entity type, actor name and email (partial matching on action and entity is already built, #622); one box on `audit_log_page.dart`. Tests.
- **Effort / Who:** S, Claude alone.

#### PLT-9. Phase 1 leftovers (§31.11, §31.14, §31.15)
- **What it is:** three small loose ends found in manual testing.
- **What gets built:** (a) `test_desktop_document_payloads_are_accepted.py` reads the old dialogs; point it at the phase 2 editors and add the sales side (quotation, order, invoice, credit note); (b) credit note and debit note pickers show `Line 1` when a line has no description -- show product code and name; (c) the price list grid counts rate rows as products, and territory-scoped lists cannot be created on screen.
- **Effort / Who:** S, Claude alone.

#### PLT-10. The stray `installer/` folder (§3)
- **What it is:** an old, unused folder on the development machine.
- **What gets built:** it holds two small files from an early attempt, is ignored by git and exists only in the owner's checkout; delete it and the `/installer/` line in `.gitignore`. Nothing reads it.
- **Effort / Who:** S, Claude alone.

#### PLT-11. PAN reports (§53 item 4)
- **What it is:** lists of customers and suppliers with no PAN (they cost the higher TDS rate) and with a PAN that does not match their GSTIN.
- **What gets built:** two reports grouped in SQL over customers and vendors; entries in `report_catalog.dart`. The TDS registers already flag deductees with no PAN. No migration.
- **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A53): `app/common/pan_report.py`; `pan_problem` beside `settle_pan` in `app/core/validation/common.py` (one rule for the write check and the report); `GET /customers/reports/pan` (CUSTOMER_VIEW) and `GET /vendors/reports/pan` (VENDOR_VIEW); *Customer PAN check* and *Supplier PAN check* under Reports > Financial. Only the six columns shown are read per live party; the format check is a pattern, so it is applied to those values rather than in SQL. No migration. Tests in `test_pan_reports.py`.

### Messaging and integration

#### MSG-1. Share on WhatsApp by hand (§51 A2)
- **What it is:** a *WhatsApp* button opens WhatsApp at the party's number with the message typed, and saves the PDF to attach.
- **What gets built:** desktop only: build the `https://wa.me/<number>?text=` link, save the print PDF and open its folder, from the document bar in `desktop/lib/phase2/document_page.dart`; record the send on the timeline (A5 endpoint exists). Widget test.
- **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A56): *WhatsApp* on an approved invoice's selection bar (beside *Send*, `DOCUMENT_SEND`). The server composes the share (`GET /messaging/share/sales-invoices/{id}`: number as `wa.me` wants it, the firm's covering note, the UPI line where MSG-2 applies) and records it (`POST /messaging/shared`: *WhatsApp shared by hand to ...* on the timeline, never *sent*) -- the timeline needed a route of its own, since A5's writer only knew outbox rows. No account, switch or opt-in needed. The desktop saves the PDF to Downloads, opens the folder with it selected, and opens `wa.me`. `app/messaging/services/hand_share.py`, `desktop/lib/ui/workspace/whatsapp_share.dart`. No migration. Tests: `test_hand_share.py`, `whatsapp_share_test.dart`.

#### MSG-2. UPI QR on the invoice (§51 A3)
- **What it is:** the customer scans the bill and pays by UPI.
- **What gets built:** a UPI ID on firm settings (migration); a `upi://pay?pa=...&am=...&tn=...` QR for the amount due in `invoice_print_service.py` and the thermal print; skipped when no UPI ID is set. Tests.
- **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A55): the UPI ID is kept on the sales invoice's **print template** beside the bank details (`document_print_templates.upi_id`, migration 0240), typed under *Print settings* on the invoice screen and checked as `name@handle`. A bill that stands and still owes money prints *Scan to pay by UPI* -- a `upi://pay` QR (payee, amount, INR, the bill number as the note) with the amount and the UPI ID beside it -- in the A4 footer and under the total on the 80 mm roll. The amount is what is left after `settled_against`, so a part-paid bill asks only for the rest and a paid one prints none; a draft, a cancelled bill or a reference copy awaiting its IRN prints none. `app/sales_invoice/services/upi_qr.py`. Tests: `test_upi_qr.py`, `print_settings_test.dart`.

#### MSG-3. Payment reminders by hand (§51 A4)
- **What it is:** *Remind* on the overdue list and the customer statement sends the statement by email or WhatsApp.
- **What gets built:** *Remind* actions calling the existing send path (`desktop/lib/ui/settings/send_message_dialog.dart`, `backend/app/messaging`) with the statement PDF; respects *no reminders*. Tests.
- **Depends on:** MSG-1 for the WhatsApp half. **Effort / Who:** S, Claude alone.
- **Built 2026-10-03** (A57): *Remind* on the Customer Statement screen (the customer on show) and on an approved invoice's selection bar (its customer; chiefly from the Overdue view), `DOCUMENT_SEND`. It sends the customer's **statement of account** -- a new PDF, `GET /customers/{id}/statement/print` (`app/customers/services/statement_pdf.py`): the movement from the oldest unpaid bill to today, the closing balance, the bills unpaid with days overdue, and the UPI line where MSG-2 applies; figures from the statement and the ageing services. By **email**: `POST /messaging/remind` queues an outbox row (`MANUAL_REMINDER`, document `CUSTOMER_STATEMENT`) whose attachment the worker renders; needs messaging and email on. On **WhatsApp by hand**: `GET /messaging/share/customer-statements/{id}` plus MSG-1's flow, recorded in the customer's audit trail. *No reminders* and a customer who owes nothing are refused by name on both roads. The letter renderer gained tables (`LetterTable`). No migration. Tests: `test_reminders.py`, `remind_dialog_test.dart`, `whatsapp_share_test.dart`.

#### MSG-4. Send other documents by hand (§51)
- **What it is:** email the order, quotation, statement, receipt and purchase order, as the invoice already is.
- **What gets built:** extend the messaging send to each printable type (`backend/app/document_framework/services/printable_types.py` lists them) with a covering message per type; *Send* on each phase 2 document bar. Tests per type.
- **Effort / Who:** M, Claude alone.

#### MSG-5. Export to Tally (§55 G4)
- **What it is:** the firm's CA, who keeps the books in Tally, imports our vouchers and ledgers.
- **What gets built:** an export in TallyPrime's XML import format for a date range: ledgers (parties, accounts) and vouchers (sales, purchase, receipt, payment, journal, credit and debit notes) with GST details; a per-firm mapping of our accounts to the CA's ledger names; Reports > Export to Tally. No migration beyond the mapping. Tests on the XML shape.
- **Needs from the CA, before release:** import a sample into their Tally. **Effort / Who:** L, Claude alone.

---

## 5. Parked, waiting and unclear

### 5.1 Parked or waiting -- what unblocks each

| Ref | Item | What unblocks it |
| --- | --- | --- |
| §77 row 8, §55 M2 | Live e-invoice and e-way bill through Direct NIC or a GSP | The owner names the route and the first firm brings its credentials or GSP contract (section 2, item 1); offline upload is already built |
| §77 row 14 | Bill of supply | A go-live firm that sells exempt goods or is under composition (section 2, item 4) |
| §78 row 8, §68 row 13 | Import bill of entry | A go-live firm that imports |
| §51 B4 | Payment links | Owner's go-ahead and a Razorpay or Cashfree merchant account |
| A13 | Real messaging sends | Owner's SMTP, WhatsApp and SMS accounts to verify against |
| §2, §43 | Licensing; update delivery within the licence | Owner (B11, deferred) |
| §3, §47 | Clean-machine installer test; window icon | A spare PC; the `.ico` with the Jugnix rebrand (B10) |
| §71-73 | Sign-in and branding, menu layout, dialog review | Owner (B9, parked; branding after the trademark is filed) |
| §39, §42.6, §42.14, §48 | Field collections offline, salesman app, portals, phone layouts | Owner (B7): next phase, after go-live |
| §49 | Home gadgets catalogue | Owner (parked 2026-09-26) |
| §37 | Screens scoped to a financial year | Low priority; take up after go-live (lists already filter by date) |
| §5 | Navigation 2.0 pass | Superseded by phase 2's menu; close when §72 is decided |
| §40 | Hosting the logic for real protection | Only if a firm moves to hosted use |
| §33 | Customer groups beside the other masters | Built in phase 2 (Masters > Customer Groups, `customer_groups_page.dart`); close it |
| §76 | Routes with no screen | Built when a firm asks for each (pinned in `test_routes_have_a_caller.py`) |
| B8 later items | §42.15, §55 G11-13, N1, N2, N7-N9, §74 row 6 | Owner parked as "later" |
| §65 row 14, §69 row 11 | RFQ and quotation comparison | A go-live firm that asks (rated low for a distributor) |
| §68 row 12 | Rate contracts / blanket orders | A go-live firm that asks |
| §70 rows 9-10 | FIFO costing; warn on negative stock | Decided no (B4); closed |
| §53.1 | 26Q FVU text file | ACC-7 (challans recorded); then Claude builds it and the CA validates with the free NSDL FVU utility |
| A5, A8, A9, A20, A31 | Defaults to confirm | The firm's CA at hand-over |
| A43, A44, A45 | Built 2026-10-02 | Owner's OK |

### 5.2 Unclear -- resolved, with a recommendation

| Ref | Question | Finding | Recommendation |
| --- | --- | --- | --- |
| §16 | Are per-firm custom fields still wanted? | Lifecycle guards built; both decisions answered (B2); the `firm_id` and permission part is not built, so a shared-store firm's new field still lands on every firm in `firm_shared` | **Build it** as MST-8 before MST-6 |
| §36 | Tally XML import, given B3's field mapping? | B3 (built, #935) maps a file from any software onto our templates; Tally exports masters and outstanding to Excel | **Close the Tally XML import.** Keep MSG-5 (export *to* Tally), which is a different need |
| §42.4 | Is 194Q's threshold handled? | TDS is typed by hand per payment with its section (`backend/app/finance/tds.py`); nothing sums purchases per supplier or suggests the deduction | **Build ACC-8** |
| §53 item 4 | Are the PAN reports built? | The TDS registers flag a deductee with no PAN; no master-level list of missing or mismatched PANs exists | **Build PLT-11** (small) |
| §31.7 | Does a real interstate sale reach the IGST rule? | Yes now: the sales, order and quotation services pass `SALES_INTERSTATE` from `backend/app/tax/services/place_of_supply.py` when the states differ | **Close** |
| §31.3 | Document views show ids | The phase 2 editors show names; the old views are phase 1, which takes no new work | **Close** |
| §31.9 | No purchase invoice from the desktop | Built: `purchase_invoice_editor_phase2.dart` | **Close** |
| §31.11 | Sales-side payload guard | The guard exists but reads the phase 1 dialogs | **Fold into PLT-9** |
| §31.13 | Stock Ledger type filter | The list now holds the server's real types | **Close** |
| §31.14 | "Line 1" on return / note pickers | Still so on the phase 2 credit and debit note editors | **Fold into PLT-9** |
| §31.15 | Price-list count; territory price lists | Still open, cosmetic | **Fold into PLT-9** |
| Concurrency | Optimistic concurrency on UOM, tax and batch | Built 2026-08-22 (#115, #116): the routers publish `ETag` and accept `If-Match` | **Close** |

### 5.3 Listed as open, found built

- **§34 System-numbered stock movements** -- built as D-QA-16: transfers, write-offs, quarantine and adjustments draw `ST`, `WO`, `QR`, `ADJ` numbers (`backend/app/inventory/services/movement_numbering.py`); a typed reference is still accepted. BACKLOG §34 should be marked built.
- **§31.16** -- a refused password shows each rule broken (#623).
- **§31.17** -- the action and entity filters match a part of the name (#622); only the single free-text box is left (PLT-8).
- **§8 slim rows** -- the pending / overdue / completed reports now answer register records (`GoodsReceiptRegisterRecord`, `SalesInvoiceRegisterRecord` and siblings); the two goods-receipt line reports answer lines, which is their subject.
- **§31.7** and **concurrency** -- section 5.2.

---

## 6. Build order in waves

Every item is Claude alone, so the waves are ordered by **go-live value**:
what a distributor's first month touches first (billing, money, GST, stock),
then what the second month needs, then the larger features. Days are rough:
S = 1, M = 3.5, L = 8.

### Wave 1 -- small, high go-live value (about 34 days)

GST and money first: GST-1, GST-2, GST-3, ACC-3, ACC-5, ACC-6, BUY-17,
PLT-11. Then billing and stock on the counter: SEL-1, MSG-2, MSG-1, MSG-3,
STK-17, STK-18, STK-10, STK-3, STK-13, STK-11, STK-9, STK-16, ACC-12. Then
masters and offers: MST-5, MST-4, MST-7, SEL-5, SEL-8, SEL-7, SEL-4, BUY-15.
Then platform: PLT-3, PLT-6, PLT-8, PLT-9, PLT-10.
**34 small items.** (BUY-5 and BUY-6, also small, wait for BUY-4 and go in wave 2.)

### Wave 2 -- medium (about 170 days)

In order: **money and tax** -- ACC-8 (194Q), ACC-7 (challans), ACC-2 (PDC),
ACC-4, GST-5, GST-7, GST-4, GST-8, ACC-11, ACC-9, ACC-10; **selling** --
SEL-9 (special rates and levels), SEL-12 (counter billing), SEL-14, SEL-13,
SEL-15, SEL-2, SEL-3, SEL-6, MSG-4; **buying** -- BUY-3, BUY-4, BUY-5,
BUY-6, BUY-10, BUY-8, BUY-9, BUY-11, BUY-1, BUY-2, BUY-7, BUY-12, BUY-13,
BUY-14; **stock** -- STK-7, STK-8, STK-5, STK-4, STK-6, STK-12, STK-14;
**masters** -- MST-8, MST-1, MST-2; **reports and platform** -- RPT-1,
RPT-2, PLT-2, PLT-4, PLT-5, PLT-7.
**48 medium items**, plus the two small ones BUY-5 and BUY-6.

### Wave 3 -- large (about 96 days)

ACC-1 bank reconciliation; STK-1 stock transfer document, then STK-2 branch
GSTINs (before any firm with branches in two states); SEL-11 claims to the
principal (after MST-1); BUY-16 landed cost; GST-6 filed returns and
amendments; PLT-1 multi-level approval (after PLT-2); MST-6 document fields
(after MST-8); SEL-10 enquiries; STK-15 kits (after STK-4); MSG-5 Tally
export; MST-3 duplicate merge.
**12 large items.**

**Total:** about 300 working days of build at one item per session, before
review and the owner's test pass. Wave 1 alone closes 34 rows in about seven
weeks of sessions, and nothing in it waits on the owner.
