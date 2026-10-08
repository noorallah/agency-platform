# Firms, set-up and configuration

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > All Sell screens > Documents > Proforma` is a screen that is not
daily work, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-05 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Firms — creating one and finishing it

A firm is created in one place and finished in several: storage, business
profile, books, tax, first branch and people are each a separate act.
Settings > Platform > Firms > **Firms** creates it, and **Set up** on that grid shows each
step and does four of them.

| Preparation | Builds |
| --- | --- |
| `unprovisioned-firm` | a platform admin, and a `SCHEMA` firm whose storage is **not** built |
| `unfinished-firm` | a platform admin, and a `SCHEMA` firm that is provisioned and **nothing else** — no profile, books, tax, branch or members |
| `ready-firm` | a platform admin, a **finished** `SCHEMA` firm (Wholesale), its firm admin, a `VIEWER`, two product categories, a customer, and a 500.00 cash receipt that has posted |

### TC-FIRM-001 — Firms is a Platform screen that needs no firm

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps**
  1. Sign in as the prepared **Platform admin**. The header reads **Platform**.
  2. Open Settings > Platform > Firms > **Firms**.
  3. Select QA01 and open it with **Open this firm**; look through the **Masters** menu.
- **Expect**
  - Step 2: the list of every firm. This is the one firm screen that works with no firm selected (the Platform part of Settings).
  - Step 3: **no Firms** under Masters. It moved to the platform screens on 2026-09-06 — as a Masters tab it needed a firm, so creating a firm was reachable only from inside another one.
### TC-FIRM-002 — Creating a shared firm, and reaching it at once

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps**
  1. Sign in as the prepared **Platform admin**. Settings > Platform > Firms > **Firms** → **New**.
  2. Type only a name, e.g. `Created qa`, and save.
  3. Fill the rest: code **`qa-s` in lower case** (e.g. `t0916abcd-s`), country `IN`, currency `INR`, financial year start `2026-04-01`, deployment mode **SHARED**. Save.
  4. Select the new row.
  5. Press **Open this firm**, then open the firm switcher.
- **Expect**
  - Step 2: refused. The five required fields are `name`, `code`, `country` (2 letters), `currency_code` (3 letters) and `financial_year_start`; everything else is optional.
  - Step 3: saves. The code is stored **upper case** — `T0916ABCD-S` — as are country and currency. The follow-up message names the next step.
  - Step 4: **Open this firm** enabled — a shared firm is ready at once. **Provision storage** hidden; there is nothing to build.
  - Step 5: "Working in …" names the new firm, the header shows it, the menu bar grows. **The firm is in the switcher.** That is the half that was broken: the switcher was read once at sign-in, so a firm created minutes earlier was refused as "not assigned to this user".
### TC-FIRM-003 — What firm creation refuses

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps (HTTP)** — sign in as the prepared platform admin and send `POST /api/v1/firms`, each time with `name`, `country: "IN"`, `currency_code: "INR"`, `financial_year_start: "2026-04-01"` and `deployment_mode: "SHARED"`, varying one thing:
  1. `code: "QA01"` (a firm that already exists — on an installed copy, use one of your own)
  2. `code: "BAD CODE"`
  3. `code: "QA-Z"`, `country: "IND"`
  4. `code: "QA-Y"`, `deployment_mode: "DATABASE"`, `database_name: "fx_nope"`, `connection_profile: "NOPE"`
- **Expect**
  1. **409**, "Firm code, GST number, or PAN number already exists." Unique among *live* firms only — a deleted firm releases its code.
  2. **422**, the code "should match pattern `^[A-Z0-9_-]+$`" — no spaces, no dots.
  3. **422**, country "should have at most 2 characters".
  4. **422**, "Connection profile 'NOPE' is not configured. Configured profiles: <this installation's own list, from `config/.env`>." Refused at creation, not at first use — otherwise the firm would provision nothing and fail far from the request that caused it. (This machine's own list is `REMOTE_A`; an installed copy sees whichever profiles its own `.env` names, which may be none.)
### TC-FIRM-004 — A dedicated firm cannot be opened until it is provisioned

- **Preconditions:** The platform administrator, and a new firm created with deployment mode **SCHEMA** whose storage has not been provisioned.
- **Steps**
  1. Sign in as the prepared **Platform admin**. Settings > Platform > Firms > **Firms**; select the prepared **New firm**.
  2. Press **Provision storage**. Wait — it runs the migrations. Refresh and select the row again.
  3. Press **Provision storage** again.
- **Expect**
  - Step 1: **Open this firm disabled** — its schema has no tables, so switching in would answer errors on every screen. **Provision storage** enabled.
  - Step 2: **Open this firm** now enabled; the row carries a provisioned date.
  - Step 3: succeeds and reports it was already provisioned. Every step is create-if-missing, so this is also the repair action after a server was unreachable.
### TC-FIRM-005 — A firm's storage routing is fixed at creation

- **Preconditions:** The platform administrator, and a new firm created with deployment mode **SCHEMA** whose storage has not been provisioned.
- **Steps (HTTP)** — as the prepared platform admin, `GET /api/v1/firms/{id}` for the prepared firm, then `PUT` it back with `name`, `code`, `country`, `currency_code`, `financial_year_start` as read and `deployment_mode: "SHARED"`.
- **Expect:** **422**, "Firm storage routing cannot be changed after creation (currently SCHEMA/<the schema the server chose for this firm>). Migrate the firm's data first." — the schema name in the message is whatever the server picked at creation, not a fixed string. Nothing moves a firm's rows between stores.
### TC-FIRM-006 — The setup panel on a firm whose storage is not built

- **Preconditions:** The platform administrator, and a new firm created with deployment mode **SCHEMA** whose storage has not been provisioned.
- **Steps**
  1. Sign in as the prepared **Platform admin**. Settings > Platform > Firms > Firms → select the prepared firm → **Set up**.
  2. **(HTTP)** Before pressing anything, `POST /api/v1/firms/{id}/open-books`, `.../apply-tax-template` and `.../create-default-branch`.
  3. On the panel, press **Provision storage**.
- **Expect**
  - Step 1: **Cannot post documents yet.** Storage is **missing** with a **Provision storage** button. Business profile, Books, Tax, Geography and Branches read "Cannot be checked until the firm's storage is provisioned." with no button and no hint. People reads "Nobody belongs to this firm yet. Only a platform administrator can open it."
  - Step 2: three **422**s — "Provision the firm's storage before opening its books.", "… before applying a tax template.", "… before creating its first branch."
  - Step 3: the list re-reads; Storage is done and Books now offers **Open the books**.
### TC-FIRM-007 — The setup panel says what an unfinished firm still needs

- **Preconditions:** The platform administrator, and a new **SCHEMA** firm that has been provisioned and nothing else: no profile, books, tax, branch or members.
- **Steps**
  1. Sign in as the prepared **Platform admin**. Settings > Platform > Firms > Firms → select the prepared firm → **Set up**.
  2. **(HTTP)** `GET /api/v1/firms/{id}/readiness`.
- **Expect**
  - Step 1: titled `Set up QA-F`; **Cannot post documents yet.** Seven rows — Storage and Books **Required**, the rest **Recommended**:

    | Row | Reads | Offers |
    | --- | --- | --- |
    | Storage | SCHEMA storage provisioned. | done |
    | Business profile | None assigned. The firm runs as GENERIC … | a profile dropdown and **Assign** |
    | Books | No chart of accounts. Nothing can post until the books are opened. | **Open the books** |
    | Tax | No tax profiles or rules. … | **Apply GST template** |
    | Geography | No country in the store. … | a hint: Settings > Set up > Locations > Places; the GST template adds the country |
    | Branches and warehouses | … 0 branches, 0 warehouses so far. | **Create head office and main warehouse** |
    | People | Nobody belongs to this firm yet. … | a hint: Settings > Platform > People > Users → Add existing user, or Settings > Platform > People > User-Firm Assignments |
  - Step 2: **200**, `can_post: false`, `ready: false`, the same seven `steps` with `status` DONE / MISSING and `required`.
  - Step 3: the same seven rows from the same implementation, and that it **cannot post** because the books are not open.
### TC-FIRM-008 — Opening the books, once

- **Preconditions:** The platform administrator, and a new **SCHEMA** firm that has been provisioned and nothing else: no profile, books, tax, branch or members.
- **Steps**
  1. Sign in as the prepared **Platform admin** → Firms → the prepared firm → **Set up** → **Open the books**.
  2. Press **Refresh**. Then **(HTTP)** `POST /api/v1/firms/{id}/open-books` again.
  3. Settings > Platform > System > **Audit Logs**, on Platform.
- **Expect**
  - Step 1: the notice names the year: "Books opened for the year starting 2026-04-01" — the year *today* falls in, aligned to the firm's year start. Books re-reads as done: "24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped, and a period open today." The button is gone, and the verdict reads **Can post documents. The recommended steps are still open.**
  - Step 2: nothing changes. The response: "The books were already open; nothing was created.", `already_open: true`, every count 0.
  - Step 3: **one** `firm.books_opened` row for this firm, with the counts (5 groups, 24 accounts, 12 periods, 2 types, 24 mappings) — not two. An audit row saying books were opened with every count at zero would be a lie, so the second call writes none.
### TC-FIRM-009 — The GST template, once

- **Preconditions:** The platform administrator, and a new **SCHEMA** firm that has been provisioned and nothing else: no profile, books, tax, branch or members.
- **Steps**
  1. As the prepared **Platform admin**, open **Set up** on the prepared firm → Tax row → **Apply GST template**.
  2. **(HTTP)** `POST /api/v1/firms/{id}/apply-tax-template` again; then once more with `{"template": "US"}`.
  3. Open this firm → Settings > Tax > **Tax Configuration**.
- **Expect**
  - Step 1: "GST set up: 10 tax profiles and 13 rules." Tax re-reads as "1 tax system, 10 profiles, 13 rules", and **Geography flips to done** ("1 country in the store") — the template adds India to a store that has no country.
  - Step 2: "The firm already has a tax system; nothing was created.", `already_configured: true`. With `US`: **422**, only `IN_GST` exists. One `firm.tax_template_applied` audit row, not two.
  - Step 3: the system, four components and eight profiles, editable.
### TC-FIRM-010 — Assigning the business profile from the panel

- **Preconditions:** The platform administrator, and a new **SCHEMA** firm that has been provisioned and nothing else: no profile, books, tax, branch or members.
- **Steps**
  1. As the prepared **Platform admin**, stay on **Platform** (no firm open) and open **Set up** on the prepared firm.
  2. Business profile row: look at **Assign** before choosing; choose **Wholesale**; press **Assign**.
- **Expect**
  - Assign is dead until a profile is chosen. The dropdown lists the **firm's own** catalogue (`GET /api/v1/business-framework/firms/{id}/profiles`), which is why this works with no firm open.
  - "Business profile set to Wholesale." The row re-reads "Assigned: WHOLESALE." and the picker is gone.
### TC-FIRM-011 — Head office and main warehouse, once

- **Preconditions:** The platform administrator, and a new **SCHEMA** firm that has been provisioned and nothing else: no profile, books, tax, branch or members.
- **Steps**
  1. As the prepared **Platform admin**, **Set up** on the prepared firm → Branches and warehouses → **Create head office and main warehouse**.
  2. **(HTTP)** `POST /api/v1/firms/{id}/create-default-branch` again.
  3. Open this firm → Masters > **Branches**, then **Warehouses**.
- **Expect**
  - Step 1: "Created branch HO and warehouse MAIN. Rename them on their own screens." The row reads "1 branch, 1 warehouse". The verdict stays **Cannot post documents yet.** — the books are still shut in this run; that is TC-FIRM-008's step, not this one's.
  - Step 2: "The firm already has a branch and a warehouse; nothing was created.", `already_present: true`.
  - Step 3: `HO` Head Office, default; `MAIN` under it.
### TC-FIRM-012 — Profile Assignment, the other way to set a profile

- **Preconditions:** The platform administrator, and a new **SCHEMA** firm that has been provisioned and nothing else: no profile, books, tax, branch or members.
- **Steps**
  1. As the prepared **Platform admin**, switch into **QA01** (the screen needs *some* firm open).
  2. Settings > Business profile > **Profile Assignment**.
  3. Select the prepared firm, open it, choose **Retail**, save. Re-open the row.
- **Expect**
  - Step 2: a grid of **every** firm, not only QA01 — the screen names the firm in the URL rather than reading `X-Firm-ID`.
  - Step 3: saved against the prepared firm, not QA01; re-opening shows Retail. The **Business profile** dropdown is populated — empty, or "The database is temporarily unavailable", means no firm is open.
### TC-FIRM-013 — Masters need no books; posting does

- **Preconditions:** The platform administrator, and a new **SCHEMA** firm that has been provisioned and nothing else: no profile, books, tax, branch or members.
- **Steps**
  1. As the prepared **Platform admin**, open the prepared firm. Masters > **Customers** → New: code `C1`, name `Before books`, type Business, currency INR. Save.
  2. **(HTTP)** `POST /api/v1/receipts` with `X-Firm-ID` of the prepared firm: `{"party_id": "<C1's id>", "settlement_date": "<today>", "amount": "100.00", "method": "CASH"}`.
- **Expect**
  - Step 1: saves. Masters do not need the books.
  - Step 2: **422**, "No ledger account is configured for CASH. Set the firm's control accounts before posting this document." The posting service refuses rather than guesses — the design working, not a broken firm.
### TC-FIRM-014 — What "finished" looks like

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps:** sign in as the prepared **Platform admin** → Settings > Platform > Firms > Firms → the prepared firm → **Set up**.
- **Expect:** **Finished. Every step is done.** — "24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped, and a period open today"; Assigned: WHOLESALE; 1 tax system, 8 profiles, 9 rules; 1 country; 1 branch, 1 warehouse; **2 members**. No buttons. The contrast with TC-FIRM-007 is the point.
### TC-FIRM-015 — Control accounts: held once something has posted

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. Sign in as the prepared **Firm admin** → Settings > Set up > Account structure > **Control Accounts**.
  2. Hover the lock on **Accounts receivable**.
  3. On **Rounding**, press **Change**. Open the account picker; look at **Save** before choosing. Choose `4000 Sales`, Save. Then change it back to `4900 Rounding`.
  4. **(HTTP)** `PUT /api/v1/finance/control-accounts/ACCOUNTS_RECEIVABLE` with `{"ledger_account_id": "<any other ASSET account>"}`.
  5. Sign in as the prepared **Viewer** → Settings > Set up > Account structure > Control Accounts.
- **Expect**
  - Step 1: 24 rows, one per posting purpose, each with the account it posts to and the classifications it may use. **Accounts receivable** and **Cash** show a lock and **1 posted** with no Change — the prepared receipt posted one line to each. Every other row offers **Change**.
  - Step 2: "1 posted line on this account. Re-pointing it would leave two accounts each holding part of one story; post a transfer entry and map a new account from the next period instead."
  - Step 3: the picker lists only **INCOME and EXPENSE** accounts — what Rounding may post to. Save is dead until a *different* account is chosen. The notice reads "Rounding posts to 4000 Sales.", then "Rounding posts to 4900 Rounding."
  - Step 4: **422**, "Accounts receivable has 1 posted line on 1100 Trade Receivables. Re-pointing it would leave two accounts each holding part of one story; post a transfer entry and map the new account from the next period instead."
  - Step 5: the tab is there and read-only — **no Change, no Map**. The server agrees: a `PUT` as the viewer is **403**.
### TC-FIRM-016 — A firm administrator cannot reach firms at all

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin** → the gear → look under **Platform**.
  2. **(HTTP)** As that user: `GET /api/v1/firms`, `POST /api/v1/firms` (any body), `GET /api/v1/firms/{QA01's id}/readiness`, `POST /api/v1/firms/{QA01's id}/open-books`.
- **Expect**
  - Step 1: **no Firms** and **no Business Profiles** card under Platform, so no setup panel. `FIRM_VIEW` and `PLATFORM_VIEW` are platform codes no firm role can hold.
  - Step 2: **403** for all four. No permission code can grant them. What they would show, a firm administrator reads as their own Accounts > All Accounts screens > Books > Chart of Accounts and Financial Years.
### TC-FIRM-017 — A firm whose people have been deleted cannot be deleted either

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps (HTTP)** — as the prepared **Platform admin**
  1. `DELETE /api/v1/users/{the firm admin's id}`, and the same for the `VIEWER`. They are the firm's only two people.
  2. `GET /api/v1/firm-members` and `GET /api/v1/users?page=1&page_size=25`, both with `X-Firm-ID: <the preparation firm's id>`.
  3. `DELETE /api/v1/firms/{the preparation firm's id}`.
  4. Take a second `ready-firm` preparation and, without deleting anybody, `DELETE` that firm.
- **Expect**
  - Step 1: **204** each.
  - Step 2: **nobody**. The firm's own directory is empty and its Users grid has no rows, so every screen agrees the firm has no people.
  - Step 3: **204** — the firm deletes. Until 2026-09-16 this answered **422**, "Assigned firms cannot be deleted.", naming a condition no screen could show; see defect **D-27-5**. The memberships themselves are untouched, because they are what a restore reads to put those people back.
  - Step 4: **422**, "Assigned firms cannot be deleted." A firm with people who still exist is still refused — that half of the guard is the point of it.

## Firm isolation — one firm never sees another's data

### TC-ISO-001 — Two firms in one schema do not see each other's customers

- **Preconditions:** The platform administrator, and one customer in each of two SHARED firms, QASH1 and QASH2. (`QA-SHONE` in QASH1 and `QA-SHTWO` in QASH2, **both in `firm_shared`**.)
- **Steps**
  1. Sign in as the prepared **Platform admin** → switch into **QASH1** → Masters > Customers → search `QA`.
  2. Switch to **QASH2**; search again. Then **MEDI01** and **FOOD01**, which share the same schema; then **QA01**.
- **Expect:** QASH1 shows only `-SHONE`; QASH2 only `-SHTWO`; MEDI01, FOOD01 and QA01 show **neither**. **If a QASH1 customer appears in QASH2, stop and report it** — the two share one schema, so nothing but the firm filter keeps them apart.
### TC-ISO-002 — Two firms in their own schemas, and a name that cannot cross

- **Preconditions:** The platform administrator, and one customer in each of two firms, QA01 and QA02. (`QA-ONE` (Isolation One) in QA01, `QA-TWO` (Isolation Two) in QA02.)
- **Steps**
  1. As the prepared **Platform admin** in **QA01**, Masters > Customers → search `Isolation One qa`.
  2. Switch to **QA02**; search the same name, then `QA`.
- **Expect**
  - Step 1: `QA-ONE`.
  - Step 2: the name finds **nothing**; `QA` finds only `QA-TWO`. A name from another firm's store cannot appear.
  - *Document numbers are the weaker check the plan's 3.3 started from: they **restart per firm**, so QA02 may have an invoice with the same number as one of QA01's — it must carry QA02's own customer. The name is the real check.*
### TC-ISO-003 — Reports read the firm you are in

- **Preconditions:** A firm administrator of QA01, and one sale taken to an approved invoice: order, dispatched delivery note, approved invoice. (a sale of yours in QA01.)
- **Steps**
  1. Sign in as the prepared **Firm admin** (QA01) → Reports > Operational → **Sales order register**; find the prepared order (customer **Fixture Buyer qa**).
  2. Sign in as any platform administrator (e.g. `platform-admin` preparation) → switch into **QA02** → the same report.
- **Expect:** step 1 lists the prepared order; step 2 does **not** — QA02's register holds only QA02's orders, and reads "Nothing to report" if it has none.
### TC-ISO-004 — Naming a firm you do not belong to is refused, not answered empty

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin** and look for any way to QA02: the firm switcher, Ctrl+K, a report.
  2. **(HTTP)** As the firm admin, `GET /api/v1/customers` with `X-Firm-ID` of **QA02**.
- **Expect**
  - Step 1: none. The switcher lists QA01 alone.
  - Step 2: **403**, "You do not have permission to perform this action." — **not** an empty list, which would look like "no data" and hide the hole.
---

## Configuration — numbering, profiles, tax and units

Most of these screens are cards on the **Settings** page (the gear at the right
of the menu bar), under **Settings**, **Set up** and **Platform**. **Ctrl+K**
opens any screen by name.

### TC-CONF-001 — Numbering series: who may change one, and a counter nobody types

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template). (and `sales-executive`)
- **Steps**
  1. Sign in as the `firm-admin` preparation's **Firm admin** → Settings > Firm > **Numbering Series**.
  2. Select **SALES_INVOICE_DEFAULT** → Edit → scroll below the **Active** switch. Change the Name, save, reopen.
  3. Press **New series** and look at the same spot.
  4. Sign in as the `sales-executive` preparation's **Seller** and open the same screen.
- **Expect**
  - Step 1: **New series**, **Edit** and **Retire** offered.
  - Step 2: a locked row with a padlock, `Next number: N`, and the reason ("The counter belongs to the server, which advances it under a lock..."); no box to type in. After the rename the next number is unchanged.
  - Step 3: a **Start numbering at** box instead, helper "Usually 1...".
  - Step 4: the list loads, and **none** of the three buttons is offered.
### TC-CONF-002 — A yearly restart without the year is refused

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. As the prepared **Firm admin**, Numbering Series → **New series**: document type Sales Invoice, code `QA-SI`, name `Check qa`, **Restart numbering each financial year** on, **Include the financial year** off → Save.
  2. Switch Include the financial year on → Save.
- **Expect**
  - Step 1: a warning under the switches says the first document of April would repeat one from March; the save is refused with the server's sentence — "This rule restarts its numbering every financial year, so the number has to include the year -- without it the first document of each new year repeats a number the firm has already issued. …" — and nothing is created.
  - Step 2: created.
### TC-CONF-003 — Previewing the next number issues nothing

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, select **SALES_INVOICE_DEFAULT** → **Preview next**, twice.
- **Expect:** a number matching the pattern — `SI-2026-2027-00000N` — equal to the locked `Next number` and the **same both times**. A preview issues nothing.
### TC-CONF-004 — A roadmap feature cannot be switched on

- **Preconditions:** A finished firm, a vendor, and a product with its own PACK to KG conversion rule. (a store of the run's own, so a profile edit here reaches no other firm.)
- **Steps**
  1. Sign in as the prepared **Platform admin**, switch into the prepared firm → Settings > Platform > Firms > Business Profiles → **Profiles** → edit **WHOLESALE** → in **Enabled features** tick **IMEI** → Save.
  2. Untick IMEI; tick **BARCODE** (if it is not already) → Save.
- **Expect**
  - Step 1: refused in the summary at the top of the form, which scrolls into view: "These features are not implemented yet and cannot be enabled: IMEI." The dialog stays open and **nothing** is written — not the features, and not the profile's other fields (until 2026-09-12 they were — BACKLOG §31.6). The six roadmap features: `IMEI`, `KITCHEN_MANAGEMENT`, `PRESCRIPTION_REQUIRED`, `PROJECT_MANAGEMENT`, `RECIPE_MANAGEMENT`, `SERVICE_CONTRACTS`.
  - Step 2: saves. The **Feature Flags** leaf beside it is the catalogue, not where a profile's features are chosen.
### TC-CONF-005 — The tax simulator: CGST and SGST within a state, IGST across

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, Settings > Tax > **Rule Simulator**. Transaction type `SALES_INVOICE`, tax profile `GST_18_LOCAL`, invoice value `1000` → Run Simulation. Then transaction type `SALES_INTERSTATE` → Run.
- **Expect:** local — no rule matched, CGST 9% = 90 and SGST 9% = 90, total **180**. Interstate — matched rule **`INTERSTATE_GST_18`**, one component IGST 18% = 180, total **180**, and the trace shows the rule matched. (QA01's rules come from the GST template, the same nine the demo firms carry.)
### TC-CONF-006 — A product's own conversion outranks the firm-wide one

- **Preconditions:** A finished firm, a vendor, and a product with its own PACK to KG conversion rule. (`QA-DET` is bought in PACK and stocked in KG, with its own PACK→KG rule at factor **1**.)
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm (or its **Firm admin**), Settings > Set up > Item lists > **Conversion Rules** → **Add**: Product *Firm-wide*, From `PACK`, To `KG`, Factor `2` → Save.
  2. Buy > Purchase Orders → New: vendor `QA-V`, product `QA-DET`, quantity **10**, Purchase UOM `PACK — Pack` → Save; open the order.
- **Expect**
  - Step 1: the firm-wide rule appears beside the product's own.
  - Step 2: the line shows **Base Qty 10**, not 20 — the product's factor of 1 outranks the firm-wide 2. (Ranked explicitly rather than by NULL sort, which PostgreSQL and SQLite order oppositely.)
### TC-CONF-007 — GST documents: the firm's own rules for dispatch, e-invoicing and input credit

*Added 2026-10-02 from the code; not yet driven. Drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, Settings > Tax > **GST Documents**. Read the banner. Choose **Block** for *Dispatch of a sale before its invoice*, set *E-invoicing applies from* to a date, and set *30-day reporting limit applies from* to a day **before** it → Save. Correct that, set *Claim input credit* to *Only bills matched to GSTR-2B*, set the matching tolerance → Save, close and reopen. Then open it as a user who holds Tax view but not the manage-tax-settings permission.
- **Expect:** a firm that has never saved sees that it is using the default shown, and saving makes it the firm's own. The 30-day date earlier than the e-invoicing date (or with none) is refused with the server's message and the dialog stays open with what was typed. After the second save the values come back on reopening. The read-only user sees the values, a disabled Save and "Changing the GST document settings needs the manage tax settings permission."
### TC-CONF-008 — A feature or module made at runtime reaches every store

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Also needs:** at least two provisioned firms in different stores (QA01 and QA02).
- **Steps:** as the prepared **Platform admin**: Settings > Business profile > **Feature Management** → New feature `QA_RUNTIME_FEAT`, then edit its name; **Module Configuration** → New module and edit it. Read the answer after each save. Delete the feature and the module.
- **Expect:** each create, update and delete answers with the list of **stores** it reached and a warning for any it could not; the new feature and module exist in every firm's store, so a profile can use them. Deleting returns the per-store list rather than an empty answer. The pages are the generic resource pages; nothing new is on screen.
### TC-CONF-009 — "Today" is the firm's own day, at any hour

*Added 2026-10-06 after D-CFG-25 (#1219, #1223, #1226). **Server side driven** over HTTP between 02:30 and 02:50 India time on 2026-10-06; results in `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** to be run **between midnight and 05:30 India time**, the hours in which the server's own (UTC) date is still yesterday's; at any other hour every step passes without showing anything. A supplier with a completed purchase return whose **Outcome** is *Refund*, dated today (TC-BUY-009 shows how); an approved, unpaid sales invoice to the prepared customer; a goods receipt or an opening stock entry of a product dated today.
- **Steps:** as the prepared **Firm admin**: (1) Buy > Payments → **Supplier refunds** → the supplier → on the return, **Record refund** dated **today** → Save. (2) Masters > Customers → the prepared customer → Opening bills → **Add opening bill** dated **today** → Save; then one dated tomorrow. (3) Sell > All Sell screens > Money > Collection Sheet → the bill → **Record promise**, *Promised on* **today** → Save promise. (4) Reports > Operational → **Stock valuation**, with no date and then as on today. (5) Record a customer receipt without typing a date, and open it. (6) Settings > Set up > Pricing > **Promotions** → New, an offer whose first day is **today**; raise an order line it applies to.
- **Expect:** (1) the refund is accepted; one dated tomorrow is refused, "A refund cannot be received on a future date." (2) the opening bill dated today is accepted and the one dated tomorrow refused, "An opening bill is one raised before the books here start, so its date cannot be after <today>." (3) the promise is accepted and reads **Due today**. (4) the valuation includes the stock that arrived today and its total equals account 1200 Inventory on the trial balance. (5) a document the server dates is dated today, the firm's day, not yesterday. (6) an offer that starts today is in force today, and one whose last day was yesterday is not; the same holds for a price list, a rate contract and a supplier scheme (this step, #1226, is unit-tested and was not driven on a running server). Nothing asks the tester to date a document on another day or to wait for the morning. The Counter Shifts list and the printed shift report use the same day (#1228).
---

## Custom fields — how a profile reaches a record

A definition applies to a record when it targets the record's entity type
**and** is either unscoped or scoped to the firm's business profile. **NULL
means every profile, not none.** `docs/BUSINESS_PROFILE_FRAMEWORK.md`, "How a
firm resolves its attributes", is the reference.

**Only a platform administrator writes definitions and rules** — a firm
administrator is refused `/business-framework/attribute-definitions` with 403
— and both screens live in a firm's store, so they need a firm open. Cases
here define as the prepared **Platform admin** inside the prepared firm, and
enter records as whichever account the case names.

**Every case runs in `ready-firm`'s own store**, because they make fields
mandatory and change the firm's profile. In QA01 that would break every
other case that saves a customer or a product.

> **The product form is not the customer form.** A customer, vendor, branch or
> warehouse form offers every field that *applies*. The product form offers
> only fields a **Mandatory Attributes** rule names for the product's
> category — mandatory or not — and no Attributes tab at all when there is
> none. So a product field needs a rule before it can be seen. Three plan rows
> assumed otherwise; see *Known defects* at the end of this section.

### TC-FIELD-001 — Unscoped applies everywhere; scoped to another profile, nowhere here

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. Sign in as the prepared **Platform admin**; switch into the prepared firm. Settings > Business profile > **Attribute Definitions**.
  2. **New**: code `SHELF_NOTE`, name `Shelf note`, TEXT, entity type `PRODUCT`, business profile **blank**. Save.
  3. **New**: code `PHARMA_NOTE`, name `Pharma note`, TEXT, entity type `PRODUCT`, business profile **Pharmacy**. Save.
  4. **(HTTP)** `GET /api/v1/business-framework/attribute-definitions/applicable?entity_type=PRODUCT` with the preparation firm's `X-Firm-ID`.
  5. Mandatory Attributes → **New**: category `FXAMB`, attribute `Shelf note`, mandatory **off**, profile blank. Save. Then Masters > **Products** → New → category **Fixture Ambient** → **Attributes** tab.
- **Expect**
  - Step 1: the definitions in *this firm's* store — the seeded ones (Batch Number, Expiry Date, IMEI …) — each showing its entity type and the profile it is narrowed to.
  - Steps 2–3: both save.
  - Step 4: `definitions` includes **SHELF_NOTE** and **not** PHARMA_NOTE. Scoping is what stops one industry's field appearing everywhere.
  - Step 5: an **Attributes** tab with a **Shelf note** box. Since 2026-09-16 the rule is not what puts it there — a definition that simply applies is offered on the product form as it is on every other master (D-27-1); the rule decides whether the box is *required*.
### TC-FIELD-002 — A mandatory definition reaches every category

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, Dynamic Attributes → New: `BIN_CODE`, `Bin code`, TEXT, `PRODUCT`, profile blank, **mandatory on**. Save.
  2. **(HTTP)** `POST /api/v1/products` with `X-Firm-ID`: `{"code": "NOBIN", "name": "No bin", "product_type": "STOCK_ITEM", "category_id": "<FXAMB's id>"}`.
  3. The same with `"attributes": [{"attribute_definition_id": "<BIN_CODE's id>", "value": "A-1"}]` and code `BIN1`.
- **Expect**
  - Step 2: **422**, "Required attributes are missing.", naming BIN_CODE's id in `missing_attribute_definition_ids`. The flag on the definition applies to **every** category it reaches — blunt, and the one with a history.
  - Step 3: saves.
  - On the desktop the form now offers a **Bin code** box, required, so step 3's product can be typed rather than posted: fixed 2026-09-16, see defect **D-27-2**.
### TC-FIELD-003 — A rule makes a field mandatory for one category only

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, Dynamic Attributes → New: `COLD_CHAIN_ID`, `Cold chain id`, TEXT, `PRODUCT`, profile blank, mandatory **off**.
  2. Mandatory Attributes → **New**: profile **Wholesale**, category `FXCHL`, attribute `Cold chain id`, **mandatory on**.
  3. Masters > Products → New, category **Fixture Chilled**, code `CH1`, leave Cold chain id empty, Save. Fill it, Save.
  4. Masters > Products → New, category **Fixture Ambient**, code `AM1`, Save.
- **Expect**
  - Step 3: the Attributes tab shows **Cold chain id** as required; empty is refused on the form ("Required business attributes are missing."); filled, it saves.
  - Step 4: saves — no Attributes tab, nothing asked. Other categories are untouched.
### TC-FIELD-004 — A rule naming a field this firm cannot see enforces nothing on the server

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, Dynamic Attributes → New: `RX_CLASS`, `Rx class`, TEXT, `PRODUCT`, profile **Pharmacy**.
  2. Mandatory Attributes → New: profile **Wholesale**, category `FXAMB`, attribute `Rx class`, mandatory **on**. Save.
  3. **(HTTP)** `POST /api/v1/products`: code `RX0`, category FXAMB, no attributes.
  4. **(HTTP)** `GET /api/v1/products/metadata?category_id=<FXAMB's id>`.
- **Expect**
  - Step 2: accepted — not an error.
  - Step 3: **saves**. The server intersects the rules with what applies to this firm, and a Pharmacy field does not.
  - Step 4: `required_attribute_definition_ids` does **not** list RX_CLASS, and neither does the optional list — the metadata and the save now answer the same question. Fixed 2026-09-16; see defect **D-27-3**.
### TC-FIELD-005 — Changing the firm's profile hides a field and keeps its value

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm: Dynamic Attributes → New `WS_GRADE`, `Wholesale grade`, TEXT, `PRODUCT`, profile **Wholesale**. Mandatory Attributes → New: profile **Wholesale**, category `FXAMB`, `Wholesale grade`, mandatory **off**.
  2. Masters > Products → New, category Fixture Ambient, code `GR1`, Wholesale grade `A`. Save.
  3. Set Up on the firm (from Platform) or Profile Assignment: change the firm to **Retail**. Open `GR1` again.
  4. Change the firm back to **Wholesale**. Open `GR1` again.
- **Expect**
  - Step 3: the **Attributes tab is gone** and nothing warned you. The value is still stored (below). This is `docs/BACKLOG.md` §16.
  - Step 4: the field and its value `A` are back. Nothing was lost; it stopped being *read*.
### TC-FIELD-006 — Changing a definition's data type strands its values

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, create `LOT_NOTE`, TEXT, `PRODUCT`, profile blank, and an optional rule for it on `FXAMB`. Create product `LN1` in Fixture Ambient with Lot note `abc`.
  2. Edit `LOT_NOTE` and change its data type to **NUMBER**. Save.
- **Expect:** accepted, **with no warning**. The stored value stays where it was: `value_text = 'abc'`, `value_number` empty, beside a definition that now says NUMBER. Record this as expected-but-wrong — it is §16's first lifecycle guard. *(Driven: `GET /api/v1/products/{id}` still returns the row with `value_text: "abc"`. What the product form shows for it was not checked.)*
### TC-FIELD-007 — A customer carries a custom field, and an edit leaves it alone

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, Dynamic Attributes → New: entity type `CUSTOMER`, code `DRUG_LICENCE_NO`, name `Drug licence no`, TEXT, mandatory **off**.
  2. Sign in as the prepared **Firm admin** → Masters > Customers → New.
  3. Fill the General tab (code `DLC`, name `Licence Holder`), then **Custom fields**: `DL-4471`. Save. Reopen.
  4. Edit the phone on the General tab (`+919800000001`), Save, reopen Custom fields.
- **Expect**
  - Step 2: a **Custom fields** tab with one box, **Drug licence no**.
  - Step 3: the value is there. **(HTTP)** `GET /api/v1/customers/{id}`: `attributes` carries one row with `value_text: "DL-4471"`.
  - Step 4: the licence is still there. A form sends `attributes` only once it has read the definitions, and an update that omits them leaves them alone.
### TC-FIELD-008 — A mandatory customer field is refused on the form and on the server

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, create `DRUG_LICENCE_NO` for `CUSTOMER` as in TC-FIELD-007, with **mandatory on**.
  2. As the prepared **Firm admin**: Masters > Customers → New, fill General, leave the licence empty, Save.
  3. **(HTTP)** `POST /api/v1/customers` with `code`, `name`, `customer_type: "BUSINESS"`, `currency_code: "INR"` and no attributes.
- **Expect**
  - Step 2: refused on the form, **"Drug licence no is required."** Nothing sent.
  - Step 3: **422**, "Required attributes are missing."
### TC-FIELD-009 — A vendor field belongs to vendors only

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, Dynamic Attributes → New: entity type `VENDOR`, `SUPPLIER_TIER`, `Supplier tier`, NUMBER.
  2. As the prepared **Firm admin**: Masters > Vendors → New (or Edit one) → **Custom fields**: `2`. Save, reopen.
  3. Masters > Customers → New: look at Custom fields.
  4. **(HTTP)** `POST /api/v1/customers` carrying `"attributes": [{"attribute_definition_id": "<SUPPLIER_TIER's id>", "value": "2"}]`.
- **Expect**
  - Step 2: one numeric box, Supplier tier; `2` after reopening.
  - Step 3: not offered.
  - Step 4: **422**, "One or more attributes do not apply to this record."
### TC-FIELD-010 — Branches and warehouses carry their own fields

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, Dynamic Attributes → New: entity type `BRANCH`, `FSSAI_LICENCE`, TEXT. And another: entity type `WAREHOUSE`, `DOCK_COUNT`, NUMBER.
  2. As the prepared **Firm admin**: Masters > Branches → Edit `HO`; Masters > Warehouses → Edit `MAIN`.
- **Expect:** a **Custom fields** heading at the foot of each dialog with **its own** box only — FSSAI licence on the branch, Dock count on the warehouse. Type a value, Save, reopen: it is there. The branch is **still the default** — saving the dialog does not clear what it does not show.
### TC-FIELD-011 — A field with fixed choices

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Platform admin** in the prepared firm, Dynamic Attributes → New: `PRODUCT`, `STORAGE_TEMPERATURE`, `Storage temperature`, TEXT, **Allowed values** `Ambient, Chilled, Frozen`. Then Mandatory Attributes → New: category `FXAMB`, Storage temperature, mandatory **off**.
  2. Masters > Products → New, category Fixture Ambient, code `PEAS`, Attributes → Storage temperature.
  3. Choose **Frozen**, Save, reopen.
  4. **(HTTP)** `PUT /api/v1/products/{PEAS id}` with `code`, `name`, `product_type`, `category_id` and `"attributes": [{"attribute_definition_id": "<id>", "value": "Cold"}]`.
  5. Edit the definition: remove `Frozen`. Reopen `PEAS`; then change its name and Save.
  6. Edit the definition: set the data type to NUMBER with the values still filled. Save.
- **Expect**
  - Step 2: a **dropdown** of the three, not a text box.
  - Step 3: Frozen is selected.
  - Step 4: **422**, "Attribute STORAGE_TEMPERATURE must be one of: Ambient, Chilled, Frozen."
  - Step 5: Frozen still shows, selectable, and **the save goes through with it unchanged**. Choosing something else off the list is still refused with "must be one of: Ambient, Chilled". Fixed 2026-09-16; see defect **D-27-4**.
  - Step 6: **422**, "Only a TEXT attribute can carry allowed values."
### TC-FIELD-012 — Reading a firm's fields needs the firm, and nothing else

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps (HTTP)** — as the prepared **Firm admin**:
  1. `GET /api/v1/business-framework/attribute-definitions/applicable?entity_type=CUSTOMER` with `X-Firm-ID` of the prepared firm.
  2. The same without `X-Firm-ID`.
  3. `POST /api/v1/business-framework/attribute-definitions` with any body, with `X-Firm-ID`.
- **Expect**
  1. **200**: `entity_type`, `definitions` (what this firm's profile allows) and `mandatory_ids`. Membership is the whole gate — the forms of anybody who can open a customer need it.
  2. **403**, "Select a firm to read its custom fields."
  3. **403**. Reading the fields a form offers is not writing the catalogue.
### TC-FIELD-013 — A unit is shared by the store; its custom-field values are per firm

- **Preconditions:** Two SHARED firms, QASH1 and QASH2, each with its own firm administrator.
- **Touches the shared store.** A UOM is one row for every firm in `firm_shared`, MEDI01 and FOOD01 included. The case writes a *value* (per firm, QASH1's own) and one definition, which every firm in the store will see — delete it at the end.
- **Steps**
  1. Sign in as the prepared **Platform admin**, switch into **QASH1**, Dynamic Attributes → New: entity type `UOM`, code `QA_PACK_NOTE` (upper case), TEXT.
  2. **(HTTP)** As the prepared **QASH1 admin**, `GET /api/v1/uom-framework/uoms?page_size=100` and pick a unit, e.g. `BAG`. `PUT /api/v1/uom-framework/uoms/{id}` with only `{"attributes": [{"attribute_definition_id": "<id>", "value": "QASH1 note"}]}`.
  3. **(HTTP)** As the prepared **QASH2 admin**, list the units and find the same id.
  4. Delete the definition (Dynamic Attributes, as the platform admin).
- **Expect**
  - Step 2: **200**; the unit's `attributes` carries "QASH1 note". The update is partial — nothing else about the unit changes.
  - Step 3: the **same unit**, with `attributes` **empty**. The unit is one row; the values are per firm.
  - No desktop form shows UOM custom fields yet.
### TC-FIELD-014 — The shared store has one custom-field catalogue

- **Preconditions:** Two SHARED firms, QASH1 and QASH2, each with its own firm administrator.
- **Touches the shared store**, deliberately — it is the case. Delete the definition at the end.
- **Steps**
  1. Sign in as the prepared **Platform admin**, switch into **QASH1**, Dynamic Attributes → New: `CUSTOMER`, code `QA_SHARED_CHECK`, TEXT.
  2. Switch into **QASH2** → Dynamic Attributes.
  3. Delete it.
- **Expect:** step 2 — **it is there.** `attribute_definitions` carries no `firm_id`, so every firm in `firm_shared` — QASH1, QASH2, MEDI01 and FOOD01 — edits one set. A firm in its own schema, like `ready-firm`'s, does not have this. It is the reason `docs/BACKLOG.md` §16 exists.
### TC-FIELD-015 — Extra fields on documents, carried down the chain and printed

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Firm > **Custom Fields** → New: name *PO reference*, type Text, entity type **Sales order** (also add one for **Quotation** with the same name), **Show on print** on. Sell > **Quotations** → New: fill *Additional details* → Save → convert to a sales order → open the order. Create a delivery note and a bill from it. Print the quotation, order and invoice. Edit the order saving without touching *Additional details*, then clear the field and save. Repeat for a purchase order → supplier bill.
- **Expect:** the six document editors — quotation, sales order, delivery note, sales invoice, purchase order, supplier bill — show *Additional details* from the firm's definitions. Values carry down the chain matched on the field's **name** (quotation → order at conversion, order → delivery note, notes/orders → sales invoice, purchase order → supplier bill) and are printed as references where *Show on print* is on. Saving without sending `attributes` leaves the values alone; sending an empty list clears them. Goods receipts, returns, notes, line-level fields and list filters on a document field are not covered yet.
### TC-FIELD-016 — A firm keeps its own custom fields, in the shared store too

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** Two SHARED firms, QASH1 and QASH2, each with its own firm administrator.
- **Steps:** as the **Firm admin of QASH1**: Settings > Firm > **Custom Fields** → New *Dock number* on Customer; Settings > Firm > **Custom Field Rules** → make it mandatory for a category. Try a code that already exists in the shared catalogue. Edit and delete the field; try to delete it after a customer holds a value. As the **Firm admin of QASH2**: open Customer → New and the field list. As the platform administrator open Attribute Definitions.
- **Expect:** the field is **QASH1's own**: offered on its forms and on no other firm's. The shared catalogue rows (existing before this change) are listed read-only to the firms. A firm's code is unique among its own and the shared live rows. A held type cannot change and a held field cannot be deleted. The platform's Attribute Definitions list shows the shared rows only.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 04-S01 | **Settings > Platform > Firms > Firms** | Offered to any role holding `FIRM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S02 | **Settings > Firm > Numbering Series** | Offered to any role holding `SETTINGS_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S03 | **Settings > Platform > Firms > Business Profiles** | Offered to any role holding `PLATFORM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S04 | **Settings > Business profile > Feature Management** | Offered to any role holding `PLATFORM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S05 | **Settings > Business profile > Module Configuration** | Offered to any role holding `PLATFORM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S06 | **Settings > Business profile > Attribute Definitions** | Offered to any role holding `PLATFORM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S07 | **Settings > Business profile > Mandatory Attributes** | Offered to any role holding `PLATFORM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S08 | **Settings > Business profile > Profile Assignment** | Offered to any role holding `FIRM_VIEW` or `PLATFORM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S09 | **Settings > Tax > Tax Configuration** | Offered to any role holding `TAX_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S10 | **Settings > Tax > Tax Rules** | Offered to any role holding `TAX_RULE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S11 | **Settings > Tax > Rule Simulator** | Offered to any role holding `TAX_SIMULATE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S12 | **Settings > Tax > Execution Log** | Offered to any role holding `TAX_RULE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S13 | **Settings > Tax > Tax Settings** | Offered to any role holding `TAX_MANAGE_SETTINGS`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S14 | **Settings > Set up > Item lists > Units of Measure** | Offered to any role holding `UOM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S15 | **Settings > Set up > Item lists > UOM Groups** | Offered to any role holding `UOM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S16 | **Settings > Set up > Item lists > Packaging Types** | Offered to any role holding `PACKAGING_MANAGE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S17 | **Settings > Set up > Item lists > Packaging Levels** | Offered to any role holding `PACKAGING_MANAGE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 04-S18 | **Settings > Set up > Item lists > Conversion Rules** | Offered to any role holding `CONVERSION_RULE_MANAGE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
