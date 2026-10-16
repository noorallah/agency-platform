# Swathi trial conversion (smaller firm)

Part 1, 2026-10-17. Counts and column names only: the data is real and is
never copied into the repository. Plan: `docs/SWATHI_IMPORT_PLAN.md`.

## Converter

`backend/scripts/swathi_dump_to_templates.py DUMP OUTPUT_DIR` reads the
`.sql` text with no MySQL server and writes one CSV per import kind, with the
headings the templates use. Run on the smaller firm's 2025-26 dump (the one
with 306 customers and two companies), output kept in
`D:\ws\agencyApp\unattended\swathi_trial\`, outside the repository.
Tests: `tests/unit/test_swathi_dump_converter.py` (synthetic dump).

| Kind | Source | Rows written |
| --- | --- | --- |
| principals | `company` | 2 |
| brands | `codehead` | 10 |
| routes (beats) | `beatman` type B | 10 |
| salesmen | `beatman` type S | 6 |
| customers | `codes` heads 8 and 28 | 306 |
| suppliers | `codes` heads 9, 27, 29 | 5 |
| chart of accounts | `codes` other heads | 38 |

Customer beat comes from `codes.mcode` (295 of 306 name one of the 10 beats;
11 name none). The licence comes from `codes.dlone` (53 customers); its
expiry is not carried, because `dgldt` holds placeholder dates (year 2099).
Email is carried only where it has an at sign: 260 of 306 hold a one-character
filler.

## Findings from the files alone

- 149 customers carry a GSTIN, 3 numbers are shared by more than one
  customer (G12: the file needs a *ParentCode*, which the converter does not
  guess), 1 PAN is shared. No customer name is repeated.
- 17 customers have no PIN, 26 no phone.
- `LicenceType` is written as `DRUG_WHOLESALE`; whether the firm has that
  type is only known at check time.
- Routes are written with no *Parent* (top level), so the area and route-type
  columns are left for the firm.
- The chart-of-accounts *Group* holds the Swathi head's name; it needs the
  saved value mapping (G6 part 2) onto the firm's account groups.

## Check and apply against SWTRIAL1: not run

The check and apply steps were **not** done. Creating the new test firm needs
a platform administrator sign-in, and none was available to this run
(the credentials were not supplied and are not to be guessed). Nothing was
created on the running backend. To finish: create firm `SWTRIAL1`, then run
check (not apply) in this order, applying each whose check is clean:
principals, brands, routes, salesmen, customers, suppliers, chart of
accounts. Expect the brand step to need the principals first, the customer
step the routes first, and the account step a value mapping.

| Kind | Rows read | Check clean | Check refused | Applied |
| --- | --- | --- | --- | --- |
| all seven | see above | not run | not run | not run |
