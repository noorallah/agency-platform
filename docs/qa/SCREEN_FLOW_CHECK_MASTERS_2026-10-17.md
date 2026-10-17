# Screen cases, Masters click round (Products, Suppliers, Places): 2026-10-17

Brief (Masters module test, part b, screen clicks): drive the Products, Suppliers
(vendors) and Places (geography) screens in the real app, as the customers screens
were on the same day (`SCREEN_FLOW_CHECK_CUSTOMERS_2026-10-17.md`). No app code,
DEFECTS.md or other shared doc was edited.

## Where it ran

Fixture firm `T1016VSH1-S`, backend at localhost:8000 (health 200). Accounts and
password are those of `SCREEN_FLOW_CHECK_SELLING_2026-10-16.md`: administrator
`t1016vsh1.tradeadmin`, VIEWER `t1016vsh1.qro`. Each flow went through
`integration_test/run.sh` from `desktop/` with `LIMIT=580`, a fresh TEMP/TMP
folder per attempt and `IT_EMAIL`/`IT_PASSWORD` set. The checkout was run from a
short path (`D:\ws\mq`): from the deep agent worktree the Windows build fails with
MSB3501 ("Could not find a part of the path ..."), the 260-character limit.

**No existing flow covers these three screens.** `sc_gr_test` is goods receipts, not
geography, and there is no `sc_pr*`/`sc_vn*` for masters; the only existing cover is
the menu walk in `roles_flow_test` (it opens the screen, nothing more). So a new
flow was written, `desktop/integration_test/sc_mst_test.dart` (copy of the `sc_*`
shape, case ids MST-VN, MST-PR, MST-GE). It runs in three parts (`IT_PART=lists`,
`places`, `editors`) because the app process dies mid-run at random (below). List
and place cases run at 1600x1000 and again at 800x600.

Left behind in the fixture firm by the flow itself (no deletes were made):
vendor `SUP-00002` "MST Vendor 1792237241762" (from an earlier draft of the flow),
vendor `SUP-00003` "MST Screen Vendor" with GSTIN `12ABC` and phone `+919812345678`
(see candidate 1: the bad GSTIN was accepted), and nothing else.

## Results

| Flow | User | Result |
| --- | --- | --- |
| roles_flow_test (menu walk) | tradeadmin | **pass** (1 of 1 step); Masters offers customers, vendors, products, branches, warehouses, trade-licences, each opened with no refusal text. One DEFECT line: inventory/inventory-import "Failed: 0" (already known from the Customers file) |
| roles_flow_test (menu walk) | qro | **did not complete**: the app process exited mid-walk on all 5 attempts (exit 79; died after the Buy area on the 3rd and 5th). Before dying it flagged the same read-only screens as in the Customers file (credit/debit notes, enquiries, rebates, pdc-received, purchases/debit-notes). Masters was not reached; the new flow covers it instead |
| sc_mst_test, lists | tradeadmin | **16 passed, 0 failed** (2 attempts; the first died at start-up/mid-run) |
| sc_mst_test, lists | qro | **16 passed, 0 failed** (3 attempts) |
| sc_mst_test, places | tradeadmin | **7 passed, 1 failed** (MST-GE-004 at 800x600: RenderFlex overflow, candidate 2) |
| sc_mst_test, places | qro | **7 passed, 1 failed** (same) |
| sc_mst_test, editors | tradeadmin | **9 passed, 0 failed** (final run; earlier runs failed on flow mistakes, see "Notes") |
| sc_mst_test, editors | qro | **2 passed, 0 failed** |

### Cases

Vendors (MST-VN) and Products (MST-PR), both sizes unless noted:

| Case | tradeadmin | qro |
| --- | --- | --- |
| 001 opens (list, columns, count agrees with API) | pass, both sizes; 800x600 drops the GSTIN/Created (vendors) and GST/MRP (products) columns | pass |
| 002 search finds a known name | pass | pass |
| 003 search with no match shows "No records" | pass | pass |
| 004 write buttons: `+ New`; selected row shows Open/Edit/Delete; Edit opens an editor with Save | pass: `+ New` enabled, Edit and Delete enabled, "Save vendor"/"Save product" enabled | pass: `+ New` absent, Edit/Delete absent, vendor row offers no Open; product row offers Open only and the editor it opens has no Save (Close only) |
| VN-010 New vendor, Save with nothing typed | pass: refused, editor stays open, nothing saved; message reads only "The request validation failed." (candidate 3) | not run |
| VN-011 bad email "not-an-email" | pass: "A valid email address is required.", nothing saved | not run |
| VN-011b bad GSTIN "12ABC" | **candidate 1**: the first time, the vendor was saved (SUP-00003 with GSTIN 12ABC, GST type "Regular (from GSTIN)"); on later runs refused only because that GSTIN now exists (no message captured) | not run |
| VN-011c bad phone "98123" | pass: "A valid E.164 phone number is required." | not run |
| VN-012 valid vendor saves and is listed | pass (name only; saved as SUP-00003, then found by search) | not run |
| VN-013 open the vendor, change phone, read back from the server | pass (phone `+919812345678` on the server) | not run |
| PR-010 New product, Save with nothing typed | pass: refused, editor open, nothing saved; "Product name is required. Choose a brand." | not run |
| PR-011 Cancel on a new product saves nothing | pass | not run |
| PR-012 open an existing product (Open) | pass: General, UOM & Size, Pricing, Price changes, Tax, Attributes, Attachments tabs | not run |
| VN-020 / PR-020 VIEWER opens the record read-only | not run | pass: no Save on either; API write to `/vendors` by qro answered 403 |

Places (MST-GE), Settings > Locations > "1 Places" (it is not in the Masters menu):

| Case | tradeadmin | qro |
| --- | --- | --- |
| 001 opens at 1600x1000 and 800x600 (India listed; footer "Read-only — geography is maintained by a platform administrator.") | pass | pass |
| 002 search ("zzqx-none" then "India") | pass; see candidate 4 for the empty wording | pass |
| 003 `+ New`, Edit, Delete | pass: all absent for both users (by design, platform-administered) | pass |
| 004 select India and drill in, at 800x600 | **fail**: RenderFlex overflowed by 43 pixels on the right (candidate 2); pass at 1600x1000 | **fail**, same |

## Candidate defects (not logged in DEFECTS.md)

1. **Vendor GSTIN is not checked for format.** `sc_mst_test.dart` step
   MST-VN-011b: New vendor, Vendor Name "MST Refusal Probe..." (first run: "MST Screen
   Vendor"), GSTIN `12ABC`, Save vendor. The vendor was saved (`SUP-00003`,
   `gstin: "12ABC"`, GST type shown as "Regular (from GSTIN)"). Email and phone, by
   contrast, are refused with a clear message. A 15-character GSTIN pattern/checksum
   is expected on a GST ledger party. (The server side was not tried by hand;
   the record read back through `GET /api/v1/vendors` carries `12ABC`.)
2. **Places screen overflows at 800x600 with a row selected.** MST-GE-004 (both users):
   open Settings > Locations > Places at 800x600, click the India row; the app
   throws "A RenderFlex overflowed by 43 pixels on the right" (twice per run, also
   when the window is shrunk to 800x600 with a row selected). At 1600x1000 none.
   Vendors and Products lists at 800x600, with a row selected, did not overflow.
3. **Empty Save on a new vendor says only "The request validation failed."**
   MST-VN-010 (tradeadmin): New vendor, press Save vendor with nothing typed. The
   editor stays open and nothing is saved (correct), but no message names the
   missing field; the product editor in the same case says "Product name is
   required. Choose a brand."
4. **Places search with no match reads as an empty master.** MST-GE-002 (both
   users): searching "zzqx-none" shows "No countries here yet | Geography is shared
   reference data. A platform administrator maintains it. | 0 records", which is the
   no-data wording rather than "No matches".
5. **A row in a searched Suppliers list would not select** (observation, cause
   uncertain). MST-VN-013 (first versions): with "MST Screen Vendor" left in the
   search box, clicking the single matching row did not show Edit/Delete (three
   attempts, one with a second click); after clearing the search box the same click
   selected it and Edit opened. Vendors and Products rows did select after a search
   was cleared with `searchList(tester, '')` (MST-VN-004). May be the click only
   taking focus out of the search box; worth a hand look.
6. **Places is not in the Masters menu**, only under Settings > Locations
   (design note, `menu_layout.dart`: `MenuPart.setUp`); the 800x600 menu bar folds
   Masters under More (`menu-area-more`), so reaching Products at that width takes
   More > Masters > Products. Not a fault; recorded because the menu walk of
   `roles_flow_test` will never visit Places.
7. **`roles_flow_test` for the VIEWER cannot be completed reliably**: the app
   process exited ("did not complete", run.sh exit 79) mid-walk on 5 of 5
   attempts, at different points. The sc_mst runs saw the same start-up/mid-run
   deaths (about 1 attempt in 3). Retried at most 5 times as instructed; the
   sc_mst parts were re-split so a death only costs one part.

## Notes on the flow (not defects)

- A row tap on Vendors/Products *selects* it and shows Open/Edit/Delete beside it
  (Vendors: Edit, Merge into..., Delete); it does not open the editor.
- The first drafts failed on flow mistakes only: button labelled "+ New" not "New",
  Save is "Save vendor" / "Save product", and Edit/Delete are not under the "…" menu.
- Not clicked: Vendor categories and types, Product categories, Brands, Principals,
  import/export dialogs (file chooser), Merge into..., Delete (no deletes by
  instruction), the Contacts/Addresses/Banking/Tax tabs of the vendor editor, the
  product Pricing/Tax/Attributes tabs, creating a product (needs a category, brand
  and units from the fixture), Places data other than the one country (the fixture
  store has only India, no states or districts to drill into).

## Re-running

    cd desktop
    for h in tradeadmin qro; do for p in lists places editors; do
      IT_EMAIL=t1016vsh1.$h@fixtures.local IT_PASSWORD=Fixture@2026pw IT_PART=$p \
        LIMIT=580 bash integration_test/run.sh sc_mst_test.dart; done; done

Run from a checkout whose path is short enough for the Windows build.
