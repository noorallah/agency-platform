# Compliance: GST returns, e-invoices and TCS

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
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
