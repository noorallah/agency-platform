# Bill series by company, cases and drive result, 2026-10-17

Item 29(e), backlog 157. Design: `docs/design/BILL_SERIES_BY_COMPANY_DESIGN.md`
section 11. Driven over HTTP by `backend/scripts/drive_bill_series.py` on a new
firm **BSER1017** (SCHEMA store `firm_bser1017`, provisioned, books opened, GST
template applied, head office made, its own firm admin), at main `6b6393f2`,
migration `20261017_0395`. No application code changed.

Set-up the script makes: companies **ASIAN** (prefix ASIAN), **PIDI** (prefix
PIDI) and **NOPFX** (no prefix); one 100.00 item at 18% under each (two under
ASIAN) plus a service item; a business customer; order and delivery-note stages
off so a bill stands alone. A new firm has no sales-bill series until its first
bill and pads to six digits, so the script raises one bill, then narrows the
padding to four, which is what lets a five-letter prefix fit (case C13 shows the
limit and its message).

| Case | Steps | Expected | Result |
| --- | --- | --- | --- |
| C01 | `ONE_SERIES`; bill of an ASIAN item | preview reason `ONE_SERIES`, series GENERAL; number is the rule's own (`SI-`) | PASS |
| C02 | `BY_COMPANY`; bill of one ASIAN item | `ASIAN-26-27-nnnn`, reason `ONE_COMPANY` | PASS |
| C03 | `series-preview` before saving | text equals the number the saved bill gets | PASS |
| C04 | bill of two ASIAN items | `ASIAN-` series | PASS |
| C05 | bill of an ASIAN and a PIDI item | reason `MIXED`, GENERAL; preview equals saved | PASS |
| C06 | bill of an item whose company has no prefix | GENERAL | PASS |
| C07 | bill of an ASIAN and an unprefixed item | GENERAL | PASS |
| C08 | ASIAN item plus 50.00 freight plus a service line | `ASIAN-` series (freight and service ignored) | PASS |
| C09 | first PIDI bill | `PIDI-` with a counter of its own (equals its preview) | PASS |
| C10 | three ASIAN bills | numbers unique and consecutive from the previewed first | PASS |
| C11 | GENERAL bills across the setting | unique and consecutive | PASS |
| C12 | `ONE_SERIES`, ASIAN bill, back to `BY_COMPANY`, ASIAN bill | GENERAL continues (+1) and ASIAN continues (+1); nothing reset or reused | PASS |
| C13 | save prefix `ASIANPAINT` on ASIAN | 422 naming the 21-character number and the limit (5 fits); prefix unchanged | PASS |
| C14 | save prefix `ASIAN` | 200 | PASS |
| C15 | save prefix `AS-IAN` | 422 (letters and digits only) | PASS |
| C16 | approved ASIAN bill, then a sales return of its line | return numbered `SR-26-27-...`, not ASIAN; the ASIAN counter moves only by the bill | PASS |

Result: **16 of 16 pass** on the second run. The first run on the freshly built
firm passed 11: the five failures (C01, C05, C06, C07, C12) were the script
expecting GENERAL to print the word `GENERAL`, when it prints the sales-bill
rule's own prefix `SI-` (design section 4: "GENERAL is the firm's existing
sales-bill rule"; the preview names it GENERAL). The script was corrected, not
the application. No application defect was found.

## Not covered by this drive

Design section 11 items that need a database-level or unit test, and were not
driven here: the race of two sessions on one prefix (integration suite, needs
PostgreSQL locks), a new financial year restarting at 1 and a back-dated bill,
the migration backfill, two companies **sharing** one prefix (the design's test
1), and a credit note and a proforma. Drive them separately.
