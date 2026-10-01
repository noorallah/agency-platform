# Phase 2 dialog review against the dialog standard

Owner, 2026-09-29: review, for the new UI, every form that opens on a click
(Change password and the like). The standard is drawn in view 11 "Dialogs" of
`dist/windows/Design/UI phase 2 wireframes.html` and recorded in
`docs/BACKLOG.md` §73; the defects found are `D-DLG-1`..`D-DLG-10` in
`docs/DEFECTS.md`. Checked by reading the code; five findings were confirmed
by hand the same day (the numbering-series text, the tax simple dialog, the
two uses of `AppDialogs.confirm`, the price-list delete with no confirm, the
geography editor closing before its save). A screenshot pass against the
running backend has not been done.

Date: 2026-09-29
Scope: `desktop/lib` (phase 2 UI at `lib/main_phase2.dart` + `lib/phase2/`, reusing most
dialogs from `lib/ui/`). Read-only code review — no files edited, no tests run.

Method: code read (Grep + Read of the Dart source), not screenshots or a running app.

## Checklist applied to every dialog (D1-D9)

- D1 Kind: a document (order/invoice/receipt...) or a master record (customer/product/
  vendor...) should be a full-page tab, not a dialog; a short task (<= ~6 fields, one
  decision) is a dialog; a yes/no is a confirm.
- D2 Title names the action ("Change password"); no internal codes/ids/capitals.
- D3 Buttons: primary on the right named by its verb (not "OK"/"Submit"/"Yes"); Cancel
  beside it; destructive action names what it destroys.
- D4 Keyboard: first field autofocused; Enter submits; Esc closes (Flutter dialogs do by
  default unless `barrierDismissible`/`PopScope` blocks it — note if blocked without
  reason).
- D5 Errors: validation under the field; server error shown INSIDE the dialog, dialog
  stays open, typed values kept. Flag SnackBar-only errors, or dialogs that pop before
  the request finishes.
- D6 Busy: submit button disabled/shows progress while saving; double submit impossible.
- D7 Size: explicit width; AlertDialog content with unbounded height that can overflow
  at 1366x768.
- D8 Readability: hard-coded colours instead of design tokens/Theme; text below 13px;
  statuses in CAPITALS or raw enum names.
- D9 Unsaved changes: a dialog with several editable fields that closes on Esc/outside
  click and silently drops edits.

Severity: **High** = D1 (a document/master in a dialog), D5 error lost or dialog pops
before save, D7 overflow risk, or an action unreachable. **Medium** = D3/D4/D6/D9.
**Low** = D2/D8 and cosmetic.

## Summary

**152 `showDialog` call sites, 105 `AlertDialog`s, 59 `WorkspaceDialog`/`CrudWorkspaceDialog` uses across 69 files, plus the 22 `ResourceDefinition` create/edit forms and `askForReason`** were reviewed by code reading (this agent covered the shared framework + Accounts/Admin/Settings directly; two areas — Masters+Stock and Sell+Buy — were reviewed by delegated sub-passes over the same file list and merged in below).

Of roughly 150 distinct dialogs, **about 69 have at least one finding**:

| Severity | Count (approx.) | Dominant cause |
| --- | --- | --- |
| High | ~35 | **A dialog pops/closes before the server confirms the write** (see Shared fixes #6) — about 25 of the 35; the rest are a document/master record squeezed into a dialog (D1), an unbounded-height overflow risk (D7), a destructive action with **no confirmation dialog at all** (5 instances), and one literal content bug (`${rule.name}` shown verbatim). |
| Medium | ~15 | Mostly D9 (no dirty-check before Escape/outside-tap discards several typed fields) and D4 (no autofocus/Enter-submit on a short task dialog), plus a few D3 (generic "Confirm" button text). |
| Low | ~19 | Almost all D8 — hand-rolled confirms duplicating `AppDialogs.confirm` (often losing its destructive red styling or copy-pasting a hardcoded `Colors.red.shade700`), password fields with no show/hide toggle, Title-Case-vs-sentence-case inconsistency, sub-13px text. |

**Top issues, in order of what to fix first:**
1. **The close-before-save pattern is systemic, not a one-off** — the dialog pops its typed values immediately on "Save" and the actual `create*`/`update*` API call runs afterward in the *caller*; a server rejection then shows only as a toast with the dialog already gone and the typed values lost. Found in ~25 dialogs across Masters, Stock, and two Sell dialogs (proforma raise, e-way bill) — territory/beat-plan/branch/warehouse/storage-node/copy-hierarchy editors, the 4 territory assignment pickers, the geography place editor, the UOM "simple dialog" cluster (4 masters), all 3 inventory master forms' siblings (thresholds editor, new inventory adjustment, opening-stock draft, stock-action dialog), and the tax "simple dialog" cluster (5 entity types). A small number of dialogs in the same codebase do this correctly (`_PackagingLevelDialog`, `ConversionRuleDialog`, `CouponDialog`, `CreditSettingsDialog`, `CrudWorkspaceDialog`, `CreditNoteDialog`) and are the pattern to copy.
2. **`_taxSimpleDialog`** (`ui/tax/tax_management_page.dart:1507-1567`) is the single worst offender: one generic `AlertDialog` of raw, snake_case-labelled `TextField`s — including hand-typed JSON for a tax rule's `conditions` and a tax profile's `components` — used to create/edit 5 different master-record types, on top of the close-before-save bug and an undisposed controller map.
3. **Five destructive actions have *no* confirmation dialog at all** (not just a weak one): delete storage node/branch type/warehouse type (`branch_warehouse_management_page.dart:838-855`), delete price list (`price_list_page.dart:133-152`), delete/retire promotion (`promotion_page.dart:197-215`), remove a customer group (`customer_group_dialog.dart:225-229`), and delete a sales target (`sales_target_page.dart:119-137`). Every one sits beside sibling code in the same file that confirms correctly, so these read as omissions.
4. **`AppDialogs.confirm`, a correctly built, destructively-styled confirm helper, is used in only 2 of ~100+ plain yes/no confirmations app-wide** — see Shared fixes.
5. **No shared password field** — 6 of 7 password inputs across the app (change/reset password, clone-user temp password, initial-forced-password-change) have no show/hide toggle; only the sign-in screen's does.
6. **One real content bug**: "Retire numbering series" (`ui/settings/numbering_series_page.dart:146`) shows the literal text `${rule.name}` to the user because of a stray `\$` escape.

## Sell

*A phase-2 route check (per instructions) found no orphaned phase-1-only document dialogs: every sales/purchase document type has both a phase-2 menu route and shares its editor widget between phase 1 (`showDialog`) and phase 2 (`showDocument`, opened as a tab) via `Phase2Scope.of(context)` branching — same source file either way, not a fork.*

| Dialog (what opens it) | File:line | Checks failed | What is wrong (one line) |
| --- | --- | --- | --- |
| Withdraw registration / withdraw e-way bill (`_askReason`) | `ui/sales/einvoice_page.dart:250-281` | High: D9-class bug, D3, D4 | Hand-rolled reimplementation of `askForReason` that reintroduces the exact "controller disposed during the dialog's close animation" bug `reason_prompt.dart`'s own doc comment records as already fixed elsewhere; also no `onSubmitted` (Enter doesn't submit). |
| Raise a proforma | `ui/sales/proforma_page.dart:658-770` (`_RaiseProformaDialog`) | High: D5 | Pops immediately with the typed values; the actual `createProformaInvoice` call runs in the caller — a server error leaves the dialog already gone and the toast the only feedback. |
| E-way bill | `ui/sales/einvoice_page.dart:606-737` (`EWayBillDialog`) | High: D5 | Same close-before-save pattern — `generateEwayBill` and its error happen after the dialog has closed. |
| Delete a sales target | `ui/commission/sales_target_page.dart:119-137`, called from :229, :343 | High: missing confirm | No confirmation dialog anywhere in the call chain (toolbar action and grid context-menu both go straight to `deleteSalesTarget`). |
| Withdraw offer | `ui/quotations/quotation_management_page.dart:889-936` (`_ReasonDialog`) | Medium: D4 | Own hand-rolled reason dialog (correct controller lifecycle, unlike einvoice's) but no `onSubmitted` — Enter doesn't submit. |
| Cancel a sales return | `ui/sales_returns/sales_return_management_page.dart:828-882` (`_CancelReasonDialog`) | Medium: D4/D7 | Third reimplementation of a reason prompt instead of reusing `askForReason`; no explicit width, no Enter-submit. |
| Add/edit a commission rate | `ui/commission/commission_page.dart:1089-1353` (`CommissionRuleDialog`) | Medium: D1 (borderline), D9 | 12+ fields plus a dynamic slab-ladder editor, opened as a plain `AlertDialog` (Esc/outside-tap dismissible by default) rather than `WorkspaceDialog`; no dirty-check before an accidental dismissal discards a fully-typed rule. |
| Adjust a commission payout | `ui/commission/payout_dialogs.dart:280-435` (`CommissionAdjustmentDialog`) | Medium: D8, D9 | Hard-coded `Colors.redAccent` for error text where every sibling dialog in the same file uses `theme.colorScheme.error`; several editable fields, no dirty-check on close. |
| New/edit sales target | `ui/commission/sales_target_page.dart:511-628` (`_SalesTargetDialog`) | Medium: D9, D4 | Several editable fields, no dirty-check on close; no autofocus/Enter-submit. |
| Redeem loyalty points on an invoice | `ui/sales/sales_invoice_management_page.dart:816-824` | Low | Reuses `askForReason`'s free-text prompt for a numeric "points to use" field — no numeric keyboard, no inline check that the input is a number before it is sent. |
| TCS settings | `ui/sales/tcs_page.dart:399-535` (`_TcsSettingsDialog`) | Low: D8 | Otherwise solid (inline error, busy state); the four numeric rate/threshold fields are plain `TextField`s with no `keyboardType`. |
| `DocumentViewDialog` read-only call sites; Hold a sales order; Withdraw a proforma; read one quotation/credit note/proforma/sales return; Raise a credit note; Commission accrual/payment dialogs; New/edit/remove customer group; Register e-invoice / raise e-way bill picker | `ui/sales/sales_order_management_page.dart:408,724-753`; `ui/sales/sales_invoice_management_page.dart:357`; `ui/delivery_notes/delivery_note_management_page.dart:378`; `ui/sales/proforma_page.dart:245-261,552-566`; `ui/quotations/quotation_management_page.dart:631-676`; `ui/sales/credit_note_page.dart:384-438,590-907`; `ui/sales_returns/sales_return_management_page.dart:557-587`; `ui/commission/payout_dialogs.dart:24-270`; `phase2/customer_groups_page.dart:106-384`; `ui/sales/einvoice_page.dart:606-802` | — | Pass. `phase2/customer_groups_page.dart:256-384` (`_GroupEditor`) is the best short-task dialog found in this batch: autofocus, Enter submits, busy state, inline error, explicit width. Its "Remove group" confirm (:106-128) is one of only two app-wide uses of `AppDialogs.confirm`, with a correct verb label (`'Remove'`). |

## Buy

| Dialog | File:line | Checks failed | What is wrong |
| --- | --- | --- | --- |
| Cancel / Close purchase order (`_ReasonDialog`) | `ui/purchases/purchase_management_page.dart:4342-4381`, called from :684, :1581-1603, :1726-1751 | Medium: D3 | Primary button is hard-coded `'Confirm'` regardless of the dialog's title — reused for both "Cancel purchase order" and "Close purchase order", never names the verb. |
| Add Note | `ui/purchases/purchase_management_page.dart:4384-4445` (`_NoteDialog`) | Low: D5, D2 | Pressing "Add" with an empty note silently no-ops with no inline error; Title Case labels ("Add Note", "Note Type") break the sentence-case convention used elsewhere. |
| Column Chooser | `ui/purchases/purchase_management_page.dart:4447-4518` | Low: D2 | Title Case ("Column Chooser") inconsistent with the sentence-case convention used everywhere else reviewed. |
| Export Purchase Orders | `ui/purchases/purchase_management_page.dart:4520-4593` | Low: D2 | Same Title Case inconsistency ("Export Purchase Orders", "Scope"). |
| Import wizard | `ui/purchases/purchase_management_page.dart:705-729`, class at :4061+ (`PurchaseImportWizard`) | Not deep-reviewed | Explicit 960×720, `barrierDismissible: false` — a substantial multi-step wizard, arguably outside the "≤6 fields" dialog category (like the excluded document editors); flagged for a closer pass rather than line-by-line reviewed here. |
| Preview an attachment; Delete selected order(s); `DocumentViewDialog`/`GoodsReceiptViewDialog` read-only call sites; print-settings openers | `ui/purchases/purchase_management_page.dart:3322-3341,625-657,1212-1222`; `ui/purchase_invoices/purchase_invoice_management_page.dart:597`; `ui/purchase_returns/purchase_return_management_page.dart:611`; `ui/goods_receipts/goods_receipt_management_page.dart:763-775`; `ui/sales/sales_invoice_management_page.dart:484-494`; `ui/delivery_notes/delivery_note_management_page.dart:618-628` | — | Pass. The delete-selected-order confirm correctly uses `showWorkspaceConfirmDialog` with `ConfirmationType.delete` and a verb label. Note: `GoodsReceiptViewDialog`'s own docstring calls itself "a second copy" of the shared `DocumentViewDialog` — worth merging if anyone touches goods receipts. |

*(Stock's table appears after Masters below — Masters and Stock were reviewed together as one sub-pass, in that order.)*

## Accounts (Finance, Tax)

| Dialog (what opens it) | File:line | Checks failed | What is wrong (one line) |
| --- | --- | --- | --- |
| Create/Edit tax component, tax profile, country mapping, migration mapping, tax rule (one shared helper, 5 call sites) | `ui/tax/tax_management_page.dart:1507-1567` (helper), called at :1298, :1331, :1365, :1393, :1423 | High: D1, D2, D5 | A master record — including a tax rule's JSON `conditions` array and a tax profile's JSON `components` array — is edited as a bare list of `TextField`s labelled by the raw snake_case API key (`tax_system_id`, `is_default`, `components`…). Worse, `Navigator.pop(context, payload)` closes the dialog on Save and the actual create/update call runs afterwards in the caller; a server refusal shows only as a transient toast with the dialog already gone and everything typed lost. Repeated for 5 entity types. |
| Same dialog | `ui/tax/tax_management_page.dart:1513-1516` | Controller leak | The `Map<String, TextEditingController>` built per open is never disposed. |
| Delete Tax System? / Delete Tax Profile? / Delete Tax Rule? | `ui/tax/tax_configuration_page.dart:419-450`, `:1438-1468`, `ui/tax/tax_rules_page.dart:558-599` | Low: D8 | Three separate copies of the same hand-rolled confirm, each hardcoding `Colors.red.shade700` instead of the theme's error colour; all duplicate `AppDialogs.confirm(ConfirmationType.delete)`, which already gives this for free. |
| Delete journal entry (draft) | `ui/finance/journal_entries_page.dart:261-280` | Low: D8 | Hand-rolled confirm; Delete button has no destructive styling at all; duplicates `AppDialogs.confirm`. |
| Reverse journal entry | `ui/finance/journal_entries_page.dart:357-389` | Medium: D3/D4 | Hand-rolled confirm + a reference `TextField` with no autofocus/Enter-submit; an irreversible action's button has no warning styling. |
| Reverse settlement (receipt/payment) | `ui/finance/settlements_page.dart:582-648` | Medium: D3/D4 | Hand-rolled reason prompt duplicating `askForReason` but without its autofocus, Enter-submit, or requiring a non-empty reason before the destructive button enables. |
| Apply settlement / set supplier credit against a bill | `ui/finance/settlements_page.dart:906-1007` (opened from :676, :791) | Medium: D4 | Amount field has no `keyboardType`, no numeric validator, no autofocus; only checks non-empty before submitting. |
| Open one audit entry | `ui/settings/audit_log_page.dart:353-367` | High: D7 | `SizedBox(width: 560, ...)` bounds width only; the inner `_detail` is a `SingleChildScrollView` that can render a long field-change table with **no height bound**, so a busy audit row can overflow at 1366x768/800x600. |
| Delete accounting period | `ui/settings/financial_years_page.dart:110-147` | Low: D8 | Plain hand-rolled confirm, non-red Delete button, duplicates `AppDialogs.confirm(ConfirmationType.delete)`. |
| Retire numbering series | `ui/settings/numbering_series_page.dart:140-174` | High: content bug | Line 146 has an escaped `\$`, so the dialog literally displays the text `${rule.name}` instead of the series name — a real user-visible bug. Also a plain hand-rolled confirm. |
| View journal entry lines | `ui/finance/journal_entry_view_dialog.dart:16-135` | Low: D8 | Otherwise clean (bounded 760px, scrollable, accounts shown as code+name) but `entry.status` is dropped into plain `Text` with no formatting, while the list screen right beside it wraps the same field in `StatusBadge` — likely shows a raw enum like `POSTED`. |
| Diagnostics report (Copy / Save / Reveal) | `core/diagnostics/diagnostics_share.dart:85-198` | Low: D8 | Otherwise strong (bounded scroll box maxHeight 320, explicit note that no passwords/tokens are included); monospace report text is 11px, below the 13px floor. |
| Whose credit? / Which return? (party/credit pickers), View settlement, Map/change control account, Diagnostics report detail | `ui/finance/settlements_page.dart:511-574,735-746,775-789`; `ui/finance/control_accounts_page.dart:304-353`; `ui/settings/diagnostics_page.dart:340-362` | — | Pass. |
| Record Receipt/Payment/Refund; numbering series create/edit | `ui/finance/record_settlement_dialog.dart` (opened from `settlements_page.dart:141`); `ui/settings/numbering_series_editor.dart` (opened from `numbering_series_page.dart:115-120`) | Not reviewed | Both files are outside this audit's file list — only their call sites were seen; flagged as open. |

## Masters

(Also see "Default units for a business profile", `ui/uom/profile_uom_defaults_dialog.dart`, reviewed under Shared framework above.)

| Dialog (what opens it) | File:line | Checks failed | What is wrong (one line) |
| --- | --- | --- | --- |
| Product / Customer / Vendor create-edit form | `product_management_page.dart:805-831`, `customer_management_page.dart:248-285`, `vendor_management_page.dart:155-170` | (skipped, per scope) | These are the doc/master forms phase 2 replaced with a full-page tab (`showDocument`) — but phase 2's menu routes `masters/products\|customers\|vendors` to these *same* page widgets (not a separate phase-2-only screen), so the phase-1 `WorkspaceDialog` fallback is still the live path whenever `Phase2Scope` reads false, not dead code. |
| Save filter (Products) | `product_management_page.dart:994-1016` | Medium: D4; leak | Plain `AlertDialog`, `TextEditingController` created loose and never disposed; no autofocus, Enter doesn't submit this 1-field dialog. |
| Product import wizard, step 4/5 | `product_management_page.dart:1054-1065, 3401-3464` | High: D5 | `widget.onImport(_preview)` loops `api.createProduct` per row with no try/catch and no staging — a mid-batch failure throws uncaught, leaving an unknown number of rows already created and no error shown in the wizard. |
| Industry Template / UOM / UOM Group / Packaging Type create-edit (`_simpleDialog`, one helper, 4 call sites) | `uom_management_page.dart:871-925` (helper), called at 513, 554, 594, 698 | Low: D8; Medium: D5 | One generic `AlertDialog` reused for 4 different masters: every field is a raw `TextField`, `status`/`industry_type` are free text instead of dropdowns, and an auto-coercion (`_coerce`) can silently turn a typed "true"/"5" into bool/number even for name-like fields. |
| Conversion rule / Territory / Beat plan / Branch / Warehouse / Type / Storage node / Copy-hierarchy create-edit (systemic pattern) | `uom_management_page.dart:659-695`; `sales_territory_management_page.dart:168-207,1548,632-697`; `beat_plan_management_page.dart:126-171,544`; `branch_warehouse_management_page.dart:920-1037,1182,1540,1795,1881` | High: D5 | Every one of these dialogs pops its payload immediately on Save, and the real `create*`/`update*` API call runs in the **caller** afterward — a server rejection surfaces only as a toast after the dialog is already gone, and for a create, everything typed is lost and must be re-entered. This is the dominant pattern across the whole Masters area (contrast with `_PackagingLevelDialog`/`ConversionRuleDialog`, which do it correctly). |
| Territory editor | `sales_territory_management_page.dart:1547-1560` | Medium: D1/D7 | 560×520, scrollable, but this is really a multi-section master record (route type, geography ladder, working days, effective dates) squeezed into a dialog rather than given a page. |
| Assign customers / Assign salesmen / Set call order / Bulk territory actions | `sales_territory_management_page.dart:258-429,437-570` | High: D5 | `AssignmentPickerDialog`/`CallOrderDialog`/`BulkTerritoryActionsDialog` all close before `setTerritoryCustomers`/`setTerritorySalesmen`/`bulkTerritory*` run; failure is a toast, picks are lost. |
| Customer group "Remove" (× icon) | `customer_group_dialog.dart:154-168,225-229` | Medium: D9/D3 | Deletes a group immediately on icon tap — **no confirmation at all**. |
| Delete: storage node / branch type / warehouse type | `branch_warehouse_management_page.dart:838-855` | High: missing confirm | `_deleteSelected` calls the delete API directly with no confirm dialog, while the sibling branch/warehouse deletes three lines away (1039-1068) correctly use `showWorkspaceConfirmDialog` — an inconsistency within the same file. |
| Delete price list | `price_list_page.dart:133-152` | High: missing confirm | `_delete` calls the API immediately, no confirmation step. |
| Delete/retire promotion | `promotion_page.dart:197-215` | High: missing confirm | `_delete` calls the API with no confirm, while `_deleteCoupon` three lines away (153-173) correctly uses `showWorkspaceConfirmDialog`. |
| Geography place editor | `geography_master_page.dart:133-167,429-546` | High: D5; Medium: D4 | `_GeoEditorDialog` pops the record and the real create/update call runs afterward in `_openEditor` — same close-before-save pattern; also a 5-field dialog with no autofocus and Enter doesn't submit. |
| Price list / Promotion "view" dialog | `price_list_page.dart:304-318`, `promotion_page.dart:369-384` | Low: D2 | Plain `AlertDialog` with no title, just content + Close. |
| `TerritoryTreeDialog`, `_PackagingLevelDialog`, `ConversionRuleDialog`, `CreditSettingsDialog`, `CustomerGroupDialog` create/edit, `CouponDialog` | `territory_tree_dialog.dart`; `packaging_levels_page.dart:159-674`; `uom_management_page.dart:945-1146`; `credit_settings_dialog.dart`; `customer_group_dialog.dart`; `coupon_dialog.dart` | — | Pass (aside from the missing delete confirm on `CustomerGroupDialog` noted above and a hardcoded error colour in `CouponDialog`). |

## Stock

| Dialog (what opens it) | File:line | Checks failed | What is wrong (one line) |
| --- | --- | --- | --- |
| Delete batch / Delete lot / Delete serial | `batch_management_page.dart:977-1006,1037-1065,1096-1124` | Low: duplicate | Three hand-rolled plain yes/no `AlertDialog`s duplicating `showWorkspaceConfirmDialog`/`AppDialogs.confirm`, which this same file uses correctly elsewhere. |
| Batch / Lot / Serial create-edit form | `batch_management_page.dart:1152-1317` (`_BatchFormDialog`), `~1319-1403` (`_LotFormDialog`), `~1574` (`_SerialFormDialog`) | High: D5 (x3) | Otherwise well built (busy spinner, controllers in `State`, disposed, dialog stays open on failure) — but a server rejection shows via `ScaffoldMessenger.showSnackBar`, which renders **behind the dialog's modal barrier** and is effectively invisible while the dialog is up. |
| Inventory thresholds editor | `inventory_management_page.dart:1540-1662` | High: D5; leak | `minimum/maximum/reorder/safety` controllers created loose and never disposed; dialog pops `submitted=true` before the real `updateInventoryRecord` call runs — close-before-save pattern, error is a toast. |
| New inventory adjustment | `inventory_management_page.dart:1757-1788,2159-2405` | High: D5 | Otherwise well built (controllers in `State`, disposed, sensible defaults) but still pops the draft before `createInventoryAdjustment` posts — a ledger-posting action whose failure discards every typed line with no recovery. |
| New / edit opening stock draft | `inventory_management_page.dart:1790-1805,2501-2587+` | Medium: D7; High: D5 | 900px-wide multi-line document editor (branch/warehouse/lines with batch, expiry, min/max/reorder/safety per line) has no `maxHeight` on its scroll view — overflow risk at 1366×768 as lines are added; also pops before the create/update call runs, same close-before-save pattern. |
| Stock action (transfer / write-off / quarantine) | `inventory_management_page.dart:1695-1755` | High: D5 | `StockActionDialog` closes before `transferStock`/`writeOffStock`/`quarantineStock` runs; failure is a toast. |
| Open a count / Post count confirmation / Abandon sheet | `physical_count_sheet_dialog.dart:17-140,294-326,261-292` | — | Pass: inline `MaterialBanner` error and stays open; Post/Abandon each name what happens and use distinct buttons; Abandon uses `showWorkspaceConfirmDialog` and shows a busy state while cancelling. |
| Inventory details (view) | `inventory_details_dialog.dart` | — | Pass: sized, titled, read-only, good actions. |

## Admin / Identity

| Dialog | File:line | Checks failed | What is wrong |
| --- | --- | --- | --- |
| Change password (My profile) | `ui/identity/change_password_dialog.dart:22-175` | Low: D8 | Otherwise a strong reference (client-side policy check next to the box, autofocus, Enter-submit via `onFieldSubmitted`, server refusal shown inline with the dialog staying open) — but none of its three `obscureText: true` fields (lines 127, 138, 151) has a show/hide toggle, unlike the sign-in screen's password field. |
| Reset password (admin → user) | `ui/identity/reset_password_dialog.dart:29-172` | Low: D8 | Same strengths (inline refusal, autofocus, Enter-submit) and the same gap — `obscureText: true` at lines 119, 132 with no visibility toggle. |
| Hire like this person (clone user) | `ui/administration/clone_user_dialog.dart:33-179` | Medium: D4; Low: D8 | Good D5 handling (server refusal shown inline, dialog stays open, values kept). But no field is autofocused, nothing wires Enter-to-submit, and the password field (line 114) has no show/hide toggle. |
| Roles by firm | `ui/identity/firm_roles_dialog.dart:18-383` | Medium: D9 | A plain `Dialog`, `barrierDismissible` left at its default (true), no dirty-check. Toggling role chips for a firm then dismissing via Escape/outside-tap/the plain "Close" button (188-191) silently drops those edits. |
| Apply a job template | `ui/administration/apply_template_dialog.dart:17-207` | Low: D4 | Solid overall (own controller disposed, bounded 520x380, search autofocused); no Enter-to-apply the highlighted row. |
| Application Settings (sign-in screen) | `ui/auth_screens.dart:304-457` | Low: D4 | Bounded (520 + scroll); API URL field has no autofocus/Enter-to-save. Cancel/Escape correctly drops nothing since no write has happened yet. |
| Add existing user (find person); Primary firm; My profile; Set up {firm} (firm setup); Password assistance; Sign-in password field | `ui/administration/find_person_dialog.dart:34-301`; `ui/identity/primary_firm_dialog.dart:15-94`; `ui/identity/profile_dialog.dart:17-265`; `ui/firms/firm_setup_dialog.dart:23-363`; `ui/auth_screens.dart:459-474`; `ui/auth_screens.dart:898-926` | — | Pass. The sign-in password field (898-926) has a correctly built show/hide `IconButton` — the reference the other password fields above should match. |

## Settings

Covered above in the Accounts table (audit log, financial years, numbering series, diagnostics) since that pass reviewed Accounts/Admin/Settings together — see the rows for `ui/settings/audit_log_page.dart`, `ui/settings/financial_years_page.dart`, `ui/settings/numbering_series_page.dart`, `ui/settings/diagnostics_page.dart` and `core/diagnostics/diagnostics_share.dart`.

## Shared framework

| Dialog (what the user clicks to open it) | File:line | Checks failed | What is wrong (one line) |
| --- | --- | --- | --- |
| Global search (Ctrl+K / Ctrl+F) | `ui/workspace/global_search.dart:232` (`_GlobalSearchDialog` build at :406) | none | Sized 980x700, autofocus, Enter submits (`onSubmitted`), own controllers disposed. Passes. |
| Columns picker (grid "Columns" button) | `ui/workspace/grid_column_chooser.dart:91,167` | D7 (minor) | Width 360 but no max height; `ListView(shrinkWrap:true)` inside unbounded `AlertDialog` content can overflow if a grid ever exposes many toggleable columns (low risk today — lists seen have <20). Buttons named "Default"/"Cancel"/"Apply" — good. |
| Switch firm (firm badge ▾) | `ui/desktop_shell.dart:1176`, dialog class `_FirmSwitcherDialog` build at :1972 | none (minor D4 nice-to-have) | Own `TextEditingController` disposed, sized 420×320, autofocus search. No Enter-to-pick-top-match wired (only clicking a row selects) — minor. Failure to switch firm surfaces as a SnackBar after the picker has already closed, which is reasonable for a picker (not a form with fields to lose). |
| Command box (Ctrl+K / Alt+G, phase 2) | `phase2/command_box.dart:117`, `_CommandBox` | none | Exemplary: `ConstrainedBox(maxWidth:640,maxHeight:520)`, own controllers disposed, autofocus, Enter opens the selection (`onSubmitted`), Up/Down navigate. Passes. |
| "Close without saving?" (any phase-2 document tab closed with unsaved typing) | `phase2/document_tabs.dart:114` (`_UnsavedWorkGuard._ask`) | D9 (partial) | Good pattern overall — this is the **one, shared** unsaved-work guard for every document opened via `showDocument`/`DocumentTabsController` in phase 2, and it is what makes D1/D9 largely solved for document editors in phase 2. Gap: `_typed` is only set by a **printable keystroke** reaching the tab's `Focus.onKeyEvent` (`_watch`, line 100-110) — picking a customer from a dropdown, toggling a switch, or choosing a date from a date-picker does not fire a character key event, so a document edited **only** through non-keyboard controls can still be closed via the tab's × with no warning. Buttons are well named ("Keep editing" / "Discard and close"). |
| Customise Home (phase 2 home page) | `phase2/home_page.dart:365` | D7 (very minor) | No explicit width on the `AlertDialog`; content is a short checkbox list (<=4 items today) so low overflow risk. Buttons "Cancel"/"Save" are fine. |
| Default units for a business profile ("Default units" action on Business Profiles list) | `ui/uom/profile_uom_defaults_dialog.dart` (shown from `ui/desktop_shell.dart:4929`) | none | Solid: width 520, server error shown inline (`_error`, red text) with the dialog staying open, Save/Close disabled while `_saving`, dialog does not pop until the save actually succeeds. No autofocus (first control is a dropdown, acceptable). Passes. |
| **CrudWorkspaceDialog** — the body every `ResourceDefinition` create/edit form uses (~20 screens via `ResourceManagementPage`, e.g. roles, permissions, branches, geo levels, chart of accounts, numbering series, etc.) | `ui/resource_management_page.dart:1267-2050` | none, by construction | Reference implementation, reviewed directly: controllers are `State`-owned and disposed (`dispose()` at :1398); `_dirty` is tracked per keystroke/selection and Escape/Cancel routes through `_confirmAndClose` (:2018) which shows "Discard unsaved changes?" (`EnterpriseConfirmationDialog.confirmDiscard`) before closing — this is the **one correct D9 implementation** in the codebase, everything else should copy it; Cancel/Save disabled while `_saving`; server field errors (`_fieldErrors`/`_submitError`) render inline via `EnterpriseValidationSummary` and the view auto-scrolls to them (`_scroll`), and a corrected field's own error clears on edit (`_fieldEdited`, :1374); Escape bound via `CallbackShortcuts` (not blocked); Ctrl+S saves (not plain Enter — see Shared fixes). Individual `ResourceDefinition`s were **not** re-reviewed field-by-field here; area agents flagged any per-definition custom-field deviations they found. |
| `WorkspaceDialog` (the shared shell most bespoke document/task dialogs build on) | `ui/workspace/workspace_dialog.dart` | — | Not a dialog itself — a shell. Facts used throughout this report: sized to `window.width/height * dialogScale` (bounded — D7 is solved for any caller that just fills `body`, so D7 findings below are only for AlertDialogs that don't use this shell); Escape and the header × both call `onClose ?? Navigator.maybePop` (a caller passing a no-op `onClose` silently breaks Escape — flag those individually); `Ctrl+S` triggers `onSave` via `WorkspaceShortcuts`, **plain Enter does not submit** unless the caller's own body wires a field's `onSubmitted`; `WorkspaceDialog` itself has **no built-in dirty-check** — every caller must implement its own D9 guard (phase 2 gets one for free via `showDocument`/`_UnsavedWorkGuard` above; phase-1-only callers and non-document `WorkspaceDialog` task dialogs do not). |
| `askForReason` (Cancel/Reject/Hold-with-reason across Sell/Buy) | `ui/workspace/reason_prompt.dart:24` | — | Well built: owns and disposes its own `TextEditingController` (the file's own doc-comment records this was fixed after two earlier bugs), sized width 420, autofocus, Enter submits via `onSubmitted`. Default `confirmLabel` is the generic word "Confirm" — callers that don't override it for a specific destructive action get a D3 finding (see area tables for which call sites do this). |
| `AppDialogs.confirm` / `AppDialogs.error` (`core/dialogs/app_dialogs.dart`) | — | — | A well-built, ready-made confirm/error helper with correctly labelled Cancel + verb buttons and destructive red styling for `ConfirmationType.{delete,logout,discardChanges,resetPassword,lockUser,unlockUser}` — but used in only **2 places in the entire app** (`phase2/customer_groups_page.dart:108`, `ui/workspace/workspace_components.dart:4384`) and `AppDialogs.error` is used **0 times**. This is the single highest-leverage shared fix — see below. |

## Shared fixes

Problems that one change to a shared widget would fix across many call sites:

1. **`AppDialogs.confirm` is barely adopted (2/≈100+ confirm-style dialogs).** `ConfirmationType.lockUser`/`unlockUser`/`resetPassword`/`logout`/`delete`/`discardChanges` already exist with correct verb labels and destructive red styling, but almost every plain yes/no confirmation in the app is a hand-rolled `AlertDialog` instead — which is how so many end up with a generic "Confirm"/"OK"/"Yes" button (D3) or an undecorated destructive action (no red). See each area table below for the specific hand-rolled confirms found (tagged "plain confirm — duplicates AppDialogs.confirm").
2. **No shared `PasswordField` widget.** Every screen hand-rolls its own `obscureText` field. Only the sign-in screen's password box (`ui/auth_screens.dart:901`) added a show/hide toggle; `ui/identity/change_password_dialog.dart`, `ui/identity/reset_password_dialog.dart`, `ui/administration/clone_user_dialog.dart` (temporary password) and the forced initial-password-change screen (`ui/auth_screens.dart:1423`) all use `obscureText: true` with **no toggle at all**. One `PasswordField` widget (copy the sign-in box's toggle) fixes all of them at once.
3. **`WorkspaceDialog` has no built-in unsaved-changes guard**, unlike `CrudWorkspaceDialog`. Phase 2 gets one for free for documents opened through `showDocument` (`_UnsavedWorkGuard`), but any `WorkspaceDialog`-based *task* dialog (not opened as a document tab) or any phase-1-only path has no D9 protection unless its own author added one. Copying `CrudWorkspaceDialog`'s `_dirty` + `EnterpriseConfirmationDialog.confirmDiscard` pattern into `WorkspaceDialog` itself (opt-in via a `trackDirty`/`onDirtyClose` parameter) would fix every short-task `WorkspaceDialog` at once rather than requiring each caller to remember it.
4. **`_UnsavedWorkGuard` (phase 2 document tabs) only notices typed characters**, not dropdown/switch/date-picker edits (`phase2/document_tabs.dart:100-110`). A document changed only through non-keyboard controls can be closed with no warning. Fixing `_typed` to also flip on any state-changing callback (or exposing a `markDirty()` the editors call) fixes every document tab at once.
5. **Plain Enter does not submit any `WorkspaceDialog`-based short-task dialog** — only `Ctrl+S`/mouse click do, because `WorkspaceShortcuts` binds save to Ctrl+S, not Enter (`ui/workspace/workspace_interactions.dart:34-35`). For a 1-2 field task dialog this is a real usability gap that would be fixed once by having `WorkspaceDialog` wire a `Shortcuts`/`Actions` binding for Enter → `onSave` when there is exactly one text field, or by each such dialog's own field using `onSubmitted`. See area tables for which short dialogs this affects.
6. **The dominant defect in the whole review: a dialog pops with its typed payload on "Save", and the real `create*`/`update*` API call runs afterward in the *caller*, not the dialog.** On success this is invisible; on a server refusal the dialog is already gone, so the error is a toast and (for a create) everything typed has to be re-entered. This is the single most repeated High-severity finding — roughly 25 dialogs across Masters (territory/beat-plan/branch/warehouse/type/storage-node/copy-hierarchy editors, the 4 territory assignment pickers, the geography editor, the UOM "simple dialog" cluster), Stock (inventory thresholds, new inventory adjustment, opening-stock draft, stock-action dialog), Accounts (the tax "simple dialog" cluster), and Sell (raise proforma, e-way bill). A handful of dialogs in this same codebase already do it correctly — `_PackagingLevelDialog`, `ConversionRuleDialog`, `CouponDialog`, `CreditSettingsDialog`, `CreditNoteDialog`, the three inventory batch/lot/serial form dialogs (aside from their SnackBar-visibility bug), and `CrudWorkspaceDialog` itself — and are the pattern every other one of these should copy: own the API call inside the dialog's `State`, keep the dialog open and disabled while the request is in flight, and only pop on success.
7. **Five destructive actions have no confirmation dialog at all**, not merely a non-shared one: delete storage node/branch type/warehouse type, delete price list, delete/retire promotion, remove a customer group, delete a sales target. Each sits beside sibling code in the same file that confirms correctly (often `showWorkspaceConfirmDialog`), so these read as omissions rather than a deliberate design choice — the fix is per-call-site, but the shared confirm helper to use for all five already exists.

## Dialogs that pass every check

- Global search — `ui/workspace/global_search.dart`
- Command box — `phase2/command_box.dart`
- Default units for a business profile — `ui/uom/profile_uom_defaults_dialog.dart`
- CrudWorkspaceDialog (the ~20 `ResourceDefinition` create/edit forms as a class) — `ui/resource_management_page.dart`
- Columns picker, Customise Home, Switch firm — `ui/workspace/grid_column_chooser.dart`, `phase2/home_page.dart`, `ui/desktop_shell.dart` (minor D7/D4 notes only, no real risk)
- **Accounts**: view journal entry (structure only), view settlement, whose-credit/which-return pickers, map/change control account, diagnostics report detail — `ui/finance/journal_entry_view_dialog.dart`, `ui/finance/settlements_page.dart:511-574,735-746,775-789`, `ui/finance/control_accounts_page.dart:304-353`, `ui/settings/diagnostics_page.dart:340-362`
- **Masters**: `TerritoryTreeDialog`, `_PackagingLevelDialog`, `ConversionRuleDialog`, `CreditSettingsDialog`, `CustomerGroupDialog` create/edit half, `CouponDialog` — `territory_tree_dialog.dart`, `packaging_levels_page.dart`, `uom_management_page.dart:945-1146`, `credit_settings_dialog.dart`, `customer_group_dialog.dart`, `coupon_dialog.dart`
- **Stock**: open a count, post-count confirmation, abandon sheet, inventory details (view) — `physical_count_sheet_dialog.dart`, `inventory_details_dialog.dart`
- **Admin/Identity**: add existing user (find person), primary firm, my profile, firm setup, password assistance, sign-in password field — `find_person_dialog.dart`, `primary_firm_dialog.dart`, `profile_dialog.dart`, `firm_setup_dialog.dart`, `auth_screens.dart:459-474,898-926`
- **Sell**: `DocumentViewDialog` read-only views, hold-a-sales-order, withdraw-a-proforma, read one quotation/credit note/proforma/sales return, raise a credit note, commission accrual/payment dialogs, new/edit/remove customer group, register e-invoice / raise e-way bill picker
- **Buy**: preview an attachment, delete selected order(s), purchase/purchase-invoice/purchase-return/goods-receipt read-only view dialogs, print-settings openers
