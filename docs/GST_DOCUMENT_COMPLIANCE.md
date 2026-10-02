# GST documents -- what the law needs from the sales and purchase chains

Which document GST requires for each movement of goods and each correction to
a sale, what the platform already does about it, and what it must change. The
work is `docs/BACKLOG.md` §77 (HIGH PRIORITY).

Written 2026-10-02 from a discussion with the owner, checked against the code
on that date. **The rules below are a summary to confirm with the firm's
chartered accountant before building**, not legal advice; figures (thresholds,
limits) change, so each one carries the date it was read.

The chain this applies to is described in `docs/SALES_TO_RECEIPT_FLOW.md`; the
rules about what a firm may skip are in `docs/SALES_CHAIN_RULES.md`.

## 1. The rules

### 1.1 Which document for which movement

| Situation | Document | Law |
| --- | --- | --- |
| Goods sold | **Tax invoice**, issued **at or before the removal** (dispatch) of the goods | CGST Act s.31(1) |
| Goods leave with no sale yet -- on approval, job work, stock transfer inside one GSTIN, supply where the quantity is not known at removal | **Delivery challan**; the tax invoice follows when the sale happens | CGST Rules r.55 |
| Goods returned, price reduced, discount after the sale | **Credit note** against the original invoice | s.34(1) |
| Price raised after the sale | **Debit note** against the original invoice | s.34(3) |
| Exempt goods, or a composition-scheme firm | **Bill of supply** instead of a tax invoice | s.31(3)(c) |
| Transfer between two GSTINs of the same business (two states) | **Tax invoice** -- a taxable supply | Sch. I |

**A credit note never sends goods.** It only corrects a sale already invoiced.

### 1.2 Credit and debit notes

- Must name the invoice they correct.
- A credit note for a year's supplies must be issued by **30 November** after
  that financial year ends (or the annual return date, if earlier); after that
  the tax cannot be reduced by it.

### 1.3 Numbering

- One series per financial year, restarting each **1 April**, for invoices,
  credit notes and debit notes.
- Up to **16 characters**, unique within the financial year (r.46(b)).

### 1.4 E-invoicing (read 2026-10-02)

| Rule | Position |
| --- | --- |
| Who | A firm whose aggregate annual turnover crossed **₹5 crore** in any year since 2017-18 |
| What | **B2B** tax invoices, credit notes and debit notes, and exports. B2C is excluded |
| How | The document is reported to the IRP; it returns an **IRN** and a **signed QR**, both printed |
| Without it | A B2B invoice from such a firm is not a valid invoice; the buyer loses input credit |
| Deadline | Firms at **₹10 crore or more**: within **30 days** of the document date, or the IRP refuses it |
| Cancellation | Within **24 hours** on the IRP; after that, a credit note |

### 1.5 E-way bill (read 2026-10-02)

- Needed when goods worth more than **₹50,000** move (some states set their
  own limit for movement inside the state).
- Applies to **every** firm, whether or not it e-invoices -- and to non-sale
  movements on a challan too (stock transfer, job work).
- A firm that e-invoices can raise it from the IRN; one that does not raises it
  from the invoice or challan directly.

## 2. What the platform does today (2026-10-02)

| Area | State |
| --- | --- |
| Tax invoice, credit note, delivery challan, proforma | Built |
| Credit note names the invoice and the line it corrects | Built (`credit_notes.sales_invoice_id`, per line) |
| Debit note **to a supplier** | Built (`app/debit_note`, §55 G8) |
| Debit note **to a customer** | Built 2026-10-02 (`app/customer_debit_note`, §77 row 5): names the invoice and lines, taxed at the invoice line's rate, owed on the invoice, GSTR-1 note type D, added to 3B 3.1(a) |
| Numbering per financial year | Built (`include_financial_year`, `auto_reset`) |
| 16-character limit on a GST document number | **Not checked** |
| Transport details on the delivery note (transporter, GSTIN, mode, LR, distance) | Built (§67 row 5) |
| IRN, acknowledgement and signed QR on the printed invoice, credit note and debit note (rule 48(4)) | Built 2026-10-02 (§77 row 11); only a REGISTERED registration prints; notes printable since the same change |
| E-invoice of credit and debit notes | Built 2026-10-02 (§77 row 4): CRN and DBN, referring to the invoice (`RefDtls.PrecDocDtls`), on the firm's route -- sandbox, or the offline bulk upload with the invoices |
| E-way bill without an IRN, on a delivery note, recorded by hand; the firm's limit and a due list | Built 2026-10-02 (§77 rows 9-10): from the invoice where the firm need not e-invoice it, from the challan where no invoice bills it (supply type from the challan reason: sale 1, line sales 10, job work 4, others 8), or raised on the portal and its 12-digit number recorded. `gst_compliance_settings.eway_bill_limit` (₹50,000 unless the firm sets its state's) drives the due list and the prompt |
| E-invoice: IRN, QR, 24-hour cancellation, e-way bill from the IRN | Built (`app/einvoice`). Each firm chooses its route (A42): **Sandbox** (rehearsal) or **Offline** -- export the portal's bulk-upload JSON, upload it by hand, import the result. Direct NIC API and GSP adapters to follow |
| E-invoice live through a GSP | **Not built** (§55 M2) |
| E-invoice for credit and debit notes | **Not built** -- registration links to `sales_invoices` only |
| Whether a firm must e-invoice, and the 30-day rule | **Recorded, not yet enforced** (#903): *e-invoicing applies from* and *30-day rule from* are dated firm settings (Settings > Tax > GST documents, `TAX_MANAGE_SETTINGS`); nothing yet refuses an unregistered B2B invoice or a late registration |
| E-way bill for a firm that does not e-invoice | **Still not possible** -- generation needs a registered IRN (A35 decides otherwise; not yet built) |
| E-way bill for a challan with no invoice (stock transfer, job work) | **Not possible** |
| Dispatch before the invoice exists | **Judged by a firm policy** (#903): OFF, WARN (the default) or BLOCK, applied to a Sale note (and a van or route sale only if the firm says *route sales need the invoice first*) dispatched by hand with no approved invoice; the warning is recorded on the dispatch and names CGST s.31. A bill that dispatches the note it raised is never judged (`GstComplianceService.dispatch_check`) |
| *Dispatch and invoice* | **Built** (#903): `POST /api/v1/delivery-notes/{id}/dispatch-and-invoice` raises and approves the invoice in the same transaction as the dispatch |
| Why a challan went out without an invoice | **Recorded and printed** (#903): every delivery note carries `challan_reason` -- Sale (default), Van or route sale, Supply on approval, Quantity not known, Job work, Other with a note |
| Credit note after 30 November | **Not checked** |
| Bill of supply | **Not built** |

## 3. The sales flow, read against the rules

The chain today (`docs/SALES_TO_RECEIPT_FLOW.md`):

```
Quotation → Sales Order → Delivery Note → DISPATCH → Sales Invoice → Receipt
                 │              │             │              │
             stock reserved   challan      goods leave    customer owes
```

**The legal moment is DISPATCH.** For a sale, the tax invoice must exist at or
before it. The chain puts the invoice *after* dispatch, and §58 (one invoice
for several delivery notes) deliberately bills a week of dispatches at once.
That is common practice and what Tally, Zoho and ERPNext allow, but for a
taxable sale of goods it is only right when the challan had a reason in 1.1.
**Decision for the owner and the firm's CA** (open item 1 below).

The flow that satisfies the rules, by kind of firm:

### Flow A -- invoice at dispatch (every firm can use it; the safe default)

```
Order (approve: stock reserved)
  → Invoice (approve)            ← the legal document, before the goods move
      → [e-invoice: IRN + QR]    ← if the firm must e-invoice, before printing
      → [e-way bill]             ← if goods worth > ₹50,000
  → Dispatch on the delivery note, which names the invoice
  → Receipt
```

The platform already supports this order: a firm with the delivery-note stage
switched off has the invoice dispatch the goods itself
(`sales_workflow_settings`), and `delivery_notes.raised_by_sales_invoice_id`
records a note raised by a bill.

### Flow B -- challan first, invoice later (only with a reason)

```
Order → Delivery note with a REASON (on approval / job work / transfer / quantity unknown)
          → [e-way bill from the challan if > ₹50,000]
          → Dispatch
      → Invoice when the sale is settled (one or several challans, §58)
          → [IRN + QR if e-invoicing]
      → Receipt
```

### Corrections after the sale

```
Goods back or price down  → Credit note against the invoice → [IRN if e-invoicing] → by 30 Nov
Price up                  → Debit note against the invoice  → [IRN if e-invoicing]
IRN wrong, < 24 hours     → Cancel on the IRP, cancel the invoice, raise a new one
IRN wrong, > 24 hours     → Credit note (cannot cancel)
```

## 4a. The redesigned sales flow (decided 2026-10-02, OWNER_DECISIONS A35)

Owner, 2026-10-02: "follow GST guidelines ... refer market standards and
redesign sales flow". Decided by Claude against what Zoho Books, ERPNext
(India Compliance) and Tally do; to be confirmed with the firm's CA.

**What the market does.** Zoho Books keeps the delivery challan for goods that
cannot be invoiced yet -- supply on approval, job work, and the like -- and
converts it to an invoice later. ERPNext raises an e-way bill from a delivery
note only for goods moving without an invoice (job work, transfers), and from
the invoice otherwise. Tally records dispatch details on the invoice itself.
None of them blocks dispatching a sale before the invoice; all of them make
the invoice-first path the easy one.

**The flow, after the change:**

```
Order (approve: stock reserved)
  ├─ SALE ──► Invoice (approve) ──► [IRN + QR] ──► [e-way bill > limit] ──► Dispatch
  │              or, on the delivery note: "Dispatch and invoice" -- raises and
  │              approves the invoice in the same action, dated the dispatch
  │
  └─ ON APPROVAL / JOB WORK / STOCK TRANSFER / QUANTITY NOT KNOWN / OTHER
           ──► Delivery note with that reason ──► [e-way bill from the note]
           ──► Dispatch ──► Invoice later (one or several notes, §58)
```

**The rules:**

1. **Every delivery note says why it goes out**: *Sale* (the default),
   *Van or route sale*, *On approval*, *Quantity not known*, *Job work*,
   *Other* (with a note). The reason prints on the challan. A van or route
   sale is judged like a sale only if the firm says its CA wants invoices
   before the van leaves; otherwise each shop is invoiced at delivery.
2. **A Sale note dispatched with no approved invoice** is judged by a firm
   policy: **warn** (default) or **block**. The warning names the rule
   (CGST s.31) and offers *Dispatch and invoice*. Warn by default for the same
   reason credit limits warn: a firm moving to the rule should not find its
   counter stopped on the first day.
3. **"Dispatch and invoice"** on a Sale note raises the invoice from the note
   and approves it in the same transaction as the dispatch, so the invoice
   exists at removal. It is the compliant path in one click and is what makes
   *block* livable.
4. **One invoice for several notes (§58)** stays. For notes with a non-sale
   reason it is the expected way to bill; for Sale notes the dispatch already
   warned.
5. **E-way bill** comes from the invoice when there is one, and from the
   delivery note only when there is none (ERPNext's rule) -- never both for
   the same goods. It no longer needs an IRN. Offered when the consignment is
   worth more than the firm's limit (₹50,000 by default; the firm sets its own,
   because states change theirs and a shipped table would go stale).
6. **E-invoicing and the 30-day rule are firm settings with a date from**, set
   by the firm administrator -- the firm knows its turnover; the platform does
   not.
7. **Credit and debit notes** follow the invoice: registered for an IRN where
   e-invoicing applies, and a credit note after 30 November of the next year
   warns, naming the date.

**What does not change:** quotation and order; stock reserved at order
approval; stock leaving at dispatch; the stage switches
(`sales_workflow_settings`) -- a firm with the delivery-note stage off already
has the invoice dispatch the goods, which is Flow A.

**Still needed from the owner:** which GSP (row 8), and whether any firm
today is composition or sells exempt goods (row 14 is later unless one is).

Sources (read 2026-10-02):
[Zoho -- delivery challan](https://www.zoho.com/en-in/pos/resources/help/delivery-challan.html),
[Zoho Books API -- delivery challans](https://www.zoho.com/books/api/v3/delivery-challans),
[India Compliance (ERPNext) -- generating an e-Waybill](https://docs.indiacompliance.app/docs/ewaybill-and-einvoice/generating_e_waybill),
[ERPNext -- India Compliance app](https://docs.frappe.io/erpnext/india-compliance-app).

## 4. What must change -- backlog §77

Numbered as in §77. Priority within it: **P1** before any e-invoicing firm
goes live; **P2** for every firm; **P3** completes the picture.

| # | Change | Pri |
| --- | --- | --- |
| 1 | **Firm GST settings:** *e-invoicing applies* (turnover crossed ₹5 cr) and *30-day rule applies* (₹10 cr or more), dated, set by the firm administrator -- **built 2026-10-02 (#903)**, recorded only until rows 6 and 7 read them | P1 |
| 2 | **Invoice before dispatch:** a per-firm policy -- *off*, *warn* (default) or *block* -- when a delivery note is dispatched with no invoice and no challan reason, with *Dispatch and invoice* -- **built 2026-10-02 (#903)** | P1 |
| 3 | **Challan reason** on the delivery note: sale (invoice follows at once), on approval, job work, stock transfer, quantity not known, other; printed on the challan -- **built 2026-10-02 (#903)** | P1 |
| 4 | **E-invoice credit notes and debit notes**, not only invoices: a document type on the registration | P1 |
| 5 | **Debit note to a customer** (§67 row 7) -- **built 2026-10-02** | P1 |
| 6 | **Refuse to print or send a B2B invoice without an IRN** where e-invoicing applies; a B2C invoice is unaffected | P1 |
| 7 | **30-day check:** a list of documents not yet registered with days left; warn near the limit; refuse after it with the portal's reason | P1 |
| 8 | **Live e-invoice and e-way bill through a GSP** (§55 M2), with duplicate-IRN handling | P1 -- needs a GSP contract |
| 9 | **E-way bill without an IRN:** from the invoice or the delivery challan, so firms below ₹5 cr and non-sale movements can raise one | P2 |
| 10 | **₹50,000 prompt:** offer the e-way bill when the goods value crosses the limit; state-wise limit as a setting | P2 |
| 11 | **IRN, acknowledgement and signed QR on the printed invoice, credit and debit note** | P2 |
| 12 | **Credit note after 30 November** of the following year: warn, naming the date | P3 |
| 13 | **16-character check** on GST document numbering rules | P3 |
| 14 | **Bill of supply** for exempt goods and composition firms | P3 |

Rows 1 to 3 and 5 are built; 4 and 6 to 14 are not. **Order of work:** 2, 3 and 1 (small, and they settle the flow) → 5 and 4 →
9, 10, 11 → 6, 7 → 8 once a GSP is chosen → 12-14.

## 5. Decisions

1. **Dispatch before invoice:** warn by default, block by firm choice;
   consolidated billing (§58) stays -- section 4a, A35. Confirm with the CA.
2. **Which GSP** for live e-invoice and e-way bill (§55 M2) -- **decided as a
   framework (A42)**: no single GSP. Each firm chooses its route in GST
   Documents settings: Sandbox, **Offline JSON** (free, built 2026-10-02),
   then **Direct NIC** (the firm's own API credentials) and one GSP adapter
   (Masters India or ClearTax), more as customers ask. Which GSP comes first
   follows the first customer who wants one.
3. **Who sets "e-invoicing applies":** the firm administrator, dated -- A35.
4. **State-wise e-way bill limits:** each firm sets its own, default ₹50,000
   -- A35.
5. **Bill of supply:** later, unless the owner names a composition or exempt
   firm today -- **owner**.

## 6. Purchases under GST -- backlog §78

Owner, 2026-10-02: "same way regarding purchases ... as per industry
standards what we need to change ... what we can configure, compare with all
other apps". Checked against the code on that date; to confirm with the CA.

### 6.1 The rules

| Rule | What it says | Law |
| --- | --- | --- |
| Blocked credit | No input credit on motor vehicles (with exceptions), food and catering, club membership, personal use, gifts and free samples, goods lost or destroyed; the tax is part of the cost. Reported as a permanent reversal | s.17(5); 3B 4(B)(1) |
| Supplier type | Only a regular registered supplier's tax invoice gives credit. A composition supplier issues a bill of supply with no tax; an unregistered one charges none (reverse charge aside) | s.16(2), s.10 |
| Supplier filed it | Credit only on what the supplier reported (GSTR-1, seen in GSTR-2B) | s.16(2)(aa) |
| 180 days | Supplier not paid (value plus tax) within 180 days of the bill: reverse the credit on the unpaid part, with interest; claim it back when paid | r.37; 3B 4(B)(2) and 4(D)(1) |
| Supplier's IRN | A supplier past ₹5 crore must e-invoice; a B2B bill from them without an IRN is not a valid invoice | r.48(4) |
| Inward e-way bill | Goods over ₹50,000 travel with one; buying from an unregistered supplier, the buyer raises it | r.138 |
| Time limit | A year's credit is claimed by 30 November after it ends | s.16(4) |

### 6.2 Today, and what other products do

| Control | Here today | Zoho Books | ERPNext (India Compliance) | TallyPrime |
| --- | --- | --- | --- | --- |
| Reverse charge with self-invoice | **Built** (§68 row 8) | Yes | Yes | Yes |
| Debit note, supplier's credit note | **Built** | Yes | Yes | Yes |
| Credit per bill line: eligible / blocked 17(5) / ineligible other | **Built 2026-10-02** (#905; was D-TAX-1) | Yes, per bill line ("Eligible for ITC") | Yes, an ineligibility reason on the bill | Yes, by ledger and voucher |
| Supplier GST treatment (regular / composition / unregistered / overseas / SEZ) | **Built 2026-10-02** (§78 row 2, A37) | Yes | Yes | Yes (registration type) |
| GSTR-2B matching | **Built 2026-10-02** (§78 row 3) | Yes | Yes (purchase reconciliation) | Yes |
| 180-day reversal | **Built 2026-10-02** (§78 row 4; Off / Report / Report and post, reclaim on payment) | Not verified | Not verified | Not verified |
| Supplier IRN on the bill | **No** | Not verified | Not verified | Not verified |
| E-way bill number on the receipt | **No** (vehicle only) | Yes (on bills) | Yes (purchase receipt) | Yes |

"Not verified" means no source was read for it on this date, not that the
product lacks it.

### 6.3 What changes, and what each firm configures

| # | Change | Configurable | Default | Pri |
| --- | --- | --- | --- | --- |
| 1 | **Credit eligibility per bill line**: Eligible, Blocked (17(5)), Ineligible (other). Defaults from the product's or expense account's setting, then from a tax rule's *Input credit blocked*, and can be changed on the line. Blocked or ineligible tax is added to the cost of the goods or expense, not to input tax, and 3B shows it as a permanent reversal. Fixes D-TAX-1 | Per product and per expense account | Eligible | P1 |
| 2 | **Supplier GST treatment**: Regular, Composition, Unregistered, Overseas, SEZ, as customers already have. A composition or unregistered supplier's bill charges no tax (reverse charge aside) and gives no credit | Per supplier | Regular if a GSTIN is on file, else Unregistered | P1 |
| 3 | **GSTR-2B matching**: import the 2B file from the portal; match by supplier GSTIN, bill number and date, and amounts within a tolerance; list Matched, Different, In 2B only, In books only | Tolerance per firm; and whether 3B claims **all** bills (as today) or **only matched** ones | ₹1; all bills, with the unmatched listed | P1 |
| 4 | **180-day check**: a list of bills unpaid past 180 days with the credit to reverse; the reversal posted on request, and the reclaim when paid | Off / Report / Report and post | Report | P2 |
| 5 | **Supplier's IRN** on the bill, and a flag on the supplier that it e-invoices; warn when that supplier's bill has none | Off / Warn | Warn | P2 |
| 6 | **E-way bill number on the goods receipt**, asked for above the firm's limit (the same setting as sales, §77 row 10) | Limit per firm | ₹50,000 | P2 |
| 7 | **30 November warning** on a bill entered after its year's credit can be claimed | -- | On | P3 |
| 8 | **Import bill of entry** (IGST on imports) | -- | -- | P3 (§68) |
| 9 | **Common credit reversal** for a firm with exempt sales | -- | -- | P3 |

**Order:** 1 (it overstates credit today) → 2 → 3 → 4, 5, 6 → 7-9.

**Decided by Claude** (OWNER_DECISIONS A36), by the products above: the
eligibility lives on the line with a default from the master, as Zoho and
ERPNext keep it; 3B keeps claiming every bill by default and lists what 2B
does not show, because blocking credit on a supplier's late filing would cost
the firm money for the supplier's mistake -- a firm whose CA wants only
matched credit switches it.

## Sources (read 2026-10-02)

- [Tally -- e-invoicing rules in India, 2026](https://tallysolutions.com/accounting/e-invoicing-rules-in-india/)
- [ClearTax -- GST changes from April 2026](https://cleartax.in/s/gst-changes-from-april-2026)
- [GimBooks -- the ₹5 crore e-invoice rule, 2026](https://www.gimbooks.com/blog/5-crore-e-invoice-turnover-rule-2026/)
- [The e-invoice 30-day reporting rule](https://righttoinformation.wiki/gst-e-invoice-30-day-reporting-time-limit-india)
- [Zoho Books -- a bill on which ITC cannot be claimed](https://www.zoho.com/in/books/kb/gst/my-vendor-has-issued-a-bill-for-which-i-cannot-claim-itc.html)
- [Zoho Books -- composition scheme FAQ](https://www.zoho.com/in/books/gst/faq/composition-scheme.html)
- [TallyPrime -- reconciling GSTR-2B](https://help.tallysolutions.com/tally-prime/gstr-2b/india-gst-status-gstr-2b-reconciliation-tally-2/)
- [ClearTax -- ITC reversal](https://cleartax.in/s/itc-reversal-gst)
- [Rule 37: the 180-day reversal](https://fillgst.com/guides/rule-37-itc-reversal)
