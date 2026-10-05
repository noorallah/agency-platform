# Selling: checked through the API, 2026-10-05

Kept apart from `08_SELLING.md`, which is regenerated from
`docs/INDEPENDENT_TEST_CASES.md` and would drop a hand-written table.

After the purchasing build (PG-1..14) the chain was driven through the real
API on a firm of its own (`selling-paid`, schema `fx_t1005j1us_s`) and its
books read back from the database. This covers the server; the screens are
still to be walked by hand.

| Case | What was driven | Result |
| --- | --- | --- |
| TC-SELL-007, 009, 010 | Order for 12 with `WELCOME10`, approved; notes for 5 and 7 dispatched | Pass: stock 100 to 88, cost of goods sold 720.00 |
| TC-SELL-011 | Both notes billed and approved (483.21 and 676.49) | Pass: sales 982.80, output tax 176.90, receivable 1,159.70 |
| TC-SELL-013 | Receipts of 241.60 and 341.61 | Pass on the corrected figures: no TCS, advance 100.00 |
| TC-SELL-014 | Advance of 95 applied, 10 more refused; receipt reversed twice | Pass: no journal for the apply, one `-REV` for the reversal |
| TC-SELL-015 | Return of 9 refused, 2 completed | Pass: 193.28 credited, stock back to 90, inventory 5,400.00 |
| TC-SELL-016 | Credit note of 50 approved, 400 refused | Pass: 59.00 (tax 9.00) credited |
| Books | Every journal balanced; bank 341.61; receivable 565.81 against the customer's 570.81 owed less 5.00 advance | Pass |

Found: D-SELL-47 (loyalty points not taken back on a return or credit note)
and D-SELL-48 (ledger CGST and SGST a paisa apart), both in
`docs/DEFECTS.md`. Not driven here: pricing ladders and offers (001 to 006),
holds (008), printing (012), proformas (017) and cases 018 to 035.

Both defects were fixed the same day: D-SELL-47 in #1146 (driven live: a
full return of the 676.49 bill took back its 13.53 points, cancelling it
restored them, a credit note of 118.00 took back 2.36) and D-SELL-48 in
#1147 (unit tests only; not driven live).
