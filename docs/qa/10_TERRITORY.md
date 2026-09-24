# Territory, routes and beats

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Territory, routes and beats

| | Route | Frequency, days | Salesperson | Round, in order |
| --- | --- | --- | --- | --- |
| North Zone | `QA-R-N1` North Sales Beat | weekly, Mon Wed Fri | Asha | `QA-C1` Revise Check, `QA-C2` Classic Stores |
| North Zone | `QA-R-N2` North Collections | fortnightly, Tue Thu | Bala | `QA-C3` Vijaya Stores |
| South Zone | `QA-R-S1` South Sales Beat | weekly, Tue Thu | Asha | `QA-C4` Anand Agencies |
### TC-TERR-001 — The territory tree

- **Preconditions:** A Wholesale firm with the territories, routes, rounds, salespeople and beat plans described in this section's preparation table.
- **Steps**
  1. Sales → **Geography**; select any row; the right-hand **Territory tree** → **Expand all**. Click the icon beside its title ("Open the tree in a larger window"); try Collapse all / Expand all; Close.
  2. Double-click `QA-R-N1` → **Details**; then **Customers** and **Salespeople**.
- **Expect**
  - Step 1: Chennai Region (Region) → North Zone and South Zone (Territory) → North Sales Beat and North Collections under North, South Sales Beat under South (Route), each node with its code and full path; the grid's Hierarchy column carries the path.
  - Step 2: **Route** section: Route type **Sales Route**, Visit frequency **Weekly**, Working days **Mon, Wed, Fri**, Runs from **Always**, Runs until **No end**. 2 customers, both active; Salespeople 1. Customers: Revise Check, Classic Stores. Salespeople: Asha Sales.
### TC-TERR-002 — A call list for a Monday, with reasons for every plan that does not run

- **Preconditions:** A Wholesale firm with the territories, routes, rounds, salespeople and beat plans described in this section's preparation table.
- **Steps:** Sales → **Call Lists**. Move to **Monday 2026-09-21** (› Next day or the date button), Salesperson Everyone. Then **Back to today**.
- **Expect:** the date button reads "Monday 2026-09-21"; the status bar "1 of 9 plan(s) run on Monday 2026-09-21". `-BP-R1-MON` is badged **Runs on Monday** and calls Revise Check then Classic Stores (the route's round, in order). Every other plan is **Not on Monday** with its reason — e.g. `-BP-R1-FRI` "Runs on Fridays; this is a Monday."
### TC-TERR-003 — Fortnightly and monthly plans, and why they skip a week

- **Preconditions:** A Wholesale firm with the territories, routes, rounds, salespeople and beat plans described in this section's preparation table.
- **Steps:** Call Lists: date **2027-01-12**, then **2026-10-13**, then **2026-10-20**.
- **Expect**
  - 2027-01-12 (a second Tuesday and an even fortnight from 2026-04-07): "4 of 9 plan(s) run" — `-R2-TUE` and `-COLL` (both Vijaya), `-R3-TUE` and `-MTH` (both Anand).
  - 2026-10-13 (second Tuesday, off fortnight): `-COLL` **Not on Tuesday**, "Runs every other Tuesday counted from 2026-04-07; this is the week between."; `-MTH` runs.
  - 2026-10-20 (third Tuesday): `-COLL` runs; `-MTH` "Runs on the second Tuesday of the month; this is the third."
### TC-TERR-004 — Building a round, and saving one unchanged

- **Preconditions:** A Wholesale firm with the territories, routes, rounds, salespeople and beat plans described in this section's preparation table.
- **Steps**
  1. Sales → **Route Builder** → Route being built `QA-R-N1` (right: 1. Revise Check, 2. Classic Stores). Tick **On no route yet** → **Find** → double-click `QA-SN` (stop 3) → drag it by ≡ above the first stop → **Save round and order**. Choose the route again.
  2. **Remove from round** on SN → Save. Then choose N1 again, change nothing → Save.
- **Expect**
  - Step 1: "3 outlet(s) on North Sales Beat, in order."; reopened: 1. SN, 2. Revise Check, 3. Classic Stores — the stops moved without a collision.
  - Step 2: "2 outlet(s) on North Sales Beat, in order." both times; the same two stops in the same order. The status bar says "Saving replaces the whole round with the list on the right." — which is why the screen refuses to save a round it could not read.
### TC-TERR-005 — A salesperson must cover the customer's route

- **Preconditions:** A Wholesale firm with the territories, routes, rounds, salespeople and beat plans described in this section's preparation table.
- **Steps:** Sales Orders → **New Order** for `QA-C4` (Anand, on S1, covered by Asha): ships from MAIN, **Salesman Bala**, one line `QA-P` qty 1 → Create draft. Then Asha → Create draft. Then Salesman blank → Create draft → reopen.
- **Expect:** Bala is refused in the editor's banner: "The selected salesperson is not assigned to this territory." — nothing saved. Asha saves. Blank saves and, reopened, the salesman is **Asha**, supplied by the customer's route.

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 10-S01 | **Sales → Geography** | Offered to any role holding `TERRITORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 10-S02 | **Sales → Route Types** | Offered to any role holding `TERRITORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 10-S03 | **Sales → Beat Plans** | Offered to any role holding `TERRITORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 10-S04 | **Sales → Call Lists** | Offered to any role holding `TERRITORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 10-S05 | **Sales → Coverage** | Offered to any role holding `TERRITORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 10-S06 | **Sales → Route Builder** | Offered to any role holding `TERRITORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 10-S07 | **Sales → Places** | Offered to any role holding `TERRITORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
