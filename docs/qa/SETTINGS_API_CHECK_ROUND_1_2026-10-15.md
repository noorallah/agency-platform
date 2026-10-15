# Settings sections: API check round 1 (2026-10-15)

Backlog 148, rows T1 and T2. Driven over HTTP against the running backend at
`http://127.0.0.1:8000`, with the kept scripts in `docs/qa/checks/settings/`
(`python docs/qa/checks/settings/setup.py`, then `python docs/qa/checks/run.py settings`).
No product code was changed.

## What was driven

- **Fixtures** (`setup.py`): `ready-firm` (a finished Wholesale firm: books open, GST
  template, head office; its Firm admin, a Viewer, a platform admin) and `unfinished-firm`
  (a provisioned firm with nothing set up), plus a Firm admin of that bare firm made by the
  script. State in `.state/settings.json` (not committed).
- **State reads**: all 12 firm sections of `GET /api/v1/settings-sections/{section}/state`
  and both platform sections (`platform/people`, `platform/firms`): step codes and order
  against the table in `desktop/docs/DESKTOP_FRAMEWORK.md`, state words, `todo_count`,
  and where the state is tied to data (To do exactly while the data is absent) the data
  was read through the record's own list endpoint.
- **Saved**: one record per step through the step's own endpoint, then the section re-read
  and the count (or state) checked to have moved: tax profiles and the GST template,
  financial years (open-books), goods types, custom fields, salesmen (with a salesman
  required on a bill), discount, approval and adjustment limits, purchase budgets, adjustment
  reasons, own fields and rules and unit sets, price lists and levels, territories, route
  types, transporters, control-account remap, cost and profit centres (including an account
  requiring a cost centre), customer groups, vendor categories and types, licence types,
  units, packaging types, categories, principals, brands, conversion rules, branch and
  warehouse types, a warehouse and a storage area, roles, templates, users, memberships.
- **Singleton settings screens** (GET, PUT the same body, change one value, PUT it back, each
  leg read back and the step read again): tax settings, GST compliance, TDS 194Q, messaging,
  price floor, credit control, loyalty, TCS, purchase workflow, sales workflow (salesman
  required), batch sale settings, trade licence settings. Lot settings is read only (see S3).

## Results

| Id | Result |
| --- | --- |
| `tc_conf_010` Tax | clean (13 + 2 singleton legs) |
| `tc_conf_011` Firm, Selling, Buying | clean |
| `tc_conf_012` Stock, Business profile, Pricing | clean |
| `tc_conf_013` Territories, Account structure, Party lists | clean |
| `tc_conf_014` Item lists, Locations | clean |
| `tc_conf_015` People, Firms | 2 failures: S1, S2 |
| `p_set_unknown_and_unauthenticated` | clean (404, 401, firm missing/unknown/garbled all 4xx) |
| `p_set_other_firm_and_roles` | clean (other firm 403 on every section; Firms 403 to firm admin and Viewer; People 403 to Viewer) |
| `p_set_read_writes_nothing` | clean (audit count unchanged after 3 reads of every section; no state changed) |
| `p_set_people_rows_offered` | 1 failure: S1 |

Run tally: `10 checks, 8 clean, 2 failing`; every failing line repeated on a second run.

## Defects

### S1 (Medium): People hands a firm administrator the User-firm assignments row

- Request: `GET /api/v1/settings-sections/platform/people/state` as the Firm admin, `X-Firm-ID` of the ready firm.
- Expected: steps `roles`, `user-templates`, `users` only; the table says step 4 "is a platform
  administrator's alone, so a firm administrator has no tab and no row for it".
- Got: four steps, the last `user-firms`, `OPTIONAL`, detail `"8 memberships"` (the live
  memberships of the firm).
- Cause: `backend/app/settings_sections/services/platform.py:136-143` (`people_section`) returns
  all four steps whoever asks; `_memberships_step` (line 115) has a firm branch for the firm
  administrator, so the row is built for them on purpose. The desktop hides the tab, so the
  screen is not affected, but the API tells every firm administrator the count of memberships.

### S2 (High): `platform/firms` answers 503 for the platform administrator

- Request: `GET /api/v1/settings-sections/platform/firms/state` as the platform administrator (no `X-Firm-ID`).
- Expected: 200, steps `business-profiles` then `firms` (Done, "N firms").
- Got: 503 "The database is temporarily unavailable.", every time.
- Cause: the server error log shows `UndefinedTable: relation "platform.business_profiles" does
  not exist` from `SELECT count(*) FROM platform.business_profiles WHERE ... status = 'ACTIVE'`.
  `firms_section` (`backend/app/settings_sections/services/platform.py:146-160`) counts
  `BusinessProfile` on the platform session, but on this installation business profiles live in
  the firm store (the Firm admin's `business-profile` state reads them), not in the platform
  schema. The Firms section cannot open at all, which is the desktop's tab 2 of TC-CONF-015 step 2.

### S3 (Low, by design, noted): the Costing method step has no screen that can be saved on Average

- `PUT /api/v1/inventory/lot-settings {"allow_billing_without_stock": false}` on a firm on Average
  is refused 422 "Billing without stock applies only to a firm that costs its stock by lot"
  (`backend/app/inventory/services/lot_switch_over.py:147-152`), even for the value the firm already
  has. Saving the screen unchanged therefore fails on Average. Written into `tc_conf_012` as an
  expected refusal, not a failure.

## Not driven

- Units of Measure To do (needs a store with no unit; every store is seeded) and Roles To do.
- Promotions, Route builder, Packaging levels, Approval levels, Numbering series, Custom field
  rules for a category outside `FXAMB`: needed bodies this round did not build; their counts
  were read in the shape checks only.
- Firms count moving after a firm is created (blocked by S2; creating a firm only to leave it
  behind was left out).
- Control accounts To do: `open-books` maps all 64 purposes and no endpoint unmaps one, so the
  To do reading was seen on the fresh bare firm (`64 of 64 unmapped`) and the move to
  `All 64 mapped` after open-books, not re-driven on a second run.
