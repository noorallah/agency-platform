# Compliance: GST returns, e-invoices and TCS

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-10-03 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Compliance — GST returns, e-invoices and TCS

A GST return is **derived on every read**, never stored: cancel an invoice and
it drops out. E-invoices and e-way bills go to a **sandbox** that marks every
reference it mints `SBX…`. E-Invoice, GST Returns and TCS are under **Sales**.

| Preparation | Starts you with |
| --- | --- |
| `compliance-firm` | a firm with GSTIN `33…` (Tamil Nadu); **`QA-B2B`** Registered Buyer with a GSTIN; **`QA-B2C`** Walk-in Buyer with none; `QA-P` at HSN **340220**, GST 18 local. This month: **Invoice A** — B2B, 10 × 100 (1,180.00), **collected and e-registered**; **Invoice B** — B2B, 5 × 100 (590.00), unpaid, **e-registered, no e-way bill**; **Invoice C** — B2C, 3 × 100 (354.00), unpaid, not registered |
| `selling-paid` | (see *Selling*) two receipts from Vijaya, who has no PAN, each charged TCS at 1% |

### TC-COMP-001 — GSTR-1 for the month

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Steps:** as the prepared **Firm admin**, Sales → **GST Returns** → this month (the From/To boxes are chosen, not typed) → **GSTR-1**.
- **Expect:** "Filing as <the firm's GSTIN>". **B2B**: Invoice A — taxable 1,000.00, CGST 90.00, SGST 90.00 — and Invoice B — 500.00, 45.00, 45.00 — under the buyer's GSTIN. **B2CS**: one row, Place **33**, 18%, taxable 300.00, CGST 27.00, SGST 27.00 — never a blank place. **CDNR**: nothing. **HSN**: 340220, quantity 18, taxable 1,800.00. **Invoices without a place of supply**: "Nothing in this section." The status bar: "Derived from the documents on every read, never stored."
### TC-COMP-002 — What rests on a bill stops it being cancelled; a return follows what is left

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Steps**
  1. Sales Invoices → **Invoice A** → **Cancel**.
  2. **Invoice C** → **Cancel** (give a reason). GST Returns → Refresh.
- **Expect**
  - Step 1: refused, naming what rests on it: "SI-… cannot be cancelled while it has money applied from RC-…; its registration with the tax authority. Reverse or cancel those first."
  - Step 2: C cancels. The **B2CS row is gone** and HSN falls to quantity 15, taxable 1,500.00. *(The plan's second refusal — by a sales return — is TC-SELL-015's return in reverse; this preparation has none.)*
### TC-COMP-003 — GSTR-3B agrees with GSTR-1

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Steps:** GST Returns → **GSTR-3B**, same month. Add GSTR-1's B2B, B2CS and CDNR taxable values by hand.
- **Expect:** **3.1(a)** taxable **1,800.00**, CGST 162.00, SGST 162.00 — equal to GSTR-1's sum; credit notes deducted 0; the inward side reads "Not derived: the purchase side files this." 3B is aggregated from the documents, not parsed out of GSTR-1.
### TC-COMP-004 — The e-invoice screen says it is a rehearsal

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Steps:** Sales → **E-Invoice**.
- **Expect:** a banner, "References marked sandbox are a rehearsal: nothing was filed with the tax authority..."; columns Invoice, Customer, Reference, E-way bill; **two** rows (A and B), each Reference an `SBX…` value (hover for `SBX… (sandbox — nothing filed)`), E-way bill —. If anything reads LIVE, stop.
### TC-COMP-005 — An invoice to a buyer with no GSTIN is refused locally

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Steps:** E-Invoice → **Register an invoice** → **Invoice C** (items read `SI-… — Walk-in Buyer qa — 354.00`) → Register.
- **Expect:** refused **locally**, in an error toast: "This invoice cannot be registered yet: the customer has no GST number." No row added, no portal code.
### TC-COMP-006 — Raising and withdrawing an e-way bill

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Steps**
  1. Select **Invoice B**'s row → **Raise bill**: Distance 120, Moving by Road, vehicle blank → Raise. Then vehicle `TN01AB1234` → Raise.
  2. With the row selected → **Cancel bill**, give a reason.
  3. **(HTTP)** `POST /api/v1/einvoice/invoices/{Invoice C id}/eway-bill` with `{"distance_km": "120", "transport_mode": "ROAD", "vehicle_number": "TN01AB1234"}`.
- **Expect**
  - Step 1: blank vehicle refused before sending: "Goods moving by road need a vehicle number on the bill."; then "E-way bill raised." and the cell fills with `SBX…`.
  - Step 2: "E-way bill withdrawn."
  - Step 3: **422**, "Register the invoice before raising its e-way bill: the bill quotes the IRN, and one without it cannot be matched to a supply." The screen does not offer it.
### TC-COMP-007 — TCS: the register, the settings, and a journal of its own

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Steps:** as the prepared **Firm admin**, Sales → **TCS**; open **Settings** (close without saving). Finance → Journal Entries → search `TCS-RC` → View one.
- **Expect**
  - The banner reads "Collecting under section 206C(1H) • (the threshold, 0) per buyer per year, then 0.100% (1.000% without a PAN)"; the register lists the two receipts from Vijaya — **2.42** and **3.42**, rate **1.000%** (no PAN), **COLLECTED**.
  - Settings: **Collect under section 206C(1H)** on; preceding year turnover 150,000,000; threshold 0; rate 0.1; without a PAN 1.0.
  - Journal: `TCS-RC-…` entries separate from the receipts' own; View reads **Dr 1100 Trade Receivables / Cr 2500 TCS Payable** — 2500, not Output Tax.
---

### TC-COMP-008 — The tax calendar on Home, and marking a return filed

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Also needs:** the prepared invoices are dated this month, so the calendar's rows are for the month just gone only if the firm traded then; if the list reads "Nothing due.", use a firm with last month's invoices.
- **Steps:** as the prepared **Firm admin**, Home → **Tax calendar**. On a GSTR-1 row choose to record it as filed, with a date and an acknowledgement number. Then withdraw it (Undo). Record a GST payment for the month and look again.
- **Expect:** one row per return per finished month (GSTR-1 due the 11th, GSTR-3B the 20th; a TCS deposit row only for a month that collected tax at source), each reading due in N days, N days late or Filed on a date. Marking GSTR-1 filed turns its row to Filed and nothing else moves; Undo puts it back. GSTR-3B closes once a GST payment is recorded for the month. A TCS row has no record button. A role that may not open GST Payment does not see the card.
### TC-COMP-009 — Filing e-invoices offline (no GSP)

*Added 2026-10-02 (decision A42).*

- **Preconditions:** a GST-registered firm with two approved B2B invoices to registered buyers, not yet registered.
- **Steps:** Settings → Tax → **GST Documents** → *E-invoice filing* → **Offline** → Save. Accounts → Tax filing → E-Invoice → **Export for portal** → tick both → save the JSON file. Open it. Then **Import portal result** with a JSON file shaped like the portal's answer (for each invoice: `DocDtls.No` the invoice number, `Irn`, `AckNo`, `AckDt`, `SignedQRCode`; give the second invoice no `Irn` and an `ErrorDetails` text). Then try **Register** on a third approved invoice.
- **Expect:** the export holds one object per invoice in the portal's schema (`Version`, `TranDtls`, `DocDtls`, `SellerDtls`, `BuyerDtls`, `ItemList`, `ValDtls`), and both invoices show **PENDING**, mode **LIVE**, route **OFFLINE**. After the import the first is **REGISTERED** with that IRN and acknowledgement, the second **FAILED** with the error text, and the message counts 1 registered, 1 refused. Register on the third comes back refused with directions to export it instead.

### TC-COMP-010 — E-way bills without an IRN, on a challan, and by hand

*Added 2026-10-02 (backlog 77 rows 9-10).*

- **Preconditions:** a firm with no *e-invoicing applies* date; Settings → Tax → GST Documents → *E-way bill needed above* **1,000**. An approved invoice worth more than 1,000 without an e-way bill; an approved **Job work** delivery note that no invoice bills; a second approved invoice.
- **Steps:** Accounts → Tax filing → E-Invoice → **E-way bills due**. Raise the first invoice's e-way bill (distance 120, road, a vehicle). Raise the job-work note's. On the second invoice choose **Record e-way bill...**: number `3510 1234 5678`. Then set an *e-invoicing applies* date in the past and try to raise an e-way bill on a new, unregistered B2B invoice. Dispatch a delivery note worth more than 1,000.
- **Expect:** the due list shows the invoices and the note with the limit 1,000. The first invoice's bill is raised without an IRN; the note's bill carries supply type **Job work**; the recorded one shows `351012345678`, marked as entered by hand. Each leaves the due list. With e-invoicing on, the unregistered invoice is refused: "Register the invoice before raising its e-way bill". Dispatching the note prompts to raise its e-way bill.

### TC-COMP-011 — Registering a credit note and a debit note

*Added 2026-10-02 (backlog 77 row 4).*

- **Preconditions:** a GST-registered firm on the **Sandbox** route; an approved, registered B2B invoice of 1,000 + 18% GST; an approved credit note of 200 + 36 against it, and an approved debit note to the customer of 100 + 18.
- **Steps:** Sell → Credit Notes → the note → **E-invoice** → **Register**. The same on the debit note. Accounts → Tax filing → E-Invoice: look at the list. Switch the firm to **Offline**, raise another credit note, and **Export for portal** with an invoice and that note ticked; open the file.
- **Expect:** each note registers with an `SBX` IRN and shows mode **SANDBOX**; the list shows them as *Credit note* and *Debit note* with their own numbers. The exported file holds the invoice (`Typ` INV) and the note (`Typ` CRN) whose `RefDtls` names the invoice it corrects, CGST and SGST each 18.00 on the 200.
---

### TC-COMP-012 — The IRN and QR on the printed documents

*Added 2026-10-02 (backlog 77 row 11).*

- **Preconditions:** TC-COMP-011 done: a registered invoice, a registered credit note and a registered debit note; plus one approved invoice never registered.
- **Steps:** Print each of the four. Withdraw the invoice's registration (inside 24 hours) and print it again.
- **Expect:** the three registered documents carry an **E-INVOICE** box under the title with the IRN, Ack No. and Ack Date and a QR code; scanning the QR returns the signed text. The credit note is titled **CREDIT NOTE**, names "Against invoice" with the invoice number and date and the reason, and splits its tax into CGST and SGST as the invoice did. The unregistered invoice and the withdrawn one print with no box.

### TC-COMP-013 — Rule 37: a bill unpaid 180 days

*Added 2026-10-02 (backlog 78 row 4).*

- **Preconditions:** an approved supplier bill of 400 + 18% local GST (CGST 36, SGST 36) dated more than 180 days ago, nothing paid; Settings > Tax > GST Documents, *180-day unpaid bills* on **Report and post**.
- **Steps:** Accounts → Tax filing → Rule 37 (180 days), as of today. **Post reversals and reclaims.** Open the trial balance and GSTR-3B for this month. Pay the bill in full. Back to Rule 37, post again; GSTR-3B for that month.
- **Expect:** the bill is listed to REVERSE CGST 36 and SGST 36. After posting the list is empty, input tax is down 72 and *Input Tax Not Claimable* up 72, and 3B shows 72 in 4(B)(2), "of which rule 37" 72. After payment the bill is listed to RECLAIM 72; once posted the books are back, and that month's 3B shows the 72 in 4(A)(5) and in 4(D)(1). With the setting on **Report only**, the list shows but posting is refused with the reason.

### TC-COMP-014 — The supplier's IRN on a bill

*Added 2026-10-02 (backlog 78 row 5).*

- **Preconditions:** a supplier with a GSTIN; Settings > Tax > GST Documents, *Supplier bill without an IRN* on **Warn** (the default).
- **Steps:** Open the supplier, tick **Supplier e-invoices**, save. Enter a bill from it with no IRN and save. Type `IRN-123` in the IRN box. Then type a 64-character IRN (e.g. 64 `a`s) and save. Approve it; **Record IRN** on the approved bill, clear it, record it again. Enter a second bill from the same supplier carrying the same IRN. Set the setting to **Off** and reopen a bill with no IRN.
- **Expect:** the first save shows the warning that the supplier e-invoices and the bill has no IRN (rule 48(4)); `IRN-123` is refused as not 64 letters and digits; with the IRN the warning goes. On the approved bill the IRN can be recorded and cleared, and the audit trail shows each change. The second bill warns that the first bill already carries this IRN. With the setting Off the missing-IRN warning is not shown (the duplicate warning still is).

### TC-COMP-015 — The e-way bill on a goods receipt

*Added 2026-10-02 (backlog 78 row 6).*

- **Preconditions:** Settings > Tax > GST Documents, e-way bill limit **50,000**; an approved purchase order worth more than 50,000 from a supplier with a GSTIN, and a second from a supplier with none.
- **Steps:** Receive the first order with no e-way bill number and save. Type `EWB-1` in the e-way bill box. Type `3312 3456 7890` and a date, and save. Complete the receipt; **Record e-way bill**, clear it, record it again. Receive the second order with no number.
- **Expect:** the first save warns that goods worth more than 50,000 need an e-way bill and none is recorded (rule 138), asking for the supplier's number; `EWB-1` is refused as not 12 digits; with the number the warning goes and it is stored as `331234567890`. On the completed receipt the number can be recorded and cleared, and the audit trail shows each change. The unregistered supplier's receipt warns that the e-way bill is yours to raise. A receipt under 50,000 shows no warning.

### TC-COMP-016 — No print or email of a B2B invoice without its IRN

*Added 2026-10-02 (backlog 77 row 6, decision A43).*

- **Preconditions:** a GST-registered firm on the **Sandbox** route with *E-invoicing applies from* set to a day in the past (Settings → Tax → GST Documents). An approved invoice dated on or after that day to a buyer **with** a GSTIN, not registered; an approved invoice to a buyer **without** a GSTIN; an approved credit note against the first invoice, not registered. Messaging switched on with an email channel that can send.
- **Steps:** (a) Sell → Sales Invoices → the B2B invoice → **Print**. Read the dialog, choose **Cancel**; Print again and choose **Print reference copy**. (b) **Send** it by email. (c) Print the consumer's invoice. (d) Print the credit note. (e) Accounts → Tax filing → E-Invoice → register the B2B invoice, then Print and Send it again.
- **Expect:** (a) a *No IRN yet* dialog: "<number> has no IRN yet. The firm e-invoices from <date> and the buyer is registered for GST, so it is not a valid tax invoice until it is registered on the portal (CGST rule 48(4)). Register it under E-invoice first, or print a reference copy marked not valid." Cancel prints nothing; the reference copy prints with **NO IRN YET - NOT A VALID TAX INVOICE** across its top. (b) the email is refused with the same sentence. (c) the consumer's bill prints as before, with no dialog. (d) the credit note is refused the same way, naming its own number. (e) once registered the invoice prints with its IRN box and no banner, and the email is accepted. A WhatsApp or SMS send is never held.

### TC-COMP-017 — The automatic invoice email waits for the IRN

*Added 2026-10-02 (backlog 77 row 6, decision A43).*

- **Preconditions:** TC-COMP-016's firm; Settings → Messaging → *Events*: *Invoice approved* on, by email; a B2B customer with an email address.
- **Steps:** Approve a new invoice to that customer. After the next messaging pass, Settings → Messaging → **Message log**. Then Accounts → Tax filing → E-Invoice → register the invoice; wait at least five minutes and look at the log again.
- **Expect:** the row stays **Queued** with the Reason "Waiting for <number>'s IRN: it goes out on the first pass after the invoice is registered on the portal." Nothing is sent and Tries does not climb. After registration the row is sent on the next pass (looked at again every 5 minutes) with the registered invoice attached -- one email, not two. Other queued messages keep going out while it waits.

### TC-COMP-018 — The 30-day limit and the To register list

*Added 2026-10-02 (backlog 77 row 7, decision A44).*

- **Preconditions:** TC-COMP-016's firm, *30-day reporting limit applies from* set to a day in the past (not before the e-invoicing date). Three approved B2B invoices, not registered: one dated 35 days ago, one dated 27 days ago, one dated today.
- **Steps:** Accounts → Tax filing → E-Invoice → **To register**. Choose **Register** on the 27-day-old invoice. Try to register the 35-day-old one from **Register an invoice** (and, on the Offline route, by **Export for portal**). Clear the *30-day reporting limit* date, Save, and open **To register** again.
- **Expect:** the list shows every approved B2B document without an IRN, oldest first, with Document, Number, Date, Customer, Amount, **Last day** (date + 30), **Days left** and Status: the 35-day-old one **Late**, with no Register button and the note "A late document cannot be registered: cancel it and raise it again under today's date."; the 27-day-old one "3 days left" (due soon, within 5 days); today's **Open**. Register on the 27-day-old one registers it and it leaves the list. Registering or exporting the late one is refused: "<number> is dated <date>; the last day to register it was <date>. The IRP refuses a document more than 30 days old ... Cancel it and raise it again under today's date." With the date cleared the list still shows the pending documents, says "The 30-day limit does not apply to this firm (Settings > Tax > GST Documents).", and has no Last day or Days left columns.

### TC-COMP-019 — A sales return's credit note on the IRP

*Added 2026-10-02 (D-TAX-2, decision A45).*

- **Preconditions:** TC-COMP-016's firm on the **Sandbox** route. A B2B customer with two approved invoices for the same product; a sales return of goods from **both** invoices, completed; a second completed return of goods that were only delivered, never invoiced.
- **Steps:** Sell → Sales Returns → the first return → **Print credit note**. Accounts → Tax filing → E-Invoice → **To register**: find it and **Register**. Print its credit note again. Switch to **Offline**, raise and complete another return of billed goods, **Export for portal** with it ticked, and open the file. Look for the second return in **To register**.
- **Expect:** before registration the credit note print is refused with the no-IRN sentence and offers a reference copy. The return is listed as **Sales return**; it registers with an `SBX` IRN, and its credit note then prints with the E-INVOICE box. The exported entry is a `CRN` whose `RefDtls` names **each** invoice it returns goods from. The return of goods never invoiced is not listed and is never registered ("... returns goods no invoice billed, so it credits no tax invoice and is not registered.").

### TC-COMP-020 — The 30 November limits and 16-character document numbers

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Also needs:** an approved invoice dated in the **previous GST year** (April to March); a supplier bill dated in the previous GST year; a numbering series for the sales invoice with a long prefix.
- **Steps:** as the prepared **Firm admin**: raise a **credit note** (and a sales return) against the old invoice dated after 30 November that follows that year's end; read the screen after saving. Raise one dated earlier. Open the old **supplier bill** after 30 November following its year. Then Settings (gear) → Firm → **Numbering Series** → the sales invoice series: set a prefix that makes the number longer than 16 characters; try a space or an underscore in the prefix. Look at the default series of a new firm for invoice, credit note, sales return, debit note, delivery challan.
- **Expect:** a credit note or sales return dated after 30 November following the supply's GST year carries a **time-limit warning** (a warning, not a refusal: the firm may have filed its annual return earlier); the same warning appears on a supplier bill for input credit claimed after that date (s.16(4)). One dated before it shows none. The GST year is April to March whatever the firm's own year. A series for the six GST documents (invoice, credit note, sales return, customer debit note, delivery challan, reverse-charge self-invoice) is refused when its numbers can exceed **16 characters** or use characters other than letters, digits, hyphen and slash; the default series use a **short financial year** so they fit. Quotations, orders, proformas and vouchers keep any length.
### TC-COMP-021 — GST checks before filing

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Also needs:** an invoice to a buyer whose GSTIN has a wrong check character; a product with no HSN; an approved invoice to a registered buyer for a firm that e-invoices but with no IRN; a credit note dated late; a credit note on a cancelled invoice; a supplier bill with a bad GSTIN.
- **Steps:** as the prepared **Firm admin**: Accounts → Tax filing → **GST checks** → choose the month → Run. Read each finding. Click a row. Fix one problem and run again. As a role without SALES_VIEW open the screen.
- **Expect:** findings are named by code and each row names its document (type, number, date, party): GSTIN_INVALID (the firm's own, a buyer's on invoices and notes, a supplier's on bills as a **warning**), HSN_MISSING and HSN_SHORT (six digits once the firm e-invoices, four below), PLACE_OF_SUPPLY_MISSING, IRN_MISSING, CREDIT_NOTE_LATE (after 30 November following the supply's year) and CREDIT_NOTE_ON_CANCELLED_INVOICE. The checks read the same invoices GSTR-1 declares. *Open document* is disabled (the desktop cannot open a sales invoice by id yet). After fixing, the finding is gone on the next run. Needs SALES_VIEW.
### TC-COMP-022 — A filed return is kept, and a change becomes an amendment

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Also needs:** invoices in last month and this month (back-date as needed).
- **Steps:** as the prepared **Firm admin**: Accounts → Tax filing → **GST Returns** → GSTR-1 for last month → **Mark filed**. Then add or edit a document in last month (a new invoice dated last month, a credit note, a changed GSTIN or rate on one) and reopen last month, then open GSTR-1 for **this** month and GSTR-3B for this month. Withdraw the filing (Undo) and look again.
- **Expect:** a filed period shows the figures **as filed** (a banner says filed; recomputing is possible but the snapshot is what is shown). Any other period's GSTR-1 carries an **Amendments** section: every earlier filed period is recomputed and compared with what was declared — B2BA (invoice by number; the GSTIN may change), B2CLA, CDNRA, B2CSA (a row gone to nothing too) and documents added to a filed period after filing. GSTR-3B carries *amendments to earlier returns*, the net change (credit notes negative). Withdrawing the filing drops its snapshot and the period is live again. One snapshot per filing under the firm's GSTIN; per-branch filing is open.
### TC-COMP-023 — A quarterly (QRMP) filer

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Steps:** as the prepared **Firm admin**: Settings (gear) → Tax → **GST Documents** → **Return filing**: frequency *Quarterly*, from a quarter's start, payment method *fixed sum* (then *self-assessed*). Accounts → Tax filing → **PMT-06 deposits** → take the suggested amount → record the deposit; reverse it. Open **GST Returns**: the quarterly GSTR-1 and the **IFF** view for month 1 or 2; Mark filed the IFF. Home → Tax calendar. Then GST Payment for a quarter and for month 1.
- **Expect:** the filing plan says which months are quarterly, the period each month files under and every due date (3B on the 22nd or 24th by the GSTIN's state). The calendar shows IFF (optional) and PMT-06 for months 1-2 and the quarter's GSTR-1 and 3B. A deposit is Dr *GST Electronic Cash Ledger* / Cr bank, reversible while the quarter is unsettled. The quarterly GSTR-1 leaves out what a filed IFF already furnished. GST payment spans the quarter, refuses months 1-2, and pays from the cash-ledger deposits before the bank. A cancellation's "after the return was due" reads the quarterly date too.
### TC-COMP-024 — Common credit reversal, rule 42

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Also needs:** taxable and exempt sales and eligible input credit in the month and later months of the year.
- **Steps:** as the prepared **Firm admin**: Settings (gear) → Tax → **GST Documents** → *Rule 42 mode* on. Accounts → Tax filing → **Rule 42** → the month → work out; post. Open GSTR-3B. Run the annual true-up and post it; reverse a posting.
- **Expect:** per period the reversal is D1 = C2 × E / F from GSTR-3B's own figures (every eligible credit taken as common), posting Dr *Input Tax Not Claimable* / Cr input tax; the year's true-up is summed month by month against what was posted and a true-up reclaim posts the mirror. GSTR-3B carries *itc reversed rule 42* (4(B)(1)) and *itc reclaimed rule 42* (4(A)(5)) in net ITC. Reversing a posting undoes it. Rule 43 (capital goods) and credit used only for taxable or only for exempt supplies are not done.
### TC-COMP-025 — A branch with its own GSTIN

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Also needs:** a second branch in another state with a warehouse; a valid GSTIN for that state (and one with a wrong check character).
- **Steps:** as the prepared **Firm admin**: Masters → Organisation → **Branches** → the second branch → **Branch GSTIN**: the wrong one, one of another state, then the valid one → Save. Raise and approve an invoice from that branch; print it; e-invoice it. Accounts → Tax filing → **GST Returns**: choose each GSTIN. Try a stock transfer (document or one-step) between the two branches' warehouses.
- **Expect:** the GSTIN is checked for shape and check character and must match the branch's state; a GSTIN makes the branch GST-registered. The branch's own GSTIN (else the firm's) decides the supplier state in place of supply, the seller block on every print, the e-invoice seller details and the e-way bill consignor. GSTR-1 and 3B take a GSTIN and read only that GSTIN's branches (the firm's own GSTIN also takes branches without one); a firm with one GSTIN is not scoped. A transfer between two GSTINs is refused, naming the sales invoice to the other branch as the way.
### TC-COMP-026 — The tax rule is kept on each line

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Sell → Documents → **Quotations** → New with a DET line; open the line's tax detail. Save, convert and bill. Open the invoice line's tax detail. Settings (gear) → Tax → **Rule Simulator** and simulate the same line. Open an old document made before this change; open a credit note.
- **Expect:** the line's tax detail names the **rule code and version** that taxed it, and the simulator answers with the same matched rule code and version. Lines saved before this change show none; credit and debit notes copy their tax from the invoice and are left out.

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 11-S01 | **Sales → E-Invoice** | Offered to any role holding `EINVOICE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 11-S02 | **Sales → GST Returns** | Offered to any role holding `SALES_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 11-S03 | **Sales → TCS** | Offered to any role holding `TCS_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
