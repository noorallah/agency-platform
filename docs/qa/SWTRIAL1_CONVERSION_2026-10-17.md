# SWTRIAL1: Swathi trial files loaded over HTTP (item 25e)

2026-10-17. Counts and column names only; the data is real and is not copied
here. Files: `D:\ws\agencyApp\unattended\swathi_trial\` (made by
`backend/scripts/swathi_dump_to_templates.py`, see `SWATHI_TRIAL_CONVERSION.md`).

## Firm

`SWTRIAL1`, SHARED storage (`firm_shared`), created by the loop administrator
through `POST /api/v1/firms`, then books opened, GST template applied, head
office created and the WHOLESALE profile assigned (the same steps as
`test_fixture.ensure_firm`). Readiness `can_post` was true. Territory levels
were made by one `GET /sales-territories/hierarchy-levels` (what "open the
Territories screen once" does). No other firm was touched.

## Server used

The backend on port 8000 was started before the principal, route, salesman
and ledger-account `import-file` routes merged: it answered 405/404 for four
of the seven kinds. A second instance of the same tree (main `42fe2c24`) was
started on port 8001 against the same database, used for every step below and
stopped afterwards. The 8000 server was not restarted.

## Result per file (check first, apply only when clean)

| File | Rows | Check | Applied |
| --- | --- | --- | --- |
| principals | 2 | clean, 2 to create | yes |
| brands | 10 | clean after principals (first check on an empty firm: 10 x Company `CO9` unknown, as expected) | yes, 10 |
| routes | 10 | clean after levels exist (first check: 10 x Parent "territory levels not set up") | yes, 10 |
| salesmen | 6 | clean, 6 to create | yes, 6 |
| customers | 306 | refused, 355 problems on all 306 rows | no |
| suppliers | 5 | refused, 6 problems on 5 rows | no |
| ledger_accounts | 38 | refused, 1 problem | no |

### customers (converter / source, not the app)

- `State`: needed for an address on all 306 rows. The converter writes no
  State and the dump holds none; the file needs it filled (one value for the
  firm would do) before it can apply.
- `PIN` missing on 17 rows, `City` on 16, `Address1` on 15 (the source rows
  have no address; most are non-party heads such as tax and freight accounts
  that landed under the customer heads, e.g. rows C4 and C13).
- `Phone`: 1 row is not a phone number.
- `Beat` is used (not ignored) by the server; all beats resolve now that the
  routes are in. `columns_ignored` was empty.

### suppliers

- `Address1` blank on 4 rows; row S2066 City `HYDERABAD` and PIN `517501` are
  not in the geography masters (SWTRIAL1 has none loaded; a firm set-up step).
  Converter/source and set-up, not the app.

### ledger_accounts

- Value mapping on `Group` sent with the request: `A S S E T`->`CA`,
  `ADMN., & OFFICE MAINTENANCE`->`IEXP`, `BANK`->`CA-BANK`,
  `CASH ON HAND`->`CA-CASH`, `P & L ACCOUNTS`->`IEXP`, `SALES`->`REV`. All
  mapped heads were accepted. `P & L ACCOUNTS` mixes income and expense heads
  (for example interest received), so it needs a per-account choice or a split
  in the converter.
- Row 39 (`A2524`): `Group` is blank in the file, so the all-or-nothing
  apply was refused. Converter/source: one account has no head.

## Defects

None found in the app. Every refusal named its row and column and wrote
nothing, as designed.

## Still to do

Customers and suppliers need State (and address) values from the converter or
the customer; ledger accounts need the one blank group filled; then check and
apply again in the same order.
