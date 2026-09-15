# Manual UI test plan

Scripted manual tests for the Flutter desktop client against a real backend,
**organised by module** so a session can take one module at a time and stop
cleanly at the end of it.

Rewritten on **2026-09-05** against the running application. The previous
version was written on 2026-08-16, before promotions, loyalty, credit notes,
proformas, TCS, GST returns, e-invoicing, customer groups and price-list
ladders existed, and its section numbers had begun to collide.

**Every case names the seeded data it needs** — which login, which firm, which
customer code, which document number. You should never have to hunt for "a
customer with a standing discount"; the case says it is `WHOLE01C01`.

A case that needs a request the desktop cannot make is marked **(HTTP)** and
gives the `curl`. Those are still manual tests: they check a guarantee the
server owes, and marking them keeps the plan honest about what clicking can
and cannot prove.

A case marked **(GAP)** covers something deliberately not built. It is there so
you do not report it as a defect — see §14.

---

# Part 1 — Before you start

## 1.1 Bring the environment up

From `backend/`:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_all_stores.py --dry-run   # what is where
.\.venv\Scripts\python.exe scripts\migrate_all_stores.py --yes       # bring all to head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Never `alembic upgrade head` on its own — it advances one schema and this
demo has four stores.

If the data looks wrong or empty, reseed **one firm at a time** so a run fits
inside a coffee:

```powershell
.\.venv\Scripts\python.exe scripts\seed_multi_firm_demo.py --firm WHOLE01
.\.venv\Scripts\python.exe scripts\verify_sample_data.py
```

`verify_sample_data.py` must end **"Every store holds together"**. If it does
not, stop and read what it says before testing anything else — every number on
every screen below is derived from those books.

From `desktop/`:

```powershell
flutter run -d windows --dart-define=API_BASE_URL=http://localhost:8000
```

## 1.2 The firms, and why there are four

| Firm | Storage mode | Where its data lives | Business profile |
| --- | --- | --- | --- |
| `WHOLE01` | `SCHEMA` | schema `wholesale_hub` in `agency_platform` | WHOLESALE |
| `FOOD01` | `SHARED` | schema `firm_shared` in `agency_platform` | FOOD |
| `MEDI01` | `SHARED` | schema `firm_shared` in `agency_platform` | PHARMACY |
| `ELEC01` | `DATABASE` | schema `electrolink_ops` in a **separate database** | ELECTRONICS |

`FOOD01` and `MEDI01` sharing one schema is the important pair: their rows sit
in the same physical tables, separated only by `firm_id`. Isolation defects
show up there first. `ELEC01` is the other end — a different database
entirely.

**The four firms trade identically on purpose.** Each has 32 purchase orders,
30 goods receipts, 58 sales orders, 58 delivery notes and 49 invoices across
three financial years. A count that differs between firms is a signal worth
chasing. The one known exception is e-invoicing: `WHOLE01` reads `IRN 13` where
its siblings read 17, because it carries a hand-made customer with no GST
number whose invoices are correctly refused.

## 1.3 Accounts

| Login | Password | Firms | Use it for |
| --- | --- | --- | --- |
| `master.ops@agency.local` | `DemoAdmin@12345` | all 4 | firm switching, cross-firm isolation |
| `whole01.admin@agency.local` | `DemoAdmin@12345` | WHOLE01 | single-firm behaviour, SCHEMA mode |
| `whole01.sales1@agency.local` | `DemoAdmin@12345` | WHOLE01 | **an operational role** — use it for every "should be refused" case |
| `whole01.sales2@agency.local` | `DemoAdmin@12345` | WHOLE01 | the second salesman, for commission |
| `food01.admin@agency.local` | `DemoAdmin@12345` | FOOD01 | SHARED mode |
| `medi01.admin@agency.local` | `DemoAdmin@12345` | MEDI01 | SHARED mode, the other half of the pair |
| `elec01.admin@agency.local` | `DemoAdmin@12345` | ELEC01 | DATABASE mode |

`platform-admin@agency.local` is **not** in this list. It must change its
password on first use and every platform-admin route refuses it until then.
Rotating it invalidates the value in `config/.env`. Use `master.ops` instead.

## 1.4 The seeded data every case refers to (WHOLE01)

**Customers**

| Code | Name | Standing discount | Segment | Own price list |
| --- | --- | ---: | --- | --- |
| `WHOLE01C01` | Vijaya Super Stores | 7.5% | Retailer (1.75%) | — |
| `WHOLE01C02` | Anand Agencies | — | Wholesaler (3.25%) | `NEGOTIATED`, 9.25% |
| `WHOLE01C03` | Classic Departmental Stores | — | Retailer (1.75%) | — |
| `OB-REV2` | Revise Check 2 | 7.5% | — | — |

`OB-REV2` was created by hand during testing. It has **no GST number**, which
is why four of this firm's invoices cannot be e-registered. Leave it alone; it
is useful precisely because it is the odd one.

**Products** — `DETER1K` Detergent Powder 1kg · `SHAMP180` Shampoo Bottle
180ml · `TOOTH150` Toothpaste 150g.

**Promotions** — `BULK5` (two revisions, line quantity ≥ 25, 5% then 7.5%) ·
`BIGORDER` (document ≥ 4,500, ₹200 off the bill, **does not stack**) ·
`CLEARANCE` (line quantity ≥ 40, 1%) · `WELCOME` (2.5%, **needs a coupon**).
Coupons `WELCOME10` (used) and `WELCOME10B` (never presented).

**Price list `STANDING`** — firm-wide, on `DETER1K` only, with breaks at 0 →
2%, 15 → 4.25%, 18 → 6.75%.

**Territories** — `WHOLE01-RGN` Chennai Region → `WHOLE01-T-N` / `WHOLE01-T-S`
zones → routes `WHOLE01-R-N1`, `WHOLE01-R-N2`, `WHOLE01-R-S1`.

**Beat plans** — `WHOLE01-BP-R1-MON`, `-R1-WED`, `-R1-FRI` (weekly),
`WHOLE01-BP-COLL` (alternate Tuesdays), `WHOLE01-BP-MTH` (second Tuesday).

## 1.5 Recording a result

For each case write **pass**, **fail** or **blocked**, and for a failure the
smallest thing that reproduces it. A screenshot taken from inside the app
(Help → Report a problem) carries the request id, which joins it to the
server-side traceback — that is worth far more than a photograph of the
screen.

---

# Part 2 — Module by module

Work down. Each module is self-contained; the order follows how a distribution
firm actually operates, so later modules can use what earlier ones produced.

## 2. Login, session and firm context

| # | Case | Expected |
| --- | --- | --- |
| 2.1 | Log in as `master.ops`, no firm chosen | Only platform screens are reachable. Firm-owned lists say a firm must be chosen, not "no records". |
| 2.2 | Choose WHOLE01, then ELEC01, from the firm switcher | Every open list reloads. No row from the previous firm survives the switch. |
| 2.3 | Log in as `whole01.admin` | The firm switcher offers WHOLE01 only. |
| 2.4 | Leave the app idle past the access-token lifetime, then click anything | It refreshes silently and the action completes. You should not be asked to log in again. |
| 2.5 | Log out, then press Back | No cached screen is reachable. |
| 2.6 | Log in with a wrong password three times | Each refusal takes about as long as a correct one. A wrong address and a wrong password should not feel different. |
| 2.7 | Two more wrong passwords (five in all), then the **right** one | The fifth wrong password is refused with "This account is locked after too many failed sign-in attempts. You can try again in 15:00." and the clock **counts down on screen** a second at a time; the right password after it is refused the same way with the time left. When it reaches zero the banner reads "The lock on this account has lifted. You can sign in now." The four attempts before it said only "Invalid email or password." `scripts/sql/check_identity_data.sql` §5 shows the fifth attempt as `locked` and the sixth as `account_locked`. |
| 2.8 | As `whole01.admin` (or `master.ops`), Users → Edit that person → tick **Clear login lock** → Save, then sign in as them with the right password | Signs in at once. The lock cleared and the failed count reset. |
| 2.9 | Do nothing else and wait 15 minutes instead of unlocking, then sign in | Also signs in: the lock lifts by itself. |
| 2.10 | Users → Edit → untick **Active**, save; sign in as them. Then set **Expires at** to a moment in the past instead and try again | Refused with "This account is inactive. Ask an administrator to reactivate it." History says `account_unavailable`. The expired case says "This account has expired. Ask an administrator to extend it." A wrong password on either still says only "Invalid email or password." Retick Active and clear the date. |
| 2.11 | Users → New with **Require password change** on; sign in as the new user | The change-password screen, and nothing else reachable. A password of 8 characters, or one with no symbol, is refused with the rule named; 12 characters with upper, lower, digit and symbol is accepted, and the app opens. |
| 2.12 | Change your own roles as `master.ops` while signed in on another window as that user | The other window is signed out on its next request. Roles, firms and password changes all revoke sessions. |
| 2.13 | Users → select that user → **Delete**; then Users → New with the same email | Deleted from the grid; the audit trail keeps the row. The address is accepted again: soft delete releases it. The new user has **no** roles or firms -- a new person to the system, not the old one back. |
| 2.13b | As `master.ops`: delete a user, choose **Deleted** in the Users grid's **Status** filter, open them (status **Deleted**, Edit and Delete dead, View opens) → **Restore** in the dialog footer; sign in as them | Back in the grid with their old firms and roles, and the old password works. |
| 2.13c | Delete a user, create a new one with the same address, then **Status** → Deleted → open the old one → Restore | Refused: "Another live account now holds this email address." Restore before re-onboarding, not after. |
| 2.13d | As `whole01.admin`, look for the Firm filter's **Deleted** choice and for **Restore** | Neither is offered. A deleted user is invisible to a firm's grid; restoring is a platform administrator's. `GET /api/v1/users?deleted_only=true` on their token lists live rows only. |
| 2.13d | As `master.ops`: untick **Active** on a test user, then choose **Inactive** in the Users grid's **Status** filter | Only the switched-off people, from every firm; the deleted ones are not among them. Then pick a firm as well: only the inactive people **in that firm**. |
| 2.14 | As `whole01.admin`, try to delete somebody who also belongs to ELEC01, and try to delete `master.ops` as anybody | Both refused, with the reason: a shared user's profile is a platform administrator's, and a platform administrator cannot be deleted at all. |
| 2.15 | Lock a firm test user out, e.g. `rr@rr.com`, with five wrong passwords. Then sign in as **`master.ops`** (a platform administrator; `whole01.admin` does not have this button, see 2.17) → Users → open them → **Reset password** in the dialog footer, set `Temp-Passw0rd!!`, leave "Require a new password" on, save. Sign in as the test user with `Temp-Passw0rd!!` | The lock is gone: they sign in at once with the temporary password and land on the change-password screen. Their other window, if any, is signed out. |
| 2.16 | Same, as `master.ops`, with "Require a new password" **off** | They sign in and the app opens straight away -- a handover, where the password you set is theirs to keep. |
| 2.17 | As `master.ops`, open your own row → Reset password | Refused: change your own from My profile. As `whole01.admin`, open anybody: no **Reset password** in the footer. |

## 3. Firm isolation — the core of this application

| # | Case | Expected |
| --- | --- | --- |
| 3.1 | As `master.ops` in FOOD01, note the customer count. Switch to MEDI01 | A different set. **These two share one schema** — if a FOOD01 customer appears here, stop and report it. |
| 3.2 | Create a customer `ISO-TEST` in FOOD01 | It does not appear in MEDI01, WHOLE01 or ELEC01. |
| 3.3 | Open a WHOLE01 sales invoice, note its number **and its customer**. Switch to ELEC01 and search that number | An invoice with the same number may well appear -- document numbers **restart per firm**, so ELEC01 has its own number 9. It must be ELEC01's own, with a **different customer**; the WHOLE01 customer must not be on it. |
| 3.3b | Still in ELEC01, search for the WHOLE01 **customer's name** from 3.3 | Not found. A name from another firm's database cannot appear -- this is the real isolation check, since numbers legitimately collide. |
| 3.4 | In ELEC01, open Reports → any report | Rows are ELEC01's. Cross-check one figure against the ELEC01 workspace. |
| 3.5 | As `whole01.admin`, try to reach another firm's data by any route the UI offers | There is none. |
| 3.6 **(HTTP)** | Call a firm-owned endpoint with `X-Firm-ID` set to a firm you are not a member of | `403`, not an empty list. An empty list would look like "no data" and hide the hole. |

## 4. Masters — customers

| # | Case | Expected |
| --- | --- | --- |
| 4.1 | Open `WHOLE01C01`, change only the phone number, save | Addresses, contacts, credit limit, payment terms and the 7.5% standing discount are all **unchanged**. This is the defect that shipped twice; check each one. |
| 4.2 | Reopen and confirm the outstanding balance | Unchanged by the edit. |
| 4.3 | On a new customer, use the place picker: choose country, then state, then district, then city | Each rung loads after the one above. Choosing a country must load states immediately, not after a second click. |
| 4.4 | Save, reopen | The place is still there, and the text fields (city, state, country) agree with the chosen ids. |
| 4.5 | Customers → Settings (needs `CUSTOMER_MANAGE_SETTINGS`) | The credit policy dialog opens. As `whole01.sales1` the action is not offered. |
| 4.6 | Set a credit limit of ₹1 on `WHOLE01C03`, then raise and approve a sales order for more | A warning names the exposure. It does **not** block — the demo firms are in warn mode. |
| 4.7 | Customer → Statement | The running balance is in date order and ends at the customer's current balance. |
| 4.8 | Customer → Ageing | The buckets sum to total outstanding, and the reconciliation line explains any gap between the bills and the account. |
| 4.9 | Assign `WHOLE01C03` to the Wholesaler group, save, reopen | The group holds. |
| 4.10 | Try to delete the `RETAILER` group while a customer is in it | Refused, naming the customer. |

## 5. Masters — vendors, products, branches, warehouses

| # | Case | Expected |
| --- | --- | --- |
| 5.1 | Open a vendor, change one field, save | Addresses, contacts, bank accounts, tax details, attachments and notes all survive. |
| 5.2 | Vendors → Categories, and → Types | Both lists load and both can be added to. (These returned nothing at all until the route order was fixed, and until 2026-09-11 the sidebar opened them on a "coming soon" placeholder -- see BACKLOG §26.) |
| 5.3 | Put a category and a type on a vendor, save, reopen | Both held. |
| 5.4 | Products → open `DETER1K` | Its UOM slots, tax profile group and category are populated. |
| 5.5 | Product → open `DETER1K` → **Attributes** tab | Fields offered match this firm's business profile. A pharmacy field must not appear in WHOLE01. (The tab is hidden until a category is set, and until 2026-09-11 it never appeared for an existing product -- see BACKLOG §27.) |
| 5.6 | Branches → rename one, save | Street lines, city, default flag and GST registration all survive. |
| 5.7 | Warehouses → rename one, save | The ten capability flags survive. (Until 2026-09-11 a warehouse with no capacity could not be saved at all -- see BACKLOG §28.) |
| 5.8 | Branches → Import, with a file whose fifth row duplicates an existing code | **Nothing** is imported. The dialog says so. Correct the file and re-import — all rows go in. |
| 5.8a | Branches → Import → **Sample file** | A CSV is saved with the eleven column headings and one filled-in example row. Choosing that file as-is previews as "1 rows ready" and imports cleanly (the example code is `BR_NORTH`; a second import of the same file is refused as a duplicate, which is correct). Reopen the imported branch: display name, both address lines and the currency are filled in (multi-word headings were silently dropped until 2026-09-11 -- see BACKLOG §31.4). The same button is on Warehouses (whose sample names the branch by **code**, pre-filled with this firm's first branch, and imports as it is), Territories, Purchase Orders and the Inventory import wizard's toolbar. A refused import names the row and field, e.g. "Row 2: mobile — A valid E.164 phone number is required." |
| 5.8b | Any import dialog, after a refusal | The message can be selected with the mouse, and the copy icon beside it puts the whole text on the clipboard. |
| 5.9 | Branches → Export, Warehouses → Export | A save dialog opens, suggesting `branches.csv` / `warehouses.csv`; after saving, the notice names the full path, and the file holds the grid's rows in the **same columns the importer reads** (code, name, display_name, ... for branches), so it can be edited and imported back. Dismissing the dialog says no file was saved. (Both were unreachable until the route order was fixed, and until 2026-09-11 both fetched the CSV, dropped it and said "Export completed." -- see BACKLOG §31.5. Territories and Vendors export the same way; Customers and Products copy their CSV to the clipboard and say so.) |
| 5.10 | Administration → **Configuration** → **UOM & Packaging** → **Packaging Levels** (two levels down the sidebar tree, a parent row only expands; or Ctrl+K and type the screen's name), pick `DETER1K` in the Product dropdown, then **type** its carton barcode into "Scan or type a code" and click **Look up** | The lookup resolves to the product and says how many base units it holds. No scanner is needed: a scanner only types the digits and presses Enter. In WHOLE01, `DETER1K` carries a `Case` level with barcode `890044465610` holding 12 base units (verified against the server on 2026-09-12). |

## 6. Configuration

Most of these screens sit under **Administration → Configuration**, a sidebar entry that expands into Business Profiles, Tax Configuration, UOM & Packaging and Numbering Series. A parent row only expands; the screens are the leaves. **Ctrl+K** opens any screen by its name and is the quickest way in.

| # | Case | Expected |
| --- | --- | --- |
| 6.1 | Administration → Configuration → **Numbering Series**, as `whole01.admin`. Then the same screen in the second client as `whole01.sales1` (same password). | As the admin, **New series**, **Edit** and **Retire** are offered on the toolbar. As `whole01.sales1`, none of the three are. |
| 6.2 | Select the sales invoice series → **Edit** → scroll to the foot of the form, below the **Active** switch. Then click **New series** and look at the same spot. | On an existing series: a locked row with a padlock reading `Next number: N` and the reason ("The counter belongs to the server, which advances it under a lock..."); no box to type in. Change the Name, save, reopen: the next number is unchanged. On a new series: a **Start numbering at** box instead, helper "Usually 1...". |
| 6.3 | **New series**: pick a document type, give it a code and name, switch **Restart numbering each financial year** on, switch **Include the financial year** off, Save. | A warning under the switches says the first document of April would repeat one from March, and to include the year or turn the restart off. The save is refused by the server with the same sentence and nothing is created. Switch Include the financial year back on and save: created. |
| 6.4 | Select the sales invoice series → **Preview next**, twice. | Matches the pattern, e.g. `SI-2026-2027-000010`, is the number 6.2 showed locked, and is the same both times: a preview issues nothing. |
| 6.5 | **As `master.ops`** with WHOLE01 selected (the Business Profiles branch is platform administration, gated on `PLATFORM_VIEW`; a firm administrator does not see it, by design): Administration → Configuration → Business Profiles → **Profiles**, edit `WHOLESALE`, and in the **Enabled features** picker tick `IMEI`, then Save | The save is refused with "These features are not implemented yet and cannot be enabled: IMEI." and the profile is unchanged. The six roadmap features (`IMEI`, `KITCHEN_MANAGEMENT`, `PRESCRIPTION_REQUIRED`, `PROJECT_MANAGEMENT`, `RECIPE_MANAGEMENT`, `SERVICE_CONTRACTS`) cannot be switched on at all; `COMMISSION` is no longer one of them. Ticking an ordinary feature such as `BARCODE` saves. The **Feature Flags** leaf beside it is the catalogue itself (name, description, active), not where a profile's features are chosen. The refusal appears in the summary at the top of the form, which scrolls into view; the dialog stays open and the profile's other fields are **not** written either (until 2026-09-12 they were -- BACKLOG §31.6). |
| 6.6 | As `master.ops` (WHOLE01), same branch → **Mandatory Attributes** → **New**: profile `WHOLESALE`, category `Core Products`, attribute `MANUFACTURER`, mandatory ticked, Save. Then as `whole01.admin`: Products → **New**, fill the required fields, category Core Products, **Attributes** tab (appears once a category is chosen) with Manufacturer left empty, Save. Afterwards untick or delete the rule. | The product save is refused, naming `MANUFACTURER` as required for that category; nothing is created. Fill Manufacturer in and save: created. (Two optional rules, `PACK_SIZE` and `COUNTRY_OF_ORIGIN`, are seeded on WHOLESALE already.) |
| 6.7 | Administration → Configuration → Tax Configuration → **Rule Simulator** (any WHOLE01 user with `TAX_SIMULATE`, e.g. `whole01.admin`). Transaction Type `SALES_INVOICE`, **Tax Profile** `GST_18_LOCAL`, Invoice Value `1000`, Run Simulation. Then change Transaction Type to `SALES_INTERSTATE` and run again. | Local: no rule matched, components CGST 9% = 90 and SGST 9% = 90, total 180. Interstate: matched rule `INTERSTATE_GST_18`, one component IGST 18% = 180, total 180, and the evaluation trace shows the rule matched. (Until 2026-09-12 the screen sent no profile and offered types no rule names, so every run answered zero and "No rule matched" -- BACKLOG §31.7.) |
| 6.8 | Administration → Configuration → UOM & Packaging → **Conversion Rules**, as `whole01.admin`. The grid lists three product rules by code (`DETER1K` PACK→KG factor 1, `SHAMP180` BOTTLE→ML 180, `TOOTH150` TUBE→G 150). Click **Add**: Product left as *Firm-wide*, From unit `PACK`, To unit `KG`, Factor `2`, Save. Then Purchases → New order for `DETER1K`, quantity 10, **Purchase UOM** `PACK — Pack` from the line's dropdown (choosing the product fills its default units first; until 2026-09-12 these were id boxes), save and open the order. | The firm-wide rule appears in the grid beside the product rules. The order line shows **Base Qty 10**, not 20: the product's own factor of 1 outranks the firm-wide 2 (verified against the server: 10 PACK of DETER1K converts to 10 KG with the firm-wide rule in place, and to 20 KG for a product with no rule of its own). Delete the firm-wide rule afterwards. (Until 2026-09-12 the Add dialog asked for unit **ids** and sent a key the server forbids, so no rule could be created from the desktop at all.) |

## 7. Buying — order to payment

All as `whole01.admin` in WHOLE01, on a build from `main` at or after 2026-09-12 (PRs #317, #319, #321 fixed three refusals in this flow). Purchase orders live under **Purchases → Purchase Orders**; receipts, invoices and returns each have their own sidebar module (**Goods Receipts**, **Purchase Invoices**, **Purchase Returns**); payments are **Finance → Payments**; stock is **Inventory → Inventory** (rows per product and warehouse) and **Inventory → Stock Ledger** (every movement with the balance after it). Lifecycle buttons (Submit, Approve, Complete, Cancel, Close) sit on the toolbar and act on the selected row; on the purchase order they are also inside the view dialog. A receipt's or return's Complete/Cancel fires straight away with no confirmation; only the order's Cancel and Close ask for a reason. Every screen reads once when opened: click **Refresh** after acting somewhere else.

**Before starting a fresh run:** Administration → Configuration → UOM & Packaging → Conversion Rules -- delete any *Firm-wide* PACK→KG rule left from 6.8. Goods Receipts → Draft filter -- Cancel any draft receipt left from an earlier run. Note DETER1K's Current in WH_NORTH on the Inventory tab; every stock figure below is relative to it.

| # | Case | Expected |
| --- | --- | --- |
| 7.1 | Purchases → Purchase Orders → **New**. Vendor `WHOLE01V01`, branch `BR_NORTH`, warehouse `WH_NORTH`, purchase date today; **Add Line**: product `DETER1K`, quantity **10**, unit price **100**; the line's Purchase UOM and Inventory UOM fill in from the product (`KG`, `KG`). **Save**. | The order appears with status **DRAFT** and a `PO-WHOLE01-BR_NORTH-2026-2027-...` number. Open it: the Line Items table shows the product as `DETER1K — ...`, the unit as `KG`, and a scrollbar under the table; the Approval banner reads "Submit this draft to send it for approval." |
| 7.2 | Select the draft: look at the toolbar and inside the view | **Approve is not offered** on a draft -- only **Submit** is -- and the Approval banner reads "Submit this draft to send it for approval." The server refuses an approval of a draft with "Submit the order first." for any client that tries; the desktop does not let you try. |
| 7.3 | **Submit**, then **Approve** | Toasts "... submitted for approval." and "... approved."; status **APPROVED**; the grid updates without the dialog closing. |
| 7.4 | Select the approved order → **Edit** → dialog **Editing withdraws the approval** → **Edit anyway**. Type a line remark and change the order remarks. **Save**. | Saved: status **DRAFT** again, the remark survives on reopening, and the view's **History** section shows the approval withdrawn. Then **Submit** and **Approve** once more. |
| 7.5 | **Goods Receipts → New**. **Purchase Order** picker (approved orders only) → yours. The line arrives with **Accepted** defaulted to 10 and "Ordered 10 · already received 0". Set Accepted to **4**, **Warehouse** `WH_NORTH`, **Save Receipt**. Select the draft → **Complete**. | After save: "Goods receipt GRN-... created as a draft. Complete it to post the stock." After Complete: "... updated.", status **COMPLETED**; Purchases → the order reads **PARTIALLY_RECEIVED**; Inventory → DETER1K in WH_NORTH is up by 4, and the Stock Ledger shows a `GOODS_RECEIPT` entry for the GRN with the balance after it. |
| 7.6 | Goods Receipts → New against the same order: the line says "already received 4", Accepted defaults to **6**. Save, Complete. | The order reads **RECEIVED**; stock is up by 10 in all; a second `GOODS_RECEIPT` entry in the ledger. |
| 7.7 | Select the **first** receipt (the 4) → **Cancel** | Status **CANCELLED**; the ledger shows `GOODS_RECEIPT_REVERSAL` −4 against that GRN and DETER1K in WH_NORTH is up by **6** from where it started (10 − 4); the order drops back to **PARTIALLY_RECEIVED**; Finance → Journal shows the reversal. Then from `backend\`: `.\.venv\Scripts\python.exe scripts\verify_sample_data.py` -- all five checks pass. |
| 7.8 | Goods Receipts → select the **seeded** `GRN-WHOLE01-WHL_HO-2026-2027-000006` (purchase invoice `PI-2026-2027-000006` was raised against it and approved) → **Cancel** | Refused: "Goods receipt ... has been invoiced, so cancelling it would leave the accrual and the payable disagreeing. Cancel the purchase invoice first, or raise a purchase return." Nothing changes. *(A purchase invoice cannot be raised from the desktop -- BACKLOG §31.9 -- so the case uses a seeded one.)* |
| 7.9 | **Purchase Returns → New**. **Goods Receipt** picker (completed receipts only) → your second receipt (the 6). On its line set **Returning** to **2**, click the **Damaged** chip, **Save Return**. Select the draft → **Approve**, then **Complete**. | After save: "Purchase return PR-2026-2027-... created as a draft. Approving and completing it is what takes the stock off." (numbered after the seeded returns, not `000001`). After Complete: status **COMPLETED**; the ledger shows `PURCHASE_RETURN` −2 and DETER1K in WH_NORTH is up by **4** from the start; Finance → Journal shows the return's entry; Reports → Operational Reports → **Damaged goods returned** lists the line. Open the return: product and unit read as code and name, not ids. |
| 7.10 | Reports → **Operational Reports**: `Purchase order register`, `Orders not yet received`, `Overdue purchase orders`, `Orders by supplier`, `Orders by buyer`, `Purchases by product` | Each opens with rows and a row count in the header. The register holds the seeded orders plus yours; not-yet-received and overdue each hold the seeded APPROVED orders; the three by-... reports are populated. |
| 7.11 | Finance → **Payments → Record Payment**. **Paid to** `WHOLE01V01`; **Amount**: the Outstanding of the oldest bill listed under **Apply to bills**; **Method** Bank; **Oldest first**; **Record payment**. | Toast "PAY-... recorded and posted to the ledger." Open Record Payment again for the same vendor: that bill's Outstanding is 0 or gone; Finance → Journal shows the payment (Dr Accounts Payable / Cr Bank). |

## 8. Stock

8.1--8.4 as `whole01.admin` in WHOLE01, which has two warehouses once 5.8a has run (`WHL_DC` seeded, `WH_NORTH` under `BR_NORTH` from the import). 8.5--8.7 as `medi01.admin` in MEDI01, whose `AMOX500` and `PARA650` are batch-tracked with staggered expiries (batches are numbered `AMOX500-YYYYMM`, one per month received, expiring 18 months after receipt); its only warehouse is `MEDI_DC`. 8.8 as `elec01.admin` in ELEC01, whose `MIX500` carries seeded serial numbers. Everything below lives under **Inventory** in the sidebar, in two collapsible groups that must be clicked open: **Stock** holds Inventory, Opening Stock, Physical Count, Stock Ledger, Transactions, Stock Summary and Stock Search; **Batch & Serial** holds Batches, Lots, Serial Numbers and Expiry Monitor. Ctrl+K and typing a tab's name opens it directly. Transfer, Write off and Quarantine are toolbar buttons on the **Inventory** tab and act on the selected row. Every screen reads once when opened: click **Refresh** after acting somewhere else. Note DETER1K's Current in WH_NORTH before starting; the figures below are relative to it.

| # | Case | Expected |
| --- | --- | --- |
| 8.1 | Inventory → **Stock** → **Stock Summary**. Then Inventory → Stock → **Inventory**, filter panel: Product `DETER1K`, **Apply**. | The summary's figures for WHOLE01 and for WH_NORTH add up to the rows the Inventory grid shows for them. DETER1K has one row per warehouse (WH_NORTH and, if it was ever received there, WHL_DC) with Current, Available and Reserved; Current in WH_NORTH is what section 7 left (start + 8). |
| 8.2 | Inventory → Stock → **Stock Ledger**, filter Product `DETER1K`, **Apply**. Open the detail (eye icon) on one row. | Every row has a Type, a Reference naming a document, a signed Quantity and the Balance after it: the two GRNs from 7.5 and 7.6, the cancelled receipt's reversal from 7.7, the return from 7.9. The balances run in order and the last one equals Current on the Inventory tab. The detail dialog is titled "Ledger details". Then set **Transaction type** to `GOODS_RECEIPT` and Apply: only the receipts remain. *(Known: the type list offers values the server never writes -- GOODS_ISSUE, PHYSICAL_COUNT, DAMAGE, EXPIRY, CORRECTION -- and lacks ones it does, such as DISPATCH and WRITE_OFF; BACKLOG §31.13.)* |
| 8.3 | Inventory → Stock → **Inventory** → select the DETER1K / WH_NORTH row → **Transfer**. The dialog "Transfer stock" says how much is available here. Quantity **3**, **Move it to** `WHL_DC - Bulk Goods Warehouse1` (every destination reads code and name), Reference `TRF-0001`, **Transfer**. | Toast "Stock transferred." Refresh: WH_NORTH is down by 3, WHL_DC up by 3 (a row appears if there was none), and the firm's total for DETER1K is unchanged. Stock Ledger: `TRANSFER_OUT` −3 and `TRANSFER_IN` +3, both referenced `TRF-0001`. Finance → Journal: **no** entry for it -- the dialog's footnote says why. Then try Quantity **999**: refused in the dialog, in a **red banner with the error icon**, with "This location holds N, so 999 cannot be moved out of it." before anything is sent. A transfer to a warehouse under another branch is allowed (WH_NORTH is under BR_NORTH, WHL_DC under the head office). |
| 8.3a | Same row → **Write off**. Quantity **1**, **Reason** Damage, Reference `WO-0001`, **Write off**. | Toast "Stock written off." WH_NORTH down by 1 more; Stock Ledger `WRITE_OFF` −1 referenced `WO-0001`; Finance → Journal shows the write-off (Dr Inventory Adjustment / Cr Inventory). |
| 8.3b | Same row → **Quarantine**. **Hold back** selected, Quantity **2**, Reference `QH-0001`, **Hold back**. Then Quarantine again → **Release**, Quantity 2, Reference `QR-0001`, **Release**. | After the hold: toast "Quarantine updated.", Available down by 2 while Current is unchanged; Stock Ledger `QUARANTINE_HOLD`. After the release: Available back up; `QUARANTINE_RELEASE`. No journal for either, as the footnote says. Holding more than is available is refused by name. |
| 8.4 | Inventory → Stock → **Physical Count** → **Open Count**. Branch `BR_NORTH`, Warehouse `WH_NORTH`, Count date today, **Open**. The sheet opens on its own. The sheet's Product column reads `DETER1K - ...` (code and name, never an id). In DETER1K's **Counted** box type its Expected **minus 1**; leave every other line blank. **Save progress**, close, reopen the count from the list, then **Post count** → the confirmation says the uncounted lines will be left alone → **Post count**. | Toast "PC-... opened over N lines." on opening; the list row reads "1 of N lines counted" after the save and "N lines · posted" after the post. Difference showed `-1` live while typing. After posting: Inventory → DETER1K in WH_NORTH is down by 1; Stock Ledger `ADJUSTMENT` −1 referenced by the count number; Finance → Journal shows the adjustment; the untouched lines moved nothing. Reopening the posted sheet is read-only ("Posted. The differences are in the ledger."). |
| 8.5 | As `medi01.admin` in MEDI01. Inventory → **Batch & Serial** → **Batches**, search `AMOX500`: note the batch with the **earliest Expiry Date** and its Available. Then Sales → Sales Orders → **New**: any customer, one line `AMOX500` quantity **5**, Save, then Approve (Submit first if that is what the toolbar offers). Sales → Delivery Notes → **New**, pick that order: the line's "Expected to ship from -- earliest expiry first, decided at dispatch" lists the batches it will draw. **Save Delivery Note**, select the draft → **Approve** → **Dispatch**. | The preview names the earliest-expiry batch first (`AMOX500-YYYYMM (expires YYYY-MM-DD): 5`). After Dispatch: status DISPATCHED; Stock Ledger (Product `AMOX500`) shows a `DISPATCH` −5 referenced by the delivery note; Batches → that earliest batch's Available is down by 5 and the later batches are untouched. |
| 8.6 | Inventory → **Batch & Serial** → **Expiry Monitor** (the group is collapsed until clicked; Ctrl+K and typing the name also opens it). | Six cards -- Expired Today, Expire in 7 Days, Expire in 30 Days, Total Expired, Quarantine, Recalled -- with counts (Total Expired > 0: batches received in 2024 and early 2025 have passed their 18 months), then an **All Batches** grid with Batch #, Product, Status, Qty, Available, Expiry Date and Warehouse. *(The screen shows counts per window and an absolute expiry date; a "days remaining" column does not exist -- BACKLOG §31.13.)* |
| 8.6a | Still in MEDI01, Inventory → Stock → **Inventory** (you arrived here from WHOLE01 with a Product filter set in 8.1). | The tab renders; the remembered WHOLE01 filter is dropped, the panel reads "Filters" with none active, and choosing a MEDI01 warehouse works. *(A remembered id from another firm used to take the section down with "This section failed to render".)* |
| 8.7 | Sales → Sales Orders → **New**: line `PARA650` with a quantity **larger than PARA650's total Available** on the Inventory tab (check it first), Save, Approve. MEDI01's credit policy is **Block** at 100%, so pick a customer with room on their limit or keep the value modest; a refused approval now says so ("... would be at N% of a ... credit limit"). Delivery Notes → **New** against it. | The editor's preview ends with "Short by N -- there is not enough available stock to cover this line." Saving is still allowed; **Dispatch** is refused with the server's own sentence ("Insufficient available stock for dispatch line." or "Reservation is insufficient for dispatch quantity."), status stays APPROVED and the ledger shows no DISPATCH. Cancel the note and the order afterwards so 8.5's figures stay readable. |
| 8.8 | As `elec01.admin` in ELEC01. Inventory → **Batch & Serial** → **Serial Numbers**; search `MIX500-`. Open one row's detail. | Up to 20 rows `MIX500-2026-0001` onward, Status AVAILABLE, Warranty End a year after the seed date, Warehouse `ELC_DC`. The detail dialog is titled "Serial: MIX500-2026-0001" and shows warranty start and end, warehouse and remarks ("Seeded onto stock on hand."). The Status filter narrows to AVAILABLE. *(The old row called this a gap; ELEC01's MIX500 has been serialised since 2026-09-08.)* |

## 9. Selling — quotation to cash

All as `whole01.admin` in WHOLE01, in order: each step feeds the next. Quotations, Sales Orders, Delivery Notes, Sales Invoices and Sales Returns are each their own sidebar entry (no groups); Credit Notes and Proforma are children of the sidebar entry called just **Sales** (under Masters, above Quotations -- click it to expand); receipts are **Finance → Receipts**; the customer's balance is on **Masters → Customers** (the **Outstanding** and **Advance** columns). Seed facts the rates below rest on: `WHOLE01C01` Vijaya Super Stores has a 7.5% standing discount; the firm-wide `STANDING` price list on `DETER1K` has breaks 0 → 2%, 15 → 4.25%, 18 → 6.75%; `WHOLE01C02` Anand Agencies has its own `NEGOTIATED` list at a flat 9.25%; promotion `BULK5` gives 7.5% on a line of 25 or more (its earlier revision gave 5% and only reaches documents dated before the second seeded year); `WELCOME` gives 2.5% only when coupon `WELCOME10` is presented. DETER1K sells at 84 under `GST_18_LOCAL`. A resolved percentage is **not printed on a saved document**: read it by reopening the editor -- **Revise** on a quotation, **Edit** on a draft order -- where a rate the server resolved is shown **under a blank box** as "Last priced at N% by the price list" (or a promotion, or the customer's standing rate), and a rate somebody typed is refilled into the box. Saving a revision prices resolved lines afresh, which is what lets a ladder move with the quantity (BACKLOG §31.14). Two facts the money rows rest on, both verified by driving the flow against the running backend on 2026-09-13: WHOLE01 has **TCS enabled** (0.1% on money received over a 5,000 threshold), so every receipt raises what the customer owes by the TCS on it -- 0.1%, or **1% for a customer with no PAN**, which WHOLE01C01 is -- and the Record Receipt dialog says so; and WHOLE01C01 already owes on seeded invoices (7,498.96 on 2026-09-13), so **an excess on a receipt becomes an advance only when the customer owes nothing else** -- otherwise it comes off the account balance and the receipt shows it as "on account". Every screen reads once when opened: click **Refresh** after acting elsewhere. The document grids list **newest first within a date** and carry a **Created** column (local date and minute) since 2026-09-13, so the document you just raised is the top row; quotations and returns show "made <date> <time>" in the row's subtitle.

| # | Case | Expected |
| --- | --- | --- |
| 9.1 | Quotations → **New Quotation**. Customer `WHOLE01C01`, leave "These prices stand until" as offered, **Add line**: Product `DETER1K`, Quantity **12**, leave **Discount %** empty (its helper reads "Blank takes this customer's 7.5%, or a price list where one applies."). **Create draft**. Select it → **Revise**. | Toast "QT-... drafted, good until ... Nothing is reserved by it." On Revise the line's Discount % box is blank and reads beneath it "Last priced at **2**% by the price list. Blank prices it afresh." -- the `STANDING` list's first break outranks the customer's 7.5% standing rate. Close the revision without saving. |
| 9.2 | Select the quotation → **Revise**, Quantity **18**, leave Discount % blank, **Save revision**. Revise again to read the helper. | "Last priced at **6.75**% by the price list" -- the ladder takes the highest break at or below 18, not the first one above zero. *(Until 2026-09-13 a revision re-sent the stored rate as typed, so the line kept 2%.)* |
| 9.3 | Quotations → **New Quotation** for `WHOLE01C02`, one line `DETER1K` qty **18**, Discount % empty, Create draft, then Revise to read the helper. | "Last priced at **9.25**% by the price list" -- that shop's own `NEGOTIATED` list replaces the firm-wide ladder rather than amending it. |
| 9.4 | On the same quotation, Revise: Quantity **30**, Save revision, Revise to read the helper. | "Last priced at **7.5**% by a promotion" -- `BULK5` applies at 25 and above and a promotion outranks either price list, so it is 7.5 for either customer. *(The plan used to say "5 or 7.5"; 5 was the promotion's first revision and reaches only documents dated before the second seeded year.)* |
| 9.5 | Revise: type **0** into Discount %, Save revision, Revise to read. | The box itself reads **0** (a typed rate is kept, not re-priced) and the line total is the full 30 × 84. Zero is a refusal of every arrangement, not a silence. Then Revise once more, set Quantity back to **12** and clear the box, Save revision -- this is the quotation 9.6 converts. |
| 9.6 | Select the C02 quotation → **Mark as sent** → **Customer accepted** (dialog "Accept QT-...", give a Reason, **Accept**) → **Convert to order**. | Toasts "QT-... marked as sent...", "QT-... accepted. Converting it is what creates the order.", "QT-... became SO-.... The order reserves the stock when it is approved." The order is numbered in the `SO` series. Afterwards the quotation no longer offers **Convert to order** at all. **(HTTP)** forcing it, `POST /api/v1/quotations/{id}/convert`, is refused: "Quotation QT-... already became SO-...." (driven 2026-09-13). |
| 9.7 | The converted order carries the quoted 9.25% as an agreed (typed) rate, so a coupon cannot lower it; use a fresh order instead. Sales Orders → **New Order**: Customer `WHOLE01C01`, **Ships from** `WHL_DC` (the form offers the first warehouse, `WH_NORTH`, which holds 1 unit), one line `DETER1K` qty **12**, Discount % blank, **Coupon** `WELCOME10`, **Create draft**. Select it → **Edit** to read the line. Then replace the coupon with `WELCOME10B`, **Save order**, Edit again. | Toast "Order drafted. Approve it to commit the stock and the credit." Under the line's blank Discount % box: "Last priced at **2.5**% by a promotion" -- the coupon's offer is a tier that **replaces** the price list's 2%, not one that compounds onto it (promotions stack only with each other). With `WELCOME10B` the helper still reads **2.5**: it is a second code on the same `WELCOME` offer, so it reaches it just as well. *(On the order converted in 9.6 the box itself reads 9.25 and the coupon changes nothing -- the quoted rate carries over as the deal; BACKLOG §31.14.)* |
| 9.8 | Edit the same order (still a DRAFT -- an approved order cannot be edited; if yours is approved, raise a new one the same way), Coupon `NOSUCHCODE`, **Save order**, Edit again. | Saves with "Order updated." and the helper falls back to "Last priced at **2**% by the price list". A typo in a field that gives money away must not refuse a sale; the helper under Coupon already says "Unrecognised codes are ignored". Put `WELCOME10` back and save. This order, not the converted one, is what 9.9 onward uses. |
| 9.9 | Select the order → **Approve**. Then Inventory → Stock → **Inventory**, filtered to DETER1K. | Status **APPROVED**; a credit warning toast may appear first (WHOLE01 warns at 80% and never blocks). Reserved on DETER1K in WHL_DC is up by 12. *(An order taken for more than the warehouse holds is still approved -- it is a back order, and that warehouse's Available goes negative.)* Reports → Operational Reports → **Promotion claims**: the `WELCOME` row for this order (coupon as last saved) reads **CLAIMED** (it was pending while the order was a draft). |
| 9.10 | Select the order → **Hold** (dialog "Hold SO-...", give a reason, **Hold**). Then Delivery Notes → **New**, pick the order in **Sales Order ***, **Save Delivery Note**. | Toast "SO-... is on hold."; the Status cell reads **APPROVED (on hold)**. The delivery note is refused **on save**, in the editor's banner: "SO-... is on hold and cannot be dispatched ("<your reason>"). Release it first." Reserved on DETER1K is **unchanged** -- a hold says "not yet", not "never". *(The refusal is at note creation; there is no Dispatch button on the order.)* |
| 9.11 | Select the order → **Release**. | Toast "SO-... released."; the Status cell reads plain **APPROVED** again -- the status it had, not a reset. The hold reason stays on the record. |
| 9.12 | Delivery Notes → **New**, pick the order, on its line set **Delivering** to **5** (the field defaults to the 12 reserved), **Warehouse** `WHL_DC - Bulk Goods Warehouse1` (pickers read `CODE - Name`), **Save Delivery Note**. Select the draft → **Approve** → **Dispatch** -- and do press Dispatch: an approved note moves nothing. *(A warehouse of another branch is fine too: stock is looked for at the warehouse's own branch; until 2026-09-13 dispatch paired it with the order's branch and refused, "Insufficient available stock for dispatch line.")* *(Shipping from a warehouse other than the order's is allowed: the reservation is released where the order made it. Until 2026-09-13 it was released from the note's warehouse, and dispatch was refused with "Reserved quantity cannot become negative.")* | Toast "Delivery note DN-... created as a draft. Dispatching it is what moves the stock." Dispatch shows no toast; after Refresh the note reads **DISPATCHED**. Sales Orders: the order reads **PARTIALLY_DELIVERED**. Inventory: WHL_DC on hand down by 5, and the order's warehouse Reserved down by 5. Stock Ledger: `DISPATCH` −5 on DETER1K referenced by the DN. Finance → Journal Entries: the note's cost-of-goods entry. |
| 9.13 | Double-click the delivery note to open its view; note the line's **Unit Price**. Then open the sales order's view and compare. | **Identical.** The note ships the deal the order struck and does not re-read the customer's current rate. *(Both views print the product as `DETER1K — ...` since 2026-09-13; the order view prints the discount as an amount, not a percentage -- BACKLOG §31.14.)* |
| 9.14 | Delivery Notes → **New** against the same order: Delivering defaults to the remaining **7**, **Warehouse** `WHL_DC - Bulk Goods Warehouse1`. Save, Approve, **Dispatch**, Refresh. | The order reads **DELIVERED** only once **both** notes are DISPATCHED (with one still APPROVED it reads PARTIALLY_DELIVERED and the figures stop short by that note). The ledger shows a second `DISPATCH` −7; the order's Reserved is back to 0. |
| 9.15 | Sales Invoices → **New Invoice**. In **Bill this delivery note** (helper "Only notes with something left to bill.") pick the **first** note -- the 5-unit one (items read "DN-... · date · Vijaya Super Stores"). Its line reads "dispatched 5 · at 84 less 2.5%" with **Bill** defaulted to 5. Type **6** into Bill. | Refused before sending: "Only 5.0 left to bill." (the server's own refusal, reached by an API client, is "Invoice quantity exceeds the available source quantity.") Set it back to **5**, **Create draft**: toast "Invoice created as a draft. Approve it to post the journal." A note that gave a unit free would show the free unit apart from the billable 5, and it could not be billed. |
| 9.16 | Select the invoice → **Approve**. Then Masters → Customers → `WHOLE01C01`. | Status **APPROVED**. Finance → Journal Entries shows the invoice's `SI-...` entry as the top row (same-day entries list newest posting first since 2026-09-13); select it → **View** (added 2026-09-13; the screen showed no lines before): Dr 1100 Trade Receivables 483.21, Cr Sales 409.50, Cr Output Tax 73.71 -- **one** tax line; the CGST 9 / SGST 9 split is on the invoice and its print, not in the journal. The customer's **Outstanding** is up by the invoice's grand total. |
| 9.17 | With the invoice selected click the **Print settings** icon: set **How many copies** to 2 and give **Copy 1 label** / **Copy 2 label** (they prefill as ORIGINAL FOR RECIPIENT / DUPLICATE FOR TRANSPORTER), save. Then **Print**. | The PDF carries both parties' GSTINs, an HSN column (`340220`), the CGST/SGST split, the HSN-wise summary, "AMOUNT CHARGEABLE, IN WORDS", and the two labelled copies. *(Copies are not defaulted for an invoice until Print settings is saved, which is why the step comes first. These are the firm's own settings, stored on the server per document type, and saving them needs `SETTINGS_UPDATE` -- the firm administrator; until 2026-09-13 the dialog asked for a platform code no firm role can hold and opened read-only. The printer dialog's own copy count is separate and repeats the whole set.)* |
| 9.18 | Finance → **Receipts** → **Record Receipt**. *(The TCS notice is the small text under **Against order (optional)**; it appears once a customer and an amount are both filled in.)* **Received from** `WHOLE01C01`, **Amount** half of the invoice's outstanding (241.60 for a 483.21 invoice), **Method** Bank, then under **Apply to invoices** type the whole amount into the **Apply** box of *your* invoice's row -- **not Oldest first**, which clears the oldest seeded invoice, because the customer already owes on seven. **Record receipt**. | The dialog shows a TCS notice for the receipt: WHOLE01C01 holds **no PAN**, so TCS is charged at **1%**, not 0.1% (2.42 on 241.60). Toast "RC-... recorded and posted to the ledger."; the row's subtitle reads "Cleared SI-..." and its badge **Applied**. Customers: Outstanding down by the amount **less the TCS** (7,982.17 → 7,742.99 on 2026-09-13); the invoice keeps the rest outstanding (241.61). |
| 9.19 | **Record Receipt** again for `WHOLE01C01`: Amount = **the invoice's remaining Outstanding + 100** (341.61), type exactly the invoice's Outstanding (241.61) into its **Apply** box, Record receipt. | The TCS notice (small text under **Against order (optional)**) reads 3.42 at 1.000%; the running line above the invoice table reads "100.00 left on account" before saving; the saved row's badge reads **On account 100** and the invoice drops out of the outstanding list. Customers: Outstanding falls by the **whole** receipt less TCS, and **Advance is unchanged** -- the customer still owes on seeded invoices, so the 100 is money against the account, not an advance. Advance rises only when a receipt exceeds everything the customer owes; never a negative balance either way. |
| 9.20 | Sales Invoices → New Invoice against the **second** delivery note (the 7), Create draft, Approve. Then Finance → Receipts: on the on-account receipt click the icon tooltipped **Apply to an invoice**. In "Apply RC-..." choose the new invoice, **Amount** 100 (what is on account), **Apply**. | Toast "RC-... applied to SI-...". The dialog's own line says it: "Nothing moves in the ledger. The money arrived when the receipt was recorded." Finance → Journal Entries shows **no new entry**; the receipt's badge changes from **On account 100** to **Applied**; Customers: Outstanding and Advance are **unchanged**, because the 100 already reduced the balance when the receipt was recorded (only money that had become an advance would move it). Applying more than is on account is refused: "RC-... has only 0.00 left unapplied." (the icon may simply be gone once nothing is left). Customers on 2026-09-13: 8,081.29 before and after. |
| 9.21 | On the first receipt (9.18) click the icon tooltipped **Reverse**, give a reason in "Why is it being reversed?", **Reverse**. | Toast "RC-... reversed."; the row's badge reads **Reversed**; Journal Entries shows the mirror entry `RC-...-REV` and the receipt's TCS entry reversed. Customers: Outstanding and Advance are back to exactly where they were before that receipt, TCS included. Reversing it again is refused: "RC-... has already been reversed." |
| 9.22 | Sales Returns → **New Return**. **Returned against**: the first invoice -- entries read "SI-... · date · customer" and the list mixes every customer's recent notes **and** invoices, so pick the one ending in **Vijaya Super Stores** (a return raised against another customer's document credits that customer; cancel it and raise again); **Line** 1 (an invoice with one product has one entry, labelled "Line 1"); **Taken back into** `WHL_DC - Bulk Goods Warehouse1`; **Quantity returned** 2. **Create draft**. Select it → **Approve** → **Complete**. Try Quantity returned 9 first if you want the cap: "Only 5.0 went out on this line." (server: "Return quantity exceeds what was dispatched on the source document (5.0000 sent, 0.0000 already returned).") | Toasts "SR-... created as a draft...", "SR-... approved. Nothing has moved yet...", then "SR-... completed: 2 back on the shelf and <amount> credited to the customer." The detail pane's "What this moves" card ticks Stock, Customer and Ledger. Stock Ledger: `SALES_RETURN` +2 in WHL_DC; Customers: Outstanding down by the credit (193.28 for 2 × 84 less 2.5% plus 18%). |
| 9.23 | Sidebar **Sales** (expand it) → **Credit Notes** → **Raise credit note** (top right). **Invoice**: the first invoice (entries name the customer); **Line** 1; **Reason** Rate difference; **Credit, before tax** 50; **Raise**. Then the row's **Approve**. | Grid row reads `59.00 (tax 9.00)`: the tax is 18% of 50, the rate that line was charged, not a profile rate read today. Approve toast "CN-... — approved. The credit and the tax are on the ledger." Customers: Outstanding down by 59. |
| 9.24 | **Raise credit note** again on the same line with **Credit, before tax** **400** -- with the 50 already credited, more than the line was charged (5 × 84 less its discount). | Refused with "A credit note cannot credit more than the line was charged: 409.50 charged, 50.00 already credited." (5 × 84 less 2.5%). The sales return in 9.22 is deliberately not netted off the cap. |
| 9.25 | Sidebar **Sales** → **Proforma** → **New**. **Sales order**: the order from 9.7 onward, now DELIVERED -- entries read "SO-... — customer — total" (only approved, part-delivered, delivered or closed orders are offered, so the order converted in 9.6, still a draft, is not), **Raise**. Select it → **Issue**. | Toasts "PI-... raised. Issue it when the customer needs it." then "PI-... issued." The number is a `PI` series. Finance → Journal Entries: **nothing** posted; Customers: Outstanding unchanged. The pane says "Not a tax invoice — no input tax credit is available against this document." |
| 9.26 | The order is DELIVERED so it cannot be edited; instead Sales Orders → **New Order** for `WHOLE01C01`, **Ships from** `WHL_DC`, one line `DETER1K` qty 3, Create draft, Approve; Proforma → New against it, Raise, Issue. Then Sales Orders → select that order → Edit is disabled; so open its view and note the lines; then **Cancel** the order (this screen asks no reason; until 2026-09-13 Cancel and Close answered "body: Field required" here). Proforma → Refresh → reopen the proforma. | The proforma's lines and totals are unchanged by anything done to the order afterwards -- they were snapshotted when it was raised, as the Raise dialog said. *(A DRAFT order can be edited; an approved one cannot, so cancellation is the only later change available here.)* |

## 10. Pricing, promotions and incentives

All as `whole01.admin` in WHOLE01. Price Lists, Promotions, Commission and Targets are tabs of the **Sales** module (a flat list); Loyalty is a tab of **Masters**; the promotion and loyalty reports are entries of **Reports → Operational Reports** or **Financial Reports** (two flat lists, no parameters). Seed facts, verified against the running backend on 2026-09-13: `STANDING` breaks 0 → 2%, 15 → 4.25%, 18 → 6.75% on DETER1K; `BULK5` has two revisions (5% to 2025-03-31, 7.5% from 2025-04-01), 34 claims across both; `BIGORDER` takes 200 off a bill of 4,500 or more and **ends the stack**; `WELCOME` is coupon-only at 2.5% with codes `WELCOME10` (4 claims) and `WELCOME10B` (1 claim -- your section 9 order, saved with that code); the loyalty scheme gives 2 points per 100, worth 1 each, expiring after 24 months, 50 needed before spending; `whole01.sales1` is **Asha** (15% of what is collected on DETER1K, 4% on everything else; the seeded DETER1K rule measures **value**, not margin) and `whole01.sales2` is **Bala** (a ladder: 2% to 50,000 then 4%, nothing below 1,000, 2% bonus when the target is met); two payouts are seeded for April to June 2026, Asha's paid and Bala's approved. On the collected basis Asha came out at **6.07%** (5.8% before section 9's receipts) and Bala at exactly **2.0%**, re-derived on the evening of 2026-09-13. Credit Notes, Proforma, Price Lists, Promotions, Commission and Targets are children of the sidebar entry called just **Sales** (under Masters, above Quotations).

| # | Case | Expected |
| --- | --- | --- |
| 10.1 | Sales → **Price Lists**. Select `STANDING` (do not double-click yet). | The pane on the right reads `STANDING · applies to Everyone`, "In force from 2000-01-01", and under **Rates** three lines for DETER1K: `2%`, `from 15: 4.25%`, `from 18: 6.75%`. The grid's **Products** column reads 3 (it counts rate rows). |
| 10.2 | Double-click `STANDING` (or the row's pencil) → **Add product**: Product `DETER1K`, **From qty** 25, **Discount %** 8, **Save**. Then Quotations → New Quotation for `WHOLE01C01`, `DETER1K` qty 30, Create draft, Revise to read the helper. Afterwards remove the 25 break again. | Toast "Price list saved."; selected, the pane shows a fourth rate line `from 25: 8%`. The quotation still reads "Last priced at **7.5**% by a promotion": `BULK5` outranks the list at 25 and above. *(Seeing the list take effect would mean ending BULK5, and editing an active offer makes a new revision that cannot be taken back, so that half is left to `test_a_promotion_reaches_a_quotation_line` and the pricing unit tests.) Remove the 25 break afterwards: double-click STANDING, the row's ✕ (tooltip "Remove this rate"), Save -- or it prices every later line of 25 or more.* |
| 10.3 | Sales → **Promotions** (Offers). | `BULK5` appears as **two rows**: Gives `5% off the line` In force `2024-04-01 to 2025-03-31`, and `7.5% off the line` `From 2025-04-01`. Select the second: the pane reads "BULK5 · revision 2 · applies at 10" and "Applies when: line_quantity GREATER_OR_EQUAL 25.0000" (the condition prints raw). Edit it, change nothing but the Description, Save: toast "Promotion BULK5 saved as a new revision; the one you opened is now inactive." and a third BULK5 row appears -- an active offer is superseded, never rewritten. This is permanent: 10.4 then counts **3** versions. Press Cancel instead of Save to keep the seeded two. |
| 10.4 | Reports → **Operational Reports** → **Promotion performance**. | One row per offer: `BULK5` with Version count **2** (**3** if you saved the edit in 10.3), Claimed count **34**, Benefit amount 12,126.16, Customer count 4 -- the revisions collapsed to one row. `BIGORDER` 23 claims, `WELCOME` 5 (4 seeded plus your section 9 order), `CLEARANCE` 0 -- it never applies, because BIGORDER ends the stack before it on every large order. |
| 10.5 | Reports → Operational Reports → **Coupon performance**. | Two rows: `WELCOME10` (promotion WELCOME) with Claimed count 4 and 2 customers, and `WELCOME10B` with **1** -- your section 9 order SO-2026-2027-000020, saved with that code. A code nobody has presented is still listed, at 0. |
| 10.6 | Reports → Operational Reports → **Promotion claims**. | One row per claim with Promotion code, Coupon code, Customer name, Document type (always SALES_ORDER -- only orders claim), Document number, Redeemed on, Benefit amount and Status (CLAIMED / PENDING / REVERSED). Your section 9 order is the top row: `WELCOME`, coupon `WELCOME10B` (the code it was last saved with), Vijaya Super Stores, SO-2026-2027-000020, 25.20, CLAIMED. **62 rows** in all on 2026-09-13 -- BULK5 34 + BIGORDER 23 + WELCOME 5, the same counts 10.4 shows. |
| 10.7 | Sales Orders → New Order for `WHOLE01C01`: `DETER1K` qty **60** at 84 (gross 5,040), Create draft, Edit to read. | Under the line's blank box "Last priced at **7.5**% by a promotion" (BULK5, not CLEARANCE's 1% at 40+: promotions apply in priority order and BULK5 is first), and the **Discount on the whole order** box is blank with the helper "Last taken off: 200 by a promotion. Blank prices it afresh." -- `BIGORDER` took the bill. *(Until 2026-09-13 the box was refilled with 200 and the Coupon box opened empty, so saving the order again switched both offers off; press **Save order** unchanged and Edit again to see both survive.)* `CLEARANCE` (priority 30) did **not** apply: BIGORDER (priority 20) ends the stack. Cancel the order afterwards (Cancel works on this screen since 2026-09-13). *(Driven through `POST /api/v1/promotions/simulate` on 2026-09-13: BULK5 and BIGORDER applied, line discount 378.00, bill discount 200.00.)* |
| 10.8 | Masters → **Loyalty**. Then Reports → Financial Reports → **Loyalty balances**. | The Loyalty page shows the scheme banner ("2 points per 100, worth 1 each and expire after 24 months. At least 50 before any can be spent." -- it printed "2.0000 ... 1.0000" until 2026-09-13) and the ledger (On, Customer, Why, Against, Points, Worth, Expires). The balances report lists each customer's Points and Amount: Anand Agencies 1,311.12, Classic Departmental Stores 1,085.27, Revise Check 2 384.79, Vijaya Super Stores 354.64 (2026-09-13). Pick one and add up its EARNED/REDEEMED/EXPIRED rows in Reports → Operational → **Loyalty movements**: the sum is the balance. |
| 10.9 | Sales Invoices → select an APPROVED invoice of `WHOLE01C02` (Anand Agencies, ~1,300 points) with something still owed (e.g. SI-2026-2027-000004, 3,698.95) → **Use points**: in "Use points on SI-..." type 100 → **Use them**. | Toast "100 points used on SI-...". Finance → Journal Entries: the top row is `LOY-RED-SI-...`; select it → **View** (or double-click): Dr **2600 Loyalty Payable** 100.00 / Cr **1100 Trade Receivables** 100.00. Finance → Receipts → **Record Receipt** → Received from `WHOLE01C02` (then Cancel the dialog): that invoice's **Outstanding** is 100 lower (3,598.95 for SI-2026-2027-000004); its Grand Total and tax are unchanged -- the bill is **settled**, not discounted. Customers: Anand's Outstanding is 100 lower too. *(Until 2026-09-13 the receipts list still showed the full amount after points were spent, so a receipt could collect that 100 again.)* |
| 10.10 | **Use points** again on the same invoice, type **5000** (more than the ~1,211 Anand holds after 10.9) → **Use them**. | Refused outright, not trimmed: "That customer holds 1211.1153 points, not 5000.0000." No journal entry, no balance moves. |
| 10.11 | Reports → Operational Reports → **Points about to lapse**. | Rows per unspent batch within 90 days -- Customer name, Points (what is *left* of the batch after spending), Amount, Earned on, Expires on, Days remaining -- ordered by expiry then customer. Rows with a **negative** Days remaining are batches already past their date that no expiry sweep has taken yet -- the balance still counts them until the sweep runs. On 2026-09-13 after 10.9: 6 rows, Anand 60.16 (2026-05-22, −114), Anand 160.59 (−93), Classic 54.12 (−63), Anand 69.39 (29), Classic 160.16 (39), Classic 160.59 (60). Anand's first batch was 160.16: the 100 points spent in 10.9 came out of the **oldest** batch first, even one already past its date. |
| 10.12 | Sales → **Commission** → **Collected** view: Collected from `2024-04-01` to today, **Show**. Divide each salesman's Commission by their Collected. | Asha's rate is **neither** of the two that govern her: a blend of 15% of the money collected on DETER1K and 4% of the money collected on everything else (6.07% on the evening of 2026-09-13, after section 9's receipts; it moves with every receipt, so check the shape rather than the figure). Her Paid on reads "Money collected", Target "Met" -- Sales → **Targets** → **Achievement** (from 2026-04-01 to 2026-09-08) shows why: target 20,145.00 invoiced, achieved 25,181.35 (125%). |
| 10.13 | Same report, Bala. | Exactly **2.00%** -- the bottom band of his ladder; a round number precisely because a ladder's floor is. Target "Missed": Targets → Achievement shows 19,659.00 wanted, 15,122.46 invoiced (76.9%), 4,536.54 short, so his 2% target bonus is not added. |
| 10.14 | Sidebar **Sales** → **Commission** → **Payouts** view (seeded: Asha PAID and Bala APPROVED for 2026-04-01..2026-06-30). **Accrue period** → in "Accrue a period" From `2025-05-01` To `2025-05-31` → **Accrue**. On Bala's new DRAFT row click **Approve**, then **Pay** ("Pay Bala (WHOLE01 Sales)": Paid on today, **Paid from** a cash or bank account, **Record payment**). **Cancel** Asha's draft. Then **Accrue period** for May 2025 again. | Toast "2 payout(s) accrued as drafts." -- Asha 574.19, Bala 27.06. Approve toast "Bala (WHOLE01 Sales) — approved. The cost and the debt are on the ledger."; Pay toast "... — paid." Cancel toast "... — cancelled. The period is free to accrue again." Finance → Journal Entries shows two references for Bala's payout, `COMM-202505-<id>` (approval: Dr Commission Expense / Cr Commission Payable) and `COMM-202505-<id>-PAY` (Dr Commission Payable / Cr the account paid from) -- select one → **View**. A `-REV` entry appears only when an **approved** payout is cancelled; cancelling Asha's draft posts nothing. *(May 2025 is free to accrue: its two earlier accruals are CANCELLED, and a cancelled payout holds no claim.)* Pay on a DRAFT is not offered; **(HTTP)** paying it answers 422 "Only an approved payout can be paid...". Accruing May 2025 again is refused: "A commission payout already covers part of that period for this salesman (2025-05-01 to 2025-05-31)." |
| 10.15 | Sign out; sign in as `whole01.sales1@agency.local` (Asha, SALES_EXECUTIVE) and expand sidebar **Sales**. Sign back in as the administrator afterwards. | **Commission is not listed at all**, nor Targets, Price Lists or Promotions -- a SALES_EXECUTIVE holds none of their view codes. **(HTTP)** with that token, `POST /api/v1/commission/payouts/{id}/approve` and `/pay` answer **403**, and so does `GET /api/v1/commission/payouts` (driven 2026-09-13). Whoever states a debt must not move the cash. |

## 11. Territory, routes and beats

All as `whole01.admin`. Geography, Route Types, Beat Plans, Call Lists, Coverage and Route Builder are children of the sidebar entry called just **Sales** (under Masters, above Quotations). Seed: `WHOLE01-RGN` Chennai Region → `WHOLE01-T-N` North Zone and `WHOLE01-T-S` South Zone → routes, as the store holds them on 2026-09-13: `WHOLE01-R-N1` North Sales Beat (weekly, Mon/Wed/Fri, **Asha**, round: Revise Check 2 then Classic Departmental Stores), `WHOLE01-R-N2` North Collections (fortnightly, Tue/Thu, **Bala**, round: Vijaya Super Stores), `WHOLE01-R-S1` South Sales Beat (weekly, Tue/Thu, **Asha**, round: Anand Agencies). No beat plan has stops of its own, so a call list calls the route's round. Beat plans: one weekly plan per working day per route (`WHOLE01-BP-R1-MON`, `-R1-WED`, `-R1-FRI`, `-R2-TUE`, `-R2-THU`, `-R3-TUE`, `-R3-THU`), `WHOLE01-BP-COLL` fortnightly on Tuesdays from 2026-04-07, and `WHOLE01-BP-MTH` monthly on the 2nd Tuesday.

| # | Case | Expected |
| --- | --- | --- |
| 11.1 | Sales → **Geography**. Select any row: the right-hand **Territory tree** panel. **Expand all**. The panel is narrow, so click the icon beside its title (tooltip "Open the tree in a larger window", added 2026-09-13): the whole tree opens in a window, already expanded, with Expand all / Collapse all and each node's menu (Filter list, Quick create child). Try Collapse all / Expand all, then Close. | Chennai Region (Region) → North Zone and South Zone (Territory) → North Sales Beat and North Collections under North, South Sales Beat under South (Route); each node shows its code and full path. The grid's Hierarchy column carries the full path for every row. |
| 11.2 | Double-click `WHOLE01-R-N1` (North Sales Beat) → **Details** tab; then glance at **Customers** and **Salespeople**. | Section **Route**: Route type **Sales Route**, Visit frequency **Weekly**, Working days **Mon, Wed, Fri**, Runs from **Always**, Runs until **No end**. Counts above: 2 customers, both active, Salespeople 1. Customers tab: Revise Check 2, Classic Departmental Stores. Salespeople tab: Asha (WHOLE01 Sales). |
| 11.3 | Sales → **Call Lists**. It opens on today (Back to today greyed out). Use › (**Next day**) or the date button to land on a **Monday**, Salesperson **Everyone**; then **Back to today**. | The date button reads "Monday 2026-09-14" (the weekday was not shown until 2026-09-13). Status bar "1 of 9 plan(s) run on Monday 2026-09-14". On any day but today the badges read **Runs on Monday** / **Not on Monday** (they said "Runs today" whatever day was chosen until 2026-09-13). `WHOLE01-BP-R1-MON` is badged **Runs on Monday** and calls Revise Check 2 then Classic Departmental Stores (the route's round, in order). Every other plan is badged **Not on Monday** with its reason, e.g. `WHOLE01-BP-R1-FRI` "Runs on Fridays; this is a Monday." |
| 11.4 | With the date button pick **2027-01-12** (a second Tuesday that is also an even fortnight from 2026-04-07), then **2026-10-13**, then **2026-10-20**. | On 2027-01-12, "4 of 9 plan(s) run on Tuesday 2027-01-12": `WHOLE01-BP-R2-TUE` and the fortnightly `WHOLE01-BP-COLL` (both Vijaya), `WHOLE01-BP-R3-TUE` and the monthly `WHOLE01-BP-MTH` (both Anand) read **Runs on Tuesday**. On **2026-10-13** (a second Tuesday in the off fortnight) COLL reads **Not on Tuesday**, "Runs every other Tuesday counted from 2026-04-07; this is the week between."; on **2026-10-20** MTH reads "Runs on the second Tuesday of the month; this is the third." *(Both gave no reason at all until 2026-09-13.)* |
| 11.5 | Sales → **Route Builder**: **Route being built** `WHOLE01-R-N1`. The right shows the round (1. Revise Check 2, 2. Classic Departmental Stores). Tick **On no route yet**, **Find**, double-click `SN` on the left to add it (stop 3), drag it by its ≡ handle above the first stop, **Save round and order**. | Toast "3 outlet(s) on North Sales Beat, in order." Choose the route again: 1. SN, 2. Revise Check 2, 3. Classic Departmental Stores -- the stops moved without a collision. Afterwards ✕ **Remove from round** on SN and Save: "2 outlet(s) on North Sales Beat, in order." |
| 11.6 | Route Builder: choose `WHOLE01-R-N1`, let the round load on the right, change nothing, **Save round and order**. | Toast "2 outlet(s) on North Sales Beat, in order."; choosing the route again shows the same two stops in the same order. The status bar says "Saving replaces the whole round with the list on the right." -- which is why the screen clears the panel before reading and refuses to save a round it could not read ("This round could not be read, so it cannot be saved over."). |
| 11.7 | Sales Orders → **New Order** for `WHOLE01C02` (Anand, on South Sales Beat, covered by **Asha**): **Ships from** `WHL_DC`, **Salesman** `Bala`, one line `DETER1K` qty 1, **Create draft**. | Refused, in the editor's banner: "The selected salesperson is not assigned to this territory." -- nothing is saved (driven over HTTP 2026-09-13: no order created). Choosing Asha saves ("Order drafted..."); leaving Salesman blank saves and, reopened, the order's salesman is Asha, supplied by the customer's route. Cancel the saved drafts afterwards (Cancel works on this screen since 2026-09-13). |

## 12. Compliance

All as `whole01.admin` in WHOLE01. E-Invoice, GST Returns and TCS are children of the sidebar entry called just **Sales** (under Masters, above Quotations). Facts the rows rest on, re-derived from the running backend on the evening of 2026-09-13 (after the owner's sections 9-11): WHOLE01 holds **13** e-invoice registrations and 6 e-way bills, every one SANDBOX; customer `OB-REV2` (Revise Check 2) has **no GST number** and no PAN; `WHOLE01C01` Vijaya has a GSTIN and **no PAN** (so TCS at 1%), `WHOLE01C02` and `WHOLE01C03` have both; the firm's **TCS is switched on** by the seed (threshold 5,000, 0.1%), so the "disabled by default" the model would give a fresh firm is not what you will see; every accounting period is OPEN. Every screen reads once when opened: **Refresh** after acting elsewhere.

| # | Case | Expected |
| --- | --- | --- |
| 12.1 | Sales → **GST Returns**. The **From** and **To** boxes hold the current month and are chosen, not typed: click ‹ (**Previous month**) once to reach August 2026 (**From** `2026-08-01` **To** `2026-08-31`; the history bills on the 12th and 22nd of every month), or click either box for one calendar in which you tap the first day and then the last (**Use this period**). Each change reads the return again. **GSTR-1** segment selected. | Heading "Filing as <the firm's GSTIN>". Four tables: **B2B — registered buyers, invoice by invoice** (Invoice, Buyer GSTIN, Taxable, CGST, SGST, IGST), **B2CS — unregistered, summarised by place and rate** (Place, Rate, ...), **CDNR — credit notes to registered buyers**, **HSN summary**. No B2CS row has a blank Place. A fifth table, **Invoices without a place of supply — named here, not filed**, lists any invoice the return could not place rather than filing it blank; for August it reads "Nothing in this section." The status bar says "Derived from the documents on every read, never stored." August 2026 on the day: **B2B** one invoice, SI-2026-2027-000009 Vijaya Super Stores, taxable 3,887.08, CGST 349.84, SGST 349.84; **B2CS** one row, Place 29, 18%, taxable 2,164.50 (Revise Check 2's SI-2026-2027-000008); **CDNR** nothing; **HSN** 330510 Shampoo Bottle 180ml, 37 units, taxable 6,051.58. *(September carries the section 9 invoices, and the two credit notes appear under CDNR.)* |
| 12.2 | Sales Invoices → select **SI-2026-2027-000009** (Vijaya, August, paid and registered) → **Cancel**. Then select **SI-2026-2027-000008** (Revise Check 2, August, unpaid, not registered) → **Cancel**: refused too, by its seeded sales return. So Sales Returns → **SR-2026-2027-000002** (2026-08-19, against SI-...-000008) → **Cancel** (reason); then SI-...-000008 → **Cancel** again. Back on GST Returns → **Refresh**. | SI-...-000009 is **refused**, naming what rests on it: "SI-2026-2027-000009 cannot be cancelled while it has money applied from RC-2026-2027-000008; its registration with the tax authority. Reverse or cancel those first." *(Until 2026-09-13 nothing was checked: a paid or registered bill cancelled, leaving the receipt clearing a cancelled bill and the customer credited twice.)* SI-...-000008 is refused with "...while it has sales return SR-2026-2027-000002. Reverse or cancel those first."; once the return is cancelled (its stock, credit and journals undone) the invoice cancels. The B2CS row is gone and the HSN taxable falls to 3,887.08 -- the return is derived on every read, never stored. |
| 12.3 | Switch the segment to **GSTR-3B**, same month. | **3.1(a) — outward taxable supplies** with Taxable, IGST, CGST, SGST, Cess; **Credit notes already deducted above**; and a sentence about the inward side the system does not know. Add up GSTR-1's B2B, B2CS and CDNR taxable values by hand: they equal 3.1(a)'s Taxable -- 3,887.08 after 12.2's cancellation (6,051.58 before). The inward side reads "Not derived: the purchase side files this." *(Nothing on screen reconciles the two for you; 3B is aggregated from the documents, not parsed out of GSTR-1.)* |
| 12.4 | Sales → **E-Invoice**. | A banner: "References marked sandbox are a rehearsal: nothing was filed with the tax authority..." The grid has **Invoice**, **Customer**, **Reference**, **E-way bill** columns and an actions column; every Reference is an `SBX...` value, cut short in the cell -- hover it for the whole `SBX... (sandbox — nothing filed)`. 13 rows for WHOLE01; six have an E-way bill reference, seven show —. |
| 12.5 | **Register an invoice** → in the **Sales invoice** picker choose one of `OB-REV2`'s approved invoices (items read `SI-... — <customer> — <total>`; pick one ending in **Revise Check 2**, e.g. SI-2026-2027-000007. The customer was not shown until 2026-09-13) → **Register**. | Refused **locally**, in an error toast, with "This invoice cannot be registered yet: the customer has no GST number." No row is added, no portal code appears. *(If the picker offers no OB-REV2 invoice, approve one of its drafts on Sales Invoices first.)* |
| 12.6 | Select a registered row with an empty E-way bill cell -- e.g. **SI-2026-2027-000003**, Vijaya Super Stores -- and click **Raise bill** on the toolbar (the row's own **Raise e-way bill** button is in the last column, off the right edge on a laptop; scroll right to see it): **Distance (km)** 120, **Moving by** Road, **Vehicle number** `TN01AB1234`, **Raise**. Then, with the row still selected, **Cancel bill** on the toolbar (or the row's **Withdraw bill**), give a reason. | Toast "E-way bill raised."; the row's E-way bill cell fills with an `SBX...` reference (hover it for the whole). Leaving the vehicle blank on a road movement is refused before sending: "Goods moving by road need a vehicle number on the bill." Raising a bill against an **unregistered** invoice is not offered on screen; **(HTTP)** `POST /api/v1/einvoice/invoices/{id}/eway-bill` on one answers 422 "Register the invoice before raising its e-way bill...". Withdraw toast "E-way bill withdrawn." |
| 12.7 | Sales → **TCS**. | The banner reads "Collecting under section 206C(1H) • 5000.00 per buyer per year, then 0.100% (1.000% without a PAN)" and the register lists the receipts already charged (Receipt, Buyer, On, Received, Paid before, Chargeable, Rate, Collected, Status). The register holds 38 rows on the day, the newest being your section 9 receipts from Vijaya -- e.g. RC-2026-2027-000012: Received 341.61, Rate 1.000% (no PAN), Collected 3.42. **Settings** opens "Tax collected at source" with the switch **Collect under section 206C(1H)** on, **Preceding year turnover** 150,000,000, **Threshold per buyer, per financial year** 5,000, **Rate %** 0.1, **Rate % without a PAN** 1.0 -- close it without saving. *(A firm the seeder never touched starts switched off; every demo firm is on.)* |
| 12.8 | Finance → Receipts → **Record Receipt** for `WHOLE01C03` (Classic, has a PAN): **Amount** 6000, **Method** Bank, type 6000 into the **Apply** box of **SI-2024-2025-000012** (8,008.14 owed), **Record receipt**. Back on Sales → TCS → **Refresh**. | The dialog's TCS notice (under Against order) read "Tax collected at source: 6.00 on 6000.00 above the threshold, at 0.100%..." -- Classic had already paid 6,419.17 this financial year, past the 5,000 threshold, so all of it is chargeable. The register's top row: Received 6,000, Paid before 6,419.17, Chargeable 6,000, Rate 0.1%, Collected 6.00, COLLECTED. Finance → Journal Entries shows **two** entries: the receipt `RC-...` and a separate `TCS-RC-...`, whose **View** reads Dr 1100 Trade Receivables 6.00 / Cr 2500 TCS Payable 6.00. Customers → **Refresh** → C03: Outstanding fell by 5,994.00, the receipt less the TCS -- 17,901.78 → **11,907.78** in the owner's run on 2026-09-14. |

## 13. Finance, reports and platform

As `whole01.admin` unless a row says otherwise. Finance is a flat list of tabs; Reports has two tabs, **Operational Reports** (40 entries) and **Financial Reports** (16); accounting periods live under **Masters → Configuration → Financial Years**, not under Finance. Trial Balance, Profit & Loss and Balance Sheet each take an **Accounting period** dropdown: pick the **same** period on all three when comparing them. Facts the rows rest on, re-derived from the running backend on 2026-09-14 after sections 9-12: WHOLE01's financial year FY2026 runs April 2026 to March 2027 in twelve periods P01-P12, all OPEN; the chart holds `1000 Cash`, `1010 Bank` and `5000 Purchases` and no `9999`; cost centres `SALES`, `OPS` (and an inactive `CC14E90`) and profit centres `NORTH`, `SOUTH` are already seeded; every WHOLE01 role is a system role.

| # | Case | Expected |
| --- | --- | --- |
| 13.1 | Finance → **Chart of Accounts** → **New**: Account Group chip **EXP · Direct Expenses**, Code `9999`, Name `Manual test account`, Account Type EXPENSE, Save. Then select it → **Edit**. | The row appears (Code, Account, Type, Status). The group must share the account's type -- any other chip is refused with "A ledger account must share its group's account type." The toolbar offers no Delete. On Edit, Account Group, Account Type and Code are fixed (chips do not respond, the dropdown does not open) and only Name, Description, the two "Requires a …" boxes and **Active** change; deactivating is the Active switch. *(Until 2026-09-14 the chips read only CA, CL, EQ, EXP, REV, and on Edit the group and type looked changeable but were silently not saved -- #369, #370.)* |
| 13.2 | Finance → **Trial Balance**, Accounting period `September 2026`. | Columns Code, Account, Type, Opening, Debit, Credit, Closing, a **Total** row, and a chip reading **Balanced** -- 19 accounts, total debit and credit both **660,640.05** on the day. Every account carrying a balance as at the period is listed, not only ones posted in it. *(Until 2026-09-14 this read "Out of balance by 58,719.61": a posting dated into an earlier month -- a cancelled August bill, an old commission payout -- never moved later months' openings. The engine carries it forward now and migration `20260914_0136` re-chained the stored balances.)* |
| 13.3 | Finance → **Profit & Loss** and **Balance Sheet**, same period. | P&L: Income and Expenses sections with totals and a **Net profit or loss** row (This period, Year to date). Balance Sheet: Assets, Liabilities, Equity with **Retained earnings brought forward** and **Result for the year**, then **Liabilities and equity**, chip **Balanced**. They agree: Total assets = Liabilities and equity; the sheet's Result for the year = P&L's Year to date net; the trial balance's total debit = total credit. On the day: P&L net **-5,200.30** this period and **-4,219.73** year to date; Balance Sheet Total assets **496,470.07**, Retained earnings brought forward 42,223.92, Result for the year -4,219.73, Liabilities and equity **496,470.07**. |
| 13.4 | Finance → **Journal Entries**. Search a document of each kind by its number (e.g. `RC-2026-2027-000013`, `TCS-RC-2026-2027-000013`, `COMM-202505-471a0b0e-PAY`, `LOY-RED-SI-2026-2027-000004`, `CN-2026-2027-000003`, `SR-2026-2027-000005`, `SI-2026-2027-000013`, `DN-WHOLE01-BR_NORTH-2026-2027-000001`, `Stock adjustment`, `PR-2026-2027-000003`, `GRN-WHOLE01-BR_NORTH-2026-2027-000005`, `PI-2026-2027-000006`, `JV-CENTRES-1`) and open it with **View**. | The row's subtitle is the entry's **description**; the module is on the View dialog's first line, "POSTED · posted by <module> · <description>" (a hand-written entry has no "posted by"). | WHOLE01 holds 387 entries on the day from **twelve** posting modules -- delivery_note 62, loyalty 57, settlements 55, sales_invoice 54, tcs 42, goods_receipt 36, purchase_invoice 30, sales_return 26, credit_note 11, purchase_return 7, commission 5, inventory 1 -- and **one** written by hand (the seeded manual expense). WHOLE01 has no customer opening balance, so no `customers` entry; the newest rows are RC-2026-2027-000013 and TCS-RC-2026-2027-000013 from 12.8. *(There is no source-module filter; the search box matches reference or description -- BACKLOG §31.15.)* |
| 13.5 | Journal Entries → **New Entry**: Accounting period `June 2026`, Journal type and Voucher type any, Date `2026-06-15`, Reference `MT-CLOSE-1`, two lines (`5000 Purchases` debit 100, `1000 Cash` credit 100), **Save Draft**. Then Masters → Configuration → **Financial Years**, select the year, on **June 2026** click **Close** (toast "June 2026 is closed. Nothing further can be booked into it."). Back on Journal Entries select the draft → **Post**. Afterwards reopen the period (**Open**). | The post is refused: "Accounting period P03 is closed and cannot accept postings." (the code is the period's; June is P03 in an April year). After **Open**, Post succeeds with "Journal entry MT-CLOSE-1 posted." Trial Balance for **September 2026** still reads **Balanced**: the June entry is carried into every later month. *(No seeded period is closed, so the row closes one itself; the New Entry dialog offers only OPEN periods, which is why the draft is written first.)* |
| 13.6 | Reports → **Operational Reports** and **Financial Reports**: open every entry in both lists (56). | Each renders with `N row(s)` in the header; an empty one reads "Nothing to report / This firm has nothing matching it yet." rather than a blank grid. The two return reports are now **Purchase returns by product** and **Sales returns by product**, and the order-progress report is **Delivery progress by order** (it was "Part-dispatched notes" until 2026-09-14, though it lists every live order -- 65 -- with Completed, Partial or Pending). Exactly **six** are empty in WHOLE01 on the day: Dispatches not yet completed, Damaged on receipt, Rejected on receipt, Invoices not yet approved, Supplier invoices not yet approved, Overdue purchase invoices. The largest are Sales order register 72, Promotion claims 64, Delivery note register 62. |
| 13.7 | Type in any search box, move to another screen, press **Ctrl+K**, type `DETER`, **Search**; select the result → **Open Details** (or double-click it). | The dialog opens wherever keyboard focus is. One result, **Detergent Powder 1kg** (a product), with "1 result found." and no error. Open Details closes the search and lands on **Masters → Products** -- the list, not that product's record. *(Until 2026-09-14 Ctrl+K did nothing once focus had left the shell, and Open Details navigated behind a search dialog that stayed open -- #371, #372.)* **(HTTP)** `GET /api/v1/search?query=DETER` answers 200 (the parameter is `query`; `q` answers 422) -- the dialog would fall back to an inventory-only search if the route failed, so the API check is the one that proves there is no 503. |
| 13.8 | Settings → **Audit Logs** with WHOLE01 selected; type `finance.accounting_period.updated` in **Action** → **Search**. Then sign in as `master.ops` on **Platform** (no firm), open it again and run the same search. | With a firm: the caption "The trail for MarketBridge Wholesale Traders Private Limited. Platform administration and other firms keep their own, in their own stores." and that firm's rows; the search leaves the two rows from 13.5 (June closed and reopened). The only filters are the **Action** and **Entity type** text boxes, matched exactly -- `finance` alone finds nothing. On the platform the same search finds nothing, because finance events stay in the firm's trail. Without a firm, as a platform administrator: "The platform trail: users, roles and firm administration..." As a firm admin without a firm the trail is refused (403 over HTTP). |
| 13.9 | Administration → **Users**, then **Roles & Permissions** (both halves). Select a **system** role (subtitle "System role", e.g. `SALES_MANAGER`) and double-click it. Then **New**: Role code `manual-test-role`, Name `Manual test role`, Permissions tick `CUSTOMER_VIEW`, Save; select it → **Edit** → tick one more permission → Save. | All load; the Roles grid reads Code, Name, Assignments, Status. On the system role the toolbar's Edit is disabled and double-clicking opens the read-only view whose subtitle reads "SALES_MANAGER — Sales Manager · System role · System roles cannot be modified." *(Until 2026-09-15 the double-click opened with no reason given -- #375.)* `CUSTOMER_VIEW` is a chip under CUSTOMER in the **New** form's Permissions section, not something to search the Roles grid for (that finds the VIEWER role). The new role's subtitle reads "Custom role" and its second save keeps both permissions. *(WHOLE01 holds only the twelve system roles, so the custom one is made here; the code must be lowercase.)* |
| 13.9b | Look at the Administration sidebar | **One** entry, **Roles & Permissions**, where Roles and Permissions used to be two. Open it: the Roles grid with a Roles / Permissions strip above it. Switch to Permissions: the sidebar entry stays highlighted and the heading still reads Roles & Permissions. |
| 13.9c | Ctrl+K, type a permission code, open the result | Lands on the **Permissions** tab directly, not on Roles -- each half keeps its own address. Sign out and in: the last screen restores to the same half. |
| 13.9c2 | Sign in as `elec01.admin`, Inventory → **Batch & Serial** → **Serial Numbers** | Twenty serials, `MIX500-2026-0001` to `MIX500-2026-0020`, all AVAILABLE, warranty 2026-09-08 to 2027-09-08. Masters → Products → `MIX500` shows **Track serial** on. |
| 13.9c3 | As `medi01.admin`, Masters → Customers → toolbar **Settings**. Then Sales Orders → select **SO-2026-2027-000010** (CityMed Clinic, DRAFT, 4,353.53) → **Approve**. Then as `food01.admin`, Sales Invoices → the **Sales stages** icon; then Delivery Notes. | "Credit policy" reads **Warn, then block**, Warn at 80, Block at 100; **Cancel**. CityMed Clinic (`MEDI01C03`): credit limit 20,000, outstanding 19,821.33. Sales Orders holds **eight** CityMed drafts. Approve is refused: "CityMed Clinic would be at 120.9% of a 20000.00 credit limit. Collect payment or raise the limit before continuing." and the order stays DRAFT. FOOD01's Sales stages shows **Delivery note** switched off, and so the **Delivery Notes** screen is **not in FOOD01's sidebar** -- a stage the firm does not type is hidden. The notes exist: Reports → Operational → **Delivery note register** reads 49 row(s), one per invoice (Sales Invoices' **Total** card also 49), raised by the service. In WHOLE01, Delivery Notes' status bar reads **62 records** and pages past the first 20. *(Until 2026-09-15 Delivery Notes, Purchase Invoices and Purchase Returns counted only the page on screen, "20 records", with no second page -- #376.)* |
| 13.9d | Finance → **Cost Centres** → New, Code `MT-CC`, Name `Manual test centre`, Save; Finance → **Profit Centres** → New, Code `MT-PC`, Name `Manual test profit centre`, Save. Then New `SALES` on Cost Centres once more. | Both grids list the new row beside the seeded ones (`SALES`, `OPS`, inactive `CC14E90`; `NORTH`, `SOUTH`). The second `SALES` is refused: "A cost centre with this code already exists." Neither grid offers Delete: deactivate with the Active switch on Edit. *(Codes are capitals, digits, `_` and `-`.)* |
| 13.9e | Finance → Chart of Accounts → Edit `5000 Purchases` → tick **Requires a cost centre** → Save. Then Journal Entries → New Entry, choose 5000 on a line | A **Cost centre \*** dropdown appears on that line and on no other; choose `SALES` (seeded). Save with it: posted. **(HTTP)** the same entry without `cost_center_id` on that line: **422**, "Ledger account 5000 requires a cost centre." Untick the flag afterwards. |
| 13.10 | Provoke a desktop report: end **agency_desktop** in Task Manager, start it again and sign in (the queued report is sent then). As `master.ops` open Settings → **Diagnostics**, Source **Desktop**, **Search**; click the group on the left, then the first line under **Occurrences** on the right. Then Source **Server**, open any group's first occurrence. | Desktop: one group, **UnexpectedTermination**, with a count one higher than before the forced close (246× on 2026-09-14 before it); the right pane shows the occurrences / first seen / last seen / versions chips and "showing the newest 50"; the newest occurrence expands to Firm, User and "Leading up to it" breadcrumbs ("Previous session started at … ended without a clean exit. The application was terminated rather than closed.") -- no Request and no stack trace, which a forced close has neither of. Server: the occurrence shows **Request <request_id>** and the stack trace. *(There is no "Help → Report a problem" control; the desktop reports crashes automatically, queued on disk until it can sign in.)* |

---

# Part 3 — Cross-cutting

## 14. Concurrency and two machines

Run these with two clients pointed at one server (or two windows of one client; the second `Start-Process` launch is a second client). Sign both in as `whole01.admin`. An editor that saves from **inside** its dialog -- customer, sales order, sales invoice, product, price list, promotion, coupon, customer group, target, payout adjustment -- shows this sentence on a lost race and keeps the dialog open with the typing in it: `Somebody else saved this <thing> while you were editing it. Your changes are still here and have not been sent. Copy anything you need, then close and reopen to see theirs.` An editor that closes first and saves after -- branch, warehouse, quotation, batch, lot, serial number, beat plan, place, territory, tax component -- cannot keep the typing, so it says so in a red toast instead: `Somebody else saved this <thing> while you were editing it. Your changes were not saved. Open it again to see theirs and redo yours.` Until 2026-09-13 six of them (price list, promotion, customer group, sales invoice, target, packaging level) showed the server's generic "The request conflicts with existing data. Please retry." instead. Server-side facts: driven on 2026-09-13, a second approval of one order and a second accrual of one payout period were both refused rather than answered with a 500, and an unchanged save left the version where it was.

| # | Case | Expected |
| --- | --- | --- |
| 14.1 | On **A** and **B**: Masters → Customers → double-click `WHOLE01C03` (Classic Departmental Stores, phone +919999900001 on 2026-09-14). On A change the phone, **Save**. On B change the phone to something else, **Save**. | A saves ("Customer updated."). B is refused **inside the editor** with the sentence above naming `customer`, the dialog stays open, B's typed phone is still in the box. Cancel B; reopen: A's phone is there. |
| 14.2 | The same on a **sales order** (Sales Orders → `SO-2026-2027-000012`, Anand Agencies, DRAFT → **Edit**, change **Remarks** on both), a **product** (Masters → Products → `TOOTH150`, edit the Description) and a **price list** (Sales → Price Lists, double-click `STANDING`, change the **Name** -- the dialog has no Description). | B refused each time with the sentence naming `sales order`, `product`, `price list`; typing kept, dialog open. |
| 14.3 | On A alone: double-click `WHOLE01C03`, change nothing, **Save**. Then double-click again, **Save** again. **(HTTP)** `GET /api/v1/customers/{id}` twice around it and compare the `ETag`. | Accepted both times. The `ETag` (and `version` in the body) is **the same before and after** -- an unchanged save must not move the version, so a client re-sending the same `If-Match` is still accepted. |
| 14.4 | On A and B: Sales Orders, select `SO-2026-2027-000019` (Anand Agencies, DRAFT, 1,079.42 -- one of the two drafts in WHOLE01 on 2026-09-14) in both grids. **Approve** on A (there is no confirmation). Then **Approve** on B, whose grid still says DRAFT. | A: the grid reloads and the row reads APPROVED (there is no success toast on this page). B: a red toast, either "Only draft sales orders can be approved." (A finished first) or the conflict sentence (both in flight); never a silent no-op and never a 500. Refresh B: APPROVED once. |
| 14.5 | Both clients approve a document that would claim the **last** use of a coupon. | Covered by `test_the_refusal_is_for_the_race_two_orders_priced_before_either_approved` in `backend/tests/unit/test_promotions.py`: the loser is **refused by name**, not silently repriced. The promotion editor has no redemption limit field, so by hand use the coupon's: Sales → Promotions → **Coupons** → `WELCOME10` (offer WELCOME, 2.5% off every line, used 4 times on 2026-09-14) → Edit → **Total claims allowed** `5` → Save. Raise two DRAFT orders for `WHOLE01C01` with **Coupon** `WELCOME10`, one on each client, then approve both: the first approves, the second is refused "Coupon WELCOME10 has been used as often as it allows. Re-save the document to price it without." Clear **Total claims allowed** afterwards and cancel the leftover draft. |
| 14.6 | On A and B: Sales → Commission → **Payouts** → **Accrue period**, From `2025-06-01` To `2025-06-30` on both (no payout covers June 2025 on 2026-09-14; the existing ones are May 2025 and April-June 2026), **Accrue** on A then on B. | A: "2 payout(s) accrued as drafts." B: "A commission payout already covers part of that period for this salesman (2025-06-01 to 2025-06-30)." -- a 409 by name, never a 500. The database holds the rule (`UQ_commission_payouts_period_active`), the service supplies the sentence. **Cancel** A's two drafts afterwards (the row's Cancel action: "... cancelled. The period is free to accrue again."). |

## 15. Permissions

Sign in as `whole01.sales1@agency.local` (Asha, `SALES_EXECUTIVE`: `CUSTOMER_VIEW`, `TERRITORY_VIEW`, `SALES_VIEW` and the three `SALES_*_CREATE` codes -- nothing else). The point is that the **server** refuses, not merely that the button is hidden: every refusal below was driven over HTTP with this user's token on 2026-09-13 and answered `403`. To drive them yourself, sign in with `POST /api/v1/auth/login` (see the appendix) and send `X-Firm-ID: 30c66274-60e9-4789-97d9-138a7a1fdc61`.

| # | Case | Expected |
| --- | --- | --- |
| 15.1 | Look for **Administration** in the sidebar, and Numbering Series under it. | **Administration is not offered at all** -- none of its tabs' codes is Asha's. **(HTTP)** `PUT .../numbering-rules/{id}` → `403`. `GET /api/v1/document-framework/numbering-rules` answers **200**: any member of the firm may read how documents are numbered, and only `SETTINGS_UPDATE` may change it (re-driven 2026-09-14; this row used to claim 403 for the read). |
| 15.2 | Masters → Customers → **Settings** (the credit-policy button on the toolbar). | The dialog **opens read-only**: the fields show the firm's policy but are disabled, **Save** is greyed (only **Close** works) and a notice reads "Changing the policy needs the manage customer settings permission." Somebody the policy warns may read the rule behind the warning. **(HTTP)** `PUT /api/v1/customers/credit-settings` → `403`. |
| 15.3 | Expand **Sales** in the sidebar and look for **Commission**. | **Not in the sidebar** (`COMMISSION_VIEW` missing). Under Sales Asha sees only the territory screens (Geography, Call Lists, Beat Plans, Coverage and the rest, on `TERRITORY_VIEW`); Price Lists, Promotions, Targets, Proforma, E-Invoice and GST Returns are hidden too, each on its own view code -- that is expected, not a fault. **(HTTP)** `POST /api/v1/commission/payouts/{id}/approve` and `.../pay` (any seeded payout id from the admin's Payouts view) → `403`. |
| 15.4 | Look for **Credit Notes** under Sales. | **Not offered** (`CREDIT_NOTE_VIEW` missing). **(HTTP)** `POST /api/v1/credit-notes/{id}/approve` → `403`. Drafting is bookkeeping; approving reverses a declared tax. |
| 15.5 | Look for **TCS** under Sales. | **Not offered** (`TCS_VIEW` missing). **(HTTP)** `PUT /api/v1/tcs/settings` → `403`. |
| 15.6 **(HTTP)** | Call the six writes above with Asha's token: `PUT` numbering rule, `PUT` credit settings, payout `approve`, payout `pay`, credit note `approve`, `PUT` TCS settings. | `403` every time (re-driven 2026-09-14 and again during the owner's run on 2026-09-15; the two reads, numbering rules and credit settings, answer 200), body `{"success": false, "error": {"code": "authorization_denied", ...}}`. A hidden button is not a control. |

## 16. Who a user is — the four tiers

New on 2026-09-05 (#235–#237). There are four kinds of user and they are not
interchangeable:

| Tier | Who | Reaches |
| --- | --- | --- |
| 1 | Platform operator (`PLATFORM` scope) | Creates firms and their people, provisions storage, sets a firm up until it works. **Refused a firm's books.** |
| 2 | All-firms super user (`ALL_FIRMS` scope) | Everything, in every firm, without needing a membership. |
| 3 | Firm administrator (`FIRM_ADMIN`) | Everything inside their own firm, including its users and their access. |
| 4 | Firm staff | The modules their job needs. |

`platform-admin@agency.local`, `master.ops@agency.local` and
`superadmin@agency.local` are all **tier 2** — the migration left every existing
designation exactly as it was (re-read from `platform.platform_admins` on
2026-09-15: all three `ALL_FIRMS`). There is no seeded tier-1 account; 16.1 makes
one, because the tier cannot be tested without one.

Facts the rows rest on, re-derived on 2026-09-15: `superadmin` was seeded by
`generate_sample_data.py`, so its password is **`Password@123`**, not the demo
firms' `DemoAdmin@12345` — five wrong attempts lock it for 15 minutes ("This
account is locked after too many failed sign-in attempts…"). It is a
**member of all four demo firms** (ELEC01 primary, FOOD01, MEDI01, WHOLE01) and
holds **no roles** in any of them. There is no screen for a platform
administrator's scope, which is why 16.1 is SQL.

| # | Case | Expected |
| --- | --- | --- |
| 16.1 **(SQL)** | `UPDATE platform.platform_admins SET scope = 'PLATFORM' WHERE user_id = (SELECT id FROM platform.users WHERE email = 'superadmin@agency.local');` (or ask for it to be run), then sign in as `superadmin@agency.local` / `Password@123` | Necessary setup. Put it back to `ALL_FIRMS` when you are done (16.6), or that account loses every firm's books. *(If the account's password has been changed from My profile -- it was during the 2026-09-15 run -- use the new one; two wrong tries already count towards the five that lock it.)* |
| 16.2 | As that user, on **Platform** (where a platform administrator always lands): Dashboard, Administration → Users, Roles & Permissions, Firms, User Templates, User-Firm Assignments; Settings → Audit Logs, Diagnostics | All offered. Running the platform is their job. |
| 16.3 | As that user: Sales, Purchases, Finance, Inventory in the sidebar; then open the firm switcher and switch into **WHOLE01** | **Not offered** on Platform. Their token carries **33** permission codes -- firm, user, role, permission, platform and system administration, none operational. The switcher still lists the **four firms they are a member of** (a `PLATFORM` administrator is not widened to every firm, but memberships they genuinely hold still show); switching into WHOLE01 offers **no business modules**, because a designation is a ceiling, not a floor, and they hold no role there. |
| 16.4 **(HTTP)** | `GET /api/v1/customers` with their token and `X-Firm-ID` of WHOLE01 | `403` `authorization_denied`, "You do not have permission to perform this action." (driven during the 2026-09-15 run; Sales Orders and Journal Entries answer the same, Users, Firms, Roles and Audit Logs answer 200). Not by a rule of its own — they are simply not exempt from the membership check. |
| 16.5 | Sign in as `master.ops@agency.local` (tier 2); open the firm switcher; switch into **SNTEST01** (a firm it has no membership in), then **WHOLE01** → Masters → Customers | The switcher lists every firm (ELEC01, FOOD01, MEDI01, WHOLE01, SNTEST01). SNTEST01 opens with no message; WHOLE01 shows the full sidebar and its customers load. Every firm, no membership needed. *(Until 2026-09-15 switching into a firm without a membership failed with "Default firm must be an active firm membership for this user." -- remembering the last firm was checked against memberships only and the refusal cancelled the switch -- #385.)* |
| 16.6 | Put 16.1 back to `ALL_FIRMS` | Housekeeping. Do not skip it. |

## 17. User templates — hiring by naming the job

Eleven platform templates are seeded. A firm may add its own; it may not edit
the platform's. Sign in as `whole01.admin`.

Facts re-derived on 2026-09-15: the eleven are Accounts (`ACCOUNTANT`), Counter
Sales (`BILLING_EXECUTIVE`, `CASHIER`), Customer Support, Field Sales
(`SALES_EXECUTIVE`), Firm Administrator, Firm Manager, Purchase Manager,
Purchasing, Read Only (`VIEWER`), Sales Manager and Warehouse; no firm template
exists yet. Retiring a template is the grid's **Delete** (a soft delete; there
is no button called Retire). **Apply templates only to people you create in
17.4a/17.4b** -- applying one to Asha or Bala would change the access sections
15 and 18 rely on.

| # | Case | Expected |
| --- | --- | --- |
| 17.1 | Administration → User Templates | 11 rows. Each names its roles — Counter Sales shows `BILLING_EXECUTIVE, CASHIER`. Origin reads **Platform**. |
| 17.2 | Select a platform template → **Edit** / **Delete** on the toolbar | Both disabled. It is offered to every firm, so no one firm may change it. Its dialog subtitle reads "… · Provided by the platform". |
| 17.3 | New → **Template code** `night-counter`, **Job name** `Night Counter`, **Roles** chips `CASHIER` and `BILLING_EXECUTIVE`, **Offered** on → Save | Created. Origin reads **This firm**; the dialog subtitle reads "… · This firm's own". |
| 17.4 | Edit it, change only the **name**, save | The roles are unchanged. An edit that says nothing about the bundle must not empty it. |
| 17.4a | Administration → Users → **New**, fill in the details, set **Job template** to Counter Sales, save | The user is created **and** holds `CASHIER` and `BILLING_EXECUTIVE`. One step, no second visit to the grid. |
| 17.4b | New again, leave **Job template** blank and pick two roles by hand | Those two roles, as before. The template field is optional. |
| 17.4c | New again: pick **ACCOUNTANT** under Roles in this firm first, then choose the **read-only · Read Only** job; then clear the job again | The job wins. The helper text under **Roles in this firm** (small grey text beneath the label) ends "Ignored when a job template is named above." Choosing the job **clears** ACCOUNTANT and **locks** the Roles chips; clearing the job unlocks them, empty. Saved with the job, the user holds only `VIEWER`. *(Until 2026-09-15 chip fields drew no helper text at all, and the Roles chips stayed clickable and kept their picks beside a chosen job -- #387, #388, #389.)* |
| 17.4d | Edit an existing user | **No** Job template field — it is create-only. Use Apply job template on the grid instead. |
| 17.5 | Administration → Users → select the user made in **17.4b** → **Apply job template** | Dialog "Apply a job template": "Whatever Manual Hire holds now is replaced by the job's roles. You can edit them afterwards like any other user.", a **Search jobs** box (name, code, description or role -- `inventory` leaves only Warehouse; a filter that hides the chosen job clears the choice), and one line per active job with its roles beneath. Apply is disabled until a job is chosen. *(The search was added at the owner's request on 2026-09-15 -- #390.)* |
| 17.6 | Choose Counter Sales → Apply | Their roles become exactly `BILLING_EXECUTIVE` and `CASHIER`. |
| 17.6a | As `master.ops`, give **Manual Hire** two global roles (Edit → **Roles in every firm** → `VIEWER`, `CUSTOMER_SUPPORT` → Save & Close) and, under **Roles by firm** (toolbar), two WHOLE01 roles (`ACCOUNTANT`, `INVENTORY_MANAGER` → that section's Save). *Both saves must land -- in the 2026-09-15 run the Roles by firm save was skipped and nothing said so; check each one before moving on.* Then as `whole01.admin`, Apply job template → Counter Sales | The WHOLE01 tier becomes exactly `BILLING_EXECUTIVE` and `CASHIER`; the two **global** roles are still there. Open the user as `master.ops`: Roles in every firm unchanged, Roles in specific firms shows the two from the template. A template overwrites the tier its caller writes and never touches the other. |
| 17.6b | Same starting point, but apply a template as `master.ops` from the grid -- choose **Warehouse** (`INVENTORY_MANAGER`) so the change is visible | The reverse: the **global** tier becomes the template's two roles, and the two WHOLE01 roles under Roles by firm are untouched. Four roles, a different four. The desktop never names a firm on this call for a platform administrator. |
| 17.7 | As `whole01.admin`, edit Manual Hire's **Roles in this firm** by hand (remove CASHIER, add VIEWER) → Save & Close → reopen | Works normally: BILLING_EXECUTIVE and VIEWER. **Also applies here** (read-only, lower in the Security section) shows the global tier -- `INVENTORY_MANAGER` after 17.6b. A template is where you start, not where you stay — nothing on the user records which template they came from. |
| 17.8 | User Templates → select `night-counter` → **Delete** (confirm), then re-open the user from 17.6 | The row leaves the grid; the user is untouched (same roles in both tiers) and `night-counter` is no longer offered as a Job template on New. Retiring is a decision about future hires. |
| 17.9 | Sign in as `whole01.sales1` → look for Administration | **Administration is not offered at all** (as in 15.1), so no User Templates either -- it needs `ROLE_VIEW`. |
| 17.10 **(HTTP)** | `POST /api/v1/user-templates` with `role_ids` naming the `PLATFORM_ADMIN` role, using `whole01.admin`'s token | `422` `business_rule_violation`, "A template cannot bundle platform or cross-firm roles." (re-driven twice on 2026-09-15, the second during the owner's run; nothing was created). That role carries every permission code. |
| 17.11 | Administration → Roles & Permissions → **Roles** as `whole01.admin` | Lists the twelve firm roles and this firm's own -- `manual-test-role` from 13.9, thirteen rows on 2026-09-15. **Not** `PLATFORM_ADMIN`, `SUPPORT_ADMIN` or `LICENSE_ADMIN`. This list was platform-admin-only until #237. |

---

## 18. Hiring like an existing person

The other half of section 17, and the more common one: an administrator
usually has a person in mind rather than a written-down job. Sign in as
`whole01.admin`.

Facts re-derived on 2026-09-15: clone **Asha** (`whole01.sales1`, role
`SALES_EXECUTIVE`, member of WHOLE01 only) -- cloning never changes the source.
The dialog checks only that the three boxes are filled and the email has an `@`;
the **server** applies the password policy: at least **12 characters** with an
upper-case letter, a lower-case letter, a digit and a symbol (`Welcome@12345`
passes). A weaker one is refused with "Password does not meet the configured
policy." and nothing is created.

| # | Case | Expected |
| --- | --- | --- |
| 18.1 | Administration → Users → select **Asha (WHOLE01 Sales)** → **Hire like this person** | Dialog "Hire like this person": "The new user gets the same roles and firms as Asha (WHOLE01 Sales), and none of their personal details, password or history. You can edit their roles afterwards like any other user." Boxes **Full name**, **Email**, **Initial password** ("They must change it when they first sign in."). |
| 18.2 | Press Create with the form empty | Refused under each box: "Give the new person a name.", "An email is required.", "An initial password is required." Nothing is created. |
| 18.3 | Type a name, an email with no `@`, a password → Create; then a proper email with the password `short` → Create | "That is not an email." under Email. With `short` the **server** refuses, and the refusal shows **on the dialog** in red -- "Password does not meet the configured policy." with its reasons ("must contain at least 12 characters", "must contain a symbol", …) -- while every box keeps what was typed. *(Until 2026-09-15 the dialog closed before creating, so a refusal arrived with the typing gone -- #392.)* |
| 18.4 | Full name `Clone Test`, Email `clone.test@agency.local`, Initial password `Welcome@12345` → Create. *(Optionally first try `short` as the password: refused by the server with the policy message.)* | Created: "Clone Test was created with the same access as Asha (WHOLE01 Sales), and must change their password on first sign-in." |
| 18.5 | Open the new user | Same roles as the source (`SALES_EXECUTIVE` in WHOLE01) and the same firm. **Blank** mobile, employee code, department, joining date; **Also applies here** reads None. |
| 18.6 | Sign out; sign in as `clone.test@agency.local` / `Welcome@12345` | A **Set a new password** screen opens instead of the application -- Current password, New password, Confirm new password, **Update password** -- and nothing else opens until it is done (e.g. `CloneTest@2026`). Afterwards the user works with Asha's access and no Administration. A password somebody else chose is not a password. |
| 18.7 | Add `CUSTOMER_SUPPORT` to Clone Test's Roles in this firm → Save & Close; then open Asha (close without saving) | Clone Test holds SALES_EXECUTIVE and CUSTOMER_SUPPORT; Asha still exactly SALES_EXECUTIVE. A clone is a starting point, not a link. |
| 18.8 | As `whole01.sales1`, look for the users grid | **Administration is not offered at all** (15.1), so there is no users grid and no **Hire like this person**. The action needs `ROLE_ASSIGN`, `ROLE_VIEW` and `USER_CREATE` — copying access is granting access. |

## 19. Setting a firm up from the platform side

Sign in as `superadmin@agency.local` (tier 2; its scope must be back at
`ALL_FIRMS` after section 16). **Its seeded password `Password@123` was changed
by the owner on 2026-09-15** — use the current one; guessing locks the account.
This is the flow a platform operator uses when a new firm is created.
Re-derived on 2026-09-15 and **run clean on 2026-09-15**: 19.1–19.5 all met the
expectations below unchanged.

**Where it lives.** User Templates is its own leaf in the Administration
sidebar (`user-templates`), not inside the Roles and Permissions group. It
carries `requiresFirm: false`, so it opens in Platform mode with no firm
selected — which is the point, since a platform operator has no own firm.

| # | Case | Expected |
| --- | --- | --- |
| 19.1 | Administration → User Templates → New | An **Offered to** picker appears in the General section -- one chip per firm reading `CODE · Name`, helper "Leave blank to offer this job to every firm." -- which a firm administrator does not see. It is create-only. |
| 19.2 | New: **Template code** `food-night`, **Job name** `Food Night`, **Offered to** the `FOOD01 · …` chip, then the **Roles** section → `CASHIER` → Save | Created. For the platform user Origin reads **One firm** (the grid does not name which); the dialog subtitle does, as "`food-night — Food Night` · Offered to one firm". Not **Every firm** (the `firm_id` never left the form) and not **This firm** (the wording #383 fixed) — either means 19.3 will fail too. |
| 19.3 | Sign in as `whole01.admin` and open User Templates | `food-night` from 19.2 is **not** listed (it would be, as **This firm**, had you chosen WHOLE01). Before this, a template written for one firm was offered to every firm. |
| 19.4 | As the platform user, New: `every-night`, `Every Night`, Roles `CASHIER`, **Offered to** left blank → Save | Offered to every firm — which is right for a job every firm has, and is why the field says so. Origin reads **Every firm**, and the platform user may still edit it. |
| 19.4a | Sign in as `whole01.admin` → User Templates → select `every-night` | Listed, Origin **Every firm**, subtitle "… · Offered to every firm". **Edit** and **Delete** are disabled. **(HTTP)** `PATCH /api/v1/user-templates/{id}` or `DELETE` with this token → `422`, "This template is offered to every firm, so only a platform administrator can change or retire it." *(Until 2026-09-15 it read "This firm" and any firm administrator could rename or retire it -- #383.)* Afterwards, as the platform user, **Delete** `food-night` and `every-night`. |
| 19.5 **(HTTP)** | As `whole01.admin`, `POST /api/v1/user-templates` with a non-empty `role_ids` and a `firm_id` that is not WHOLE01's | `422` `business_rule_violation`, "You can only act within your own firm." (re-driven 2026-09-15; nothing created — check the grid afterwards). Refused, not silently redirected. |

**Two things worth knowing before you drive 19.5**, both of which decide whether
the row is even runnable:

- **The `firm_id` does not have to be a real other firm.** `_target_firm`
  (`app/identity/services/identity_service.py`) refuses a firm caller naming
  *any* firm but their own, and for a firm caller it never looks the firm up —
  so `11111111-1111-1111-1111-111111111111` takes the same branch and gives the
  same message. That matters practically: `whole01.admin` **cannot discover
  ELEC01's id at all**, because `/api/v1/firms` is platform-only. A row that
  required a real one would strand whoever ran it.
- **`role_ids` must be non-empty and well-formed**, or the body is refused by
  validation before the service is reached and you are testing pydantic rather
  than the firm check. Its *contents* are never examined here: `_target_firm`
  runs first, ahead of `_assert_roles_are_assignable`, so any role id from your
  own firm does.

---

## 20. A firm administrator creating users

The button that was not there. `FIRM_ADMIN` holds `USER_CREATE`, `USER_UPDATE`,
`ROLE_ASSIGN` and `ROLE_VIEW` — everything running a firm's people needs — and
the New-user gate also demanded `FIRM_VIEW`, which is a platform code the role
can never be given. Sign in as `whole01.admin`.

Re-derived against the code on **2026-09-15**. Three rows had gone stale since
they were written on 09-05..09-09 and are corrected below; the changes are
called out where they are, so a reader who remembers the old wording can see
what moved rather than wondering whether they misread it.

| # | Case | Expected |
| --- | --- | --- |
| 20.1 | Administration → Users | **New** and **Edit** are offered. Before this they were not, for any firm administrator. **Edit is per row**, though: it is disabled for somebody who also works in another firm, and for a deleted row — see 20.1a. |
| 20.1a | Select a user who belongs to WHOLE01 **only** → **Edit**; then try it on a shared user (the one 20.6 makes) | The first opens. The second is **disabled**, and double-clicking the row or using the context menu says why rather than doing nothing: "… also works in another firm, so their profile is managed by a platform administrator. Use Roles by firm to set what they do in yours." A silent no-op reads as a broken screen; this is the rule speaking. *(Added 2026-09-15 — `canEdit`/`editRefusal` were never covered here, and 20.6 deliberately creates exactly the row that triggers them.)* |
| 20.2 | New → look at **Firms** before typing anything | **The firm you have open in the switcher is already ticked** — WHOLE01 for `whole01.admin`, who belongs to nothing else. The form used to open empty and then silently remove the membership the save had just created, leaving a user in no firm and invisible in the grid. *(Corrected 2026-09-15: the prefill is `api.activeFirmId`, the firm currently open, not "your own firm" — the two differ for anybody in more than one firm.)* |
| 20.2a | Fill in name, email, password → Save | Created and in WHOLE01, visible in the grid straight away. |
| 20.2b | New again, **clear** the Firms box, save | Created in **no** firm — allowed, and deliberate. They will not appear in the grid; find them with **Add existing user**. |
| 20.2c | As `superadmin`, open New | Firms is **empty**, not prefilled. A platform administrator has no own firm, and quietly using whichever one their switcher shows would be a surprise. |
| 20.3 | Open the form again and look at **Firms** | Lists the firms *you* belong to (`/api/v1/me/firms`). It read `/api/v1/firms`, which is platform-only, so it used to come back empty with a failed load. |
| 20.4 | Sign in as `superadmin@agency.local` and open the same form | **Firms** lists every firm (`/api/v1/firms`). Same field, different source — one line in `userDefinition` decides which. |
| 20.5 **(HTTP)** | As `whole01.admin`, `PUT /api/v1/users/{id}/firms` naming a firm you do not staff | `422`, "You can only assign firms you administer." Refused by name, not silently dropped. **You do not need ELEC01's id**: the reach check is a set difference and runs *before* the firm-exists check, so any UUID that is not WHOLE01's gives the same refusal — which matters, because `whole01.admin` cannot read `/api/v1/firms` to find a real one. *(Clarified 2026-09-15; the row named ELEC01 and was not runnable as written.)* |
| 20.6 **(HTTP)** | As `superadmin`, put a user in **both** WHOLE01 and ELEC01. Then as `whole01.admin`, save that user with WHOLE01 only. Re-read as `superadmin` | **Both** memberships survive. The endpoint replaces for a platform caller and merges for a scoped one — otherwise a firm administrator correcting their own firm would remove the person from every other firm on the platform. HTTP rather than the screen because the screen **refuses this on purpose** (20.1a): the merge is what protects the API from any other client, and the disabled button is a courtesy on top of it. |
| 20.7 | As `whole01.admin`, set a user's primary firm to something else | The primary does not move. It is one flag across every firm somebody belongs to, so a caller who can see only some of them must not set it. Exception, and it is deliberate: somebody with **no** primary at all gets one, so a new hire still lands somewhere when they sign in. |
| 20.8 | Follow `docs/USER_ADMINISTRATION_GUIDE.md` §3 end to end | Create a user, apply **Counter Sales** (`CASHIER` + `BILLING_EXECUTIVE`), sign in as them: Sales and Inventory offered, **Finance offered but holding only Receipts and Payments**, Administration not. *(Corrected 2026-09-15. This row said Finance was **not** offered, which stopped being true on 2026-09-06: Finance is gated on any of `ACCOUNT_VIEW`, `RECEIPT_VIEW`, `PAYMENT_VIEW` — before that a cashier holding exactly the right codes signed in to an empty sidebar. Chart of Accounts, Control Accounts and Journal Entries must **not** appear; if they do, the tabs lost their own codes and the module gate is doing the work alone, which is the wrong fix in the other direction.)* |

---

## 20a. Roles: global and firm-level

Two tiers. A **platform** administrator writes the global set on the user
form (**Roles in every firm**); either administrator writes one firm's set
under **Roles by firm** on the Users grid. They are additive, and a firm
administrator cannot remove a global grant.

The defect behind the screen: the single Roles box wrote through a path that
replaced every row regardless of firm, so a platform administrator pressing
Save without changing anything collapsed each firm's separate roles into one
global grant.

Use a user who belongs to **two** firms — create one and add both memberships
first.

*Re-derived 2026-09-15: every label and refusal below still matches the code
(`Roles in every firm` / `Roles in this firm`, `Also applies here`, `Roles in
specific firms`, "This person belongs to no firm you administer."). No changes.
Note the ordering trap — 20a.6b and 20a.8h both need a user who is in **your**
firm, and 20a.8j needs one in two, so make both before you start.*

| # | Case | Expect |
| --- | --- | --- |
| 20a.1 | As `master.ops`, Administration → Users → edit that user | The roles field is labelled **Roles in every firm**, and says it applies in every firm including ones added later. |
| 20a.2 | Set it to `VIEWER` and save | Saved as the global set. |
| 20a.3 | Select the row → **Roles by firm** | A section per firm the person belongs to — and **not** firms they do not belong to. `VIEWER` appears once at the top under **Applies in every firm**, greyed and unclickable. |
| 20a.4 | Give WHOLE01 `SALES_MANAGER`, press its **Save** | Saved for WHOLE01. Each firm has its own Save, enabled only once that firm changed. |
| 20a.5 | Give ELEC01 `CASHIER`, save | Saved for ELEC01. WHOLE01 still shows `SALES_MANAGER` — one Save affects one firm. |
| 20a.6 | Re-open the user form and press **Save** without changing anything | **Both firms keep their own roles.** This is the regression case: before the fix, WHOLE01 and ELEC01 both ended up holding every role, globally. |
| 20a.6b | Sign in as `whole01.admin` → Users → **edit** that person | Under Security, **Also applies here** shows the global roles as read-only text, or `None`. A firm administrator could not see them at all before: a global grant applies in their firm, so the form reported less than the person could do. |
| 20a.6c | As `master.ops`, edit the same person | **Also applies here** is absent — the Roles field above already *is* their global set. In its place, **Roles in specific firms** shows what each firm holds, read-only: `WHOLE01: SALES_MANAGER · ELEC01: CASHIER`, or `None`. Each caller sees the tier they cannot write. |
| 20a.6d | Give someone roles in one firm and none in another, then re-open | Only the firm holding roles is listed. A firm with none is left out rather than shown empty, so the line stays readable as firms are added. |
| 20a.7 | Sign in as `whole01.admin` → Users → that person → **Roles by firm** | One section, WHOLE01. `VIEWER` is shown greyed under **Applies in every firm** and cannot be cleared. |
| 20a.8 | Remove `SALES_MANAGER` in WHOLE01 and save | Removed in WHOLE01. `VIEWER` survives — a firm administrator may not undo a platform grant. |
| 20a.8b | As `master.ops`, Users → **New** | Under Security: **Job template**, **Roles in every firm**, and nothing that names a firm. **Apply roles to** is gone — the form writes the global tier only, and Roles by firm is the only place a firm-tier role is written. |
| 20a.8c | Create a user: two firms, a role | Granted globally. Check with **Roles by firm**: both firm sections are empty; the role sits under **Applies in every firm**. |
| 20a.8d | Give one firm a role from **Roles by firm**, then re-open the form and Save it unchanged | The firm keeps its role and the global set is unchanged — one writer per tier, so neither save can touch the other's rows. |
| 20a.8e | Create another naming a **job template** | The job's roles land globally, the same tier the Roles field would have written. |
| 20a.8f | As `master.ops` **with a firm selected**, edit a user | **One** roles field under Security, **Roles in every firm**, plus the read-only **Roles in specific firms** listing every firm the person holds roles in — the selected one included. No second column. The helper says a role in one firm only is set under Roles by firm. |
| 20a.8g | Add a role there and save, then check **Roles by firm** | It is under **Applies in every firm**; no firm section changed. The switcher has no say in where a role lands. |
| 20a.8h | Sign in as `whole01.admin` → Users → edit somebody in WHOLE01 | The roles field is labelled **Roles in this firm** and **Also applies here** shows the global grants read-only. Nothing names a firm. |
| 20a.8i | Press **Roles by firm** in the dialog footer (edit **or** view) | The per-firm editor opens without closing the form. Offered to anyone holding `ROLE_ASSIGN` and `ROLE_VIEW`. |
| 20a.8j | As `whole01.admin`, select a person who is in WHOLE01 **and** ELEC01 → **Roles by firm** | **One section, WHOLE01**, with chips that respond and a Save that lands. This was the broken case: the dialog read the platform-only firm list, answered 403, and showed a firm administrator an error and no firm at all. ELEC01 is not listed — its Save would be refused by name. |
| 20a.8k | As `whole01.admin`, open Roles by firm on somebody who is in ELEC01 only | "This person belongs to no firm you administer." — not "belongs to no firm yet", which would be false. |
| 20a.9 **(HTTP)** | As `whole01.admin`, `PUT /api/v1/users/{id}/firms/{ELEC01 id}/roles` | Refused: "You can only set roles in firms you administer." |
| 20a.9b **(HTTP)** | As `whole01.admin`, `GET /api/v1/users/{id}/firms/{ELEC01 id}/roles` | Refused the same way: "You can only read roles in firms you administer." The read used to answer for any firm. `.../firms/{WHOLE01 id}/roles` still answers 200. |
| 20a.10 **(HTTP)** | As `master.ops`, `PUT /api/v1/users/{id}/firms/{firm}/roles` for a firm the user is **not** a member of | Refused: "Add the user to this firm before giving them a role in it." A role there would sit in the table and stay out of the token. |

---

## 21. The five modules a firm administrator could not open

`_operational_permissions` is the list `FIRM_ADMIN` and `FIRM_MANAGER` are
built from, and five groups had never been added to it. Sign in as
`whole01.admin`. **If you were already signed in when this shipped, sign out
and back in** — a token carries the claims it was minted with.

*Verified against `system_seed.py` on 2026-09-15: `_operational_permissions`
now names all five groups, `loyalty` carries `LOYALTY_MANAGE_SETTINGS` and
`tcs` carries `TCS_MANAGE`, so 21.4 and 21.5 get their settings screens. 21.6
holds too — `whole01.sales1` is seeded with `SALES_EXECUTIVE` alone, which is
six read/create codes and none of the five groups. Only 21.7's location
changed.*

| # | Case | Expected |
| --- | --- | --- |
| 21.1 | Sales → Credit Notes | Offered, and opens. Draft, approve and the approve gate are all reachable. |
| 21.2 | Sales → Proforma | Offered, and opens. |
| 21.3 | Sales → E-Invoice | Offered, and opens. Check the mode badge reads SANDBOX. |
| 21.4 | Masters → Loyalty | Offered, and opens. Settings included — `LOYALTY_MANAGE_SETTINGS` is granted. |
| 21.5 | Sales → TCS | Offered, and opens, settings included. |
| 21.6 | As `whole01.sales1`, try all five | Still refused, all five. The grant widened one role, not everybody. |
| 21.7 | Administration → Firms | **Still not offered**, deliberately. Deciding which firms exist is not a firm's own business — `FIRM_VIEW` is a platform code no firm role may hold. *(Corrected 2026-09-15: the row said **Masters** → Firms. The tab moved to Administration when platform mode arrived — filed under Masters it was a firm's own master data, so the screen that **creates** a firm was reachable only from inside another firm and invisible to a platform administrator. Looking under Masters now finds nothing there for anybody, which passes this row for the wrong reason.)* |
| 21.8 **(HTTP)** | `GET /api/v1/credit-notes`, `/proforma-invoices`, `/einvoice/registrations`, `/loyalty/settings`, `/tcs/settings` with a `whole01.admin` token | `200` on all five. They answered `403` before. |

---

## 22. A cashier can see the till

`CASHIER` held exactly the right codes and was offered **no module at all** —
Receipts and Payments are Finance tabs, Finance was gated on `ACCOUNT_VIEW`,
and a tab naming no codes inherits its module's.

Make a cashier first: **Users → New**, set **Job template** to nothing and pick
the `CASHIER` role alone. (The seeded `counter-sales` template pairs it with
`BILLING_EXECUTIVE`, which hides the whole problem.)

| # | Case | Expected |
| --- | --- | --- |
| 22.1 | Sign in as that user | **Finance** is in the sidebar. Before this the sidebar was empty. |
| 22.2 | Open Finance | Exactly two tabs: **Receipts** and **Payments**. |
| 22.3 | Look for Chart of Accounts, **Control Accounts**, **Cost Centres**, **Profit Centres**, Journal Entries, Ledgers, Trial Balance, P&L, Balance Sheet, Refunds | **None of the ten.** Widening the module without gating its tabs would have handed a cashier the ledger — that would be the wrong fix twice over, so both halves are load-bearing. *(Three names added 2026-09-15: Control Accounts, Cost Centres and Profit Centres are all `ACCOUNT_VIEW` Finance tabs and were written after this row was.)* |
| 22.4 | Record a receipt | Works. `RECEIPT_CREATE`. |
| 22.5 | Sign in as `whole01.accounts` (or any `ACCOUNTANT`) → Finance | **All twelve** tabs, exactly as before. Nobody lost one — every code now on a tab is one that whoever held `ACCOUNT_VIEW` already had. *(Was "nine" — count them rather than trusting this: Chart of Accounts, Control Accounts, Cost Centres, Profit Centres, Journal Entries, Receipts, Payments, Refunds, Ledgers, Trial Balance, Profit & Loss, Balance Sheet. An `ACCOUNTANT` may hold fewer if they lack `JOURNAL_VIEW` or a report code, so what this row really asks is that nothing disappeared.)* |
| 22.6 | As `whole01.admin` → Finance | All twelve. |

---

## 23. The audit trail

Two things here, and the first is a regression that shipped on 2026-09-05 and
was found on 2026-09-06: moving the platform designation into its own claim
left two checks looking for it in the old place, so **no platform administrator
could read any audit trail at all**.

*Verified against the code on 2026-09-15, no changes. The Settings module takes
**any** of `SETTINGS_VIEW` / `AUDIT_LOG_VIEW` / `DIAGNOSTICS_VIEW`; Audit Logs
demands `AUDIT_LOG_VIEW` and carries `requiresFirm: false`, which is what makes
23.1 work with no firm selected; Diagnostics demands `DIAGNOSTICS_VIEW`, which
`FIRM_ADMIN` does not hold. `audit_scope` refuses the platform trail without
platform authority, as 23.6 expects. One thing the rows do not say: 23.4a–23.4c
are the **merge**, and the unit suite cannot see it — it builds one SQLite
schema holding every table, so both stores resolve to the same session there
and merging would double every row. If the merge is broken you will find it
here or in `tests/integration/`, nowhere else.*

| # | Case | Expected |
| --- | --- | --- |
| 23.1 | Sign in as `superadmin@agency.local`, no firm selected → Settings → Audit Logs | The **platform** trail: user, role and firm administration. Answered 403 between 2026-09-05 and 2026-09-06. |
| 23.2 | Same user, select WHOLE01 → Settings → Audit Logs | **That firm's** trail, not the platform's. Also 403 in that window. |
| 23.3 | As `whole01.admin` → Settings | The module opens with **Audit Logs** in it. It used to open empty — offered on `SETTINGS_VIEW`, with both tabs demanding codes the role did not hold. |
| 23.4 | Read it | WHOLE01's history and nothing else. |
| 23.4a | Promote somebody (Users → Apply job template), then re-open Settings → Audit Logs **as `whole01.admin`** | The promotion is listed, naming the template. It is written to the *platform* store — user administration is a platform path — and the firm's trail now merges the platform rows carrying this firm's id. |
| 23.4b | Check the order around it | Newest first across both stores, not the firm's rows followed by the platform's. |
| 23.4c | Filter by action `user_template.applied` | The filter reaches both stores. Filtering one and not the other would answer a half-truth. |
| 23.5 | Look for **Diagnostics** | **Not there.** `DIAGNOSTICS_VIEW` is deliberately withheld — error reports are telemetry for whoever maintains the product, not something a firm owns. |
| 23.6 **(HTTP)** | `GET /api/v1/audit-logs` with a `whole01.admin` token and **no** `X-Firm-ID` | `403`. Reading the platform trail needs platform authority. |
| 23.7 | As `whole01.sales1` → Settings | Not offered at all. |

---

## 24. Hiring somebody who already has an account

`list_users` is scoped to the caller's own members, so a firm administrator
could not find — or even learn the existence of — a person who already works
elsewhere. Sign in as `whole01.admin`.

*Verified against `lookup_users` on 2026-09-15, no changes: gated on
`USER_CREATE` rather than `USER_VIEW` (24.15), a firm caller must send three
characters and gets at most ten **whatever `page` says** (24.2, 24.20), a
platform caller may send nothing (24.17). The **User-Firm Assignments** tab
carries `requiresPlatformAdmin: true`, which is what 24.21 and 24.22 are
checking — a flag rather than a permission code, because a platform
administrator passes code checks by designation. The section deliberately
drives **one route answering two callers differently** — 24.2–24.16 are the firm caller's narrow
lookup (three characters, ten results, no paging, no firm ever named) and
24.17–24.20 the platform caller's directory (empty term lists everyone not in
the firm, ordinary paging). Two routes would have meant two implementations of
"not a platform administrator" and two response shapes for one dialog, so the
difference is the design rather than an inconsistency to report.*

| # | Case | Expected |
| --- | --- | --- |
| 24.1 | Administration → Users → **Add existing user** | A search box. It is offered with no row selected — the person is not in the grid, which is the point. |
| 24.2 | Type `el` | Nothing searched: "at least 3 characters". |
| 24.3 | Type `elec` | ELEC01's people, found by **email**. |
| 24.4 | Type `Electro` | The same person found by **name**. |
| 24.5 | Look at a result | Name, email, and nothing else. **No firm is named** — you must not learn which firms they work in. |
| 24.6 | Type part of one of your own people's names | Listed, marked **Already in this firm**, and Add is disabled. |
| 24.7 | Type something matching nobody | "They may not have an account yet — use New." |
| 24.8 | Pick an ELEC01 person, set job **Counter Sales**, Add | Added. They appear in WHOLE01's user list. |
| 24.9 | Open their row | **Edit is disabled**, and it says they also work in another firm and their profile is managed by a platform administrator. |
| 24.10 | Apply job template / set roles on them | Both work. Those are yours. |
| 24.11 **(HTTP)** | `GET /api/v1/users/{id}/firms` as `whole01.admin` | **Only WHOLE01.** It returned every membership until 2026-09-06. |
| 24.12 **(HTTP)** | Same as `superadmin` | Both firms — a platform caller still sees them all. |
| 24.13 **(SQL)** | Check their ELEC01 roles | Unchanged. Adding them to WHOLE01 touches nothing in ELEC01. |
| 24.14 | As `whole01.sales1`, look for Add existing user | Not offered. It needs `USER_CREATE`. |
| 24.15 **(HTTP)** | `GET /api/v1/users/lookup?q=elec` with a `whole01.sales1` token | `403`. `USER_VIEW` deliberately does not reach it. |
| 24.16 **(HTTP)** | `GET /api/v1/users/lookup?q=` as `whole01.admin` | `422`: "Type at least 3 characters". An empty term is the shortest of all, and a firm caller gets a lookup, not the directory. |
| 24.17 | Sign in as `master.ops`, select **WHOLE01**, Users → **Add existing user** | The dialog **opens already listing** everyone with an account who is not in WHOLE01, with no typing. The helper reads "Leave blank to list everyone not yet in this firm." WHOLE01's own people are **not** listed — they are in the grid beside the button — and neither is any platform administrator. |
| 24.18 | Type `e` | Filtered on one character; the three-character rule is a firm caller's. Clear the box and the full list returns. |
| 24.19 | Pick somebody, Add | Added to WHOLE01, and gone from the dialog's list next time it opens. |
| 24.20 **(HTTP)** | `GET /api/v1/users/lookup?q=&page=1&page_size=2` as `master.ops` with `X-Firm-ID: WHOLE01` | Two rows and a `pagination` block whose `total_records` is everybody not in WHOLE01. The route pages for a platform caller and caps at ten for a firm one, whatever `page` says. |
| 24.21 | As `whole01.admin`, open Administration | Users, Roles & Permissions, User Templates — and **no User-Firm Assignments**. That tab is a platform administrator's; Users → Edit → Firms and Add existing user are the firm administrator's ways to the same thing. |
| 24.22 | As `master.ops`, with or without a firm selected, open Administration | **User-Firm Assignments** is there, with the Firm filter. |

> **Tidy up:** 24.8 leaves a real ELEC01 person in WHOLE01. Remove the
> membership and the WHOLE01 roles afterwards, or reseed.

---

## 25. A firm's own roles and its own templates

The point of this one: **you are not limited to what the platform shipped.**
A role is a bundle of permissions, a template is a bundle of roles, and a firm
administrator may write both. Sign in as `whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 25.1 | Administration → Roles & Permissions → **Roles** | The **twelve** firm roles — `FIRM_ADMIN`, `FIRM_MANAGER`, `SALES_MANAGER`, `SALES_EXECUTIVE`, `PURCHASE_MANAGER`, `PURCHASE_EXECUTIVE`, `INVENTORY_MANAGER`, `ACCOUNTANT`, `BILLING_EXECUTIVE`, `CASHIER`, `CUSTOMER_SUPPORT`, `VIEWER`. **None of the four platform ones**: `PLATFORM_ADMIN`, `SUPPORT_ADMIN`, `LICENSE_ADMIN` and `SYSTEM_AUDITOR`. *(The fourth was missing from this row until 2026-09-15; 16 seeded roles, 12 of them a firm's.)* |
| 25.2 | New → code `night-desk`, name `Night Desk` → Save | Created, and it belongs to WHOLE01. |
| 25.3 | Open it → **Permissions** | **167 of the 189 codes** — 30 permission groups, 22 of them platform (`platform`, `firm`, `system_administration`, `high_risk`). Re-derived 2026-09-15; a count carries the date it was taken, so re-run it rather than trusting this one if it matters. Tick `SALES_VIEW`, `RECEIPT_CREATE`, `CUSTOMER_VIEW`. |
| 25.4 | Look for `FIRM_CREATE`, `PLATFORM_SETTINGS`, `VOID_INVOICE`, `AUDIT_LOG_VIEW` | **Not in the list at all.** `list_permissions` filters `PLATFORM_PERMISSION_CODES` out of a firm-scoped read, so the platform codes are not merely refused on assignment — they are never offered, and `set_role_permissions` refuses them again if one is named directly. |
| 25.4a | Now look at what **you** can do: Settings → Audit Logs, still as `whole01.admin` | It opens, on your own firm's trail. So you **hold** `AUDIT_LOG_VIEW` and cannot **grant** it — and that is not a contradiction. `PLATFORM_PERMISSION_CODES` answers "what may a firm administrator not *grant*", which is a different question from what they may hold; `AUDIT_LOG_VIEW` sits in the `system_administration` group and was granted to `FIRM_ADMIN` directly on 2026-09-06, beside `SETTINGS_VIEW` and `SETTINGS_UPDATE`, which had always been there for the same reason. *(Added 2026-09-15. Worth doing once: confusing the two sets is how a permission's reach gets misjudged, and this is the clearest place in the plan to see the difference.)* |
| 25.5 | New role with code `platform_admin` | Refused — the designation and the twelve seeded codes are reserved, case-insensitively. |
| 25.6 | User Templates → New → name it, pick **Night Desk** as its role | Created, Origin **This firm**. A template may bundle any role you may assign. |
| 25.7 | Users → New → set **Job template** to it → Save | The new user holds `night-desk` and nothing else. |
| 25.8 | Sign in as that user | They can do exactly what you ticked in 25.3, and nothing more. |
| 25.9 | Edit the role, remove `RECEIPT_CREATE`, and have them sign out and in | Gone for them too. A role is not versioned — editing it changes everybody holding it. |
| 25.10 | Delete `night-desk` while somebody holds it | **It is deleted.** No refusal, no warning. |
| 25.10a | Have that person sign in again | They no longer have the role's permissions, and nothing on screen says why. Know who is on a role before deleting it. |

> **Tidy up:** 25.2–25.7 leave a role, a template and a user in WHOLE01.
> Remove them or reseed.

---

---

# Part 4 — Known gaps

Do **not** raise these as defects. They are deliberate, and each is recorded in
`docs/MODULE_STATUS.md` with what is blocking it.

**Five entries came off this table on 2026-09-15**, and it is worth knowing why
before you read the rest of it. They all said "built, but nothing exercises it",
which was true when written and stopped being true on 2026-09-08 when the demo
seeder was extended to reach exactly those five paths. A stale row here is worse
than a stale row anywhere else in this plan: this table tells you **not to
raise** what it lists, so each of those five was quietly excluded from testing
for a week after it became testable. They are now in the table below the gaps,
with the firm that carries each.

| Area | State |
| --- | --- |
| Emailing a document | Not built. The PDF exists; there is no SMTP client or mail configuration. Deferred by the owner. |
| Licensing | Not built. A permission and a role exist and are unused. Deferred by the owner. |
| `lots` | The one table still holding no live row in any store. |
| `IMEI`, `PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`, `SERVICE_CONTRACTS`, `PROJECT_MANAGEMENT` | Declared as roadmap features and refused if switched on. Six, not seven: `COMMISSION` came off on 2026-09-03, because `app/commission` shipped on 08-23 and the flag outlived the fact — an administrator was being refused a feature the platform had. |

### No longer gaps — these are testable, and on which firm

Each is one deliberate choice on one demo firm, so the ordinary case sits beside
the exceptional one. **Do** raise a defect against any of these.

| Area | Where it lives now |
| --- | --- |
| Serial numbers | **ELEC01**'s mixer grinder has `track_serial` set, with up to twenty serials carrying warranty dates. Tracking only — receipts and issues do not demand the numbers, so the trading history is unaffected. Needed `SERIAL_NUMBER` and `WARRANTY` on the ELECTRONICS profile, which the feature seed backfills. |
| Packaging levels | Each firm's **first product** carries a `Case` level with a barcode. |
| Cost and profit centres | **Two of each per firm**, plus one posted manual journal naming them. Manual deliberately: the automatic postings name no centre, so a seeded account that required one would refuse them. |
| Shortened sales chains | **FOOD01** has `delivery_note_stage` off, so every one of its invoices is billed off the order and `SalesChainService` dispatches the goods — the one path that moves stock from an invoice. Note the consequence, which is an open product question rather than a defect: FOOD01's Delivery Notes screen is hidden when the stage is off, so its service-raised notes can only be read through the Delivery note register report. |
| Credit **blocking** | **MEDI01** is in `BLOCK` mode (warn 80, block 100) and CityMed Clinic sits on a 20,000 limit the history crosses, so refused approvals appear in the seeder's notes and the refused orders stay unapproved on the grid. The other three firms are in `WARN`, so both paths are seeded. |

---

## 26. Platform mode, and the switcher that was empty

Sign in as **`platform-admin@agency.local`**. This account is `ALL_FIRMS` and
holds **no** firm memberships, which is what made the defect visible: its token
carries all 189 permission codes, so the sidebar offered Sales, Purchases and
Inventory, while `/me/firms` answered an empty list so no firm could be
selected and every one of those screens refused its first request.

*Re-derived 2026-09-15, no changes. Two practical notes. `platform-admin`'s
password is `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` from `config/.env` **only until
somebody signs in and changes it** — on this database that has happened, so use
`master.ops` if it will not let you in; both are `ALL_FIRMS` and nothing in the
cases changes. And 26.9 covers the contrast that matters: `superadmin` is also
`ALL_FIRMS` but a member of all four firms, and still starts on Platform —
membership is not what decides the landing.*

| # | Step | Expect |
| --- | --- | --- |
| 26.1 | Sign in | The header firm control reads **Platform**, and so does the status bar. |
| 26.2 | Look at the sidebar | Dashboard, Administration, Settings (and Licensing if seeded). **No** Sales, Purchases, Inventory, Masters, Finance or Reports. |
| 26.3 | Open Administration | **Firms**, Users, Roles & Permissions, User Templates, User-Firm Assignments. **No** Tax, UOM, Business Profiles or Numbering Series — those live in a firm's own store. |
| 26.4 | Open the firm control | A **Platform** entry at the top with a tick beside it, then all four firms — even though this account is a member of none. |
| 26.5 | Pick `WHOLE01` | Notification names the firm; the sidebar grows Sales, Purchases, Inventory, Masters, Finance, Reports; Administration gains its configuration tabs. |
| 26.6 | Open Sales → Sales Orders | Real rows. Before this change the module was offered and this screen failed. |
| 26.7 | Open the firm control and pick **Platform** | "Working on the platform. No firm is selected." The firm-owned modules go away again. |
| 26.8 | Sign out and back in | Lands on **Platform**, not on `WHOLE01`. Deliberate: a reach over every firm's books must not restore itself silently. |
| 26.9 | Sign in as `superadmin@agency.local` | Also `ALL_FIRMS`, but a member of all four. Still starts on **Platform**; the switcher looks the same as before. |
| 26.10 | Sign in as `whole01.admin@agency.local` | **No** Platform entry anywhere, one firm, lands in it as always. Nothing about a firm user's experience changed. |

## 26a. The user menu: who you are, and where you start

`GET /api/v1/me` names the signed-in person; `PUT /api/v1/me/primary-firm` is
theirs to call. Use a user who belongs to **two** firms.

*Verified against the code on 2026-09-15, no changes. All three routes exist
(`/me`, `/me/firms`, `/me/primary-firm`) and are gated on being signed in and
nothing else, which is what 26a.10 checks — `whole01.sales1` holds
`SALES_EXECUTIVE`, six codes, none of them `USER_VIEW`, so it is the right
account for 26a.8 and 26a.10.*

| # | Step | Expect |
| --- | --- | --- |
| 26a.1 | Sign in, open the account menu (top right) | The first row is your **full name** with your **email** under it -- not the address you typed, and not the word "User". The status bar shows the same name. |
| 26a.2 | Close the app with "remember me" on, relaunch | Still your name. This used to read "User", because a restored session never passes through the login form. |
| 26a.3 | Account menu → **Primary firm** | A dialog listing your firms with the current primary selected and **Save** dead. Choose the other, Save. A notice says which firm you will start in next time. Nothing on screen switched. |
| 26a.4 | Open the firm switcher | The primary is labelled `primary` beside its code. |
| 26a.5 | Switch to the non-primary firm, work there, sign out, sign in | You land in the **primary** firm, not the one you were last in. Switching is for the session; the primary is for next time. Until 2026-09-08 it was the reverse, so the flag meant nothing to anybody who ever switched. |
| 26a.6 | As a user with **one** firm, open the account menu | No **Primary firm** entry -- there is nothing to choose. Same for a platform administrator, who always starts on Platform. |
| 26a.7 **(HTTP)** | `PUT /api/v1/me/primary-firm` with a firm you do not belong to | Refused: "You can only make a firm you belong to your primary firm." |
| 26a.8 | Account menu → **My profile**, as `whole01.sales1` (no `USER_VIEW`) | Opens. Name and email at the top; Work, Contact, Firms, Access and Sign-in sections; unset fields read **Not set**; roles grouped as **In every firm** and **In WHOLE01**; the primary firm marked **Primary**. No boxes to type in, and a line saying these are the administrator's to change. |
| 26a.9 | Same as `master.ops` | A **Platform administrator** chip under the name. |
| 26a.10 **(HTTP)** | `GET /api/v1/me` as `whole01.sales1` | 200 with `profile` and `roles`, on a token that cannot call `GET /users/{id}`. |
| 26a.11 | My profile → **Change password**: a new password of 8 characters, then one with no symbol | Refused beside the box with the rule named; nothing sent. |
| 26a.12 | Same, wrong current password, otherwise valid | The server's refusal shown in the dialog; it stays open for another try. |
| 26a.13 | Same, correct current password, `Str0ng-Passw0rd!` twice | Both dialogs close, you land on the login screen with "Password changed. Sign in with your new password." Any other window you were signed in on is signed out on its next request. Sign in with the new password; set it back afterwards. |

**(HTTP)** `GET /api/v1/me/firms` as `platform-admin` returns four firms, each
with `is_primary: false` — no membership row, so nobody's primary. The same
call as `whole01.admin` still returns one.

## 27. Creating a firm and setting it up

**Sign in as `master.ops@agency.local`.** Not `platform-admin@agency.local`,
which this section used to name: that account is created at startup from
`AGENCY_BOOTSTRAP_ADMIN_PASSWORD` and its password is changed on first use, so
on a database anybody has signed into it no longer takes the value in
`config/.env`. Both hold the same designation and `ALL_FIRMS` scope, so nothing
about the cases changes -- only which account can reach them. On a *fresh*
database the bootstrap account is the only one that exists, and `master.ops`
comes from the demo seeder.

Only a platform administrator can do any of 27.1--27.20. `require_platform_admin()`
guards every `/api/v1/firms` route and never reads a permission, so `FIRM_CREATE`
gates the desktop's **New** button and nothing else.

*Verified against the code on 2026-09-15: every route this section drives is
there — `POST /{firm_id}/provision`, `GET /{firm_id}/readiness`, `POST
/{firm_id}/open-books`, `POST /{firm_id}/apply-tax-template`, `POST
/{firm_id}/create-default-branch`, and `GET`/`PUT /finance/control-accounts`.
**One row was wrong and is corrected: 27.23j** — see it for why. One thing
before you start:
**`SNTEST02` may already exist** from an earlier run of this section, in which
case 27.4 answers 409 rather than saving and every row after it is testing the
wrong firm. Check Administration → Firms first and use a fresh code
(`SNTEST03`, and so on) if it is taken — the code is unique among live firms,
so even a soft-deleted one releases it but a live one does not.*

### 27a. Creating the record

| # | Case | Expect |
| --- | --- | --- |
| 27.1 | Administration → **Firms**, on **Platform** | The list of all firms. This is the one Administration tab that needs no firm selected. |
| 27.2 | Masters → look for Firms | Not there. It moved on 2026-09-06; a firm's own master data needs a firm, so creating a firm was reachable only from inside another one. |
| 27.3 | **New** → save with only a name | Refused. `name`, `code`, `country` (2 letters), `currency_code` (3 letters) and `financial_year_start` are the five required fields; everything else is optional. |
| 27.4 | Enter code `sntest02` in lower case | Stored as `SNTEST02`. Code, country and currency are upper-cased on the way in. |
| 27.5 **(HTTP)** | `POST /api/v1/firms` with code `WHOLE01` | **409**, "Firm code, GST number, or PAN number already exists." The three are unique among *live* firms only, so a soft-deleted firm releases its code. |
| 27.6 **(HTTP)** | Same with code `BAD CODE` | **422**. The pattern is `^[A-Z0-9_-]+$` -- no spaces, no dots. |
| 27.7 **(HTTP)** | Same with `country: "IND"` | **422**. Two letters, ISO-style. |
| 27.8 | Create with deployment mode `SHARED` | Saves. The follow-up message names the next step. |
| 27.9 **(HTTP)** | Create with mode `DATABASE` and `connection_profile: "NOPE"` | **422**, "Connection profile 'NOPE' is not configured. Configured profiles: REMOTE_A." Refused at creation rather than at first use -- otherwise the firm provisions nothing and fails far from the request that caused it. |

### 27b. What creation does and does not do

| # | Case | Expect |
| --- | --- | --- |
| 27.10 | Select the new `SHARED` row | **Open this firm** enabled -- a shared firm is ready at once. **Provision storage** hidden; there is nothing to provision. |
| 27.11 | Create a second firm with mode `SCHEMA` | **Open this firm** **disabled** -- its schema has no tables, so switching in would answer errors on every screen. **Provision storage** enabled. |
| 27.12 | Press **Provision storage**, refresh, select it again | **Open this firm** now enabled. The response carries `provisioned_at`. |
| 27.13 | Press **Provision storage** again | Succeeds, reporting it was already provisioned. Every step is create-if-missing, so this is also the repair action after a target server was unreachable. |
| 27.14 **(HTTP)** | `PUT /api/v1/firms/{id}` changing `deployment_mode` | **422**, "Firm storage routing cannot be changed after creation (currently SCHEMA/…). Migrate the firm's data first." Nothing moves a firm's rows between stores, so the routing is fixed at creation. Verified 2026-09-06. |

### 27c. Reaching the new firm

| # | Case | Expect |
| --- | --- | --- |
| 27.15 | Press **Open this firm** | "Working in …". The header shows it and the sidebar grows the whole application. |
| 27.16 | Open the firm switcher | The new firm is listed. **This is the half that was broken**: the switcher is read once at sign-in, so without the refresh a firm created minutes earlier was not in it and `switchFirm` refused it as "not assigned to this user". |
| 27.17 | Go back to **Platform** and look at Administration | There is **no Configuration heading**. Every one of its eighteen descendants lives in a firm's store, so with no firm it had nothing under it -- and until 2026-09-06 it was offered anyway and opened nothing. |

### 27d. Setting the business profile

**Not** *Masters → Firm Settings*, which this section said until 2026-09-06 and
which does not exist. It is **Administration → Configuration → Business
Profiles → Profile Assignment**, and it needs a firm selected.

| # | Case | Expect |
| --- | --- | --- |
| 27.18 | With any firm open: Administration → Configuration → Business Profiles → **Profile Assignment** | A grid of **every** firm, not just the one you are in. The screen names the firm in the URL rather than reading `X-Firm-ID`. |
| 27.19 | Select the new firm, open it, choose a profile, save | Saved against that firm. The **Business profile** dropdown must be populated -- if it is empty or the dialog says "The database is temporarily unavailable", you are in platform mode with no firm selected, and the catalogue it reads lives in each firm's store. |
| 27.20 | Re-open the row | The profile you chose is shown. Until it is set the firm trades as GENERIC, with the features and modules of no particular industry. |
| 27.21 | Sign in as `whole01.admin@agency.local` → Administration | **No** Firms tab and **no** Business Profiles group. `FIRM_VIEW` and `PLATFORM_VIEW` are platform codes no firm role can hold. |
| 27.22 **(HTTP)** | As `whole01.admin`, `GET` and `POST /api/v1/firms` | **403** for both. Measured 2026-09-06. No permission code can grant this. |

### 27e. The firm is not finished — the setup panel says what it needs

A provisioned firm with a profile still cannot trade. It needs a chart of
accounts, a financial year, open periods, journal and voucher types, and a
mapped control account for each of the 24 posting purposes. As of 2026-09-08
**Set up** on the Firms grid shows every step and opens the books itself.

| # | Case | Expect |
| --- | --- | --- |
| 27.23 | Administration → Firms, select `SNTEST02` → **Set up** | A panel titled `Set up SNTEST02`. The verdict reads **Cannot post documents yet.** Seven rows: Storage, Business profile, Books, Tax, Geography, Branches and warehouses, People. Storage and Books say **Required**, the rest **Recommended**. Books says "No chart of accounts" with an **Open the books** button; the rows with no button name the screen they are done on. |
| 27.23a **(HTTP)** | `GET /api/v1/firms/{id}/readiness` as `master.ops` | 200, `can_post: false`, the same seven steps with `status` DONE / MISSING and `required`. As `whole01.admin`: **403**. |
| 27.23b | From `backend`, run `.\.venv\Scripts\python.exe scripts\check_firm_readiness.py SNTEST02` | The same seven rows, from the same implementation, and **`CANNOT post -- books not open`**. |
| 27.23c | Press **Open the books** | The notice names the year: "Books opened for the year starting 2026-04-01" (the year *today* falls in, aligned to the firm's year start -- not the firm's `financial_year_start` if that is years old). The list re-reads: Books is done, "24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped, and a period open today", the button is gone, and the verdict reads **Can post documents. The recommended steps are still open.** |
| 27.23d | Press **Refresh**, then **(HTTP)** `POST /api/v1/firms/{id}/open-books` again | Nothing changes; the response says "The books were already open; nothing was created." with `already_open: true`. Settings → Audit Logs on the platform trail shows **one** `firm.books_opened` row with the counts, not two. |
| 27.23e | Create a `SCHEMA` firm, do **not** provision it, open **Set up** | Storage is **missing** with a **Provision storage** button on the row; every store-side step reads "Cannot be checked until the firm's storage is provisioned" with no button and no hint. Press it: the list re-reads and Books now offers **Open the books**. **(HTTP)** `POST .../open-books` on such a firm before provisioning: **422**, "Provision the firm's storage before opening its books." |
| 27.23f | On the panel, Tax row → **Apply GST template** | The notice reads "GST set up: 8 tax profiles and 6 rules." Tax re-reads as done, "1 tax system, 8 profiles, 6 rules", and **Geography** flips to done too -- the template adds India if the store has no country. Press it again **(HTTP)** `POST /api/v1/firms/{id}/apply-tax-template`: "The firm already has a tax system; nothing was created.", `already_configured: true`, and one `firm.tax_template_applied` audit row, not two. Open this firm → Administration → Configuration → Tax Configuration: the system, four components and eight profiles are there, editable. |
| 27.23g | Business profile row → choose **Wholesale** in the dropdown → **Assign** | "Business profile set to Wholesale." and the row re-reads as "Assigned: WHOLESALE" with the picker gone. The dropdown listed the **firm's own** catalogue (`GET /api/v1/business-framework/firms/{id}/profiles`), so this works from platform mode with no firm open -- Profile Assignment still needs one. Assign is dead until a profile is chosen. |
| 27.23h | **(HTTP)** `POST .../apply-tax-template` with `{"template": "US"}` | **422**. Only `IN_GST` exists. |
| 27.23i | Branches and warehouses row → **Create head office and main warehouse** | "Created branch HO and warehouse MAIN. Rename them on their own screens." The row re-reads as done, "1 branch, 1 warehouse", and with People already done the verdict reads **Finished. Every step is done.** Open this firm → Masters → Branches: `HO` Head Office, default; Warehouses: `MAIN` under it. Press it again **(HTTP)**: "The firm already has a branch and a warehouse; nothing was created." On a firm that named its own branch first, only the warehouse is created, under that branch. |
| 27.23j | Open this firm → Finance → **Control Accounts** | 24 rows, one per posting purpose, each showing the account it posts to and which classifications it may post to. On a fresh firm every row offers **Change**. As `whole01.admin` on WHOLE01: Accounts receivable, Sales revenue, Output tax, Inventory and the rest that trading has touched show a lock and "N posted" with no picker -- hover for why; only the purposes nothing has posted to (Rounding, TCS payable, the loyalty pair) offer Change. Change one: the picker lists only accounts of the allowed classification; Save is dead until a different account is chosen; the notice reads "Rounding posts to …". **(HTTP)** `PUT /api/v1/finance/control-accounts/ACCOUNTS_RECEIVABLE` on WHOLE01 with any other asset account: **422**, "Accounts receivable has N posted lines on 1100 Trade Receivables. Re-pointing it would leave two accounts each holding part of one story…". To see the **read-only** half -- the tab present, no Change, no Map -- you need somebody holding `VIEWER`, and **no seeded demo user does**: make one (Users → New, job template **Read Only**) or grant `VIEWER` to a spare account. *(Corrected 2026-09-15: this row said `whole01.sales1` holds `VIEWER`. It does not — `seed_multi_firm_demo.py` calls `set_user_roles` with `SALES_EXECUTIVE` alone, which replaces rather than adds, and that role carries no `ACCOUNT_VIEW`. As written the row shows **no Finance tab at all**, which is the *other* half of the sentence, so it would read as broken gating rather than as the plan being wrong. The `VIEWER`-holding users, `auditor.multi1/2`, come from `generate_sample_data.py` and are not in the four demo firms.)* |
| 27.24 | In the new firm, create a customer and a product | Both save. Masters do not need the books. |
| 27.25 | On a firm whose books are **not** open, raise a sales invoice and try to **approve** it | **Refused.** `DocumentPostingService` refuses rather than guesses. This is the design working, not a fault in the new firm -- open the books first. |
| 27.26 | **Set up** on `WHOLE01` | **Finished. Every step is done.** -- 24 accounts, 3 financial years, 36 periods, all 24 control accounts mapped; a profile, tax, a country, a branch and a warehouse, and members. No buttons. The contrast is the point: it shows what "finished" looks like. |
| 27.26a | Sign in as `whole01.admin` → Administration | No Firms tab, so no panel; and **(HTTP)** both routes answer **403**. Their result is visible to a firm administrator as their own Finance → Chart of Accounts and Financial Years. |

### 27f. Custom fields and mandatory fields

How a profile reaches a product. `docs/BUSINESS_PROFILE_FRAMEWORK.md`,
"How a firm resolves its attributes", is the reference. Stay signed in as
`master.ops` **with a firm selected** -- both screens live in that firm's
store, so platform mode does not offer them.

A definition applies when it targets the entity type **and** is either
unscoped or scoped to the firm's profile. **NULL means every profile, not
none** -- that is the whole grammar of the table, and reading it backwards is
what put an IMEI on a pharmacy's products in `20260801_0011`.

| # | Case | Expect |
| --- | --- | --- |
| 27.27 | Administration → Configuration → Business Profiles → **Dynamic Attributes** | The definitions in *this firm's* store. Each row shows its entity type and which profile it is narrowed to. |
| 27.28 | New → entity type `PRODUCT`, leave **business profile** blank | Applies to every profile. This is what a field every firm needs looks like. |
| 27.29 | New → entity type `PRODUCT`, business profile = **something other than this firm's** | Saved, and **not** offered on this firm's products. Scoping is what stops one industry's field appearing everywhere. |
| 27.30 | Masters → Products → New | The field from 27.28 appears; the one from 27.29 does not. |
| 27.31 | Set 27.28's definition **mandatory**, then create a product without it | Refused. The flag on the definition applies to **every** category it reaches -- blunt, and the one with a history. |
| 27.32 | Clear that flag. Administration → Configuration → Business Profiles → **Mandatory Attributes** → New, naming one category | Required for that category only. Products in other categories still save without it. |
| 27.33 | Add a mandatory rule naming a definition scoped to **another** profile | Accepted and **inert** -- `mandatory_ids` intersects the rules against what applies, so a rule this firm cannot see enforces nothing. Not an error. |
| 27.34 | Create a product carrying a value, then change the firm's business profile in Profile Assignment | The field **stops appearing** and its value is still in `product_attribute_values`. Nothing warns you; this is `docs/BACKLOG.md` §16. |
| 27.35 | Change the profile back | The field and its value reappear. Nothing was lost -- it stopped being *read*. |
| 27.36 | Change a definition's **data type** after a product carries a value | Accepted with no warning, and the value stops being read -- it sits in the old typed column. Record this as expected-but-wrong; it is §16's first lifecycle guard. |

**Customers and vendors carry the same fields as of 2026-09-08.** Stay in
the same firm.

| # | Case | Expect |
| --- | --- | --- |
| 27.36a | Dynamic Attributes → New → entity type `CUSTOMER`, code `DRUG_LICENCE_NO`, TEXT, mandatory **off**; then Masters → Customers → New | A **Custom fields** tab with one box, Drug licence no. Type `DL-4471`, fill the rest, Save. Reopen: the value is there. **(HTTP)** `GET /api/v1/customers/{id}`: `attributes` carries one row with `value_text: "DL-4471"`. |
| 27.36b | Edit the same customer's phone from the General tab and Save | The licence is still there. The form sends `attributes` only once it has read the definitions; an update that omits them leaves them alone. |
| 27.36c | Set the definition **mandatory**, then Customers → New with the box empty → Save | Refused on the form: "Drug licence no is required." Nothing sent. **(HTTP)** `POST /api/v1/customers` without it: **422**, "Required attributes are missing." |
| 27.36d | New definition, entity type `VENDOR`, `SUPPLIER_TIER`, NUMBER; Masters → Vendors → Edit a vendor → **Custom fields** | One numeric box, Supplier tier. Type `2`, Save, reopen: `2`. The customer form does **not** offer it, and **(HTTP)** sending its id on a customer answers **422**, "One or more attributes do not apply to this record." |
| 27.36d2 | New definition, entity type `BRANCH`, `FSSAI_LICENCE`; Masters → Branches → Edit `HO` | A **Custom fields** heading at the foot of the dialog with one box. Type a value, Save, reopen: it is there. The same for a `WAREHOUSE` definition on Masters → Warehouses. Each dialog asks for its own entity type only. |
| 27.36d3 | Dynamic Attributes → New: entity type `PRODUCT`, `STORAGE_TEMPERATURE`, TEXT, **Allowed values** `Ambient, Chilled, Frozen`; then Masters → Products → New → Attributes | The field is a **dropdown** of the three, not a text box. Choose one, save, reopen: it is selected. **(HTTP)** `PUT` the product with `"Cold"` for it: **422**, "Attribute STORAGE_TEMPERATURE must be one of: Ambient, Chilled, Frozen." Edit the definition and remove `Frozen`: a product already holding Frozen still shows it, selectable, and saves unchanged. Set the data type to NUMBER with values still filled: **422**, "Only a TEXT attribute can carry allowed values." |
| 27.36d4 **(HTTP)** | Define a `UOM` attribute, then `PUT /api/v1/uom-framework/uoms/{id}` with `attributes` as `whole01.admin`, and `GET` the unit as `medi01.admin` (a SHARED firm sharing the store) | WHOLE01 reads its value back; MEDI01 reads an empty `attributes` on the same unit. The unit is one row for every firm in the store; its custom-field values are per firm. A `TAX_PROFILE` attribute on `PUT /api/v1/tax-framework/profiles/{id}` round-trips the same way. No desktop form shows either yet. |
| 27.36e **(HTTP)** | `GET /api/v1/business-framework/attribute-definitions/applicable?entity_type=CUSTOMER` with `X-Firm-ID`, as `whole01.sales1` | 200: the customer definitions this firm's profile allows and `mandatory_ids`. Membership of the firm is the whole gate. Without `X-Firm-ID`: **403**, "Select a firm to read its custom fields." |

**If the firm is `SHARED`**, one more case, and it is the reason §16 exists:

| # | Case | Expect |
| --- | --- | --- |
| 27.37 | Add a definition in your new `SHARED` firm, then open Dynamic Attributes as `medi01.admin@agency.local` | **It is there.** `attribute_definitions` carries no `firm_id`, so every firm in `firm_shared` edits one set. A firm in its own schema or database does not have this. |

Delete the test firms afterwards, or leave them; a firm with no data costs
nothing. A `SCHEMA` firm leaves its schema behind either way.

## Appendix — driving the API by hand

For the **(HTTP)** cases. See `.claude/skills/run-app` for the full recipe.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"whole01.sales1@agency.local","password":"DemoAdmin@12345"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# /me/firms, **not** /firms. `GET /api/v1/firms` is platform-only and answers
# 403 for every firm user, including the token above -- so a recipe built on it
# fails on the step before the one you are testing. `/me/firms` returns
# {id, code, name, is_primary}; the firm id is `id`.
FIRM=$(curl -s http://localhost:8000/api/v1/me/firms \
  -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])")

curl -s -w "\nHTTP %{http_code}\n" -X POST \
  http://localhost:8000/api/v1/document-framework/numbering-rules \
  -H "Authorization: Bearer $TOKEN" -H "X-Firm-ID: $FIRM" \
  -H "Content-Type: application/json" -d '{...}'
```

*Corrected 2026-09-15: this read `FIRM=<the WHOLE01 id from GET /api/v1/firms>`,
which no firm token can call.*

A platform caller is the other way round — `/api/v1/firms` lists every firm and
`/me/firms` returns only the ones they are a member of, which for
`platform-admin` is none. Pick the route that matches the token in your hand.

**Never write a token to a file inside the repo.** A previous run committed one;
`.tok` and `uvicorn-*.log` are in `backend/.gitignore` because of it.

Every response carries a `requestId`. Quote it when reporting anything — it
joins the screen to the server log.
