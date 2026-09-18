# Defect register

One list of every known defect: what is open, and what was fixed, when and
where. Started on 2026-09-18, because defects were being recorded in three
places -- `docs/BACKLOG.md` §31, the "Known defects" notes at the end of each
section of `docs/INDEPENDENT_TEST_CASES.md`, and PR descriptions -- and nobody
could answer "is there anything open?" without reading all three.

**This file is the index; the detail stays where it was found.** Each row
links to the full write-up. Status here was checked against the code on
2026-09-18 unless the row says otherwise.

## How to use it

- **Found a defect:** add a row to **Open** with the next id for its area
  (`D-BUY-9`, `D-SELL-1`, ...), the date, a one-line summary, the evidence, and
  a link to where it is written up. Keep an existing id when it already has one
  (`D-27-4`, `BL-31.13`).
- **Fixed it:** move the row to **Fixed**, add the date, the PR, and the test
  that fails when the fix is reverted. A fix without such a test is not done.
- **Decided it is not a defect:** move it to **Not a defect** with the reason.
- **Severity.** *High* -- wrong money, stock or tax, or a rule that can be
  bypassed. *Medium* -- a wrong record or a broken screen with a workaround.
  *Low* -- wording, a missing label, a convenience.
- **Evidence.** *Live* -- seen in real rows or on screen. *Code* -- read off the
  code and not yet driven. Drive a *Code* row before fixing it.

---

## Open

### Buying -- found writing the Buying data trail, 2026-09-18

Full write-ups: PR #435 and `docs/DATA_TRAIL_BY_OPERATION.md` §9.

| Id | Severity | Summary | Evidence |
| --- | --- | --- | --- |
| D-BUY-1 | High | **Purchase approval can be skipped.** The create request accepts `status`, so a purchase order can be saved straight as APPROVED with no submit or approval. `backend/app/purchase/schemas/purchase.py` (`status: PurchaseOrderStatus = PurchaseOrderStatus.DRAFT` on the create model), written as given by `purchase_service.py`. | Live: 64 orders in `firm_shared` went straight to APPROVED with no approval history |
| D-BUY-2 | High | **Cancelling an approved supplier invoice leaves its journal posted.** `cancel_invoice` in `purchase_invoice_service.py` only changes the status. The goods receipt then becomes cancellable again, and cancelling it debits goods-received-not-invoiced (2300) a second time. | Code |
| D-BUY-3 | High | **A purchase return with no price is valued at zero.** `unit_price` defaults to 0 on the return line (`purchase_return/schemas/purchase_return.py`) and the service does not fall back to the receipt's price, so the stock's value goes to 5400 and the payable is debited nothing. The purchase invoice line has the same default. The seeder sends no price. | Live: every seeded return (6 in WHOLE01, 12 in `firm_shared`) and TEST01's PR-2026-2027-000001 are 0.00 |
| D-BUY-4 | Medium | **A reversal journal is dated the first day of the original's period**, not the day of the cancel (`finance/services/journal_engine.py`). A cancel on the 16th posts on the 1st. | Live: GRN-TEST01-...-000003's reversal |
| D-BUY-5 | Medium | **Invoices and returns do not check that the source receipt is COMPLETED** (`purchase_invoice_service.py`, `purchase_return_service.py`). | Code |
| D-BUY-6 | Medium | **A purchase return does not lower what the supplier's bill still owes** (`settlements/services/settlement_service.py`). | Code |
| D-BUY-7 | Medium | **Invoicing part of a receipt line clears the whole line's accrual** (`_accrued_cost` in `purchase_invoice_service.py`). | Code |
| D-BUY-8 | Low | Three small ones: a supplier advance can never be allocated after it is recorded; receiving that moves an order's status writes an audit row but no history row; an edit's two history rows share one timestamp. | Code |

### Stock -- found writing the Stock data trail, 2026-09-18

Full write-ups: the PR that added `docs/DATA_TRAIL_BY_OPERATION.md` §10, and
the section itself. BL-31.13 (the Stock Ledger's type filter) already covers
the filter and is not repeated here.

| Id | Severity | Summary | Evidence |
| --- | --- | --- | --- |
| D-STK-1 | High | **A physical count adjusts the wrong row for a batch line.** `PhysicalCountService.post` measures the variance against the batch's own stock row but posts the adjustment through `InventoryAdjustmentCreate`, which has no `batch_id` (`backend/app/inventory/schemas/inventory.py`), so `create_adjustment` lands it on the product's untracked row -- creating one if there is none -- and the batch row never corrects (`backend/app/inventory/services/physical_count_service.py`, `post`; `inventory_service.py`, `create_adjustment`). | Code -- no store holds a count over a batch row |
| D-STK-2 | High | **A sales order reserves expired stock.** `allocate_for_reservation` ranks batches by expiry with expired ones included; only `allocate_for_dispatch` skips them (D-8-1). The hold sits on stock that can never ship while the in-date batch stays free to be promised to a second order (`backend/app/inventory/services/inventory_service.py`, `allocate_for_reservation`). | Live: both pharmacy fixture stores reserve SO-2026-2027-000001 on `-B1` (expired 2026-08-17) and dispatch from `-B2` |
| D-STK-3 | Medium | **Posting a count commits per adjusted line.** `create_adjustment` commits inside the loop in `PhysicalCountService.post`, so a failure on a later line leaves earlier lines adjusted, journaled and committed while the sheet stays DRAFT; re-posting rewrites their `variance_quantity` to 0 beside a `transaction_id` that still points at the movement. | Code |
| D-STK-4 | Medium | **A serial number's status never moves.** Nothing outside `app/batch_serial` reads or writes `serial_numbers`; no movement sets `inventory_transactions.serial_id`, so a serialised unit that is dispatched stays `AVAILABLE`. | Live: zero movements carry `serial_id` or `lot_id` in nineteen stores; Code |
| D-STK-5 | Low | **A count with nothing counted can be posted**, reading POSTED with `adjusted_lines` 0 (`PhysicalCountService.post` has no "at least one counted line" check). | Live: WHOLE01 `PC-2026-2027-000005` |
| D-STK-6 | Low | **Two writes with no named audit row:** a quarantine hold or release leaves only `inventory.transaction.created` (`quarantine_stock` calls no `record_audit`), and Save progress on a count (`PhysicalCountService.update`) writes none. | Live (the hold's request holds one audit row); Code |
| D-STK-7 | Low | **A cancelled order's release is dated today (UTC) while its reservation is dated the order date** (`sales_order_service.py`, `_release_inventory` vs `_reserve_inventory`), so the ledger shows the release before the hold. | Live: WHOLE01 SO-2026-2027-000015 to 000018, reserved 2026-09-13, released 2026-09-12 |
| D-STK-8 | Low | **Expiry Monitor's "Expired Today" and "Total Expired" are the same count** (`expiry_dashboard` evaluates `expired_condition(today)` for both), and every card counts `batches` rows whether or not any stock is left. | Code |
| D-STK-9 | Low | **A reversing movement is dated the original's `transaction_date`** (`reverse_transaction`), so the stock ledger by date shows the goods leaving the day they arrived and `inventories.last_transaction_at` goes backwards -- the stock-side twin of D-BUY-4. | Live: WHOLE01 `SALES_RETURN_REVERSAL` for SR-2026-2027-000002 dated 2026-08-19 |
| D-STK-10 | Low | **Batch and serial audit rows are bare `CREATE` / `UPDATE` / `DELETE` with empty `after_data`**, unlike every other module's `module.action` naming, so an exact-match filter for `batch.created` finds nothing; and `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md` still lists quantity columns on `batches` that the model no longer has, while the `InventoryTransactionType` docstring says counts and write-offs are unbuilt. | Live (the rows); Code (the docs) |

### Found in manual testing and not yet fixed -- `docs/BACKLOG.md` §31

| Id | Severity | Summary | Evidence |
| --- | --- | --- | --- |
| BL-31.9 | High | **A purchase invoice cannot be raised from the desktop.** The Purchase Invoices screen offers View, Approve, Cancel and Close only; nothing calls `POST /api/v1/purchase-invoices`. Test cases that need one use the API or a seeded invoice. | Live, re-checked 2026-09-18 |
| BL-31.13 | Medium | **The Stock Ledger's type filter lists movements the server never writes** (`GOODS_ISSUE`, `PHYSICAL_COUNT`, `RESERVATION`, `DAMAGE`, `EXPIRY`, `QUARANTINE`, `CORRECTION`, ...) and leaves out the real ones (`DISPATCH`, `WRITE_OFF`, `QUARANTINE_HOLD`, the reversals). `inventory_management_page.dart`. | Re-checked in code 2026-09-18 |
| BL-31.14 | Low | **What a saved sales document does not show:** the resolved discount percentage, the coupon, labels on the Allocate/Reverse icons, default invoice print copies. One decision inside it: whether a coupon should apply to an order converted from a quotation. (Its "Line 1" item was fixed in #398.) | As recorded 2026-09-13, not re-checked |
| BL-31.15 | Low | **Small gaps from sections 10-13:** no source-module filter on Journal Entries; Ctrl+K hides a failing search; the Loyalty page cannot show one customer's balance; promotion conditions print raw; targets cannot name a salesman from the desktop; two reports missing from the catalogue. | As recorded 2026-09-13, not re-checked |
| BL-31.16 | Low | **A refused password says only "does not meet the configured policy"** while the server sends which rule broke (`core/validation/common.py` passes `details`). | Server side re-checked 2026-09-18 |
| BL-31.17 | Low | **Audit trail filters match exactly**, so typing `user` finds nothing (`common/audit/services/reader.py`: `AuditLog.action == filters.action`). | Re-checked in code 2026-09-18 |

---

## Fixed

| Id | Fixed | Summary | PR | Guard |
| --- | --- | --- | --- | --- |
| D-SETUP-1 | 2026-09-18 | Setup.exe's database step ran hidden and its exit code was never read, so a failed install reported success. | #432 | compiled; probe of `ExecAndCaptureOutput` |
| D-SETUP-2 | 2026-09-18 | Every Setup upgrade failed before its migrations: `ALTER ROLE ... WITH LOGIN` is refused to a non-superuser. | #432 | `tests/integration/test_database_bootstrap.py` |
| D-SETUP-3 | 2026-09-18 | The generated administrator password was lost in the hidden window. | #432 | -- |
| D-SETUP-4 | 2026-09-18 | `.env.example` shipped `AGENCY_APP_VERSION=0.1.0` and a live `REMOTE_A` profile into every customer's settings. | #433 | `tests/unit/test_env_template.py` |
| D-SETUP-5 | 2026-09-18 | The `-SkipStart` hint left out `-SkipSync`; an install folder with a space in its path never started the backend. | #434 | probe run; `tests/unit/test_cli_entry_point.py` |
| D-27-5 | 2026-09-16 | A firm whose people had been deleted could never be deleted. | #419 | `test_a_firm_whose_people_were_deleted_can_still_be_deleted` |
| D-2-1 | 2026-09-16 | A wrong password on an inactive or expired account named the account's state. | #418 | `test_a_wrong_password_never_names_the_state` |
| D-8-1 | 2026-09-16 | Dispatch drew an expired batch. | #418 | three tests in `test_inventory_foundation.py` |
| D-11-1 | 2026-09-16 | A new firm's territory hierarchy was invented on every read and never saved. | #418 | `test_a_new_firms_hierarchy_is_written_by_the_read_that_invents_it` |
| D-20-1 | 2026-09-16 | Asking for roles on somebody in no firm refused after the account was already made. | #418 | `save_refusal_keeps_the_record_test.dart` |
| D-27-1 to D-27-4 | 2026-09-16 | Product custom fields: an applicable field was never offered, a mandatory one blocked every product, an inert rule was enforced, a withdrawn choice could not be saved back. | #418 | `test_product_master.py`, `test_entity_attributes.py` |
| BL-31.3 | 2026-09-13 | Document views showed raw ids instead of product, unit, tax profile and customer names. | commits `43f949d`, `dccbf65`; #398 | `desktop/test/document_line_labels_test.dart` |
| BL-31.1, 31.2, 31.4-31.8, 31.10-31.12 | 2026-09-09 to 09-12 | Found in manual testing and fixed the same day; each is written up in `docs/BACKLOG.md` §31. | see §31 | see §31 |

Defects found and fixed during the manual-testing runs of 2026-09-13 to 09-15
(#336-#413) are recorded in each PR and in the plan-correction PRs for their
section; they were not given ids, and are not repeated here.

## Not a defect

| Id | Decided | Summary | Reason |
| --- | --- | --- | --- |
| TC-ROLE-009 | open decision | Deleting a role that people hold goes through with no warning, and they are left with an empty sidebar. | Recorded as the behaviour, not a defect; whether it should refuse or warn with a count is the owner's decision. |
