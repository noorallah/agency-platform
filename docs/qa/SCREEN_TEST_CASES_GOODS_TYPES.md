# Screen test cases: goods types (backlog 89, phase 2 desktop)

Written 2026-10-08. Edited by hand, like `SCREEN_TEST_CASES_BUY_SELL_PRICE.md`
beside it: the generator writes only the numbered files `00` to `14`.

## Purpose

TC-MAST-017 to 030 in `docs/INDEPENDENT_TEST_CASES.md` were driven over HTTP
and carry the rules and the figures
(`GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). This book is what a **person
sees and can do** on the screens backlog 89 added or changed: Goods Types, the
product category form, the product form, Unit Sets, the extra-field switch,
the Add Batch dialog, the goods receipt and the Stock menu. The columns, the
four kinds of case and the refusal rules N1 to N3 (the screen says why in
words; the editor stays open with the typing kept; nothing is saved) are those
of the buying and selling book.

Click flow: `desktop/integration_test/sc_gt_test.dart`, one step per case id.
It is run in parts, because a long run is cut off on a PC short of memory:

```bash
# from desktop/, Git Bash, backend running
IT_PART=types,categories IT_EMAIL=<admin> IT_PASSWORD=<password> \
  bash integration_test/run.sh sc_gt_test.dart
# parts: types, categories, products, sets, fields, batches, receipt
# a role user (handle starting gt) runs the Role cases; any other user SC-GM-001
```

## Users

Firm TEST01 (`test_fixtures`), made by `docs/qa/checks/goods_types/setup.py`:

| Id | Handle | Role |
| --- | --- | --- |
| FA | `admin` | Firm administrator |
| FM | `gtmanager` | `FIRM_MANAGER` |
| SM | `gtsales` | `SALES_MANAGER` |
| WH | `gtstore` | `INVENTORY_MANAGER` |
| PH | `pharmaadmin`, `pharmacashier` | administrator and cashier of a firm of its own (`setup_firms.py`) |
| GE | `genericadmin` | administrator of a firm with no goods type in use |
| PL | `platform` | platform administrator, in no firm |

Before every FA case the flow makes, over HTTP, three categories that sort
first in every list (*Med* carrying Medicine, *Plain* carrying none, *Phone*
carrying Electronics) and one product in *Med* and one in *Plain*. Medicine on
TEST01 has the defaults HSN `3004` and tax group `GST_12_LOCAL`.

## Goods Types (Settings > Firm > Goods Types)

| Id | Kind | User | Steps on screen | Expected on screen | Book case |
| --- | --- | --- | --- | --- | --- |
| SC-GT-001 | Positive | FA | Open the screen; search `MEDICINE` | Columns Code, Name, Kind, Tracks, In use, Default HSN, Default tax group, Active; **+ New**; the Medicine row reads Shared, "Batch, expiry, manufacturing date", its defaults | TC-MAST-017 |
| SC-GT-002 | Positive | FA | **+ New**; Code, Name; switch **Batches** on; **Save & Close** | "Goods Types saved."; the row reads Own, Batch, In use Yes | TC-MAST-017 |
| SC-GT-003 | Negative | FA | **+ New**; Code `MEDICINE`, a Name; **Save & Close** | "A goods type with code MEDICINE already exists."; N1 to N3 | TC-MAST-017 |
| SC-GT-004 | Negative | FA | **+ New**; a Code, no Name; **Save & Close** | "Name is required."; N1 to N3 | TC-MAST-017 |
| SC-GT-005 | Negative | FA | Select Medicine (shared) | No Edit, no Delete; **Open** shows every box locked and "A shared goods type cannot be changed. Add one of the firm's own." | TC-MAST-017 |
| SC-GT-006 | Positive | FA | Select Food; **Use in this firm**; select it again; **Stop using** | "Food is now in use." then "Food is no longer in use."; In use follows | TC-MAST-018 |
| SC-GT-007 | Negative | FA | Select Medicine, which a category carries; **Stop using** | The server's sentence naming the category ("... is still the goods type of category ..., so it cannot be dropped ..."); In use stays Yes | TC-MAST-018 |
| SC-GT-008 | Positive | FA | Select an own type; **Set defaults**; HSN `3004`, tax group `GST_12_LOCAL`; **Save** | "Defaults saved for ..."; both show on the row | TC-MAST-020 |
| SC-GT-009 | Negative | FA | **Set defaults** with a tax group that does not exist; **Save** | "No active tax profile found for the given group code." inside the dialog; N1 to N3 (the HSN typed beside it is not saved either) | TC-MAST-017 |
| SC-GT-010 | Negative | FA | Select an own type a category carries; **Delete**; confirm | The server's reason, naming the category; the type stays | TC-MAST-018 |
| SC-GT-011 | Positive | FA | Select an own type nothing uses; **Delete**; confirm | The row is gone | TC-MAST-018 |
| SC-GT-012 | Negative | FA | **+ New**; type a Name; **Cancel** | "Discard unsaved changes?"; **Cancel** there keeps the dialog and the typing | (N2) |
| SC-GT-013 | Positive | FA | Select an own type; **Edit**; change the Name; **Save & Close** | Code cannot be typed over; the name is saved; the Batches switch is kept | TC-MAST-017 |
| SC-GT-020 | Role | FM, SM, WH | Open the screen; select Medicine | The list is read; no **+ New**, **Use in this firm**, **Stop using** or **Set defaults** | TC-MAST-019 |

## Product categories (Settings > Item lists > Product Categories)

| Id | Kind | User | Steps on screen | Expected on screen | Book case |
| --- | --- | --- | --- | --- | --- |
| SC-GC-001 | Positive | FA | Open the list; search the fixture categories | Goods type column: Medicine for *Med*, General for *Plain* | TC-MAST-017 |
| SC-GC-002 | Positive | FA | **+ New**; Category code, Name; pick the **Paint** chip under Goods type; **Save & Close** | Only goods types in use are offered as chips; saved with Paint | TC-MAST-017 |
| SC-GC-003 | Positive | FA | Select that category; **Edit**; pick **Medicine**; **Save & Close** | The form opens with Paint chosen; saved with Medicine | TC-MAST-018 |
| SC-GC-004 | Negative | FA | **+ New** with a code already used | "A product category with this code already exists."; N1 to N3 | (N1-N3) |

## Product form (Masters > Products > + New)

| Id | Kind | User | Steps on screen | Expected on screen | Book case |
| --- | --- | --- | --- | --- | --- |
| SC-GP-001 | Positive | FA | Category *Med* | "Goods type: Medicine"; Track batch, Track expiry and Track manufacturing date shown and on; no serial or warranty switch; HSN / SAC `3004`; tax profile `GST_12_LOCAL` | TC-MAST-020, 021 |
| SC-GP-002 | Positive | FA | Category *Plain*; then **Show all tracking options** | "Goods type: General" and "No tracking for this goods type."; the switch then shows all six, off | TC-MAST-021 |
| SC-GP-003 | Positive | FA | Category *Phone* | "Goods type: Electronics"; Track serial and Track warranty on; no batch switch | TC-MAST-021 |
| SC-GP-004 | Positive | FA | Category *Med*; open **Unit set**; tick **Show all unit sets**; open it again | First the sets of Medicine and of all goods (*Strip, box of 10* among them, not *Litre, loose*); with the tick, more | TC-MAST-022 |
| SC-GP-005 | Positive | FA | Category *Med*, a name, Unit set *Strip, box of 10*; **Save product** | The conversion box reads 10; saved with the type, its switches, the unit set and HSN `3004` | TC-MAST-020, 022 |
| SC-GP-006 | Positive | FA | Open the product just saved | "Goods type: Medicine"; "Units from: Strip, box of 10"; no Unit set box | TC-MAST-021, 022 |
| SC-GP-007 | Negative | FA | **Save product** with nothing typed | "Product name is required."; N1 to N3 | (N1-N3) |
| SC-GP-008 | Negative | FA | Product code of an existing product, a name; **Save product** | The server's sentence about the code; never "Somebody else saved this product"; N1 to N3 | (N1-N3) |
| SC-GP-009 | Positive | FA | Category *Phone*, then Category *Med*, before saving | The type line, the switches and the HSN follow the new category; nothing of Electronics stays on | TC-MAST-020 |
| SC-GP-020 | Role | FM, SM, WH | Open Products | FM is offered **+ New**; SM and WH read the list and are not | TC-MAST-019 |
| SC-GI-001 | Positive | FA | Products > **…** > **Import** | "Import products" with the template in Excel and CSV, **Choose file…**, **Check file**, **Import**. The check of a file is not clicked: the file is chosen in the operating system's own window (TC-MAST-027, 028 carry it over HTTP) | TC-MAST-027 |

## Unit Sets (Settings > Business profile > Unit Sets)

| Id | Kind | User | Steps on screen | Expected on screen | Book case |
| --- | --- | --- | --- | --- | --- |
| SC-US-001 | Positive | FA | Open the list; search *Strip, box of 10* | The row reads Strip, Box, Strip, "1 Box = 10 Strip", Medicine, Shared | TC-MAST-022 |
| SC-US-002 | Positive | FA | **+ New**; Name; Base unit Strip; Purchase unit Box; conversion 10; **Save & Close** | The conversion box appears once the two units differ; "Unit Sets saved."; factor 10 | TC-MAST-022 |
| SC-US-003 | Negative | FA | **+ New**; a Name, no base unit; **Save & Close** | "Choose the base unit the set is counted in."; N1 to N3 | TC-MAST-022 |
| SC-US-004 | Negative | FA | **+ New**; Name `strip, BOX of 10`; a base unit; **Save & Close** | "A unit set named strip, BOX of 10 already exists."; N1 to N3 | TC-MAST-022 (D-MST-20) |
| SC-US-005 | Negative | FA | Select *Piece, loose* (shared) | No Edit, no Delete; **Open** says "A shared unit set cannot be changed or deleted. ..." | TC-MAST-022 |
| SC-US-006 | Positive | FA | Select the own set; **Delete**; confirm | The row is gone | TC-MAST-022 |
| SC-US-020 | Role | FM, SM, WH | Open the screen | FM is offered **+ New**; SM and WH read the list and are not | TC-MAST-022 |

## Extra fields, batches, the receipt and the menu

| Id | Kind | User | Steps on screen | Expected on screen | Book case |
| --- | --- | --- | --- | --- | --- |
| SC-GF-001 | Positive | FA | Settings > Firm > Custom Fields; select a shared optional field; **Switch off for this firm**; select it again; **Switch on for this firm** | "... is switched off for this firm."; In use reads No; then "... is switched on for this firm." | TC-MAST-025 |
| SC-GB-001 | Positive | FA | Stock > Batches > **+ New**; Product (type its code, pick it), Batch Number, the two dates; **Create** | The batch is saved and the dialog closes | TC-MAST-023 (a) |
| SC-GB-002 | Negative | FA | The same with the expiry date before the manufacturing date | "The expiry date ... is before the manufacturing date .... Check the two dates."; N1 to N3 | TC-MAST-023 (D-STK-23) |
| SC-GB-003 | Positive | FA | Select a batch row | **Open** is offered | (list) |
| SC-GB-004 | Negative | FA | **+ New** for a product that tracks no batch | "... is not tracked by batch, so a batch cannot be added for it. Switch batch tracking on for the product first."; N1 to N3 | TC-MAST-023 (c) |
| SC-GB-005 | Negative | FA | **+ New**; a Batch Number, no product; **Create** | "Choose the product this batch is of."; nothing is sent | (N1-N3) |
| SC-GX-001 | Positive | FA | Buy > Goods Receipts > **+ New**; pick an approved order with a Medicine line and a line of a product with no type | The Medicine line asks an expiry date and a manufacturing date; the other line asks neither | TC-MAST-020, 023 |
| SC-GM-001 | Role | every user | Open the Stock area of the menu | Batches is offered only if the firm's goods need `BATCH`, Serial Numbers only for `SERIAL`, Expiry Monitor only for `EXPIRY` (what `/business-framework/active-modules` answers); a firm with no goods type in use is offered none of them; a role without the stock permissions is offered no Stock area at all; the platform administrator in no firm is offered Home and Settings | TC-MAST-026 |
