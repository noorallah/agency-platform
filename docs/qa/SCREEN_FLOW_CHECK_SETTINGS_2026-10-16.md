# Screen cases, Settings as one screen per subject: click tests against the real server, 2026-10-16

Flow: `desktop/integration_test/sc_set_test.dart`. Book: `04_FIRMS_AND_CONFIGURATION.md`,
TC-CONF-010 to TC-CONF-015 (the cases that said "no screen was clicked").
Firm **T1016XXBV-R** (Ready t1016xxbv), built by `scripts/test_fixture.py ready-firm`
(SCHEMA store, every Set up step done, WHOLESALE profile, two categories, a
customer, one 500.00 cash receipt). Users: `t1016xxbv.readyadmin@fixtures.local`
(Firm admin) and `t1016xxbv.readyviewer@fixtures.local` (VIEWER), password
`Fixture@2026pw`. Window 1600x1000.

## How to run it

From `desktop/` in Git Bash, one run at a time:

```
IT_EMAIL=<suffix>.readyadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=900 bash integration_test/run.sh sc_set_test.dart
IT_EMAIL=<suffix>.readyviewer@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=900 bash integration_test/run.sh sc_set_test.dart
```

`IT_PART=subjects`, `IT_PART=search` or `IT_PART=batch` runs one part. If
another session is running Flutter on the machine, give the run its own
`TEMP`/`TMP` folder: twice a run died with "did not complete" when the
`flutter_tools.*` listener folder in the shared `%TEMP%` was deleted under it.

What the flow does: presses the gear, each section, its one card, and checks
the tab strip left to right, each Start here chip and the note against the
book; then opens every tab in turn (a tab must show its body) and counts app
errors and overflows the whole time. Each case's *Search settings* step types
the name and presses the card found. The one write is Stock > Batch rules,
near-expiry window: 30 -> 45, read back from `GET /api/v1/batch-serial/sale-settings`,
reopened, put back to 30 and read back again. The Viewer is refused the same
change and the server value is compared before and after.

Not driven: TC-CONF-010 step 8, TC-CONF-011 steps 4 and 6 (they need a firm
with no tax, no open year or a required salesman; the flow leaves the fixture
as found) and TC-CONF-015 step 2 (the platform administrator is a member of no
firm and needs its own run).

## Results

| Case | Step | Firm admin | Viewer | Note |
| --- | --- | --- | --- | --- |
| TC-CONF-010 | Tax opens as one screen | PASS | PASS | Admin: all eight tabs in the book's order; rows 1, 2 Done (10 profiles, 9 rules, from the GST template), 3 to 5 Optional; note "Tax is ready for this firm.". Viewer: no Tax settings tab and no Rule simulator (codes it lacks), the rest open |
| TC-CONF-010 | Search "Tax Rules" | PASS | PASS | opens as a screen |
| TC-CONF-011 | Firm opens as one screen | **FAIL** | PASS | Admin: no **1 Firm settings** tab and no row 1; strip starts at "2 Financial years" (see findings). Viewer sees "1 Firm settings" (Wholesale Distribution), FY2026 open |
| TC-CONF-011 | Selling opens as one screen | PASS | PASS | Seven rows, all Optional |
| TC-CONF-011 | Buying opens as one screen | PASS | PASS | Three rows, all Optional |
| TC-CONF-011 | Search "Credit Control" | PASS | PASS | opens as a window (Credit policy) |
| TC-CONF-012 | Stock opens as one screen | PASS | PASS | Strip also has **4 Costing method**, which the book does not list (book is behind the build) |
| TC-CONF-012 | Business profile opens as one screen | **FAIL** | PASS (only "6 Unit sets") | Admin and Viewer see only **6 Unit sets**; steps 1 to 5 need `PLATFORM_VIEW` (see findings) |
| TC-CONF-012 | Pricing opens as one screen | PASS | PASS | Four rows Optional, None yet / Scheme off |
| TC-CONF-012 | Search "Unit Sets" | PASS | PASS | opens as a screen |
| TC-CONF-012 | Batch rules: change, read back, put back | PASS | — | 30 -> 45 "Batch rules saved.", reopened shows 45, back to 30. The firm's row now exists, so Start here reads "Set for this firm" instead of "Left as it comes" |
| TC-CONF-012 | Batch rules: Viewer cannot change it | — | PASS | Box disabled, Save disabled, says "Changing the batch rules needs the manage sales settings permission."; server 30 -> 30 |
| TC-CONF-013 | Territories & routes opens as one screen | PASS | PASS | Four rows Optional, None yet |
| TC-CONF-013 | Account structure opens as one screen | PASS | PASS | Control accounts Done, "All 64 mapped" |
| TC-CONF-013 | Party lists opens as one screen | PASS | PASS | Five rows Optional |
| TC-CONF-013 | Party lists row 1 Open | PASS | — | Customer Groups list shown inside the subject |
| TC-CONF-013 | Search "Route Builder" | PASS | PASS | opens as a screen |
| TC-CONF-014 | Item lists opens as one screen | PASS | PASS | Units Done (36 units). Viewer: no Conversion rules, Packaging types, Packaging levels tabs |
| TC-CONF-014 | Locations opens as one screen | PASS | PASS | Places "1 country, 36 states". Viewer: no Storage areas tab |
| TC-CONF-014 | Search "Product Categories" | PASS (one run FAIL) | PASS | Two of three admin runs raised an uncaught app error here (see findings) |
| TC-CONF-015 | People opens as one screen | PASS | not offered | Admin: Roles, User templates, Users, Check: Permissions; no User-firm assignments; Roles "13 ready-made", Users "2 people" |
| TC-CONF-015 | Firms not offered to a firm admin | PASS | — | no Firms section |
| TC-CONF-015 | System stays as cards | PASS | — | Audit Logs card, no one-screen card |
| TC-CONF-015 | Search "Users" | PASS | not offered | |

Last full runs: Firm admin passed 21, failed 2, not run 2; Viewer passed 20,
failed 0, not run 2. No overflow and no other app error in either.

## Findings

- **The Firm admin cannot open the firm's own Firm settings, and the Viewer can.**
  TC-CONF-011 step 2 as readyadmin: the Firm strip reads "Start here, 2 Financial
  years, 3 Numbering, ... 8 Approval levels, Yours: My branch and warehouse";
  there is no "1 Firm settings" tab and no row 1 on Start here. As readyviewer
  the same screen shows "1 Firm settings" (Wholesale Distribution). The tab
  needs `FIRM_VIEW` (`desktop/lib/ui/workspace/module_catalog.dart:529-531`),
  which is a platform-group code the FIRM_ADMIN role does not hold, while VIEWER
  takes every code ending `_VIEW` (`backend/app/identity/system_seed.py:620-622`,
  `_all_read_permissions`) and so holds it. Either the role seed or the tab's
  code is wrong; the read-only role reaching further than the administrator is
  the inversion to fix.
- **Business profile shows a firm admin only "6 Unit sets".** TC-CONF-012
  step 2 expects six tabs; steps 1 to 5 (Profile assignment, Feature
  management, Module configuration, Attribute definitions, Mandatory
  attributes) need `PLATFORM_VIEW` in `module_catalog.dart` (line 303 and
  around), so neither the firm admin nor the Viewer is offered them, and the
  lone tab is numbered 6. Either the book's expectation is for a platform
  administrator, or a firm admin should see at least the read-only steps.
- **Opening Product Categories can raise an uncaught error.** Search "Product
  Categories" as the firm admin, press the card: in two of three runs the app
  reported "Cannot reach the API server." from `ApiClient.tradeLicenceTypes`
  as an unhandled exception (the same call answers 200 in 30 ms over HTTP, so
  the request failure itself was a dropped connection). The read is fired with
  `unawaited(api.tradeLicenceTypes().then(...))` and no error handler
  (`desktop/lib/ui/desktop_shell.dart:6541`; the same shape at line 6978), so
  any failed read becomes an app error instead of being ignored or said.
- **The book is behind the build on Stock**: the strip has "4 Costing method"
  between Batch rules and Yours: Inventory settings; TC-CONF-012 does not
  list it.
