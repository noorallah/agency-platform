# Goods types (backlog 89): the screens, clicked against the real server, 2026-10-08

Cases: `SCREEN_TEST_CASES_GOODS_TYPES.md`. Flow:
`desktop/integration_test/sc_gt_test.dart`, run in the real phase 2 app at
**1366x768** against the running backend (main `3265c5c2`, every store on
`20261008_0353`), on the fixture firm TEST01 and on the two firms of its own
that the API check made. Nothing was run on a demo firm. The HTTP half of the
same module is `GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`.

**Outcome: 50 cases. First drive: 46 pass, 4 fail, for three findings (one
High, one Medium, one Low). After the fix batch the four were clicked again on
the fixed build and pass, and three cases were added for the dialog that could
not be used before.** No screen overflowed at 1366x768 and the app threw no
error of its own in any run.

## Findings

| Id | Severity | Case | Screen | What a person sees | Expected | Fixed |
| --- | --- | --- | --- | --- | --- | --- |
| D-UI-72 | High | SC-GB-001, 002 | Stock > Batches > + New (and Lots, Serial Numbers) | The Add Batch dialog has no product box. Every Create answers "The request validation failed. product_id: Field required", whatever is typed: a batch cannot be added from the screen at all. Add Lot and Add Serial are built the same way. Older than backlog 89 | A product box; the batch saved; the server's own refusals (dates the wrong way round, a product that tracks no batch) readable on the dialog | Yes: a product box that searches as it is typed, in all three dialogs |
| D-UI-73 | Medium | SC-GT-010, SC-GP-008 | Goods Types, Delete of a type a category carries; New product with a code already used | "Somebody else saved this goods type while you were editing it. Your changes were not saved. ..." for the delete, and "Somebody else saved this product while you were editing it. ..." for the new product. Nobody else saved anything: the server refused for a reason of its own and the reason was thrown away | The server's sentence | Yes: only the stale-write sentence reads as a lost race on a delete; the product form says it is a new record |
| D-UI-74 | Low | SC-GC-001 (one run) | Product Categories list | Every category read **General**, a Medicine one included, in a run where the read of the goods types' names was dropped (the development PC resets some answers, D-PERF-3). The next run read Medicine | General only for a category with no type | Yes: a dash for a type whose name is not known |

## Results

FA is the firm administrator; the Role cases name their user.

| Case | Result | What the screen did |
| --- | --- | --- |
| SC-GT-001 | Pass | Row: MEDICINE, Medicine, Shared, "Batch, expiry, manufacturing date", Yes, 3004, GST_12_LOCAL, Yes |
| SC-GT-002 | Pass | "Goods Types saved."; row Own, Batch, Yes; server `track_batch` and `in_use` true |
| SC-GT-003 | Pass | "Please review the following before saving / A goods type with code MEDICINE already exists."; dialog open, typing kept, nothing saved |
| SC-GT-004 | Pass | "Name is required." under the box; dialog open, nothing saved |
| SC-GT-005 | Pass | Edit and Delete absent; Open says "A shared goods type cannot be changed. Add one of the firm's own." with no Save |
| SC-GT-006 | Pass | "Food is now in use." then "Food is no longer in use."; the server followed both |
| SC-GT-007 | Pass | "Medicine is still the goods type of category TABLETS ..., so it cannot be dropped. Give that category another type first."; still in use |
| SC-GT-008 | Pass | "Defaults saved for ..."; row shows 3004 and GST_12_LOCAL |
| SC-GT-009 | Pass | "No active tax profile found for the given group code." inside the dialog; typing kept; the HSN beside it not saved |
| SC-GT-010 | **Fail**, then Pass | First: "Somebody else saved this goods type while you were editing it ..." (D-UI-73). On the fixed build: "Held ... is still the goods type of category ... Held, so it cannot be deleted. Give that category another type first."; the type stays |
| SC-GT-011 | Pass | Confirmed "Delete Goods Types?"; the row and the record are gone |
| SC-GT-012 | Pass | "Discard unsaved changes? / You have unsaved changes. Closing now will discard them."; Cancel there keeps the typing |
| SC-GT-013 | Pass | Code locked; name saved; Batches kept |
| SC-GT-020 FM, SM, WH | Pass | Each reads the list; + New, Stop using and Set defaults are absent for all three |
| SC-GC-001 | Pass (see D-UI-74) | *Med* reads Medicine, *Plain* reads General; first page of the list: 119 rows name a type, 86 read General |
| SC-GC-002 | Pass | Chips offered: Electronics, Medicine, Paint (the three in use; Food and Cosmetics are not); saved with Paint |
| SC-GC-003 | Pass | Opens with "Paint · Batch" chosen; saved with Medicine |
| SC-GC-004 | Pass | "A product category with this code already exists."; dialog open, typing kept |
| SC-GP-001 | Pass | "Goods type: Medicine"; Track batch, expiry, manufacturing date on; HSN 3004; tax profile GST_12_LOCAL |
| SC-GP-002 | Pass | "Goods type: General" and the no-tracking hint; Show all tracking options then shows all six, off |
| SC-GP-003 | Pass | "Goods type: Electronics"; Track serial and Track warranty on; no batch switch |
| SC-GP-004 | Pass | Seven sets offered (Bottle carton of 24, Piece loose, the firm's own all-goods set, Strip box of 10 and of 15, Tube box of 20, Unit box of 10); eleven with Show all unit sets |
| SC-GP-005 | Pass | Conversion box 10; saved with Medicine, batch and expiry on, the unit set, HSN 3004 |
| SC-GP-006 | Pass | "Goods type: Medicine"; "Units from: Strip, box of 10"; no unit set box |
| SC-GP-007 | Pass | "Product name is required."; nothing saved |
| SC-GP-008 | **Fail**, then Pass | First: refused and kept open, but worded "Somebody else saved this product while you were editing it ..." (D-UI-73). On the fixed build: "Product code already exists in this firm."; editor open, typing kept, nothing saved |
| SC-GP-009 | Pass | After Phone then Med: "Goods type: Medicine", the three medicine switches on, HSN 3004, no serial switch left on |
| SC-GP-020 FM / SM / WH | Pass | + New enabled for FM; absent for SM and WH |
| SC-GI-001 | Pass | … menu: Import price revisions, Import, Export. "Import products": template (Excel, CSV), Choose file…, the update tick, Check file, Import. The check of a file was not clicked (the operating system's file window) |
| SC-US-001 | Pass | Row: Strip, box of 10 / Strip / Box / Strip / 1 Box = 10 Strip / Medicine / Shared / Yes |
| SC-US-002 | Pass | The conversion box appeared once Purchase unit was Box; "Unit Sets saved."; factor 10 |
| SC-US-003 | Pass | "Choose the base unit the set is counted in."; dialog open, name kept |
| SC-US-004 | Pass | "A unit set named strip, BOX of 10 already exists." |
| SC-US-005 | Pass | Edit and Delete absent; Open says why |
| SC-US-006 | Pass | Confirmed "Delete Unit Sets?"; gone |
| SC-US-020 FM / SM / WH | Pass | + New enabled for FM; absent for SM and WH |
| SC-GF-001 | Pass | "Trade licence no (check) is switched off for this firm."; In use Yes to No; "... is switched on for this firm." |
| SC-GB-001 | **Fail**, then Pass | First: "The request validation failed. product_id: Field required" (D-UI-72). On the fixed build: product picked, batch saved, dialog closed |
| SC-GB-002 | **Blocked**, then Pass | First: the same refusal, before the dates were read. On the fixed build: "The expiry date 2026-06-01 is before the manufacturing date 2027-06-01. Check the two dates."; dialog open, typing kept |
| SC-GB-003 | Pass | A batch row offers Open |
| SC-GB-004 | Pass (added after the fix) | "... is not tracked by batch, so a batch cannot be added for it. Switch batch tracking on for the product first."; dialog open, nothing saved |
| SC-GB-005 | Pass (added after the fix) | "Choose the product this batch is of."; nothing sent |
| SC-GX-001 | Pass | On one receipt the Medicine line asks an expiry date and a manufacturing date; the line of a product with no type asks neither |
| SC-GM-001 FA, FM, WH | Pass | Server tracking BATCH, EXPIRY, SERIAL; Stock offers Batches, Lots, Serial Numbers, Expiry Monitor |
| SC-GM-001 SM | Pass | No Stock area (areas Sell, Accounts, Masters, Reports) |
| SC-GM-001 GE | Pass | Server tracking empty; Stock offers none of the four |
| SC-GM-001 PH admin, cashier | Pass | Server tracking empty (the API check took Medicine out of use there); none of the four; the cashier has no Stock area |
| SC-GM-001 PL | Pass | In no firm: Home and Settings only, "Platform Dashboard" on Home |

## Established behaviour

- A category offers only the goods types the firm has in use, as chips with
  what each tracks beside the name.
- Changing the category of a product **not yet saved** replaces the type, its
  switches and its HSN; nothing of the first type stays behind.
- The Stock menu follows the server's answer exactly. A role with no stock
  permission is offered no Stock area whatever the goods need.
- A platform administrator who has chosen no firm sees Home and Settings; the
  areas need a firm (the shell's half of D-CFG-26: the menu is not blanked,
  because nothing is asked while no firm is chosen).
- A batch row in the phase 2 list offers Open only; Edit is inside the view.
- The app reopens the screen a user last had open, and a screen reads its
  lists when it opens: the product form offers the categories that existed
  then. A category made by somebody else afterwards is offered once Products
  is opened again. (The flow makes its records before the app starts for this
  reason.)

## Not clicked

- The check and apply of a product import file (TC-MAST-027, 028): the file is
  chosen in the operating system's own window, which a click flow cannot drive.
  Both are driven over HTTP.
- Custom Field Rules by goods type (TC-MAST-024) on screen; driven over HTTP.
- Add Lot and Add Serial after the fix: the same product box as Add Batch,
  covered by the code and not clicked.
- A batch or serial moved to another product (D-STK-22): the edit form does not
  offer the product, so the refusal cannot be reached from the screen.

## Notes on the run

- The app under test ended without a word in six runs of about twenty (exit 79,
  "did not complete"), at a different step each time, with nothing in its own
  log or in the Windows event log. The PC had under 4 GB free. The flow is
  therefore run in parts (`IT_PART`), and a part that is cut off is run again.
  Not registered as a defect of the app: no run of a person's own copy is known
  to have ended this way.
- `run.sh` passes `IT_PART` through; nothing else in the harness changed.
