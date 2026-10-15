# Masters API check, round 1 (2026-10-16)

Driven over HTTP against the running backend with the kept scripts in
`docs/qa/checks/masters/` (`python docs/qa/checks/run.py masters`). Set-up is
`masters/setup.py` (four fixtures: `customer-master`, `branch-master`,
`loyalty-viewer`, `accountant`; state in `.state/masters.json`, not committed).
Cases are from `docs/qa/05_MASTERS.md`: TC-CUST-001..015 (the second
TC-CUST-011 is `tc_cust_011b`), TC-MAST-001..016 and TC-MAST-033. TC-MAST-017..032
and 034 already have checks in `checks/goods_types/` and were skipped, as was the
"Screen checks" section. Every script makes its own records under a fresh tag and
was run at least twice. Result: **39 of 39 scripts clean** (17 customer, 16
master, 6 probes). No backend code was changed.

## Findings

No server defect was found in this round. Every failure on first run was a
case-text mismatch or my own script (fixed). The five case-text corrections
below are where the case says something the server, correctly, does not do.

## Per case

PASS means the API half passed; "screen-only" steps are named in each script's docstring and were not driven.

| Case | Result | Note |
| --- | --- | --- |
| TC-CUST-001 | PASS | Minimal update (phone only) and whole-record echo keep terms, segment, address, contact, balance. |
| TC-CUST-002 | PASS | Ids held; address text is derived from the ids, wrong typed text is overwritten. Picker rungs screen-only. |
| TC-CUST-003 | PASS | Seller reads the policy, write is 403; default policy warn 80 / block 100. |
| TC-CUST-004 | PASS | credit-status warns, approval under WARN is not blocked. The Approve anyway dialog is screen-only. |
| TC-CUST-005 | PASS | Statement 590 then receipt 200, closing 390; ageing 390 in the first bucket, reconciles. |
| TC-CUST-006 | PASS | Segment assigns; deleting one in use is refused ("still in"). |
| TC-CUST-007 | PASS | Seller 403 on each of five terms, zero terms 201; Sales Manager 403 on edit and import; Firm Manager step not driven (no such account). |
| TC-CUST-008 | PASS | One opening bill of 1,500, journal `<code>-OB`, 2,000 refused, 600 taken, cancel and add-bill refused, negative makes none. |
| TC-CUST-009 | PASS | Change refused while receipt/invoice stands; allowed after reversal / cancel; -OB-REV and -OB2 journals; delete after 0. |
| TC-CUST-010 | PASS | Sales Manager 403 on record, cancel, batch and file import (check and apply); admin records, refuses tomorrow, cancels, file check then apply. Customer Support step not driven. |
| TC-CUST-011 | PASS | Figures 82.6% / 118.0% exact; WARN approves, BLOCK refuses the order of 10 and the second bill. See correction 1. |
| TC-CUST-012 | PASS | Rows carry area and city; placed vs unplaced supplier. Pickers and print screen-only. |
| TC-CUST-013 | PASS | Account rows, receipt as a row, over-allocation 422, on-account row, statement closing equals last balance, seller reads but cannot add a receipt. |
| TC-CUST-014 | PASS | Parent with 4 shops, GST once, duplicate refused naming the holder, family, delete refused, clear parent. |
| TC-CUST-015 | PASS | Paging (last, skip, from_start) on 8 entries instead of 100+; Download sheet and remembered Show choice screen-only. |
| TC-CUST-011b | PASS | Default billing/shipping flags: lone address both, second ticked shipping, back to same-as-billing. Bill print screen-only. |
| TC-MAST-001 | PASS | Six vendor child collections survive a phone-only update and a whole-record echo. |
| TC-MAST-002 | PASS | Categories and types list, accept a row, vendor takes both, children intact. |
| TC-MAST-003 | PASS | Slots read back as set (ids); names-not-ids is screen-only. |
| TC-MAST-004 | PASS | Branch rename keeps address, city, state, GST registration, PAN, default (TEST02). |
| TC-MAST-005 | PASS | Warehouse rename keeps capacity, unit, default and all nine flags; no-capacity warehouse saves. |
| TC-MAST-006 | PASS | Five-row import with a duplicate code refused, nothing written; the clean four import. Copy icon screen-only. |
| TC-MAST-007 | PASS (API half) | Export columns are the importer's; warehouse import by branch code. Sample file, save dialog and notice are screen-only (the desktop builds them; there is no server template for branches or warehouses). |
| TC-MAST-008 | PASS | Case barcode resolves to product, level Case, 12. |
| TC-MAST-009 | PASS | See correction 2. |
| TC-MAST-010 | PASS | Preview suggests Name and GSTIN, Code unmapped is named, mapped import creates both, saved mapping round-trips. |
| TC-MAST-011 | PASS | See correction 3. Sales-analysis grouping not driven. |
| TC-MAST-012 | PASS (partial) | Warning, merge (invoice re-pointed, balance summed, duplicate soft-deleted, 403 without CUSTOMER_DELETE), vendors the same. **Not driven:** merge refused for a document in a closed financial year (would need to close a year in a shared test firm). |
| TC-MAST-013 | PASS | Accounts replaced whole; administrator sees the number, Sales Manager and Accountant see `XXXXXXXXXXXX3456`; audit trail never holds the number; files soft-delete. |
| TC-MAST-014 | PASS | Link by PAN, wrong PAN and already-linked refused, combined statement 118 / 0 / 118, link read back. Party Adjustments set-off is screen-only. |
| TC-MAST-015 | PASS | CUS-/SUP-/PRD- five digits; a typed code stands and the counter steps over it. |
| TC-MAST-016 | PASS (partial) | See correction 4. |
| TC-MAST-033 | PASS | Brand needs a company, product needs a brand, import Brand checks, update with blank Brand keeps it, Copy keeps it, brand in use not deletable. Forms, Lists sheet and the Unbranded filter are screen-only. |

## Probes

| Probe | Result |
| --- | --- |
| `p_mst_other_firm` | PASS: another firm's header 403 on customers, vendors, products, branches, warehouses; its ids 404; edit, delete and merge refused; list does not show it. |
| `p_mst_stale_version` | PASS: current If-Match accepted, stale 409 (customer and vendor), version moves, no header still accepted. |
| `p_mst_omitted_children` | PASS: omitted collections untouched, explicit `[]` clears only that one (customer and vendor). |
| `p_mst_soft_delete` | PASS: customer with an approved bill not deletable; clean one leaves reads and lists; the code is reusable but a restore then refuses with 409 (never two live rows). |
| `p_mst_import_bad_row` | PASS: customers, suppliers and products: check writes nothing, apply with a bad row imports nothing, neither good row is written. |
| `p_mst_page_size` | PASS: `page_size=100000` and `page=0` are 422 on six master lists. |

## Case-text corrections (the case is wrong, the server is right)

1. **TC-CUST-011, steps 3-4 (BLOCK mode):** a bill that would take the customer to 141.6% is refused already when it is typed (422 "Collect payment or raise the limit before continuing."), not saved and then refused at Approve. It stays a draft only when it was typed under WARN and approved under BLOCK; the check drives both. The order of 10 behaves as written (draft saved, approval refused).
2. **TC-MAST-009:** predates backlog 125. The same GSTIN on a second customer is now **refused** (409 naming the holder and saying to make it a shop), so "Save anyway" does not apply to a GSTIN; only a repeated PAN with a different GSTIN is a warning (`QA-TN` is the example that saves).
3. **TC-MAST-011:** a price revision "dated yesterday" is refused ("New rates start today or later ... A price dated back would change today's price without saying so"). Use one dated today (applies today) and one dated next week. In the revision file the bad row is reported as row 3 (heading is row 1).
4. **TC-MAST-016:** a malformed PAN cannot be imported through the customer or supplier import (422 "... is not a PAN"), so the "one with a malformed PAN (import it through the customer import)" precondition cannot be built; only legacy rows can hold one. The script drives the missing-PAN rows and the good-PAN exclusion only.
5. **TC-MAST-013:** the masked number reads `XXXXXXXXXXXX3456` (padded), not just `3456`.

## Not driven

TC-CUST-007 step 6 (Firm Manager) and TC-CUST-010 Customer Support refusal (no such accounts in the set-up); TC-MAST-012 closed-year refusal; TC-MAST-011 sales-analysis dimensions; TC-MAST-014 Party Adjustments set-off; every screen-only step named above. Credit-policy checks (`tc_cust_004`, `tc_cust_011`) change the TEST01 policy and put it back in a `finally`.
