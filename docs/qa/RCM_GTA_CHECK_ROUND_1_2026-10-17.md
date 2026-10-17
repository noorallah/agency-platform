# Reverse charge on transport (GTA) bills: check round 1

2026-10-17, away-list item 28 (customer C10, backlog 158, decision A29). Driven
over HTTP against the backend on port 8000 (version 1.3.0, main at the time),
in a **new** test firm `RCM01`. DEMO01, TEST01 and the demo firms were not
touched. Scripts: `docs/qa/checks/rcm/` (`setup.py`, `setup2.py`, `setup3.py`,
`setup5.py`, `setup6.py` build the firm; `check.py` drives and prints PASS/FAIL;
`run1.log` is its output). The sign-in password is read from the loop's file at
run time and is in no script or log. The scripts hold two ids of RCM01 (head
office and warehouse) that `setup4`-style lookups would replace on a new firm.

## Firm and set-up

| Step | How | Result |
| --- | --- | --- |
| Firm | `POST /firms` RCM01, SHARED, India, FY from 2026-04-01 | created |
| GST registered, intra-state | `PUT /firms/{id}` with GSTIN `33FXRCM1234B1ZG`, state Tamil Nadu (test GSTIN with a valid check character) | saved |
| Readiness | open books, apply GST template, default branch HO (WHOLESALE profile assigned) | `can_post` true |
| Rules | `RCM_GTA_5_LOCAL` and `RCM_GTA_5_INTERSTATE` saved with status ACTIVE | active (saving made a new version; the template's version of each stays listed INACTIVE) |
| Service item | `FREIGHT-GTA` "Freight inward (GTA)", type SERVICE, SAC 996511, tax profile group `RCM_GTA_5` | created |
| Transporters | `GTA-TN` (Tamil Nadu) and `GTA-KA` (Karnataka), both Unregistered, billing address with state | created |
| Purchase stages | PO and goods-receipt stages switched off (default branch and warehouse set), so the bill is typed alone | saved |

The case (local or interstate) comes from the transporter's address state
against the firm's; no GSTIN is needed.

## Results

Two bills of Rs 10,000, one per transporter, entered on the purchase-invoice
route and approved. All 31 checks passed.

| Check | Local (TN) | Interstate (KA) |
| --- | --- | --- |
| No tax payable to the transporter (`tax_total` 0, grand total = amount owed = 10,000) | PASS | PASS |
| Self-assessed tax, every line flagged reverse charge, total 500 | PASS: CGST 250 + SGST 250 | PASS: IGST 500 |
| Self-invoice number issued | PASS `RSI-26-27-000001` | PASS `RSI-26-27-000002` (distinct) |
| Journal balanced (10,500) | PASS | PASS |
| Dr 10,000 to an expense, not stock | PASS: 5000 Purchases (EXPENSE) | PASS |
| Dr input tax | PASS: 1320 CGST 250, 1330 SGST 250 | PASS: 1310 IGST 500 |
| Cr transporter | PASS: 2100 Trade Payables 10,000 | PASS |
| Cr RCM payable | PASS: 2270 CGST 250, 2280 SGST 250 | PASS: 2260 IGST 500 |
| No stock movement | PASS (0 inventory transactions in the firm) | PASS |

GSTR-3B for October 2026 (both bills):

| Check | Result |
| --- | --- |
| 3.1(d) taxable 20,000; CGST 250, SGST 250, IGST 500 | PASS |
| 4(A)(3) CGST 250, SGST 250, IGST 500 | PASS |
| Left out of 4(A)(5) eligible credit | PASS (zero) |

GST payment, period 2026-10:

| Check | Result |
| --- | --- |
| Preview: cash 1,000 (500 + 500), every head's credit available but none used on it | PASS |
| Recorded to the Cash account | PASS: Dr 2260 500, 2270 250, 2280 250; Cr 1000 Cash 1,000 |

Debit note off the local bill, taxable 4,000 (40 percent):

| Check | Result |
| --- | --- |
| Note carries no tax of its own; approves | PASS |
| Journal takes its share of the tax off | PASS: Dr 2270 100, Dr 2280 100; Cr 1320 100, Cr 1330 100 |
| 3.1(d) falls to taxable 16,000, CGST 150, SGST 150, IGST 500 | PASS |
| 4(A)(3) falls to CGST 150, SGST 150, IGST 500 | PASS |
| Payment preview for the period falls to 800 | PASS |

## Defects and observations

None of these fails an item-28 check. Register as the owner sees fit; I did not
edit `docs/DEFECTS.md`.

- **D-RCM-1 (low), a debit note on a service bill credits Purchase Price
  Variance.** Steps: approve a bill for the service item (Dr 5000 Purchases
  10,000), then a debit note for taxable 4,000. Its journal credits **5400
  Purchase Price Variance** 4,000 (Dr 2100 Trade Payables 4,000), not 5000. Both
  accounts are EXPENSE, so profit is right, but Purchases is overstated by 4,000
  and PPV shows a variance that was a price reduction on a service.
- **D-RCM-2 (low), freight lands in "Purchases".** The brief asks for the freight
  expense; the bill debits 5000 Purchases, the same account as goods. There is no
  freight-inward account to map, so freight cannot be told from goods cost on the
  trial balance without a cost centre. Not wrong, a gap.
- **D-RCM-3 (low), a service bill with the goods-receipt stage off raises a goods
  receipt.** The draft's line shows `source_document_number`
  `GRN-RCM01-HO-2026-2027-000001`, so a service uses up goods-receipt numbers
  (no stock moved). Seen on the response only; the receipt itself was not read.
- **D-RCM-4 (low), the GST payment is not netted for a later note.** After the
  1,000 payment was recorded, the debit note cut the period's cash to 800, but
  nothing flags the 200 now overpaid (it sits as a debit balance in the RCM
  payable accounts). Fine for a return not yet filed; a person must know to
  adjust.

## Not verified

- Screens: Tax rules, product, supplier, bill and GST payment were not opened;
  only the routes the desktop calls.
- The negative case (rules left INACTIVE, so the bill is taxed as before) and a
  GTA with a GSTIN were not driven.
- The self-invoice print/PDF, a purchase return (as against the debit note), and
  cancelling a reverse-charge bill were not driven here.
- Run against the server on port 8000 as it was; no code was changed.
