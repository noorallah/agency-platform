# Goods types (backlog 89): API check, round 1, 2026-10-08

Backend verified over HTTP; **screens not** (that is the next unit but one).
Driven against the running backend at main `6edf8a4c`, every store on
`20261008_0353`, the morning backlog 89 was merged. Nothing here was run on a
demo firm.

**Outcome: 14 cases, 12 pass, 2 fail; 19 probes, 6 fail. Nine findings: no
High, three Medium, six Low. Three sentences of case text are wrong.** No role
got more than its seeded permissions allow.

**After the fix batch (the same day, #1359): 33 of 33 scripts clean against
the restarted server.** Eight of the nine findings are fixed, the case text is
corrected, and what is left is D-IDN-13, seen once and not reproduced. See
*The fix batch* at the end.

## How to run it again

The checks are kept scripts, one per case or probe, under
`docs/qa/checks/goods_types/` (33 of them), on the shared helper
`docs/qa/checks/common.py`:

```powershell
# once per machine, from backend\
.venv\Scripts\python.exe scripts\test_fixture.py product-master
.venv\Scripts\python.exe scripts\test_fixture.py platform-admin
.venv\Scripts\python.exe ..\docs\qa\checks\goods_types\setup.py <admin suffix> <platform suffix>
.venv\Scripts\python.exe ..\docs\qa\checks\goods_types\setup_firms.py   # two firms of its own, about two minutes each
# every round, from the repository root
backend\.venv\Scripts\python.exe docs\qa\checks\run.py goods_types
```

The runner prints only failures and a tally. Each script makes its own records
under a fresh suffix, so any one runs alone and runs twice. A script asserts
what its **case** expects, so a finding below stays a failing script until it
is fixed: that script is the re-drive.

First full run: **33 scripts, 24 clean, 7 failing for the findings below, 2
lost their connection** (D-PERF-3, the development PC resets some answers
larger than about 64 KB: `GET /products?page_size=100` was reset 3 times in 3
and `GET /products/metadata` 2 in 3, while the server logged 200). Both had
passed when run alone. `common.py` asks a **read** again up to six times and
never a write. Since the fix batch the helpers `_gt.py` and `_lib.py` read 25
rows a page through `all_rows` in `common.py`, and the full run after it lost
no connection: **33 of 33 clean**.

## Where it ran

| Firm | Store | Used for |
| --- | --- | --- |
| TEST01 | `test_fixtures` | everything that needs no firm of its own; admin suffix `t1008nnr7` |
| TEST02 | `test_fixtures_2` | "another firm": reads, one own goods type made and deleted, one product with *Track batch* on and no type |
| `T1008MK9X-F` | `fx_t1008mk9x_f` | new firm, **Pharma Distribution** as its first profile |
| `T1008FTRV-F` | `fx_t1008ftrv_f` | new firm, **Generic Business** as its first profile; GST template and default branch added |

Roles on TEST01: firm administrator, `FIRM_MANAGER`, `SALES_MANAGER`,
`INVENTORY_MANAGER`; on the two new firms an administrator, a `FIRM_MANAGER`
and a `CASHIER` (no `BATCH_VIEW`); one `ALL_FIRMS` platform administrator.

Left behind on TEST01: Medicine, Paint and Electronics in use (Medicine with
defaults HSN `3004` and `GST_12_LOCAL`, Electronics with none), one optional
shared customer field `GTQ_TRADE_LICENCE_NO` switched on, and each run's
products, categories, unit sets, batches and customers under its suffix.

## Cases

| Case | Result | What the server did |
| --- | --- | --- |
| TC-MAST-017 | Pass (25 checks) | Five shared types; a change to one is 422 *is a shared goods type and cannot be changed here*; the firm's own type is 201 and in use; code `MEDICINE` in either case is 409 *already exists*; an unknown default tax group is 422. Products in *Tablets* and *Tablets > Strips* carry Medicine, in *Sundries* and with no category null |
| TC-MAST-018 | Pass (24) | A rename keeps the type; after the change to Food the old product keeps Medicine and the new one takes Food; moved to *Enamels* it takes Paint; no category gives null. *Stop using* is 409 while a category carries the type, then accepted. Deleting the firm's own type is 409 for the category, then 409 for the product (*Deactivate it instead*) |
| TC-MAST-019 | Pass (22) | Firm manager and sales manager read the list and get 403 on create and on use; the administrator's writes succeed. The pharmacy firm started with Medicine and one `goods_type.starting_set` audit row; the generic firm with none and no row. Medicine dropped, profile changed and changed back: still not in use |
| TC-MAST-020 | Pass (30) | P1 to P6 exactly as written. A receipt with no batch is refused at **Complete**, not at save (*must be received with a batch number*); switching batch tracking off while stock is held is 422 |
| TC-MAST-021 | Pass, API part (16) | `/products/metadata` names the category's type (a sub category takes its parent's), nine `switches` per type, the two defaults and the unit sets; all four roles read it. What the form shows is for the screen unit |
| TC-MAST-022 | Pass (41) | Eight shared sets; a shared set cannot be changed (422); a repeated name is 409; `US-1` 10, `US-2` 15, `US-3` Carton and 120, `US-6` 12; the back-dated order of 2 Box is 20 Strip; `US-7` keeps Case and 6 after the set is edited and deleted; `unit_set_id` on an update is 422; the sales manager reads and is refused the add |
| TC-MAST-023 | Pass (13) | (a) 201; (b) 422 with the case's sentence, then 201 without the expiry; (c) 422; (d) 201, then 422; (e) 200 with the product's switch off; (f) saved; (g) 403 and nothing written |
| TC-MAST-024 | Pass (20) | (a) the field is offered for the Paint category only; (b) 422 *Required attributes are missing*, then 201; (d) 422 *do not apply*; (e) 200 and the value kept; (f) 422, 201, 201; (g) 409; (h) 422; (i) 403 |
| TC-MAST-025 | Pass (14), step (e) not driven | Off: the old value stays, a new customer is not offered the field, a value sent is 422. On again: the value is unchanged. An own field is 404; the firm manager 403; two `firm_custom_field.use_changed` rows |
| TC-MAST-026 | **Fail** (D-CFG-26) | With a firm: `[]`, then `BATCH` with Paint, `BATCH, SERIAL` with Electronics, `[]` when both go; a product that tracks batches with no type gives `BATCH`; the cashier is answered the same list and refused the batch and serial lists themselves (403). **With no `X-Firm-ID` the call answers 503**, where the case expects 200 with every row null |
| TC-MAST-027 | Pass (19) | The template says the three tracking columns are optional and has a UnitSet column; the four products take their category's type, the sub category its parent's; a cell saying No wins; `maybe` is named by row and column and nothing is imported; the sales manager is 403 on the check and on the template |
| TC-MAST-028 | **Fail** (D-MST-17) | Everything as written except `UX-2`: the row with both a Unit and a UnitSet is imported with **no pack conversion** |
| TC-MAST-029 | Pass (16); case text wrong | Five features and no more; the Generic profile lists Attachments only; (a) to (e) accepted, (f) 403 naming `VEHICLE_TRACKING`, (g) accepted |
| TC-MAST-030 | Pass (25) | The copy keeps the set and the **source's** factor 12; a hand-typed product copies with its own rule; with the set deactivated the copy keeps units and rule and drops the set; the source's version does not move; the sales manager is 403 |

### What each role got

| Route | Firm administrator | Firm manager | Sales manager | Inventory manager |
| --- | --- | --- | --- | --- |
| Goods type: add, change, use, delete (`CUSTOM_FIELD_MANAGE`) | allowed | 403 | 403 | 403 |
| Unit set: add, change, delete (`UOM_MANAGE`) | allowed | allowed | 403 | 403 |
| Product: add, copy (`PRODUCT_CREATE`) | allowed | allowed | 403 | 403 |
| Product import: check, apply (`PRODUCT_IMPORT`) | allowed | allowed | 403 | 403 |
| Extra-field rule, switching a shared field off | allowed | 403 | not driven | not driven |
| Batch: add (`BATCH_CREATE`) | allowed | allowed | 403 | not driven |
| Reading goods types, unit sets, product metadata | 200 | 200 | 200 | 200 |

Every answer matches `app/identity/system_seed.py`.

## Findings

| Id | Severity | Finding | Script that fails | Cause |
| --- | --- | --- | --- | --- |
| D-MST-17 (GTQ-A1) | Medium | **An import row naming both a Unit and a UnitSet loses the set's pack rule, without a word.** The Unit overwrites the stock, purchase and sales unit together, so the purchase unit equals the stock unit and the factor is dropped. The template says "A Unit on the same row is kept", and the check gives no warning | `tc_mast_028.py` | `app/products/services/product_import.py:532`, with `product_service.py:1760` dropping the factor |
| D-STK-22 (GTQ-B3) | Medium | **A batch or a serial can be moved onto a product that does not track it.** `PUT /batch-serial/batches/{id}` and `/serials/{id}` with a new `product_id` judge the **old** product only: 200 for a product with no batch (or serial) tracking. Nothing checks that the new product is the firm's own either; across two schemas that fails as a 409 with the wrong reason, and in the shared store it was **not driven** | `q_batch_other_firm.py`, `q_serial_move_untracked.py` | `app/batch_serial/services/batch_serial_service.py:624` and about `:1313` |
| D-CFG-26 (GTQ-B1) | Medium | **`GET /business-framework/active-modules` with no `X-Firm-ID` answers 503**, and so do `/features` and `/attribute-definitions`: the platform store holds no `business_profiles` table (`UndefinedTable`). A platform administrator who belongs to no firm asks it when the shell starts. Not established whether it is older than backlog 89 | `tc_mast_026.py`, `q_platform_without_firm.py` | `app/business/api/router.py:1060` |
| D-STK-23 (GTQ-B2) | Low | A batch is accepted with an expiry date before its manufacturing date (2026-06-01 against 2027-06-01: 201) | `q_expiry_before_manufacturing.py` | `batch_serial_service.py:353` and `:605`; no validator on the schema |
| D-MST-18 (GTQ-A2) | Low | `/products/metadata?category_id=` for a **deleted** category answers that category's goods type | `p_deleted_category.py` | `product_service.py:1829` (`_stored_category`) |
| D-MST-19 (GTQ-A3) | Low | A goods type can be deleted while a deleted product still holds it; restoring the product leaves it pointing at a type that is gone | `p_deleted_category.py` | `app/products/repositories/goods_type_repository.py:96` |
| D-MST-20 (GTQ-A4) | Low | A unit set's name is unique only in the same case: *strip, BOX of 10* is accepted beside the shared *Strip, box of 10*, and the import matches names without case, so one of the two wins silently | `p_unit_set_types.py` | `app/uom/repositories/unit_set_repository.py:51` |
| D-MST-21 (GTQ-A5) | Low | *Stop using* a goods type forgets the firm's HSN and tax-group defaults for it, and a body sent with `in_use: false` has its defaults ignored unchecked (an unknown tax group included) | none | `set_use` in `app/products/services/goods_types.py` |
| D-IDN-13 (GTQ-A6) | Low | Seen once, not reproduced: one account signing in twice at the same moment had one sign-in refused 409 *This record changed since you loaded it* | none | not traced |

**Decisions taken for the fix batch, by the usual standard, for the owner to
overrule.** D-MST-17: with a UnitSet on the row the Unit column names the stock
unit only when the set is absent; with both, the set fills the units and its
pack rule, and the check warns that the row's Unit was passed over, so the
template sentence is corrected to match. D-STK-22: a batch or serial that has
any movement cannot change product at all; one with none is judged against the
new product exactly as a new batch would be. D-CFG-26: with no firm the three
reads answer 200 with nothing firm-specific (`goods_tracking` null), not an
error. D-MST-21: the defaults are kept when a type is dropped and come back
when it is used again.

## Case text corrected

All five are corrected in `docs/INDEPENDENT_TEST_CASES.md` and in the
regenerated `docs/qa/05_MASTERS.md`, with two more that follow from the fixes:
TC-MAST-028 now expects a Unit beside a UnitSet to be passed over with a
warning (three warnings, not two), and TC-MAST-026 (h) expects 200 with an
empty list when no firm is named.

- **TC-MAST-028:** the shared set *Tin, loose* does not exist. The set tied to
  no goods type is *Piece, loose*.
- **TC-MAST-029, last sentence:** assigning Pharmacy to a firm that already
  has a profile hands out **no** goods type and writes no
  `goods_type.starting_set` row. A firm gets its profile's types with its
  **first** profile only, as TC-MAST-019 says.
- **TC-MAST-025 (e):** "a second firm in the same store" needs two firms in the
  shared store (`shared-pair`); TEST01 and TEST02 are stores of their own, where
  a shared field of one simply does not exist in the other.
- **TC-MAST-020:** the receipt with no batch is refused when it is
  **completed**, not when it is saved.
- **TC-MAST-029 (d):** a route needs the sales hierarchy levels saved first,
  which the firm administrator is refused (403) and the platform administrator
  did. Say so under *Also needs*.

## Not driven

- Every step that reads a screen: the product form, the menus, the firm
  switcher, sign-in refreshing the menu.
- TC-MAST-025 (e), for the reason above.
- D-STK-22 across two firms of the **shared** store.
- The sales manager and the inventory manager on the extra-field routes.

## The four findings of the attended check of step 1

| Finding | State on main |
| --- | --- |
| The demo seeders never hand out a starting type | **Fixed** in step 6 (`6d269344`, in the squash `6edf8a4c`): `scripts/seed_multi_firm_demo.py` calls `start_firm_goods_types` and gives its category the type. `scripts/seed_volume_firm.py` still inserts the profile row directly, which changes nothing because its profile, Wholesale, starts with no type. The seeders were **not run**. `scripts/generate_sample_data.py` still gives its categories no type (recorded in backlog 89) |
| `start_firm_goods_types` writes no audit row | **Fixed** in step 6: `goods_type.starting_set`, seen live on the new pharmacy firm (one row, `["MEDICINE"]`) |
| Migration `_seed_shared` reads only live shared rows | **Fixed** in step 6: it passes over any id already held, retired rows included |
| Goods types have no repository layer | **Fixed** in step 6: `app/products/repositories/goods_type_repository.py` |

## What the migration left on the demo firms (read only)

| Firm | Goods types in use | Categories carrying a type | `goods_tracking` |
| --- | --- | --- | --- |
| MEDI01 | Medicine | 0 of 1 | Batch, Expiry |
| FOOD01 | Food | 0 of 1 | Batch, Expiry |
| ELEC01 | Electronics | 0 of 1 | Serial |
| PERF01 | none | 0 of 20 | Batch, Expiry (from its products) |
| WHOLE01, LEARN01, QA01, SNTEST01, OWNTEST1 | none | 0 | none |

The migration put each profile's starting type in use and gave **no existing
category a type**, so on MEDI01 a new product filed under the existing category
is General and tracks nothing until an administrator gives that category
Medicine. Products already there keep their switches. This is what backlog 89
says it does; it is here because the owner will meet it on the demo firms
before the seeders are run again.

## The fix batch (2026-10-08, #1359)

One commit. Each fix has a unit test beside it, and the script that failed is
the re-drive.

| Id | What changed | Re-drive |
| --- | --- | --- |
| D-MST-17 | With a UnitSet on the row the set fills every unit and the pack rule; the row's Unit is passed over and the check says so (*is passed over: the unit set '...' fills this product's units and its pack conversion.*). The template sentence and the functional guide say the same | `tc_mast_028.py` clean |
| D-STK-22 | A batch, lot or serial given a new `product_id` is judged against **that** product, as one added by hand is: the firm's own (404), tracking such a record (422), allowing every dated field the record holds (422). One that stock, a movement or a serial stands on cannot change product (422). A serial is refused a batch of another product, on create and update | `q_batch_other_firm.py`, `q_serial_move_untracked.py` clean |
| D-CFG-26 | `/active-modules`, `/active-features`, `/features` and `/attribute-definitions` with no `X-Firm-ID` answer 200 with nothing, where the store holds no catalogue. The shell no longer asks while no firm is selected, because an empty module list read as an answer would hide every screen | `tc_mast_026.py`, `q_platform_without_firm.py` clean |
| D-STK-23 | An expiry or best-before date before the manufacturing date is refused on a batch added or edited by hand (422); the same day is allowed; a goods receipt is not asked | `q_expiry_before_manufacturing.py` clean |
| D-MST-18 | The metadata for a deleted category names no goods type | `p_deleted_category.py` clean |
| D-MST-19 | A goods type a **deleted** product still holds is refused deletion (409, *Deactivate it instead*), so a restored product finds its type. The script expected the delete to pass and the product to lose its type; it now expects the refusal | `p_deleted_category.py` clean |
| D-MST-20 | A unit set's name is refused whatever its case or outer spaces | `p_unit_set_types.py` clean |
| D-MST-21 | The defaults stay on the retired row and come back when the type is used again; a default sent with the drop is checked and kept | unit test only |

**Left as it was, and why.** `/profiles`, `/modules` and the category rules of
the same router still fail with no firm: nothing asks them without one, and an
empty catalogue there would read as "no profiles exist". D-IDN-13 stays open.

**Not verified.** The shell's half of D-CFG-26 has no widget test and was not
looked at on screen (the screen unit will). D-STK-22 across two firms of the
**shared** store was not driven live; the unit test covers two firms in one
schema. D-MST-21 has no live script. The server was re-driven on the branch's
code before the merge; one late change (the "has it moved" question is asked
only when the product changes) was made after that run and is covered by the
unit tests and by re-running the two D-STK-22 scripts after the merge.
