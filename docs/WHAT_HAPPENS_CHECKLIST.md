# What happens when you… — a checklist

For each important action: what it changes, where to see the change on screen,
and what refuses it. Use it while testing (did everything that should move,
move — and nothing else?) and when explaining the product.

Sources: [`SALES_TO_RECEIPT_FLOW.md`](SALES_TO_RECEIPT_FLOW.md) and
[`PURCHASE_TO_PAYMENT_FLOW.md`](PURCHASE_TO_PAYMENT_FLOW.md), both driven
against a running backend, plus the manual test plan run of sections 9–13
(2026-09-13/14). Account numbers are the seeded chart.

## How to check any row

| To see | Open |
| --- | --- |
| Stock: on hand, reserved, available | **Inventory → Inventory** (the product's row, per warehouse) |
| Stock movements | **Inventory → Stock Ledger** / **Transactions** |
| The journal an action posted | **Finance → Journal Entries** → search the document number → **View** ("posted by <module>") |
| What a customer owes | **Masters → Customers** → the customer → Outstanding; **Statements** for the story |
| What a supplier is owed | **Masters → Vendors**; **Reports → Financial → Vendor outstanding** |
| Whether the books still agree | **Finance → Trial Balance** → the period → chip **Balanced** |
| Who did it and when | **Settings → Audit Logs** |

**Rule of thumb:** only a handful of actions move stock or money. Everything
else — raising, editing, sending, approving a delivery note — writes history
(an audit row and a lifecycle event) and nothing more.

---

## Selling

| Action | Status | Stock | Journal (Dr / Cr) | Customer balance | Also | Refused when |
| --- | --- | --- | --- | --- | --- | --- |
| Raise / send / accept a **quotation** | DRAFT → SENT → ACCEPTED | — | — | — | Tax is priced, nothing posts | Expired (`valid_until` passed) |
| **Convert** quotation to order | Quotation converted; order DRAFT | — | — | — | Order is priced again at its own date | Already converted ("already became SO-…") |
| Create / edit a **sales order** | DRAFT (editing an approved one returns it to DRAFT) | — | — | — | Promotions and coupons priced (claim PENDING) | — |
| **Approve** the order | APPROVED | **Reserved** up, **available** down, on hand unchanged | — | — | Credit assessed; promotion claim becomes CLAIMED | Credit policy **BLOCK** over the limit (message names the %); offer or coupon used up; not a draft |
| **Hold** / release the order | Flag only — status kept | Stays reserved | — | — | Delivery notes refused while held | — |
| **Cancel** the order | CANCELLED | Reservation **released** | — | — | Promotion claims reversed | Already closed/cancelled |
| Raise / approve a **delivery note** | DRAFT → APPROVED | — | — | — | — | Order on hold; order not approved |
| **Dispatch** the delivery note | DISPATCHED; order → PARTIALLY_DELIVERED / DELIVERED | Reservation released, **on hand down** | Dr 5200 Cost of Goods Sold / Cr 1200 Inventory (at moving average) | — | — | Available stock short; no open period |
| **Cancel** a delivery note | CANCELLED | — | — | — | — | Already DISPATCHED / COMPLETED / CLOSED |
| Raise a **sales invoice** (draft) | DRAFT | — | — | — | Tax breakup stored for reprint | Billing more than was dispatched |
| **Approve** the invoice | APPROVED | — (stock left at dispatch) | Dr 1100 Trade Receivables / Cr 4000 Sales + Cr 2200 Output Tax | **Up** by the grand total | Loyalty points earned (if scheme on): Dr 5700 Loyalty Expense / Cr 2600 Loyalty Payable; appears in GST Returns | Credit BLOCK; closed period; missing control account |
| **Cancel** an approved invoice | CANCELLED | — | Mirror of the approval journal | **Down** by the grand total | Drops out of GST Returns | Money applied from a receipt; a live credit note or sales return; loyalty points spent on it; registered with the tax authority (message names each) |
| **Record a receipt** | Receipt POSTED | — | Dr 1010 Bank (or Cash) / Cr 1100 Trade Receivables | **Down**; excess over what is owed becomes unapplied **advance** | TCS if applicable (next row); commission on collected basis counts it | Allocations above what an invoice owes |
| …with **TCS** due (buyer past the threshold) | Register row COLLECTED | — | Separate entry `TCS-RC-…`: Dr 1100 Trade Receivables / Cr 2500 TCS Payable | Falls by receipt **less** the TCS | 0.1% with PAN, 1% without, on the part above the threshold | — |
| **Apply an advance** to an invoice | — | — | **None** (the receipt already posted) | Only the advance part moves | — | More than the unapplied advance |
| **Reverse** a receipt | Reversed | — | Mirror journal | Put back by the stored amounts | Allocations stop clearing | — |
| **Refund** an advance | Refund POSTED | — | Dr 1100 Trade Receivables / Cr 1010 Bank | Advance down | — | More than the advance |
| **Redeem loyalty points** on a bill | — | — | Dr 2600 Loyalty Payable / Cr 1100 Trade Receivables | **Down** (settles part of the bill, tax unchanged) | Points balance down | More points than held |
| **Credit note** approve | APPROVED | — | Dr 4100 Sales Returns + Dr 2200 Output Tax / Cr 1100 Trade Receivables | **Down** | Lands in GST Returns CDNR in the month issued | More than the invoice line's charged value less earlier credits |
| **Sales return** complete | COMPLETED | **On hand up** (goods back) | Two entries: Dr 4100 Sales Returns + Dr 2200 Output Tax / Cr 1100; and Dr 1200 Inventory / Cr 5200 COGS | **Down** | — | More than was delivered |
| **Proforma** issue | ISSUED | — | **None, by design** | — | Own PI number series | Order not approved |
| **E-invoice** register / e-way bill | REGISTERED (SANDBOX) | — | — | — | Reference `SBX…` — nothing is filed | No GSTIN / HSN (named) |

## Buying

| Action | Status | Stock | Journal (Dr / Cr) | Supplier balance | Refused when |
| --- | --- | --- | --- | --- | --- |
| Raise / submit / **approve** a purchase order | DRAFT → SUBMITTED → APPROVED | — | — | — | Approve before submit ("Submit the order first") |
| Raise a goods receipt (draft) | DRAFT | — | — | — | Order not approved |
| **Complete** the goods receipt | COMPLETED; order → PARTIALLY_RECEIVED / RECEIVED | **On hand up** | Dr 1200 Inventory / Cr 2300 Goods Received Not Invoiced (cost, no tax) | — | — |
| **Cancel** a completed receipt | CANCELLED | Stock back off | Reversal at the moving average; gap to 5400 Purchase Price Variance | — | Already invoiced (use a purchase return) |
| **Approve** a purchase invoice | APPROVED | — | Dr 2300 GRNI + Dr 1300 Input Tax / Cr 2100 Trade Payables; price difference to 5400 | **Up** | Closed period |
| **Record a payment** | POSTED | — | Dr 2100 Trade Payables / Cr 1010 Bank | **Down** | — |
| **Purchase return** complete | COMPLETED | **On hand down** | Dr 2100 Trade Payables / Cr 1200 Inventory + Cr 1300 Input Tax | **Down** | — |

## Stock on its own

| Action | Stock | Journal | Notes |
| --- | --- | --- | --- |
| **Opening stock** | On hand up | Posts against inventory | Once per product/warehouse |
| **Stock adjustment** / physical count posted | On hand up or down | Dr or Cr 1200 Inventory against 5500 Inventory Adjustment | Reason required |
| **Write-off** | On hand down | Posts (reaches the ledger) | Reason required |
| **Transfer** between warehouses | Out of one, into the other | **None** — same goods, same value | — |

## Incentives

| Action | Journal | Notes |
| --- | --- | --- |
| **Accrue** a commission period | **None** — drafts only | One live payout per salesman per period; a second is refused by name |
| **Approve** a payout | Dr 5600 Commission Expense / Cr 2400 Commission Payable | Snapshot: later receipts do not change it |
| **Pay** a payout | Dr 2400 Commission Payable / Cr Cash or Bank | Needs `COMMISSION_PAY` |
| **Cancel** a draft payout | — | Frees the period to accrue again |
| **Points lapse** (expiry sweep) | Dr 2600 Loyalty Payable / Cr 5700 Loyalty Expense for what lapsed | Only what is left of a batch |

## Books and controls

| Action | Effect | Refused / notes |
| --- | --- | --- |
| **Close** an accounting period | Nothing can post into it | Posting reads "Accounting period P03 is closed and cannot accept postings." **Open** to allow again |
| Posting **back-dated** into an earlier month | Every later month's opening moves with it | Trial balance stays Balanced (fixed 2026-09-14) |
| **Manual journal entry** — save draft | Nothing posts | Must balance |
| **Post** a manual entry | Posts to the named accounts | Account requiring a cost centre refuses a line without one |
| **Reverse** a posted entry | Mirror entry | — |
| Customer **opening balance** | Dr 1100 Trade Receivables / Cr Opening Balance Equity | No chart or open period → refused |
| **Credit policy** change | Next approvals judged by it | Needs `CUSTOMER_MANAGE_SETTINGS` |
| **GST Returns** | Nothing stored — read from the documents every time | A cancelled invoice drops out; a credit note lands in its issue month |

## Two quick sanity checks after any test

1. **Finance → Trial Balance**, the month you worked in → chip **Balanced**.
2. **Settings → Audit Logs** → the newest rows are exactly the actions you took.
