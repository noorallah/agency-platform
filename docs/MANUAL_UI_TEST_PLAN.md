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

All as `whole01.admin` in WHOLE01, in order: each step feeds the next. Quotations, Sales Orders, Delivery Notes, Sales Invoices and Sales Returns are each their own sidebar entry (no groups); Credit Notes and Proforma are tabs of **Sales**; receipts are **Finance → Receipts**; the customer's balance is on **Masters → Customers** (the **Outstanding** and **Advance** columns). Seed facts the rates below rest on: `WHOLE01C01` Vijaya Super Stores has a 7.5% standing discount; the firm-wide `STANDING` price list on `DETER1K` has breaks 0 → 2%, 15 → 4.25%, 18 → 6.75%; `WHOLE01C02` Anand Agencies has its own `NEGOTIATED` list at a flat 9.25%; promotion `BULK5` gives 7.5% on a line of 25 or more (its earlier revision gave 5% and only reaches documents dated before the second seeded year); `WELCOME` gives 2.5% only when coupon `WELCOME10` is presented. DETER1K sells at 84 under `GST_18_LOCAL`. A resolved percentage is **not printed on a saved document**: read it by reopening the editor -- **Revise** on a quotation, **Edit** on a draft order -- where a rate the server resolved is shown **under a blank box** as "Last priced at N% by the price list" (or a promotion, or the customer's standing rate), and a rate somebody typed is refilled into the box. Saving a revision prices resolved lines afresh, which is what lets a ladder move with the quantity (BACKLOG §31.14). Two facts the money rows rest on, both verified by driving the flow against the running backend on 2026-09-13: WHOLE01 has **TCS enabled** (0.1% on money received over a 5,000 threshold), so every receipt raises what the customer owes by the TCS on it -- 0.1%, or **1% for a customer with no PAN**, which WHOLE01C01 is -- and the Record Receipt dialog says so; and WHOLE01C01 already owes on seeded invoices (7,498.96 on 2026-09-13), so **an excess on a receipt becomes an advance only when the customer owes nothing else** -- otherwise it comes off the account balance and the receipt shows it as "on account". Every screen reads once when opened: click **Refresh** after acting elsewhere. The document grids list **newest first within a date** and carry a **Created** column (local date and minute) since 2026-09-13, so the document you just raised is the top row; quotations and returns show "made <date> <time>" in the row's subtitle.

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
| 9.9 | Select the order → **Approve**. Then Masters → Products → DETER1K, or Inventory → Stock → Inventory for DETER1K in WHL_DC. | Status **APPROVED**; a credit warning toast may appear first (WHOLE01 warns at 80% and never blocks). Reserved on DETER1K in WHL_DC is up by 12. *(An order taken for more than the warehouse holds is still approved -- it is a back order, and that warehouse's Available goes negative.)* Reports → **Promotion claims**: the `WELCOME` row for this order reads **CLAIMED** (it was pending while the order was a draft). |
| 9.10 | Select the order → **Hold** (dialog "Hold SO-...", give a reason, **Hold**). Then Delivery Notes → **New**, pick the order in **Sales Order ***, **Save Delivery Note**. | Toast "SO-... is on hold."; the Status cell reads **APPROVED (on hold)**. The delivery note is refused **on save**, in the editor's banner: "SO-... is on hold and cannot be dispatched ("<your reason>"). Release it first." Reserved on DETER1K is **unchanged** -- a hold says "not yet", not "never". *(The refusal is at note creation; there is no Dispatch button on the order.)* |
| 9.11 | Select the order → **Release**. | Toast "SO-... released."; the Status cell reads plain **APPROVED** again -- the status it had, not a reset. The hold reason stays on the record. |
| 9.12 | Delivery Notes → **New**, pick the order, on its line set **Delivering** to **5** (the field defaults to the 12 reserved), Warehouse `WHL_DC`, **Save Delivery Note**. Select the draft → **Approve** → **Dispatch**. *(Shipping from a warehouse other than the order's is allowed: the reservation is released where the order made it. Until 2026-09-13 it was released from the note's warehouse, and dispatch was refused with "Reserved quantity cannot become negative.")* | Toast "Delivery note DN-... created as a draft. Dispatching it is what moves the stock." Dispatch shows no toast; after Refresh the note reads **DISPATCHED**. Sales Orders: the order reads **PARTIALLY_DELIVERED**. Stock Ledger: `DISPATCH` −5 on DETER1K referenced by the DN. Finance → Journal Entries: the note's cost-of-goods entry. |
| 9.13 | Double-click the delivery note to open its view; note the line's **Unit Price**. Then open the sales order's view and compare. | **Identical.** The note ships the deal the order struck and does not re-read the customer's current rate. *(Both views print the product as `DETER1K — ...` since 2026-09-13; the order view prints the discount as an amount, not a percentage -- BACKLOG §31.14.)* |
| 9.14 | Delivery Notes → **New** against the same order: Delivering defaults to the remaining **7**. Save, Approve, Dispatch. | The order reads **DELIVERED**; the ledger shows a second `DISPATCH` −7. |
| 9.15 | Sales Invoices → **New Invoice**. In **Bill this delivery note** (helper "Only notes with something left to bill.") pick the **first** note -- the 5-unit one (items read "DN-... · date · Vijaya Super Stores"). Its line reads "dispatched 5 · at 84 less 2.5%" with **Bill** defaulted to 5. Type **6** into Bill. | Refused before sending: "Only 5 left to bill." (the server's own refusal, reached by an API client, is "Invoice quantity exceeds the available source quantity.") Set it back to **5**, **Create draft**: toast "Invoice created as a draft. Approve it to post the journal." A note that gave a unit free would show the free unit apart from the billable 5, and it could not be billed. |
| 9.16 | Select the invoice → **Approve**. Then Masters → Customers → `WHOLE01C01`. | Status **APPROVED**. Finance → Journal Entries shows the invoice's `SI-...` entry as the top row (same-day entries list newest posting first since 2026-09-13): Dr Accounts Receivable 483.21, Cr Sales 409.50, Cr Output Tax 73.71 -- **one** tax line; the CGST 9 / SGST 9 split is on the invoice and its print, not in the journal. The customer's **Outstanding** is up by the invoice's grand total. |
| 9.17 | With the invoice selected click the **Print settings** icon: set **How many copies** to 2 and give **Copy 1 label** / **Copy 2 label** (they prefill as ORIGINAL FOR RECIPIENT / DUPLICATE FOR TRANSPORTER), save. Then **Print**. | The PDF carries both parties' GSTINs, an HSN column (`340220`), the CGST/SGST split, the HSN-wise summary, "AMOUNT CHARGEABLE, IN WORDS", and the two labelled copies. *(Copies are not defaulted for an invoice until Print settings is saved, which is why the step comes first. These are the firm's own settings, stored on the server per document type, and saving them needs `SETTINGS_UPDATE` -- the firm administrator; until 2026-09-13 the dialog asked for a platform code no firm role can hold and opened read-only. The printer dialog's own copy count is separate and repeats the whole set.)* |
| 9.18 | Finance → **Receipts** → **Record Receipt**. **Received from** `WHOLE01C01`, **Amount** half of the invoice's outstanding (241.60 for a 483.21 invoice), **Method** Bank, then under **Apply to invoices** type the whole amount into the **Apply** box of *your* invoice's row -- **not Oldest first**, which clears the oldest seeded invoice, because the customer already owes on seven. **Record receipt**. | The dialog shows a TCS notice for the receipt: WHOLE01C01 holds **no PAN**, so TCS is charged at **1%**, not 0.1% (2.42 on 241.60). Toast "RC-... recorded and posted to the ledger."; the row's subtitle reads "Cleared SI-..." and its badge **Applied**. Customers: Outstanding down by the amount **less the TCS** (7,982.17 → 7,742.99 on 2026-09-13); the invoice keeps the rest outstanding (241.61). |
| 9.19 | **Record Receipt** again for `WHOLE01C01`: Amount = **the invoice's remaining Outstanding + 100** (341.61), type exactly the invoice's Outstanding (241.61) into its **Apply** box, Record receipt. | The dialog's running line reads "100 left on account" before saving; the saved row's badge reads **On account 100** and the invoice drops out of the outstanding list. Customers: Outstanding falls by the **whole** receipt less TCS, and **Advance is unchanged** -- the customer still owes on seeded invoices, so the 100 is money against the account, not an advance. Advance rises only when a receipt exceeds everything the customer owes; never a negative balance either way. |
| 9.20 | Sales Invoices → New Invoice against the **second** delivery note (the 7), Create draft, Approve. Then Finance → Receipts: on the on-account receipt click the icon tooltipped **Apply to an invoice**. In "Apply RC-..." choose the new invoice, Amount up to the advance, **Apply**. | Toast "RC-... applied to SI-...". The dialog's own line says it: "Nothing moves in the ledger. The money arrived when the receipt was recorded." Finance → Journal Entries shows **no new entry**; the receipt's badge changes from **On account 100** to **Applied**; Customers: Outstanding and Advance are **unchanged**, because the 100 already reduced the balance when the receipt was recorded (only money that had become an advance would move it). Applying more than is on account is refused: "RC-... has only 0.00 left unapplied." |
| 9.21 | On the first receipt (9.18) click the icon tooltipped **Reverse**, give a reason in "Why is it being reversed?", **Reverse**. | Toast "RC-... reversed."; the row's badge reads **Reversed**; Journal Entries shows the mirror entry `RC-...-REV`. Customers: Outstanding and Advance are back to exactly where they were before that receipt, TCS included. Reversing it again is refused: "RC-... has already been reversed." |
| 9.22 | Sales Returns → **New Return**. **Returned against**: the first invoice (SI-... · date); **Line** 1; **Taken back into** `WHL_DC`; **Quantity returned** 2. **Create draft**. Select it → **Approve** → **Complete**. Try Quantity returned 9 on a new draft first if you want the cap: "Only 5 went out on this line." (server: "Return quantity exceeds what was dispatched on the source document (5.0000 sent, 0.0000 already returned).") | Toasts "SR-... created as a draft...", "SR-... approved. Nothing has moved yet...", then "SR-... completed: 2 back on the shelf and <amount> credited to the customer." The detail pane's "What this moves" card ticks Stock, Customer and Ledger. Stock Ledger: `SALES_RETURN` +2; Customers: Outstanding down by the credit. |
| 9.23 | Sales → **Credit Notes** → **Raise credit note**. **Invoice**: the first invoice; **Line** 1; **Reason** Rate difference; **Credit, before tax** 50; **Raise**. Then the row's **Approve**. | Grid row reads `<total> (tax <tax>)`: the tax is 18% of 50, the rate that line was charged, not a profile rate read today. Approve toast "CN-... — approved. The credit and the tax are on the ledger." Customers: Outstanding down by 59. |
| 9.24 | **Raise credit note** again on the same line with **Credit, before tax** larger than the line was charged (5 × 84 less its discount). | Refused with "A credit note cannot credit more than the line was charged: 409.50 charged, 50.00 already credited." (5 × 84 less 2.5%). |
| 9.25 | Sales → **Proforma** → **New**. **Sales order**: the order from 9.6 (any approved, delivered or closed order qualifies), **Raise**. Select it → **Issue**. | Toasts "PI-... raised. Issue it when the customer needs it." then "PI-... issued." The number is a `PI` series. Finance → Journal Entries: **nothing** posted; Customers: Outstanding unchanged. The pane says "Not a tax invoice — no input tax credit is available against this document." |
| 9.26 | The order is DELIVERED so it cannot be edited; instead Sales Orders → **New Order** for `WHOLE01C01`, one line `DETER1K` qty 3, Create draft, Approve; Proforma → New against it, Raise, Issue. Then Sales Orders → select that order → Edit is disabled; so open its view and note the lines; then Cancel the order (reason). Reopen the proforma. | The proforma's lines and totals are unchanged by anything done to the order afterwards -- they were snapshotted when it was raised, as the Raise dialog said. *(A DRAFT order can be edited; an approved one cannot, so cancellation is the only later change available here.)* |

## 10. Pricing, promotions and incentives

All as `whole01.admin` in WHOLE01. Price Lists, Promotions, Commission and Targets are tabs of the **Sales** module (a flat list); Loyalty is a tab of **Masters**; the promotion and loyalty reports are entries of **Reports → Operational Reports** or **Financial Reports** (two flat lists, no parameters). Seed facts, verified against the running backend on 2026-09-13: `STANDING` breaks 0 → 2%, 15 → 4.25%, 18 → 6.75% on DETER1K; `BULK5` has two revisions (5% to 2025-03-31, 7.5% from 2025-04-01), 34 claims across both; `BIGORDER` takes 200 off a bill of 4,500 or more and **ends the stack**; `WELCOME` is coupon-only at 2.5% with codes `WELCOME10` (4 claims) and `WELCOME10B` (never presented); the loyalty scheme gives 2 points per 100, worth 1 each, expiring after 24 months, 50 needed before spending; `whole01.sales1` is **Asha** (4% flat plus 15% of the *margin* on DETER1K) and `whole01.sales2` is **Bala** (a ladder: 2% to 50,000 then 4%, nothing below 1,000, 2% bonus when the target is met); two payouts are seeded for April to June 2026, Asha's paid and Bala's approved. On the collected basis Asha came out at **5.8%** and Bala at exactly **2.0%** on the day of writing.

| # | Case | Expected |
| --- | --- | --- |
| 10.1 | Sales → **Price Lists**. Select `STANDING` (do not double-click yet). | The pane on the right reads `STANDING · applies to Everyone`, "In force from 2000-01-01", and under **Rates** three lines for DETER1K: `2%`, `from 15: 4.25%`, `from 18: 6.75%`. The grid's **Products** column reads 3 (it counts rate rows). |
| 10.2 | Double-click `STANDING` (or the row's pencil) → **Add product**: Product `DETER1K`, **From qty** 25, **Discount %** 8, **Save**. Then Quotations → New Quotation for `WHOLE01C01`, `DETER1K` qty 30, Create draft, Revise to read the helper. Afterwards remove the 25 break again. | Toast "Price list saved." The quotation still reads "Last priced at **7.5**% by a promotion": `BULK5` outranks the list at 25 and above. *(To see the list take effect, Promotions → BULK5 revision 2 → Edit → set **Until** to yesterday → Save; then the same quotation reads 8% by the price list. Put the window back afterwards -- note that editing an active offer makes a new revision.)* |
| 10.3 | Sales → **Promotions** (Offers). | `BULK5` appears as **two rows**: Gives `5% off the line` In force `2024-04-01 to 2025-03-31`, and `7.5% off the line` `From 2025-04-01`. Select the second: the pane reads "BULK5 · revision 2 · applies at 10" and "Applies when: line_quantity GREATER_OR_EQUAL 25". Edit it, change nothing but the Description, Save: toast "Promotion BULK5 saved as a new revision; the one you opened is now inactive." and a third BULK5 row appears -- an active offer is superseded, never rewritten. |
| 10.4 | Reports → **Operational Reports** → **Promotion performance**. | One row per offer: `BULK5` with Version count **2**, Claimed count **34**, Benefit amount, Customer count 4 -- the two revisions collapsed to one row. `WELCOME` and `BIGORDER` and `CLEARANCE` each on one row too. |
| 10.5 | Reports → Operational Reports → **Coupon performance**. | Two rows: `WELCOME10` (promotion WELCOME) with Claimed count 4, and `WELCOME10B` with 0 -- listed although nothing ever presented it. |
| 10.6 | Reports → Operational Reports → **Promotion claims**. | One row per claim with Promotion code, Coupon code, Customer name, Document type (always SALES_ORDER -- only orders claim), Document number, Redeemed on, Benefit amount and Status (CLAIMED / PENDING / REVERSED). Your 9.7 order is here as `SO-...` with coupon WELCOME10. |
| 10.7 | Sales Orders → New Order for `WHOLE01C01`: `DETER1K` qty **60** at 84 (gross 5,040), Create draft, Edit to read. | Under the line's blank box "Last priced at **7.5**% by a promotion" (BULK5, not CLEARANCE's 1% at 40+: promotions apply in priority order and BULK5 is first), and **Discount on the whole order** shows 200 -- `BIGORDER` took the bill. `CLEARANCE` (priority 30) did **not** apply: BIGORDER (priority 20) ends the stack. Cancel the order afterwards. |
| 10.8 | Masters → **Loyalty**. Then Reports → Financial Reports → **Loyalty balances**. | The Loyalty page shows the scheme banner ("2 points per 100, worth 1 each and expire after 24 months. At least 50 before any can be spent.") and the ledger (On, Customer, Why, Against, Points, Worth, Expires). The balances report lists each customer's Points and Amount; Anand Agencies and Classic Departmental Stores hold the most. Pick one and add up its EARNED/REDEEMED/EXPIRED rows in Reports → Operational → **Loyalty movements**: the sum is the balance. |
| 10.9 | Sales Invoices → select an APPROVED invoice of `WHOLE01C02` (Anand Agencies, ~1,300 points) with something still owed → **Use points**: in "Use points on SI-..." type 100 → **Use them**. | Toast "100 points used on SI-...". Finance → Journal Entries: `LOY-RED-SI-...` posts Dr Loyalty Payable / Cr Accounts Receivable. The invoice's Outstanding fell by 100; its Grand Total and tax are unchanged -- the bill is **settled**, not discounted. |
| 10.10 | **Use points** again on the same invoice, type a number larger than the balance → **Use them**. | Refused outright, not trimmed: "That customer holds N points, not M." |
| 10.11 | Reports → Operational Reports → **Points about to lapse**. | Rows per unspent batch within 90 days -- Customer name, Points (what is *left* of the batch after spending), Amount, Earned on, Expires on, Days remaining -- ordered by expiry then customer. |
| 10.12 | Sales → **Commission** → **Collected** view: Collected from `2024-04-01` to today, **Show**. Divide each salesman's Commission by their Collected. | Asha's rate is **neither** of the two that govern her: a blend of 15% of the margin on DETER1K and 4% of the value of everything else (5.8% on 2026-09-13; it moves with the data, so check the shape). Her Paid on reads "Money collected", Target "Met". |
| 10.13 | Same report, Bala. | Exactly **2.00%** -- the bottom band of his ladder; a round number precisely because a ladder's floor is. Target "Missed". |
| 10.14 | Commission → **Payouts** view. Then **Accrue period** From `2025-05-01` To `2025-05-31`, **Accrue**. On Bala's new DRAFT row click **Approve**, then **Pay** (Paid on today, Paid from the cash account, **Record payment**). Cancel Asha's draft. | Toast "2 payout(s) accrued as drafts." Approve toast "Bala (WHOLE01 Sales) — approved. The cost and the debt are on the ledger."; Pay toast "... — paid." Finance → Journal Entries shows three references for that payout: `COMM-202505-<id>`, `COMM-202505-<id>-PAY`, and on a cancelled one `-REV`. Pay on a DRAFT is not offered; **(HTTP)** paying it answers 422 "Only an approved payout can be paid...". Accruing May 2025 again is refused: "A commission payout already covers part of that period for this salesman (2025-05-01 to 2025-05-31)." |
| 10.15 | Sign in as `whole01.sales1@agency.local`. | **Commission is not in the sidebar at all** -- a SALES_EXECUTIVE holds no COMMISSION_VIEW. **(HTTP)** with that token, `POST /api/v1/commission/payouts/{id}/approve` and `/pay` answer **403**. Whoever states a debt must not move the cash. |

## 11. Territory, routes and beats

All as `whole01.admin`. Geography, Route Types, Beat Plans, Call Lists, Coverage and Route Builder are tabs of **Sales**. Seed: `WHOLE01-RGN` Chennai Region → `WHOLE01-T-N` North Zone and `WHOLE01-T-S` South Zone → routes `WHOLE01-R-N1` North Sales Beat (Mon/Wed/Fri, Asha, Vijaya), `WHOLE01-R-N2` North Collections (Tue/Thu, Bala, Anand), `WHOLE01-R-S1` South Sales Beat (Tue/Thu, Asha, Classic). Beat plans: one weekly plan per working day per route (`WHOLE01-BP-R1-MON`, `-R1-WED`, `-R1-FRI`, `-R2-TUE`, `-R2-THU`, `-R3-TUE`, `-R3-THU`), `WHOLE01-BP-COLL` fortnightly on Tuesdays from 2026-04-07, and `WHOLE01-BP-MTH` monthly on the 2nd Tuesday.

| # | Case | Expected |
| --- | --- | --- |
| 11.1 | Sales → **Geography**. Select any row: the right-hand **Territory tree** panel. **Expand all**. | Chennai Region (REGION) → North Zone and South Zone (TERRITORY) → the three routes (ROUTE). The grid's Hierarchy column carries the full path for every row. |
| 11.2 | Double-click `WHOLE01-R-N1` → **Details** tab. | Section **Route**: Route type SALES, Visit frequency WEEKLY, **Working days** `Mon, Wed, Fri`, Runs from Always, Runs until No end. |
| 11.3 | Sales → **Call Lists**. Use ‹ › or the date button to land on a **Monday**, Salesperson **Everyone**. | Status bar "N of 9 plan(s) run on <date>". `WHOLE01-BP-R1-MON` is badged **Runs today** with its stops (Vijaya Super Stores). `WHOLE01-BP-R1-FRI` is badged **Not today** and reads "Runs on Fridays; this is a Monday." -- every plan that is not due says why. |
| 11.4 | Pick **2027-01-12** (a second Tuesday that is also an even fortnight from 2026-04-07; 2026-09-08 was the last such day). | `WHOLE01-BP-R2-TUE`, `WHOLE01-BP-R3-TUE`, the fortnightly `WHOLE01-BP-COLL` and the monthly `WHOLE01-BP-MTH` all read **Runs today**. On 2026-10-13 (a second Tuesday in an odd fortnight) COLL reads Not today. |
| 11.5 | Sales → **Route Builder**: Route being built `WHOLE01-R-N1`. Double-click two outlets from the left (e.g. `WHOLE01C02` and `WHOLE01C03`) to add them, drag the last stop above the first, **Save round and order**. | Toast "3 outlet(s) on North Sales Beat, in order." Reopen the route: the stop numbers follow the new order and nothing collided. Remove the two added outlets afterwards (✕ **Remove from round**, Save). |
| 11.6 | Route Builder: choose `WHOLE01-R-N1`, let the round load on the right, change nothing, **Save round and order**. | Toast for the same list; reopening shows it unchanged. The status bar says "Saving replaces the whole round with the list on the right." -- which is why the screen clears the panel before reading and refuses to save a round it could not read ("This round could not be read, so it cannot be saved over."). |
| 11.7 | Sales Orders → **New Order** for `WHOLE01C02` (Anand, on North Collections, covered by Bala): **Salesman** `Asha`, one line `DETER1K` qty 1, **Create draft**. | Refused, in the editor: "The selected salesperson is not assigned to this territory." Choosing Bala saves; leaving Salesman blank saves and the customer's round supplies Bala. |

## 12. Compliance

All as `whole01.admin` in WHOLE01. E-Invoice, GST Returns and TCS are tabs of the **Sales** module (flat list, no groups). Facts the rows rest on, from the seed and from driving the API on 2026-09-13: WHOLE01 holds **13** e-invoice registrations and 6 e-way bills, every one SANDBOX; customer `OB-REV2` (Revise Check 2) has **no GST number** and four refused invoices; the firm's **TCS is switched on** by the seed (threshold 5,000, 0.1%), so the "disabled by default" the model would give a fresh firm is not what you will see; every accounting period is OPEN. Every screen reads once when opened: **Refresh** after acting elsewhere.

| # | Case | Expected |
| --- | --- | --- |
| 12.1 | Sales → **GST Returns**. The **From** and **To** boxes hold the current month; set them to a month with invoices (the history bills on the 12th and 22nd of every month, so **From** `2026-08-01` **To** `2026-08-31`), **Refresh**, with the **GSTR-1** segment selected. | Heading "Filing as <the firm's GSTIN>". Four tables: **B2B — registered buyers, invoice by invoice** (Invoice, Buyer GSTIN, Taxable, CGST, SGST, IGST), **B2CS — unregistered, summarised by place and rate** (Place, Rate, ...), **CDNR — credit notes to registered buyers**, **HSN summary**. No B2CS row has a blank Place. A fifth table, **Invoices without a place of supply — named here, not filed**, lists any invoice the return could not place rather than filing it blank; for August it reads "Nothing in this section." The status bar says "Derived from the documents on every read, never stored." |
| 12.2 | Sales Invoices → select an APPROVED August invoice of a registered buyer → **Cancel** (reason). Back on GST Returns → **Refresh**. | The invoice is gone from B2B and the HSN totals fell by its amounts. The return is derived on every read, never stored. *(Pick an invoice with no receipt against it; one that has been paid refuses to cancel.)* |
| 12.3 | Switch the segment to **GSTR-3B**, same month. | **3.1(a) — outward taxable supplies** with Taxable, IGST, CGST, SGST, Cess; **Credit notes already deducted above**; and a sentence about the inward side the system does not know. Add up GSTR-1's B2B, B2CS and CDNR taxable values by hand: they equal 3.1(a)'s Taxable. *(Nothing on screen reconciles the two for you; 3B is aggregated from the documents, not parsed out of GSTR-1.)* |
| 12.4 | Sales → **E-Invoice**. | A banner: "References marked sandbox are a rehearsal: nothing was filed with the tax authority..." The grid has **Invoice**, **Customer**, **Reference**, **E-way bill** columns and an actions column; every Reference reads `SBX... (sandbox — nothing filed)`. 13 rows for WHOLE01. |
| 12.5 | **Register an invoice** → in the **Sales invoice** picker choose one of `OB-REV2`'s approved invoices (items read `SI-... — <total>`) → **Register**. | Refused **locally**, in an error toast, with "This invoice cannot be registered yet: the customer has no GST number." No row is added, no portal code appears. *(If the picker offers no OB-REV2 invoice, approve one of its drafts on Sales Invoices first.)* |
| 12.6 | On a registered row with an empty E-way bill cell click **Raise e-way bill**: **Distance (km)** 120, **Moving by** Road, **Vehicle number** `TN01AB1234`, **Raise**. Then on the same row **Withdraw bill** (reason). | Toast "E-way bill raised."; the row's E-way bill cell fills with a sandbox reference. Leaving the vehicle blank on a road movement is refused before sending: "Goods moving by road need a vehicle number on the bill." Raising a bill against an **unregistered** invoice is not offered on screen; **(HTTP)** `POST /api/v1/einvoice/invoices/{id}/eway-bill` on one answers 422 "Register the invoice before raising its e-way bill...". Withdraw toast "E-way bill withdrawn." |
| 12.7 | Sales → **TCS**. | The banner reads "Collecting under section 206C(1H) • 5000.00 per buyer per year, then 0.100% (1.000% without a PAN)" and the register lists the receipts already charged (Receipt, Buyer, On, Received, Paid before, Chargeable, Rate, Collected, Status). **Settings** opens "Tax collected at source" with the switch **Collect under section 206C(1H)** on, **Preceding year turnover** 150,000,000, **Threshold per buyer, per financial year** 5,000, **Rate %** 0.1. *(A firm the seeder never touched starts switched off; every demo firm is on.)* |
| 12.8 | Finance → Receipts → **Record Receipt** for `WHOLE01C03`, any amount above 5,000 against one of its open invoices, **Record receipt**. Back on Sales → TCS → **Refresh**. | The dialog showed a TCS notice before saving. The register gains a row for that receipt: Received = the amount, Chargeable = the part above what this buyer had already paid past the threshold this year, Collected = 0.1% of it, Status posted. Finance → Journal Entries: the receipt's entry carries a `TCS_PAYABLE` credit for exactly Collected. Customers → C03: Outstanding fell by the receipt **less** Collected. |

## 13. Finance, reports and platform

As `whole01.admin` unless a row says otherwise. Finance is a flat list of tabs; Reports has two tabs, **Operational Reports** (40 entries) and **Financial Reports** (16); accounting periods live under **Masters → Configuration → Financial Years**, not under Finance. Trial Balance, Profit & Loss and Balance Sheet each take an **Accounting period** dropdown: pick the **same** period on all three when comparing them.

| # | Case | Expected |
| --- | --- | --- |
| 13.1 | Finance → **Chart of Accounts** → **New**: Account Group any, Code `9999`, Name `Manual test account`, Account Type EXPENSE, Save. | The row appears (Code, Account, Type, Status). There is no Delete; deactivating is the Active switch on Edit. |
| 13.2 | Finance → **Trial Balance**, Accounting period `September 2026`. | Columns Code, Account, Type, Opening, Debit, Credit, Closing, a **Total** row, and a chip reading **Balanced**. Every account carrying a balance as at the period is listed, not only ones posted in it. |
| 13.3 | Finance → **Profit & Loss** and **Balance Sheet**, same period. | P&L: Income and Expenses sections with totals and a **Net profit or loss** row (This period, Year to date). Balance Sheet: Assets, Liabilities, Equity with **Retained earnings brought forward** and **Result for the year**, then **Liabilities and equity**, chip **Balanced**. They agree: Total assets = Liabilities and equity; the sheet's Result for the year = P&L's Year to date net; the trial balance's total debit = total credit. |
| 13.4 | Finance → **Journal Entries**. Page through the list reading each row's subtitle ("Posted by <module>" or "Written by hand"). | Over the history you meet **thirteen** posting modules: delivery_note, sales_invoice, sales_return, credit_note, goods_receipt, purchase_invoice, purchase_return, settlements, loyalty, tcs, commission, plus inventory (adjustments, opening stock) and customers (opening balances). *(There is no source-module filter; the search box matches reference or description -- BACKLOG §31.15.)* |
| 13.5 | Journal Entries → **New Entry**: Accounting period `June 2026`, Journal type and Voucher type any, Date `2026-06-15`, Reference `MT-CLOSE-1`, two lines (`5000 Purchases` debit 100, `1000`-series cash account credit 100), **Save Draft**. Then Masters → Configuration → **Financial Years**, select the year, on **June 2026** click **Close** (toast "June 2026 is closed. Nothing further can be booked into it."). Back on Journal Entries select the draft → **Post**. Afterwards reopen the period (**Open**). | The post is refused: "Accounting period P03 is closed and cannot accept postings." (the code is the period's; June is P03 in an April year). After **Open**, Post succeeds with "Journal entry MT-CLOSE-1 posted." *(No seeded period is closed, so the row closes one itself; the New Entry dialog offers only OPEN periods, which is why the draft is written first.)* |
| 13.6 | Reports → **Operational Reports** and **Financial Reports**: open every entry in both lists (56). | Each renders with `N row(s)` in the header; an empty one reads "Nothing to report / This firm has nothing matching it yet." rather than a blank grid. The two return reports are now **Purchase returns by product** and **Sales returns by product**. Over two years of WHOLE01 history none is empty except those listing pending or damaged goods. |
| 13.7 | Press **Ctrl+K** inside WHOLE01, type `DETER`, **Search**. | Results across kinds (products, inventory...) with "N results found." and no error. **(HTTP)** `GET /api/v1/search?q=DETER` answers 200 -- the dialog would fall back to an inventory-only search if the route failed, so the API check is the one that proves there is no 503. |
| 13.8 | Settings → **Audit Logs** with WHOLE01 selected; then sign in as `master.ops` on **Platform** (no firm) and open it again. | With a firm: the caption "The trail for WHOLE01. Platform administration and other firms keep their own..." and that firm's rows. Without a firm, as a platform administrator: "The platform trail: users, roles and firm administration..." As a firm admin without a firm the trail is refused (403 over HTTP). |
| 13.9 | Administration → **Users**, then **Roles & Permissions** (both halves). Select a **system** role (Origin/subtitle "System role") and double-click it; then select a custom role → **Edit** → change its Permissions → Save. | All load. On the system role the toolbar's Edit is disabled and double-clicking shows "System roles cannot be modified." rather than opening silently. The custom role's permissions save. |
| 13.9b | Look at the Administration sidebar | **One** entry, **Roles & Permissions**, where Roles and Permissions used to be two. Open it: the Roles grid with a Roles / Permissions strip above it. Switch to Permissions: the sidebar entry stays highlighted and the heading still reads Roles & Permissions. |
| 13.9c | Ctrl+K, type a permission code, open the result | Lands on the **Permissions** tab directly, not on Roles -- each half keeps its own address. Sign out and in: the last screen restores to the same half. |
| 13.9c2 | Sign in as `elec01.admin`, Inventory → **Batch & Serial** → **Serial Numbers** | Up to twenty `MIX500-...` serials, AVAILABLE, each with a warranty year. Masters → Products → `MIX500` shows **Track serial** on. |
| 13.9c3 | As `medi01.admin`, Customers → Settings | Policy **BLOCK**, warn 80, block 100. Open CityMed Clinic: credit limit 20,000. Sales → Orders: some of that customer's orders sit unapproved; **(HTTP)** `POST /sales-orders/{id}/approve` on one answers 422 naming the exposure. As `food01.admin`, Settings → Sales workflow: **Delivery note** stage off; Sales → Delivery Notes still lists one per invoice, raised by the service. |
| 13.9d | Finance → **Cost Centres** → New `SALES`, Save; Finance → **Profit Centres** → New `NORTH`, Save | Both grids list the row. Neither offers Delete: deactivate instead. |
| 13.9e | Finance → Chart of Accounts → Edit `5000 Purchases` → tick **Requires a cost centre** → Save. Then Journal Entries → New Entry, choose 5000 on a line | A **Cost centre \*** dropdown appears on that line and on no other; choose `SALES`. Save with it: posted. **(HTTP)** the same entry without `cost_center_id` on that line: **422**, "Ledger account 5000 requires a cost centre." Untick the flag afterwards. |
| 13.10 | Provoke a client error (for example open the Inventory tab of a firm whose warehouse list you have made unreadable, or any red "This section failed to render" you meet), then as `master.ops` open Settings → **Diagnostics**, Source **Desktop**. | The report is listed with its type, message and an `N×` count; opening it shows **Request <request_id>**, the firm, the user, "Leading up to it" breadcrumbs and the stack trace. *(There is no "Help → Report a problem" control; the desktop reports crashes automatically, queued on disk until it can sign in.)* |

---

# Part 3 — Cross-cutting

## 14. Concurrency and two machines

Run these with two clients pointed at one server (or two windows of one client; the second `Start-Process` launch is a second client). Sign both in as `whole01.admin`. Every editor that sends a version shows the **same** sentence on a lost race, `Somebody else saved this <thing> while you were editing it. Your changes are still here and have not been sent. Copy anything you need, then close and reopen to see theirs.` -- and keeps the dialog open with the typing in it. Until 2026-09-13 six of them (price list, promotion, customer group, sales invoice, target, packaging level) showed the server's generic "The request conflicts with existing data. Please retry." instead. Server-side facts: driven on 2026-09-13, a second approval of one order and a second accrual of one payout period were both refused rather than answered with a 500, and an unchanged save left the version where it was.

| # | Case | Expected |
| --- | --- | --- |
| 14.1 | On **A** and **B**: Customers → Customers → double-click `WHOLE01C03` (Classic Departmental Stores). On A change the phone, **Save**. On B change the phone to something else, **Save**. | A saves ("Customer updated."). B is refused **inside the editor** with the sentence above naming `customer`, the dialog stays open, B's typed phone is still in the box. Cancel B; reopen: A's phone is there. |
| 14.2 | The same on a **sales order** (Sales → Sales Orders, any DRAFT, edit the Notes on both), a **product** (Masters → Products, edit the description) and a **price list** (Sales → Price Lists, double-click `STANDING`, edit the Description). | B refused each time with the sentence naming `sales order`, `product`, `price list`; typing kept, dialog open. |
| 14.3 | On A alone: double-click `WHOLE01C03`, change nothing, **Save**. Then double-click again, **Save** again. **(HTTP)** `GET /api/v1/customers/{id}` twice around it and compare the `ETag`. | Accepted both times. The `ETag` (and `version` in the body) is **the same before and after** -- an unchanged save must not move the version, so a client re-sending the same `If-Match` is still accepted. |
| 14.4 | On A and B: Sales → Sales Orders, select the same DRAFT order in both grids. **Approve** on A (confirm). Then **Approve** on B, whose grid still says DRAFT. | A: the grid reloads and the row reads APPROVED (there is no success toast on this page). B: a red toast, either "Only draft sales orders can be approved." (A finished first) or the conflict sentence (both in flight); never a silent no-op and never a 500. Refresh B: APPROVED once. |
| 14.5 | Both clients approve a document that would claim the **last** redemption of an offer. | Covered by `test_the_refusal_is_for_the_race_two_orders_priced_before_either_approved` in `backend/tests/unit/test_promotions.py`: the loser is **refused by name**, not silently repriced. To see it by hand: Promotions → `WELCOME` → Edit → **Max redemptions** = claimed + 1 → Save (a new revision), raise two orders for `WHOLE01C01` with coupon `WELCOME10`, approve both: the second is refused naming the offer. Put the limit back afterwards. |
| 14.6 | On A and B: Sales → Commission → **Payouts** → **Accrue period** From `2025-06-01` To `2025-06-30` on both, **Accrue** on A then on B. | A: "2 payout(s) accrued as drafts." B: "A commission payout already covers part of that period for this salesman (2025-06-01 to 2025-06-30)." -- a 409 by name, never a 500. The database holds the rule (`UQ_commission_payouts_period_active`), the service supplies the sentence. **Cancel** the four drafts afterwards so the period is free again. |

## 15. Permissions

Sign in as `whole01.sales1@agency.local` (Asha, `SALES_EXECUTIVE`: `CUSTOMER_VIEW`, `TERRITORY_VIEW`, `SALES_VIEW` and the three `SALES_*_CREATE` codes -- nothing else). The point is that the **server** refuses, not merely that the button is hidden: every refusal below was driven over HTTP with this user's token on 2026-09-13 and answered `403`. To drive them yourself, sign in with `POST /api/v1/auth/login` (see the appendix) and send `X-Firm-ID: 30c66274-60e9-4789-97d9-138a7a1fdc61`.

| # | Case | Expected |
| --- | --- | --- |
| 15.1 | Look for **Administration** in the sidebar, and Numbering Series under it. | **Administration is not offered at all** -- Numbering Series needs `SETTINGS_VIEW`, which Asha lacks, and so does every other tab of that module. **(HTTP)** `GET /api/v1/document-framework/numbering-rules` → `403`; `PUT .../numbering-rules/{id}` → `403`. |
| 15.2 | Customers → Customers → **Settings** (the credit-policy button on the toolbar). | The dialog **opens read-only**: the fields are disabled, **Save** is greyed and a notice reads "Changing the policy needs the manage customer settings permission." Somebody the policy warns may read the rule behind the warning. **(HTTP)** `PUT /api/v1/customers/credit-settings` → `403`. |
| 15.3 | Look for **Commission** under Sales. | **Not in the sidebar** (`COMMISSION_VIEW` missing). **(HTTP)** `POST /api/v1/commission/payouts/{id}/approve` and `.../pay` (any seeded payout id from the admin's Payouts view) → `403`. |
| 15.4 | Look for **Credit Notes** under Sales. | **Not offered** (`CREDIT_NOTE_VIEW` missing). **(HTTP)** `POST /api/v1/credit-notes/{id}/approve` → `403`. Drafting is bookkeeping; approving reverses a declared tax. |
| 15.5 | Look for **TCS** under Sales. | **Not offered** (`TCS_VIEW` missing). **(HTTP)** `PUT /api/v1/tcs/settings` → `403`. |
| 15.6 **(HTTP)** | Call all six endpoints above with Asha's token. | `403` every time, body `{"success": false, "error": {"code": "authorization_denied", ...}}`. A hidden button is not a control. |

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
designation exactly as it was. There is no seeded tier-1 account; 16.1 makes
one, because the tier cannot be tested without one.

| # | Case | Expected |
| --- | --- | --- |
| 16.1 **(SQL)** | `UPDATE platform.platform_admins SET scope = 'PLATFORM' WHERE user_id = (SELECT id FROM platform.users WHERE email = 'superadmin@agency.local');` then sign out and back in | Necessary setup. Put it back to `ALL_FIRMS` when you are done, or that account loses every firm. |
| 16.2 | As that user: Dashboard, Administration → Users, Roles & Permissions, Firms | All offered. Running the platform is their job. |
| 16.3 | As that user: Sales, Purchases, Finance, Inventory in the sidebar | **Not offered.** Their token carries 33 permission codes, none operational. |
| 16.4 **(HTTP)** | `GET /api/v1/customers` with their token and `X-Firm-ID` | `403`. Not by a rule of its own — they are simply not exempt from the membership check. |
| 16.5 | Sign in as `master.ops@agency.local` (tier 2) and switch between firms | Unchanged from before. Every firm, no membership needed. |
| 16.6 | Put 16.1 back to `ALL_FIRMS` | Housekeeping. Do not skip it. |

## 17. User templates — hiring by naming the job

Eleven platform templates are seeded. A firm may add its own; it may not edit
the platform's. Sign in as `whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 17.1 | Administration → User Templates | 11 rows. Each names its roles — Counter Sales shows `BILLING_EXECUTIVE, CASHIER`. Origin reads **Platform**. |
| 17.2 | Select a platform template → Edit / Retire | Both disabled. It is offered to every firm, so no one firm may change it. |
| 17.3 | New → code `night-counter`, name `Night Counter`, pick one or two roles → Save | Created. Origin reads **This firm**. |
| 17.4 | Edit it, change only the **name**, save | The roles are unchanged. An edit that says nothing about the bundle must not empty it. |
| 17.4a | Administration → Users → **New**, fill in the details, set **Job template** to Counter Sales, save | The user is created **and** holds `CASHIER` and `BILLING_EXECUTIVE`. One step, no second visit to the grid. |
| 17.4b | New again, leave **Job template** blank and pick two roles by hand | Those two roles, as before. The template field is optional. |
| 17.4c | New again, name a job **and** pick a different role | The job wins. The helper text under Roles says so; check it does. |
| 17.4d | Edit an existing user | **No** Job template field — it is create-only. Use Apply job template on the grid instead. |
| 17.5 | Administration → Users → select a user → **Apply job template** | A picker listing each job with the roles beside it, and a line saying the person's roles are **replaced** and editable afterwards. |
| 17.6 | Choose Counter Sales → Apply | Their roles become exactly `BILLING_EXECUTIVE` and `CASHIER`. |
| 17.6a | As `master.ops`, give a user two global roles and, under **Roles by firm**, two WHOLE01 roles. Then as `whole01.admin`, Apply job template → Counter Sales | The WHOLE01 tier becomes exactly `BILLING_EXECUTIVE` and `CASHIER`; the two **global** roles are still there. Open the user as `master.ops`: Roles in every firm unchanged, Roles in specific firms shows the two from the template. A template overwrites the tier its caller writes and never touches the other. |
| 17.6b | Same starting point, but apply the template as `master.ops` from the grid | The reverse: the **global** tier becomes the template's two roles, and the two WHOLE01 roles under Roles by firm are untouched. Four roles, a different four. The desktop never names a firm on this call for a platform administrator. |
| 17.7 | Edit that user's roles by hand afterwards | Works normally. A template is where you start, not where you stay — nothing on the user records which template they came from. |
| 17.8 | Retire `night-counter`, then re-open the user from 17.6 | The user is untouched. Retiring is a decision about future hires. |
| 17.9 | Sign in as `whole01.sales1` → Administration | No User Templates tab. It needs `ROLE_VIEW`. |
| 17.10 **(HTTP)** | `POST /api/v1/user-templates` with `role_ids` naming the `PLATFORM_ADMIN` role, using `whole01.admin`'s token | `422`, "A template cannot bundle platform or cross-firm roles." That role carries every permission code. |
| 17.11 | Administration → Roles & Permissions → **Roles** as `whole01.admin` | Lists the twelve firm roles and any of this firm's own. **Not** `PLATFORM_ADMIN`, `SUPPORT_ADMIN` or `LICENSE_ADMIN`. This list was platform-admin-only until #237. |

---

## 18. Hiring like an existing person

The other half of section 17, and the more common one: an administrator
usually has a person in mind rather than a written-down job. Sign in as
`whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 18.1 | Administration → Users → pick somebody with roles → **Hire like this person** | A dialog naming them, saying the new user gets the same roles and firms and **none** of their personal details, password or history. |
| 18.2 | Press Create with the form empty | Refused, field by field. Nothing is created. |
| 18.3 | Type a name, an email with no `@`, a password → Create | "That is not an email." |
| 18.4 | Fill it in properly → Create | Created. The message names both people. |
| 18.5 | Open the new user | Same roles as the source. **Blank** mobile, employee code, department, joining date. |
| 18.6 | Sign in as the new user with the password you typed | Forced to change it. A password somebody else chose is not a password. |
| 18.7 | Change the new user's roles, then re-open the source | The source is unchanged. A clone is a starting point, not a link. |
| 18.8 | As `whole01.sales1`, open the users grid | No **Hire like this person**. It needs `ROLE_ASSIGN`, `ROLE_VIEW` and `USER_CREATE` — copying access is granting access. |

## 19. Setting a firm up from the platform side

Sign in as `superadmin@agency.local` (tier 2). This is the flow a platform
operator uses when a new firm is created.

| # | Case | Expected |
| --- | --- | --- |
| 19.1 | Administration → User Templates → New | An **Offered to** picker appears, which a firm administrator does not see. |
| 19.2 | Create a template with **Offered to** set to one firm | Created. Origin shows that firm. |
| 19.3 | Sign in as `whole01.admin` and open User Templates | The template from 19.2 is **not** listed, unless you chose WHOLE01. Before this, a template written for one firm was offered to every firm. |
| 19.4 | As the platform user, create one with **Offered to** left blank | Offered to every firm — which is right for a job every firm has, and is why the field says so. |
| 19.5 **(HTTP)** | As `whole01.admin`, `POST /api/v1/user-templates` with `firm_id` naming a different firm | `422`, "You can only act within your own firm." Refused, not silently redirected. |

---

## 20. A firm administrator creating users

The button that was not there. `FIRM_ADMIN` holds `USER_CREATE`, `USER_UPDATE`,
`ROLE_ASSIGN` and `ROLE_VIEW` — everything running a firm's people needs — and
the New-user gate also demanded `FIRM_VIEW`, which is a platform code the role
can never be given. Sign in as `whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 20.1 | Administration → Users | **New** and **Edit** are offered. Before this they were not, for any firm administrator. |
| 20.2 | New → look at **Firms** before typing anything | **WHOLE01 is already ticked.** The form used to open empty and then silently remove the membership the save had just created, leaving a user in no firm and invisible in the grid. |
| 20.2a | Fill in name, email, password → Save | Created and in WHOLE01, visible in the grid straight away. |
| 20.2b | New again, **clear** the Firms box, save | Created in **no** firm — allowed, and deliberate. They will not appear in the grid; find them with **Add existing user**. |
| 20.2c | As `superadmin`, open New | Firms is **empty**, not prefilled. A platform administrator has no own firm, and quietly using whichever one their switcher shows would be a surprise. |
| 20.3 | Open the form again and look at **Firms** | Lists the firms *you* belong to. It read `/api/v1/firms`, which is platform-only, so it used to come back empty with a failed load. |
| 20.4 | Sign in as `superadmin@agency.local` and open the same form | **Firms** lists every firm. Same field, different source. |
| 20.5 **(HTTP)** | As `whole01.admin`, `PUT /api/v1/users/{id}/firms` naming ELEC01 | `422`, "You can only assign firms you administer." Refused by name, not silently dropped. |
| 20.6 **(HTTP)** | As `superadmin`, put a user in **both** WHOLE01 and ELEC01. Then as `whole01.admin`, save that user with WHOLE01 only. Re-read as `superadmin` | **Both** memberships survive. The endpoint replaces for a platform caller and merges for a scoped one — otherwise a firm administrator correcting their own firm would remove the person from every other firm on the platform. |
| 20.7 | As `whole01.admin`, set a user's primary firm to something else | The primary does not move. It is one flag across every firm somebody belongs to, so a caller who can see only some of them must not set it. |
| 20.8 | Follow `docs/USER_ADMINISTRATION_GUIDE.md` §3 end to end | Create a user, apply **Counter Sales**, sign in as them: Sales and Inventory offered, Finance and Administration not. |

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

| # | Case | Expected |
| --- | --- | --- |
| 21.1 | Sales → Credit Notes | Offered, and opens. Draft, approve and the approve gate are all reachable. |
| 21.2 | Sales → Proforma | Offered, and opens. |
| 21.3 | Sales → E-Invoice | Offered, and opens. Check the mode badge reads SANDBOX. |
| 21.4 | Masters → Loyalty | Offered, and opens. Settings included — `LOYALTY_MANAGE_SETTINGS` is granted. |
| 21.5 | Sales → TCS | Offered, and opens, settings included. |
| 21.6 | As `whole01.sales1`, try all five | Still refused, all five. The grant widened one role, not everybody. |
| 21.7 | Masters → Firms | **Still not offered**, deliberately. Deciding which firms exist is not a firm's own business. |
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
| 22.3 | Look for Chart of Accounts, Journal Entries, Ledgers, Trial Balance, P&L, Balance Sheet, Refunds | **None of them.** Widening the module without gating its tabs would have handed a cashier the ledger. |
| 22.4 | Record a receipt | Works. `RECEIPT_CREATE`. |
| 22.5 | Sign in as `whole01.accounts` (or any `ACCOUNTANT`) → Finance | **All nine** tabs, exactly as before. Nobody lost one. |
| 22.6 | As `whole01.admin` → Finance | All nine. |

---

## 23. The audit trail

Two things here, and the first is a regression that shipped on 2026-09-05 and
was found on 2026-09-06: moving the platform designation into its own claim
left two checks looking for it in the old place, so **no platform administrator
could read any audit trail at all**.

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
| 25.1 | Administration → Roles & Permissions → **Roles** | The twelve firm roles. **Not** `PLATFORM_ADMIN`, `SUPPORT_ADMIN` or `LICENSE_ADMIN`. |
| 25.2 | New → code `night-desk`, name `Night Desk` → Save | Created, and it belongs to WHOLE01. |
| 25.3 | Open it → **Permissions** | **167** to choose from. Tick `SALES_VIEW`, `RECEIPT_CREATE`, `CUSTOMER_VIEW`. |
| 25.4 | Look for `FIRM_CREATE`, `PLATFORM_SETTINGS`, `VOID_INVOICE`, `AUDIT_LOG_VIEW` | **Not in the list at all.** The 22 platform codes are not offered, so there is nothing to get wrong. |
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

| Area | State |
| --- | --- |
| Emailing a document | Not built. The PDF exists; there is no SMTP client or mail configuration. Deferred by the owner. |
| Licensing | Not built. A permission and a role exist and are unused. Deferred by the owner. |
| Serial numbers | Built, but no demo firm serialises — screens work, no seeded data. |
| Packaging levels | Built, no seeded rows. |
| Cost and profit centres | Present in finance, used by nothing. |
| Shortened sales chains | A firm can be configured to type fewer than four documents; no demo firm is. |
| Credit **blocking** | Built. Every demo firm is in **warn** mode, so blocking is not exercised. |
| `IMEI`, `PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`, `SERVICE_CONTRACTS`, `PROJECT_MANAGEMENT` | Declared as roadmap features and refused if switched on. |

---

## 26. Platform mode, and the switcher that was empty

Sign in as **`platform-admin@agency.local`**. This account is `ALL_FIRMS` and
holds **no** firm memberships, which is what made the defect visible: its token
carries all 189 permission codes, so the sidebar offered Sales, Purchases and
Inventory, while `/me/firms` answered an empty list so no firm could be
selected and every one of those screens refused its first request.

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
| 27.23j | Open this firm → Finance → **Control Accounts** | 24 rows, one per posting purpose, each showing the account it posts to and which classifications it may post to. On a fresh firm every row offers **Change**. As `whole01.admin` on WHOLE01: Accounts receivable, Sales revenue, Output tax, Inventory and the rest that trading has touched show a lock and "N posted" with no picker -- hover for why; only the purposes nothing has posted to (Rounding, TCS payable, the loyalty pair) offer Change. Change one: the picker lists only accounts of the allowed classification; Save is dead until a different account is chosen; the notice reads "Rounding posts to …". **(HTTP)** `PUT /api/v1/finance/control-accounts/ACCOUNTS_RECEIVABLE` on WHOLE01 with any other asset account: **422**, "Accounts receivable has N posted lines on 1100 Trade Receivables. Re-pointing it would leave two accounts each holding part of one story…". `whole01.sales1` holds `VIEWER`, which carries `ACCOUNT_VIEW`, so the tab shows for them **read-only** -- no Change, no Map; a role without `ACCOUNT_VIEW` has no Finance tab at all. |
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

FIRM=<the WHOLE01 id from GET /api/v1/firms>

curl -s -w "\nHTTP %{http_code}\n" -X POST \
  http://localhost:8000/api/v1/document-framework/numbering-rules \
  -H "Authorization: Bearer $TOKEN" -H "X-Firm-ID: $FIRM" \
  -H "Content-Type: application/json" -d '{...}'
```

Every response carries a `requestId`. Quote it when reporting anything — it
joins the screen to the server log.
