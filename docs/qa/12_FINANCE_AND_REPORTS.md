# Finance, reports, audit and diagnostics

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > All Sell screens > Documents > Proforma` is a screen that is not
daily work, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-04 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Finance, reports and the rest of the platform

The books are on the **Accounts** menu (with Receipts on Sell and Payments on
Buy); Reports has **Operational** and **Financial**; accounting periods live
under **Settings > Firm > Financial Years**. Trial Balance, Profit & Loss and Balance
Sheet each take an **Accounting period**: pick the same one on all three.

The cases that change a firm's books — a new account, a closed period, a cost
centre, an account that demands one — use `ready-firm`, a store of the run's
own with a fresh chart (1000 Cash, 5000 Purchases, and no 9999).

### TC-FIN-001 — A new ledger account, and what cannot change afterwards

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps:** as the prepared **Firm admin**, Accounts > All Accounts screens > Books > **Chart of Accounts** → **New**: group chip **REV** first, code `9999`, name `Manual test account`, type EXPENSE → Save. Then group **EXP · Direct Expenses** → Save. Select it → **Edit**.
- **Expect:** with REV: "A ledger account must share its group's account type." With EXP: the row appears (Code, Account, Type, Status). No Delete on the toolbar. On Edit, group, type and code are fixed; only Name, Description, the two "Requires a …" boxes and **Active** change.
### TC-FIN-002 — The three statements balance and agree

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Steps:** as the prepared **Firm admin**, Accounts > **Trial Balance**, this month's period; then **Profit & Loss** and **Balance Sheet**, the same period.
- **Expect:** the trial balance has Code, Account, Type, Opening, Debit, Credit, Closing, a Total row and a **Balanced** chip — 1100 Trade Receivables among the rows. P&L: Income and Expenses with a Net profit or loss row (This period, Year to date). Balance Sheet: Assets, Liabilities, Equity with Retained earnings brought forward and Result for the year, chip **Balanced**. They agree: Total assets = Liabilities and equity; the sheet's Result for the year = the P&L's year-to-date net; total debit = total credit. *(The figures are this preparation's own; the relationships are the test.)*
### TC-FIN-003 — A closed period refuses a posting; its trail says who closed it

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Firm admin**, Accounts > Journal Entries → **New Entry**: period June 2026, any journal and voucher type, date 2026-06-15, reference `MT-CLOSE-1`, lines `5000 Purchases` Dr 100 and `1000 Cash` Cr 100 → **Save Draft**.
  2. Settings > Firm > **Financial Years** → the year → **June 2026** → **Close**.
  3. Accounts > Journal Entries → the draft → **Post**.
  4. Reopen June (**Open**) → Post again.
  5. Settings > Platform > System > Audit Logs → Action `finance.accounting_period.updated` (in full) → Search. Then sign in as the prepared **Platform admin**, stay on Platform, and run the same search.
- **Expect**
  - Step 2: "June 2026 is closed. Nothing further can be booked into it."
  - Step 3: refused: "Accounting period P03 is closed and cannot accept postings." (June is P03 in an April year.)
  - Step 4: "Journal entry MT-CLOSE-1 posted." The trial balance for a later month still reads **Balanced**.
  - Step 5: in the firm, the caption "The trail for Ready qa…" and **two** rows (closed, reopened); `finance` alone would find nothing (exact match). On Platform the same search finds **nothing** — finance events stay in the firm's trail.
### TC-FIN-004 — Journal entries say which module posted them

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Steps:** Accounts > Journal Entries; search each: `SI-2026-2027-000001`, `DN-`, `RC-2026-2027-000001`, `TCS-RC-2026-2027-000001`; open each with **View**.
- **Expect:** each row's subtitle is the entry's description; the View dialog's first line reads "POSTED · posted by <module> · <description>" — sales_invoice, delivery_note, settlements, tcs. The search matches reference or description; there is no source-module filter (BACKLOG §31.15).
### TC-FIN-005 — Every report opens, and an empty one says so

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Steps:** Reports > **Operational** and **Financial Reports**: open every entry.
- **Expect:** each renders with `N row(s)` in the header, or — when empty — "Nothing to report / This firm has nothing matching it yet." rather than a blank grid. The sales order register, delivery note register and invoice reports hold the prepared documents; the purchase reports are empty (this store bought nothing).
### TC-FIN-006 — Ctrl+K finds a product and lands on its screen

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Steps:** as the prepared **Firm admin**, type in any search box, move to another screen, press **Ctrl+K**, type `QA-PM` → Search; select the result → **Open Details**.
- **Expect:** the dialog opens wherever focus is; one result, **Slot Check qa** (a product), "1 result found."; Open Details closes the search and lands on **Masters > Products**. **(HTTP)** `GET /api/v1/search?query=QA-PM` → 200 (the parameter is `query`; `q` answers 422).
### TC-FIN-007 — Cost and profit centres, and an account that demands one

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. Settings > Set up > Account structure > **Cost Centres** → New `SALES`, `Sales` → Save; New `SALES` again. Settings > Set up > Account structure > **Profit Centres** → New `NORTH`, `North` → Save.
  2. Chart of Accounts → Edit `5000 Purchases` → tick **Requires a cost centre** → Save. Accounts > Journal Entries → New Entry → choose 5000 on a line.
  3. **(HTTP)** `POST /api/v1/finance/journal-entries` with a 5000 line and no `cost_center_id`.
  4. Untick the flag.
- **Expect**
  - Step 1: the rows appear; the second SALES: "A cost centre with this code already exists." No Delete on either grid — deactivate with Active.
  - Step 2: a **Cost centre \*** dropdown on that line and no other; with SALES chosen the entry saves.
  - Step 3: **422**, "Ledger account 5000 requires a cost centre."
### TC-FIN-008 — A blocking credit policy refuses the approval

- **Preconditions:** As *selling-firm*, plus a **blocking** credit policy and the delivery-note stage switched off in the sales workflow settings. (BLOCK at 100%; Anand's limit 1,000; a draft order for 20 detergent.)
- **Steps:** as the prepared **Firm admin**, Masters > Customers → toolbar **Settings**; Cancel. Sell > Sales Orders → the prepared draft → **Approve**.
- **Expect:** the policy reads **Warn, then block**, warn 80, block 100. Approve is refused: "Anand Agencies qa would be at 179.9% of a 1000.00 credit limit. Collect payment or raise the limit before continuing." The order stays DRAFT.
### TC-FIN-009 — A firm that does not type delivery notes

- **Preconditions:** As *selling-firm*, plus a **blocking** credit policy and the delivery-note stage switched off in the sales workflow settings. (delivery-note stage off; Vijaya's order for 4, approved.)
- **Steps:** as the prepared **Firm admin**, Settings > Selling > **Sales Stages** (the same dialog as the Sales stages icon on Sales Invoices). Look for Delivery Notes on the Sell menu. Then Sales Invoices → New → bill the prepared **order** (4) → Create draft → Approve. Reports > Operational → **Delivery note register**.
- **Expect:** Sales stages shows **Delivery note** switched off, and **Delivery Notes is not on the Sell menu** — a stage the firm does not type is hidden. The invoice approves straight off the order; the service raises and dispatches the note itself (the order reads **DELIVERED**), and the register lists that note. *(Whether a hidden screen should hide notes that exist is an open product question, not a defect.)*
### TC-FIN-010 — Roles and Permissions are two Settings screens with an address each

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, click the gear and look under **Platform > People**; open **Roles**, then **Permissions**. Ctrl+K a permission code (e.g. `CUSTOMER_VIEW`) → open it. Sign out and in.
- **Expect:** Roles and Permissions are two cards under Platform > People, each opening in a tab of its own with its own heading. Ctrl+K lands on **Permissions** directly; after signing in again the last screen restores to the same one (confirm: the 1.3.0 tab strip keeps both open). (Creating and editing roles is TC-ROLE-001 and TC-ROLE-002.)
### TC-FIN-011 — A crash report reaches Diagnostics

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps:** sign in on the desktop, end **agency_desktop** in Task Manager, start it again and sign in as the prepared **Platform admin** (the queued report is sent then). Settings > Platform > System > **Diagnostics** → Source **Desktop** → Search; open the **UnexpectedTermination** group's first occurrence. Then Source **Server**, any group's first occurrence.
- **Expect:** Desktop: the UnexpectedTermination count one higher than before; occurrences / first seen / last seen / versions chips; the newest occurrence shows Firm, User and "Leading up to it" breadcrumbs ("Previous session started at … ended without a clean exit…") — no Request and no stack trace. Server: **Request <request_id>** and the stack trace.
### TC-FIN-012 — Bank reconciliation against a statement

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Also needs:** a bank statement file for the bank ledger account in the layout the import expects (date, narration, reference, debit, credit, balance), with lines matching the firm's postings (one by amount and date within 3 days, one by cheque number or UTR, two postings that tie, one that sums two entries) and one line with nothing behind it; a user holding JOURNAL_POST.
- **Steps:** as the prepared **Firm admin**: Accounts > **Bank Reconciliation** → pick the bank account → **Import statement**; import it again. Press **Auto-match**. Match a tied line by hand; match one line to **two** entries summing to it; **Unmatch** one; remove a statement. Open the *reconciliation statement* as on a date with the statement's printed closing balance. Then Settings > Firm > Financial Years → the month's close checks.
- **Expect:** lines are matched to **postings on the bank ledger** (receipts, payments, contra vouchers, expenses and journals alike). A line already imported on the account is refused. Auto-match pairs on amount, journal date within 3 days and reference; ties are left for a person. A manual match of one line to several entries must sum to the line. The reconciliation statement shows the book balance, unmatched entries and unmatched statement lines, and checks against the printed closing balance. The cleared date is the matched line's date. Reading needs LEDGER_VIEW, importing and matching JOURNAL_POST. The month's close checklist lists the unmatched lines (never refusing).
### TC-FIN-013 — Post-dated cheques: hold, deposit, clear, bounce

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** a bank account; the invoice of 483.21 for Vijaya; a supplier bill for the issued side.
- **Steps:** as the prepared **Firm admin**: Sell > All Sell screens > Money > **Post-dated Cheques** → New: Vijaya, 483.21, cheque number, cheque date a week ahead → Save (held). Try **Deposit** today. Filter *due today*. On the cheque date **Deposit**; then **Clear**. Take a second cheque, deposit it and **Bounce** it with charges 100. Cancel a third while held. Then Buy > All Buy screens > Money > **Post-dated Cheques** → issue one to a supplier and run through hold and deposit.
- **Expect:** holding posts nothing; deposit records the receipt (payment on the issued side) through the settlement service, mode Cheque, and is **not allowed before the cheque's date**; clearing posts nothing. A bounce reverses the settlement on the day returned and posts the return charges (Dr bank charges / Cr bank, and Dr receivable / Cr cheque-return charges on the customer's account); a cheque can be cancelled while held. The received side needs the receipt grants and the issued side the payment grants.
### TC-FIN-014 — Payment mode and instrument date on receipts and payments

*Added 2026-10-02 from the code; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps:** as the prepared **Firm admin**: Sell > **Receipts** → Record Receipt for Vijaya with mode **Cheque**, an instrument number and instrument date; again with **UPI** and **Cash**. Buy > **Payments** → the same for a supplier. Open the cash book and the bank book. Reports > Financial → collections by mode.
- **Expect:** each receipt and payment stores its mode and instrument date; the cash and bank books gain **Mode** and **Instrument** columns; collections by mode read the mode on each receipt.
### TC-FIN-015 — Bank details on documents, and printing a cheque

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** a bank ledger account; a payment to a supplier by cheque; a cashier user (PAYMENT_CREATE) and an accountant (ACCOUNT_VIEW only); a sheet of paper or the PDF preview.
- **Steps:** as the prepared **Firm admin**: Accounts > All Accounts screens > Tax filing > **Bank Details** → the bank account → name, number, IFSC, branch, UPI ID; mark **print on documents**; try marking a second account. Print an invoice and a quotation. As the accountant open the screen. Then Buy > **Payments** → the cheque payment → **Cheque layout** → adjust the offsets → **Test print**; **Print cheque** with a payee override. Try a cash payment, a bank-transfer payment and a reversed one.
- **Expect:** one set of details per bank ledger account (asset accounts only) and at most one marked to print: its details fill an empty bank block, and an empty UPI ID, on every print that has one (text typed on a template still wins). The full number is shown to ACCOUNT_MANAGE or PAYMENT_CREATE; everybody else reads the last four; the audit entry masks it. The cheque leaf is a CTS-2010 layout — date boxes, payee, amount in words on two lines, `**12,34,567.00/-`, A/c Payee crossing — moved by the bank account's offsets and dated on the cheque's own date; cash, non-cheque and reversed payments are refused.
### TC-FIN-016 — Checks before closing a month, and the ageing bands

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Also needs:** a draft document dated in the month, an unmatched bank statement line (TC-FIN-012) and an overdue sales and purchase bill.
- **Steps:** as the prepared **Firm admin**: Settings > Firm > **Financial Years** → open the month → **Close**: read the checklist first. Change the close-check settings and run again. Then in the same screen set the **ageing bands** (for example 0-15, 16-45, 46-90, 90+). Reports > Financial → customer ageing and vendor ageing. Reports > **Due** lists: the sales invoices due today and the purchase invoices due in 7 days.
- **Expect:** closing a month lists what is not finished (per the firm's settings, including unmatched bank lines); the list never refuses by itself. Both ageing reports use the firm's bands (the vendor row carries a `buckets` list instead of four fixed columns). The due reports list sales bills due, and purchase bills due within the days asked (0 today, 7 the week ahead).
### TC-FIN-017 — TDS challans and TDS on purchases (194Q)

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** payments with TDS deducted (194C or similar) and expense postings with TDS; a supplier whose approved bills this year exceed 50 lakh (or lower the threshold in the settings); the supplier's PAN.
- **Steps:** as the prepared **Firm admin**: Masters > Vendors → the supplier → *Usual TDS section* 194C. Buy > Payments → Record Payment and look at the section. Accounts > All Accounts screens > Tax filing > **TDS Challans** → *Open deductions* → New: select one section's deductions, enter BSR code, challan serial, date, interest and fees → Save. Create a second challan with the same CIN. Cancel the first. Open the TDS return and *Challans due*. Then Settings > Tax > **TDS on Purchases (194Q)** → switch on, threshold 50 lakh, 0.1%, 5% without PAN → Save. Open Record Payment for the over-threshold supplier. Reports > Financial → 194Q register.
- **Expect:** the payment prefills the supplier's usual section. The challan carries one section; its tax is the sum of the deductions chosen; one live challan per CIN; it posts Dr TDS payable, Dr TDS interest and fees, Cr bank. Cancelling posts a mirror journal and frees the deductions. The TDS return fills each deductee row's challan serial, BSR code and date, and *Challans due* shows deposited and still to deposit. The 194Q figure is the rate on the **excess** over the threshold of the supplier's approved bills without GST in the April-March year, less 194Q already deducted on posted payments; the payment prefills section and amount and never overwrites a figure you typed.
### TC-FIN-018 — Cash flow statement

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Steps:** as the prepared **Firm admin**: Accounts > All Accounts screens > Statements > **Cash Flow** → choose the period range; compare with Profit & Loss and Balance Sheet for the same periods. As a role without PROFIT_LOSS_VIEW open it.
- **Expect:** sections are built from the account groups — current assets and liabilities are operating, other assets investing, other liabilities and equity financing; cash is the cash and bank accounts. The statement shows opening and closing cash and says whether it **reconciles** (the movement equals the change in cash). Needs PROFIT_LOSS_VIEW.
### TC-FIN-019 — Files attached to journals, receipts and payments

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Also needs:** a PDF; the ATTACHMENTS feature enabled.
- **Steps:** as the prepared **Firm admin**: Accounts > **Journal Entries** → open an entry → **Files** → add the PDF; delete it. Do the same on a receipt (Sell > Receipts) and a payment (Buy > Payments).
- **Expect:** each file is a reference (name, type, path, caption) held against exactly one of a journal entry or a settlement; deleting is soft and audited. Without the ATTACHMENTS feature the control is not offered.
### TC-FIN-020 — Export to Tally

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Also needs:** TallyPrime to import into (the build notes say a CA should import a sample before release).
- **Steps:** as the prepared **Firm admin**: Accounts > All Accounts screens > Books > **Export to Tally** → the mappings: give two accounts their Tally names and groups → Save. Choose the dates → **Export**. Open the XML; import it into a Tally company.
- **Expect:** every posted journal of the period is one voucher typed by its source (Sales, Purchase, Credit Note, Debit Note, Contra, Receipt or Payment for settlements, otherwise Journal). Lines on the receivable or payable control accounts name the party of the document, so the masters carry a ledger per customer and supplier under Sundry Debtors/Creditors with its GSTIN; other accounts go out under their mapped name and group (or their own name in the group their purpose suggests). GST travels as the tax ledgers. Tally accepts the file and its trial balance agrees with the platform's.
### TC-FIN-021 — Approvals by level, and bulk reject

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** three users: a **Sales** user, a **Sales manager** and the **Firm admin**.
- **Steps:** as the **Firm admin**: Settings > Firm > **Approval Levels** → New rule: document type *Sales order*, level 1 from 0 role Sales Manager; level 2 from 10,000 role Firm Administrator. Save. As the **Sales** user raise an order of 20,000 and a small one of 500. As the **Sales manager**: Sell > All Sell screens > Documents > **Approvals** → pending → **Sign off** the big order; try **Approve** on the order itself. As the administrator open Approvals and **Sign off** level 2. Raise another and **Reject** with a reason; reject two at once (bulk). Also try an order of 500 and a purchase order. Home bell.
- **Expect:** with no rule for the total nothing changes. Otherwise levels are signed in order, one level per person, and Approve goes through only when the approver can sign the last open level; anyone else is refused naming the level and roles. *Sign off* records the next level and the **last** sign-off approves the document through its own service (if the module refuses, the signature stays). A sign-off counts while the total is no more than it was signed at. *Reject* needs a reason, clears the sign-offs and returns a submitted purchase order to draft; bulk reject is per row. An order the chain raised itself is not gated. Platform administrators are not limited. The bell shows *Documents awaiting the next sign-off*. Applies to sales orders, sales invoices, purchase orders and purchase invoices.
### TC-FIN-022 — The notification bell, and one search box on the audit trail

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a purchase order awaiting approval, a requisition waiting, a stock adjustment request waiting and a failed email; a user who may approve and a user who may not.
- **Steps:** as the **Firm admin**: look at the bell on Home. Open it and mark it read; make another item wait and look again. As the user who may **not** approve open the bell. Then Settings > Platform > System > **Audit Logs** → type a person's name or email in the search box; then an action name; then a record type.
- **Expect:** the bell is derived from the documents — it counts approvals waiting (purchase orders, the multi-level chain, requisitions, stock adjustment requests), failed messages of the last 7 days and stock alerts — and is offered only to someone who could act on each. Reading marks what has been seen; a change in count makes it new again. The audit search matches action, record type, the actor's name or email, and, for user rows, the subject, on both stores of a firm's merged trail.
### TC-FIN-023 — Sales and purchase analysis: compare years, basis, margin, saved layouts

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Also needs:** orders and invoices in the same period of the previous year (back-dated), a user with PRODUCT_VIEW_COST_PRICE and one without.
- **Steps:** as the prepared **Firm admin**: Sell > All Sell screens > Insight > **Sales Analysis** → basis *Ordered* then *Invoiced*; switch on **Compare with last year**; read cost, margin and margin %; **Save layout**, reopen it. Sign in as the user without cost-price rights. Buy > All Buy screens > Insight > **Purchase Analysis** → basis *Received*/*Ordered*, compare, average rate. Open **Rate Trend**.
- **Expect:** the ordered basis counts approved orders instead of invoices; the previous-year column is the same period shifted one year; cost, margin and margin percent appear only with PRODUCT_VIEW_COST_PRICE. Layouts are saved per user and report. The purchase analysis has the same controls plus average rate on every figure (sales too); the rate trend shows the rate by month.
### TC-FIN-024 — Search at volume, and nightly retention

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** for retention, an installed server with its scheduled backup task; for speed, PERF01 loaded if you want the volume figures (the expected timings are in the performance notes).
- **Steps:** as the prepared **Firm admin**: press Ctrl+K and type part of an invoice number (for example the middle digits); type part of a customer name. Open GSTR-1 and GSTR-3B for the month and Customer Outstanding. On the server, run the nightly backup task and read its log; set the retention switch off and run again.
- **Expect:** a fragment of a number or name finds the document (on a large firm through the trigram index). The returns and the outstanding report give the same answers as before and are quicker (the month's GSTR-1 about 3.7 s and 3B 2.9 s on the 110,000-invoice test firm; a quarter is still slower). The nightly backup task also runs retention (`purge-retention --yes --scheduled`); with the platform-wide switch off it returns at once; a retention failure is logged and never fails the backup.
### TC-FIN-025 — Phase 1 leftovers: price list counts, territory picker, return pickers

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Price Lists** → open the grid, read the count column for a list with 3 breaks of one product; New list with scope **One territory**. Sell > Returns & notes > **Sales Returns** → New and open the picker of returnable lines for a line with no description.
- **Expect:** the price list grid counts **distinct products** ("1 (3 rates)"); the *One territory* scope has a territory picker; a returnable line with no description is labelled by product code and name, and "Line N" only when nothing is known.
---

## A cashier can see the till

`CASHIER` holds exactly `RECEIPT_CREATE`, `RECEIPT_VIEW`, `PAYMENT_CREATE` and
`PAYMENT_VIEW`, and was offered **no module at all**: Receipts and Payments
were Finance tabs, Finance was gated on `ACCOUNT_VIEW`, and a tab naming no codes
inherits its module's. The module now takes any of `ACCOUNT_VIEW`, `RECEIPT_VIEW`,
`PAYMENT_VIEW`, **and every tab names its own code** — both halves are
load-bearing. In the 1.3.0 menu Receipts is on **Sell** and Payments on **Buy**;
the other ten screens are on **Accounts** and in Settings > Set up > Account structure.

The module's twelve screens: Chart of Accounts (Accounts > All Accounts screens),
Control Accounts, Cost Centres, Profit Centres (Settings > Set up > Account
structure), Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance
Sheet (Accounts), Receipts (Sell), Payments (Buy), Refunds (Sell > All Sell
screens > Money).

### TC-CASH-001 — A cashier gets the till, holding Receipts and Payments only

- **Preconditions:** A QA01 user holding the CASHIER role only, and a customer to record a receipt against. (`CASHIER` alone, no job template. That combination is the whole setup: the seeded Counter Sales template pairs CASHIER with BILLING_EXECUTIVE, which is what hid the bug.)
- **Steps:** sign in as the prepared **Cashier**; read the menu bar; open the Sell and Buy menus and look for Accounts.
- **Expect:** The menu bar offers Sell and Buy (before the fix it was empty), with exactly **Sell > Receipts** and **Buy > Payments**. **No Accounts menu**, so **none** of Chart of Accounts, Control Accounts, Cost Centres, Profit Centres, Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance Sheet, Refunds. Widening the module without gating its tabs would have handed a cashier the ledger.
### TC-CASH-002 — Recording a receipt, with a searchable party picker

- **Preconditions:** A QA01 user holding the CASHIER role only, and a customer to record a receipt against.
- **Steps**
  1. As the prepared **Cashier**, Sell > Receipts → **Record Receipt**.
  2. In the party picker, type part of the prepared customer code (`QA-TI`); clear it; type part of its name (`Till Customer`); then type `zzzz-nobody`.
  3. Choose **QA-TILL**, amount `100`, method Cash → save.
- **Expect**
  - Step 1: the dialog opens with the picker filled. **This failed until 2026-09-15** with "You do not have permission to perform this action." — the picker read `GET /api/v1/customers`, which needs `CUSTOMER_VIEW`, so the role was blocked one step short of the only thing it exists to do. The money screens read `GET /api/v1/receipts/parties` now (#403).
  - Step 2: both narrow the list, each option reading `CODE  Name` on one line; a search matching nobody says so under the field rather than showing an empty sheet.
  - Step 3: the receipt is recorded and listed.
### TC-CASH-003 — An accountant keeps all twelve

- **Preconditions:** A QA01 user hired with the *Accounts* job template (role ACCOUNTANT only). (`ACCOUNTANT` alone. No accountant is seeded in any demo firm.)
- **Steps:** sign in as the prepared **Accountant** → open Accounts, Sell > Receipts and Buy > Payments.
- **Expect:** **all twelve** tabs. `ACCOUNTANT` carries `ACCOUNT_VIEW`, `JOURNAL_VIEW`, `RECEIPT_VIEW`, `PAYMENT_VIEW`, `LEDGER_VIEW`, `TRIAL_BALANCE_VIEW`, `PROFIT_LOSS_VIEW` and `BALANCE_SHEET_VIEW`; every code now on a tab is one whoever held `ACCOUNT_VIEW` already had, so nobody lost one.
### TC-CASH-004 — A firm administrator keeps all twelve

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** sign in as the prepared **Firm admin** → open Accounts, Sell > Receipts, Buy > Payments and Settings > Set up > Account structure.
- **Expect:** all twelve tabs.
---

## The audit trail

Settings is offered on any of `SETTINGS_VIEW`, `AUDIT_LOG_VIEW`,
`DIAGNOSTICS_VIEW`; Audit Logs needs `AUDIT_LOG_VIEW` and no firm; Diagnostics
needs `DIAGNOSTICS_VIEW`, which `FIRM_ADMIN` does not hold.

### TC-AUDIT-001 — A platform administrator reads the platform trail

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps:** sign in as the prepared **Platform admin**, no firm selected → Settings > Platform > System > **Audit Logs**.
- **Expect:** the **platform** trail — user, role and firm administration: `identity.login`, `user.created`, `user.firm_roles_set` and the like, including the prepared own setup a moment ago. Each row names who did it. *(Answered 403 between 2026-09-05 and 09-06: the designation had moved claims and the check had not.)*
### TC-AUDIT-002 — Selecting a firm switches to that firm's trail

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps:** as the prepared **Platform admin**, switch into **QA01** (the header changes from Platform, the menu bar grows) → Settings > Platform > System > Audit Logs.
- **Expect:** **QA01's** trail — firm-owned work such as `customer.created`, `sales_invoice.created`, `settlement.receipt.recorded` from preparations that sold or took money in QA01 — with platform rows carrying QA01's id interleaved. Not the platform trail of TC-AUDIT-001: selecting a firm is what sets `X-Firm-ID`.
### TC-AUDIT-003 — A firm administrator reads their own firm's history, naming people

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** sign in as the prepared **Firm admin** → **Settings**; read Audit Logs; look for Diagnostics.
- **Expect**
  - Settings opens with **Audit Logs** in it. It used to open empty — offered on `SETTINGS_VIEW` with both tabs demanding codes the role lacked.
  - QA01's history and nothing else. **Every row names the person who did it** and, where the subject is a person, who it was done to (#407, #409).
  - **No Diagnostics.** Error reports are telemetry for whoever maintains the product, not something a firm owns.
### TC-AUDIT-004 — A promotion lands in the firm's trail, in time order, and a filter reaches both stores

- **Preconditions:** A firm administrator of QA01, and a QA01 user given two roles picked by hand.
- **Steps**
  1. As the prepared **Firm admin**: Masters > Customers → New `QA-A`, name `Audit Before qa` → Save.
  2. Settings > Platform > People > Users → **Manual Hire (qa)** → **Apply job template** → Counter Sales → Apply.
  3. Masters > Customers → New `QA-B`, name `Audit After qa` → Save.
  4. Settings > Platform > System > **Audit Logs**. Read the top rows.
  5. Filter by action `user_template.applied` — **typed in full**.
- **Expect**
  - Step 4: from the top, `customer.created` (Audit After), `user_template.applied` and `user.roles_set` (both naming Manual Hire), `customer.created` (Audit Before) — **strictly descending timestamps straight through**. The promotion is written to the *platform* store (user administration is a platform path) and the customers to QA01's; nothing marks which came from where. A block of user-administration rows at one end and customers in another means the stores were concatenated, not merged. The promotion names the template **and the role codes it granted** — `role_codes` beside `role_ids`, `template_code` beside `template_id`.
  - Step 5: the promotion is found. A filter that reached one store and not the other would answer a half-truth that reads as correct because something came back. *(Exact match: `user` finds nothing — BACKLOG 31.17.)*
### TC-AUDIT-005 — The platform trail needs platform authority

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps (HTTP):** `GET /api/v1/audit-logs` as the prepared firm admin with **no** `X-Firm-ID`.
- **Expect:** **403**.
### TC-AUDIT-006 — Somebody with none of the three codes has no Settings at all

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** sign in as the prepared **Seller**; read the menu bar and open the gear.
- **Expect:** **No Platform part** on the Settings page, so no Audit Logs card — withheld, not an empty screen (confirm: the gear itself stays, because This PC and me is everybody's). A screen that opens and does nothing reads as broken rather than withheld.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 12-S01 | **Accounts > All Accounts screens > Books > Chart of Accounts** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S02 | **Settings > Set up > Account structure > Control Accounts** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S03 | **Settings > Set up > Account structure > Cost Centres** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S04 | **Settings > Set up > Account structure > Profit Centres** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S05 | **Accounts > Journal Entries** | Offered to any role holding `JOURNAL_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S06 | **Accounts > Expenses** | Offered to any role holding `EXPENSE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S07 | **Accounts > All Accounts screens > Books > Opening Balances** | Offered to any role holding `JOURNAL_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S08 | **Sell > Receipts** | Offered to any role holding `RECEIPT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S09 | **Buy > Payments** | Offered to any role holding `PAYMENT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S10 | **Sell > All Sell screens > Money > Post-dated Cheques** | Offered to any role holding `RECEIPT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S11 | **Buy > All Buy screens > Money > Post-dated Cheques** | Offered to any role holding `PAYMENT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S12 | **Buy > All Buy screens > Money > Payment Runs** | Offered to any role holding `PAYMENT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S13 | **Sell > All Sell screens > Money > Refunds** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S14 | **Accounts > All Accounts screens > Books > Party Adjustments** | Offered to any role holding `PARTY_ADJUSTMENT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S15 | **Accounts > All Accounts screens > Books > Contra Vouchers** | Offered to any role holding `JOURNAL_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S16 | **Accounts > Bank Reconciliation** | Offered to any role holding `LEDGER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S17 | **Accounts > All Accounts screens > Books > Export to Tally** | Offered to any role holding `LEDGER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S18 | **Accounts > All Accounts screens > Tax filing > TDS Challans** | Offered to any role holding `ACCOUNT_VIEW` or `JOURNAL_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S19 | **Accounts > All Accounts screens > Tax filing > Bank Details** | Offered to any role holding `ACCOUNT_VIEW` or `PAYMENT_CREATE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S20 | **Accounts > Ledgers** | Offered to any role holding `LEDGER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S21 | **Accounts > Trial Balance** | Offered to any role holding `TRIAL_BALANCE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S22 | **Accounts > Profit & Loss** | Offered to any role holding `PROFIT_LOSS_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S23 | **Accounts > All Accounts screens > Statements > Cash Flow** | Offered to any role holding `PROFIT_LOSS_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S24 | **Accounts > Balance Sheet** | Offered to any role holding `BALANCE_SHEET_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S25 | **Reports > Operational** | Offered to any role holding `REPORT_VIEW` or `SALES_VIEW` or `PURCHASE_VIEW` or `CREDIT_NOTE_VIEW` or `DEBIT_NOTE_VIEW` or `PARTY_ADJUSTMENT_VIEW` or `JOURNAL_VIEW` or `PROFORMA_VIEW` or `LOYALTY_VIEW` or `PROMOTION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S26 | **Reports > Financial** | Offered to any role holding `REPORT_VIEW` or `SALES_VIEW` or `PURCHASE_VIEW` or `CREDIT_NOTE_VIEW` or `DEBIT_NOTE_VIEW` or `PARTY_ADJUSTMENT_VIEW` or `JOURNAL_VIEW` or `PROFORMA_VIEW` or `LOYALTY_VIEW` or `PROMOTION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S27 | **Settings > Platform > System > Audit Logs** | Offered to any role holding `AUDIT_LOG_VIEW` or `FIRM_AUDIT_LOG_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S28 | **Settings > Platform > System > Diagnostics** | Offered to any role holding `DIAGNOSTICS_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S29 | **Settings > Platform > System > Platform Dashboard** | Offered to the platform administrator only. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
