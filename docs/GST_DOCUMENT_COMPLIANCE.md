# GST documents -- what the law needs from the sales chain

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
| Debit note **to a customer** | **Not built** (§67 row 7) |
| Numbering per financial year | Built (`include_financial_year`, `auto_reset`) |
| 16-character limit on a GST document number | **Not checked** |
| Transport details on the delivery note (transporter, GSTIN, mode, LR, distance) | Built (§67 row 5) |
| E-invoice: IRN, QR, 24-hour cancellation, e-way bill from the IRN | Built, **sandbox only** (`app/einvoice`) |
| E-invoice live through a GSP | **Not built** (§55 M2) |
| E-invoice for credit and debit notes | **Not built** -- registration links to `sales_invoices` only |
| Whether a firm must e-invoice, and the 30-day rule | **Not recorded** -- any firm can register, none is required to |
| E-way bill for a firm that does not e-invoice | **Not possible** -- generation needs a registered IRN |
| E-way bill for a challan with no invoice (stock transfer, job work) | **Not possible** |
| Dispatch before the invoice exists | **Allowed without question** (the delivery-note stage) |
| Why a challan went out without an invoice | **Not recorded** |
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
| 1 | **Firm GST settings:** *e-invoicing applies* (turnover crossed ₹5 cr) and *30-day rule applies* (₹10 cr or more), dated, set by the firm administrator | P1 |
| 2 | **Invoice before dispatch:** a per-firm policy -- *warn* (default) or *block* -- when a delivery note is dispatched with no invoice and no challan reason | P1 |
| 3 | **Challan reason** on the delivery note: sale (invoice follows at once), on approval, job work, stock transfer, quantity not known, other; printed on the challan | P1 |
| 4 | **E-invoice credit notes and debit notes**, not only invoices: a document type on the registration | P1 |
| 5 | **Debit note to a customer** (§67 row 7) | P1 |
| 6 | **Refuse to print or send a B2B invoice without an IRN** where e-invoicing applies; a B2C invoice is unaffected | P1 |
| 7 | **30-day check:** a list of documents not yet registered with days left; warn near the limit; refuse after it with the portal's reason | P1 |
| 8 | **Live e-invoice and e-way bill through a GSP** (§55 M2), with duplicate-IRN handling | P1 -- needs a GSP contract |
| 9 | **E-way bill without an IRN:** from the invoice or the delivery challan, so firms below ₹5 cr and non-sale movements can raise one | P2 |
| 10 | **₹50,000 prompt:** offer the e-way bill when the goods value crosses the limit; state-wise limit as a setting | P2 |
| 11 | **IRN, acknowledgement and signed QR on the printed invoice, credit and debit note** | P2 |
| 12 | **Credit note after 30 November** of the following year: warn, naming the date | P3 |
| 13 | **16-character check** on GST document numbering rules | P3 |
| 14 | **Bill of supply** for exempt goods and composition firms | P3 |

**Order of work:** 2, 3 and 1 (small, and they settle the flow) → 5 and 4 →
9, 10, 11 → 6, 7 → 8 once a GSP is chosen → 12-14.

## 5. Decisions

1. **Dispatch before invoice:** warn by default, block by firm choice;
   consolidated billing (§58) stays -- section 4a, A35. Confirm with the CA.
2. **Which GSP** for live e-invoice and e-way bill (§55 M2) -- **owner**.
3. **Who sets "e-invoicing applies":** the firm administrator, dated -- A35.
4. **State-wise e-way bill limits:** each firm sets its own, default ₹50,000
   -- A35.
5. **Bill of supply:** later, unless the owner names a composition or exempt
   firm today -- **owner**.

## Sources (read 2026-10-02)

- [Tally -- e-invoicing rules in India, 2026](https://tallysolutions.com/accounting/e-invoicing-rules-in-india/)
- [ClearTax -- GST changes from April 2026](https://cleartax.in/s/gst-changes-from-april-2026)
- [GimBooks -- the ₹5 crore e-invoice rule, 2026](https://www.gimbooks.com/blog/5-crore-e-invoice-turnover-rule-2026/)
- [The e-invoice 30-day reporting rule](https://righttoinformation.wiki/gst-e-invoice-30-day-reporting-time-limit-india)
