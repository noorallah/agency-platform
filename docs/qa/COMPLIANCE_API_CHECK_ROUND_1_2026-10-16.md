# Compliance API check, round 1 (2026-10-16)

Scope: `docs/qa/11_COMPLIANCE.md`, TC-COMP-001..028, driven over HTTP against the running backend
(`http://127.0.0.1:8000`) with kept scripts in `docs/qa/checks/compliance/`. Run all with
`python docs/qa/checks/run.py compliance` (backend venv python): **19 of 19 scripts clean**
(14 case scripts and 5 probes). State is `docs/qa/checks/.state/compliance.json` (not committed).

## Result per case

| Case | Result | Notes |
| --- | --- | --- |
| TC-COMP-001 GSTR-1 for the month | PASS | B2B A and B under the buyer GSTIN, B2CS 33/18%/300/27/27, HSN 340220 qty 18 / 1,800, CDNR empty, no unplaced. The banner and status-bar text are screen-only. |
| TC-COMP-002 cancel refused, return follows | PASS | A refused ("cannot be cancelled while it has money applied from RC-...; its registration..."). Own B2C bill cancels and drops out of B2CS and HSN. |
| TC-COMP-003 GSTR-3B agrees with GSTR-1 | PASS | 1,800 / 162 / 162 on firm one; 3B equals GSTR-1 on firm two too. The "Not derived" text is screen-only. |
| TC-COMP-004 e-invoice list is a rehearsal | PASS | Two rows, all `SBX`, mode SANDBOX, none LIVE, no e-way bill. Banner and hover text are screen-only. |
| TC-COMP-005 no GSTIN refused locally | PASS | 422 "the customer has no GST number", no registration row made. |
| TC-COMP-006 raise and withdraw e-way bill | PASS, with a case-text correction | Blank vehicle refused, raised `SBX...`, withdrawn. Step 3 is wrong (see corrections). |
| TC-COMP-007 TCS | PASS, with a case-text correction | Register empty, no `TCS-RC` journal, preview says omitted from 1 April 2025. |
| TC-COMP-008 tax calendar | PASS (API half) | Filing recorded and undone; GSTR-3B row does not move. Home card and role-hiding are screen-only. |
| TC-COMP-009 offline filing | PASS (API half) | Export holds the portal schema, rows PENDING/LIVE/OFFLINE, import gives 1 registered and 1 failed, third Register comes back FAILED with directions. Settings put back to SANDBOX. |
| TC-COMP-010 e-way bills without IRN / by hand | PASS (partial) | Due list, raise on an unregistered B2B bill, by-hand record stored as `351012345678` and marked by hand. Not driven: the 1,000 limit via settings, the Job work note, dispatch prompt. |
| TC-COMP-011 credit and debit note on the IRP | SKIPPED (not driven this round: needs approved credit and debit notes against a registered invoice; round 2) |
| TC-COMP-012 IRN and QR on printed documents | SKIPPED (printed PDF/QR, screen-only) |
| TC-COMP-013 Rule 37 | SKIPPED (needs a supplier bill older than 180 days; round 2) |
| TC-COMP-014 supplier IRN on a bill | SKIPPED (purchase bill screen warnings; round 2) |
| TC-COMP-015 e-way bill on a goods receipt | SKIPPED (goods receipt flow; round 2) |
| TC-COMP-016 no print/email without IRN | SKIPPED (print dialog and email send; screen and messaging) |
| TC-COMP-017 invoice email waits for the IRN | SKIPPED (needs the messaging pass and an email channel) |
| TC-COMP-018 30-day limit, To register | PASS (API half) | Late / due soon (3 days left) / open, last day = date + 30, late register refused naming the last day and "raise it again under today's date", registered bill leaves the list, limit off when its date is clear. Offline export of the late bill not driven. |
| TC-COMP-019 sales return credit note on the IRP | SKIPPED (needs two invoices and returns; round 2) |
| TC-COMP-020 30 November limits, 16-character numbers | SKIPPED (numbering-series settings and previous-year documents; round 2) |
| TC-COMP-021 GST checks | PASS (partial) | GSTIN_INVALID on an invoice with a bad check character, not on a good one, counts agree, 4 HSN digits. HSN, IRN, credit-note and late-note findings not driven. |
| TC-COMP-022 filed return kept, amendment | PASS | Filed shows `filed: true`, a late bill is left out of the figures and appears in `amendments.added` and in 3B's amendments; withdrawing makes the period live again. |
| TC-COMP-023 quarterly (QRMP) | PASS (partial) | Plan reads back, IFF month 1 due the 13th, quarterly GSTR-1 spans three months, IFF month 3 refused, PMT-06 suggestion due the 25th. Deposits, calendar rows, GST payment for a quarter not driven. |
| TC-COMP-024 Rule 42 | SKIPPED (needs exempt supplies and eligible credit; round 2) |
| TC-COMP-025 branch GSTIN | SKIPPED (branch master screen and a second state; round 2) |
| TC-COMP-026 tax rule kept on each line | SKIPPED (quotation to invoice line detail; belongs with the tax module) |
| TC-COMP-027 input credit on stock written off | SKIPPED (needs a supplier bill and stock adjustments; round 2) |
| TC-COMP-028 return in another unit on HSN summary | SKIPPED (needs a PIECE/BOX rule and a return chain; round 2) |

Tally: **14 PASS, 0 FAIL, 14 SKIPPED** of 28. Screen checks 11-S01..S03 not run.

Probes (all pass): `p_comp_gstr_agree` (GSTR-1 and 3B agree on B2B local, B2B interstate IGST and B2CS), `p_comp_period_limit`
(three calendar months allowed, four and a year refused naming the limit, to-before-from refused), `p_comp_other_firm`
(401/403 and no cross-firm reads or writes), `p_comp_cancel_drops` (a cancelled bill leaves B2B, 3B and HSN and the series counts it),
`p_comp_sandbox_marks` (SBX on every sandbox row, LIVE only from the Offline route, LIVE not selectable).

## Defects

No High or Medium defect found. Two Low observations:

| Severity | Symptom | Expected vs got | Request | Suspect |
| --- | --- | --- | --- | --- |
| Low | Recording an e-way bill by hand with no document named says "not both" | "Name an invoice or a delivery note" vs "Name an invoice or a delivery note, not both." | `POST /api/v1/einvoice/eway-bills/record` with only `eway_bill_number` | `backend/app/einvoice/services/eway_bills.py:287` (one message for both "neither" and "both") |
| Low | The sandbox registers, and customers are saved with, a buyer GSTIN whose check character is wrong; GST checks then flag the same invoice GSTIN_INVALID (ERROR) | A sandbox rehearsal that accepts what the portal would reject hides the problem until filing; the fixture's own GSTINs all fail the check | `POST /api/v1/einvoice/invoices/{id}/register` for a bill to a buyer with `33FXBUY...B1Z3` | Not located (registration path in `einvoice_service.register`); a design choice may apply, flagged for the owner |

## Case-text corrections (4)

1. **TC-COMP-006 step 3** (Invoice C, 422 "Register the invoice before raising its e-way bill"): Invoice C is a consumer's bill, never e-invoiced, so the server raises its e-way bill from the invoice itself (200, `SBX...`, by design, backlog 77 row 9). The refusal only occurs for a B2B invoice with no IRN once the firm has an *e-invoicing applies from* date (checked via `PUT /api/v1/tax-framework/gst-compliance-settings`). Reword the step: set the date, use an unregistered B2B invoice.
2. **TC-COMP-006 step 1 wording**: the server says "Goods moving by road need a vehicle number on the **e-way bill**." (case says "on the bill").
3. **TC-COMP-007**: the settings (on, turnover 150,000,000, threshold 0) belong to the *selling-invoiced* preparation. On `compliance-firm` the policy reads disabled, threshold 5,000,000, turnover 0. State which preparation the settings line assumes. Also the case's `compliance-firm` GSTINs are made up and fail their check character, so the GST checks screen (TC-COMP-021) lists three GSTIN_INVALID rows on the untouched preparation; say so or make the fixture produce valid ones.
4. **TC-COMP-018 / 010**: the To register and e-way "due" lists are empty unless *E-invoicing applies from* is set; the case preconditions for 010 say "no e-invoicing date" yet the list is only meaningful once the date is set for TC-018. Make the setting explicit in both preconditions. Also the case 009 says Register on a third invoice is "refused"; the API answers 200 with a FAILED registration whose message gives the directions.

## Side effects on fixture firms

- Firm one `T1016NUB8-G` (read only by every script): Invoice C had an e-way bill raised during exploration and was withdrawn (CANCELLED row remains). Otherwise unchanged.
- Firm two `T1016JYAC-G` (`compliance-firm` fixture, built this round): every changing script makes its own customers and bills here (about 40 invoices, some cancelled, some registered, some dated last month), adds stock by adjustment (the fixture stocks only a few pieces), and temporarily sets the GST document policy and e-invoice route; all are put back in `finally`. A quarter-end GSTR-1 filing for last month is recorded and withdrawn by TC-008 and TC-022. A re-run adds more bills but fails nothing.
- The checks assume the fixture invoices are dated in the current month and that "last month" has no filed return.
- Two new fixture firms were built (`T1016NUB8-G`, `T1016JYAC-G`); no third.

## Market comparison

Tally Prime, Zoho Books and Busy all give a distributor a GSTR-1 and 3B that can be exported in the portal's JSON/Excel offline-tool format and, in Tally and Zoho, filed or pushed straight to the GSTN through a GSP. They also offer GSTR-2A/2B matching (this module has an import and reconciliation), GSTR-9/9C annual return working papers, e-invoice IRN and QR with bulk generation, e-way bill generation with Part-B (vehicle) updates and consolidated e-way bills, HSN summary validation against the portal master, ITC ineligibility rules (17(5)), a return-wise reconciliation of books against the return with drill-down, and auto-reminders for due dates. What this lacks for a distributor: **a live GSP/IRP connection** (only the sandbox and an offline file route), **GSTR-9/9C**, **Part-B vehicle updates and consolidated e-way bills**, **an export of GSTR-1/3B in the portal's upload JSON** (the module derives the figures but the file export was not seen in these routers), and **credit note / sales return linkage to GSTR-1 in one drill-down** (not driven this round). It is ahead of Busy on QRMP (IFF, PMT-06), rule 37/42 workings and the 30-day IRP limit, which Busy handles weakly.

## Triage (2026-10-16)

- The e-way bill message for "neither document" is **D-CMP-29**, fixed in this branch (`eway_bills.py` now names the missing document; guard `tests/unit/test_eway_bill_note.py::test_a_hand_recorded_bill_must_name_its_document`).
- The GSTIN check character accepted at customer save and sandbox registration is **D-CMP-30**, Low, left for the masters round (item 14).
- Three ways: backend `test_eway_bill_note.py` and `test_einvoice.py`; UI: no screen code changed, so no widget test or analyze; UI clicks: not done -- no screen touched, and the click flows' fixture firm t10069cwy no longer signs in (away item 17).
