# The money pass: every priced document screen, clicked against the real server, 2026-10-10

The fourth measure of D-UI-97. D-UI-95 was a line's total with tax shown
under *Taxable* on the quotation, sales order and sales invoice; D-UI-96 was
five more screens working a line's taxable value out short. The widget tests
now hold those screens to answers the server priced. This is the same check
with nothing standing in for anything.

Flow: `desktop/integration_test/money_pass_flow_test.dart`, run in the real
phase 2 app against the server on port 8000 (main at `0c3154b1`), on the
fixture firm `T1010UORM-S` (a `selling-firm` of
`backend/scripts/test_fixture.py`, with one supplier, *Money Pass Supplier*,
added over HTTP), as the firm administrator. No demo firm was touched.

For each document the flow types a line, waits for the server's pricing,
**reads the row and the foot before saving**, saves, reads the saved document
back over HTTP and compares. The row must have shown the line's taxable value
(its amount less its tax), the rate that tax is of it, and its amount; the
screen must have shown the document's total.

**Outcome: eight screens, eight Pass, on the second run. Nothing wrong was
found in what any screen shows.**

## What was clicked

| Screen | What was typed | Row on screen | The server's saved document | Result |
| --- | --- | --- | --- | --- |
| Quotation | Vijaya Stores, 10 Detergent at 84.00 (2% from the price list) | 823.20 ; 18% ; 971.38 | taxable 823.20, tax 148.18, amount 971.38, total 971.38 | Pass |
| Sales order | the same | 823.20 ; 18% ; 971.38 | the same | Pass |
| Proforma | the approved order chosen | 823.20 ; 18% ; 971.38 | the order's own line | Pass |
| Sales invoice | 5 billed off a dispatched delivery note | 411.60 ; 18% ; 485.69 | taxable 411.60, tax 74.09, amount 485.69, total 485.69 | Pass |
| Sales return | 2 back off that bill, approved | 164.64 ; 18% ; 194.28 | taxable 164.64, tax 29.64, amount 194.28, total 194.28 | Pass |
| Purchase order | Money Pass Supplier, 10 Detergent at 60.00 | 600.00 ; 18% ; 708.00 | taxable 600.00, tax 108.00, amount 708.00, total 708.00 | Pass |
| Purchase bill | the receipt of those 10 billed | 600.00 ; 18% ; 708.00 | the same | Pass |
| Purchase return | 2 back off that receipt | 120.00 ; 18% ; 141.60 | taxable 120.00, tax 21.60, amount 141.60, total 141.60 | Pass |

## The first run

Five Pass, two Fail, one not run. The sales invoice and the purchase bill
each showed the right figures (checked against the server's own pricing of
the same lines, asked for over HTTP: 411.60 / 74.09 / 485.69 and 600.00 /
108.00 / 708.00), but the flow's Save left the editor open and no bill was on
the server afterwards, so there was no saved document to hold the row to, and
the sales return had no bill to come off.

**Why is not established.** The first run waited twelve seconds for an editor
to close and typed the supplier's invoice number before choosing the
receipts; the second waits twenty and types it after, and both bills saved.
The purchase bill's screen showed the number box empty at the save, so its
number had not been kept. Whether either was the flow's own timing or
something a person could meet was not run down. It is written here, not
claimed either way.

## What this does not cover

- One line a document, one rate of tax (18%), within the state, in rupees.
  Two lines at two rates and a buyer in another state are held by the widget
  tests against the server's kept answers, on the quotation only.
- No discount on the whole document, no delivery charge and no charge on a
  line was typed: the fixture's 2% price-list discount is the only reduction.
  Those parts are in the kept answers the widget tests read.
- The customer debit note, credit note and supplier debit note show the
  taxable figure the server sends, and were not driven.
- It was run on a fixture firm and not on DEMO01.

## What the run left

On `T1010UORM-S` only, from the two runs together: the quotations, sales
orders, delivery notes, sales invoice, sales return, purchase orders, goods
receipts, purchase bill and purchase returns the flow raised, and the stock
they moved. The firm was made for this pass and holds nothing else; it was
not counted afterwards.

## Running it again

```bash
cd backend && ./.venv/Scripts/python.exe scripts/test_fixture.py selling-firm
# add a supplier named "Money Pass Supplier" to the new firm, then, with the
# desktop app closed (the flow builds and starts its own copy):
cd desktop && LIMIT=840 IT_EMAIL=<suffix>.tradeadmin@fixtures.local \
    IT_PASSWORD='Fixture@2026pw' bash integration_test/run.sh \
    money_pass_flow_test.dart
```
