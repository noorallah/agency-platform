# Decisions waiting for the owner

Compiled overnight on 2026-10-01 while the functional backlog was built. Each
entry says what is decided today (by convention, so the product works) and what
the owner is asked to confirm or change. Nothing here blocks the build; each is
a question only the owner, a go-live firm or its CA can answer.

## A. Confirm what was decided by convention tonight

| # | Area | Decided | Ask |
| --- | --- | --- | --- |
| A1 | Price floor (§64 row 2) | A product's minimum selling price is **per stock unit**, the unit its cost is kept in; a line sold by the box is judged on the box's share | Is per stock unit how your firms think of a minimum price, or per selling unit? |
| A2 | Price floor | Cost is one weighted average per product, so an old near-expiry batch is judged against today's average | **Parked by you** -- the near-expiry exemption (§64) waits for this discussion |
| A3 | Discount limit (§64 row 3) | Only typed discounts count; a person's limit is the largest among their roles that have one; nobody is limited until a limit is set | OK? |
| A4 | Debit note (§65 row 6) | A claim larger than what the bill still owes is refused (e.g. the bill is already paid) | Or should the excess become a supplier credit set against a later bill? |
| A5 | Debit note | The claimed value is credited to *purchase price variance*, as purchase returns post | Or a separate price-difference / purchase-returns account? Ask your CA |
| A6 | Debit note | Cancelling one needs a reason | OK? |
| A7 | PAN from GSTIN (§53) | A customer's PAN is unique in the firm, but one company has a GSTIN per state: a PAN filled from a second state's GSTIN is left blank rather than refusing that branch | Drop PAN uniqueness for customers instead? (Goes with §75 row 3) |
| A8 | 26Q (§53.1) | Exported as a workbook for the CA / RPU, not the FVU text file -- that needs challans recorded as documents (the §53.1 challan screen) | Have the CA confirm the codes (reason `C`, `PANNOTAVBL`, Act sections as stored vs the newer split codes like 194J-a/b) |
| A9 | MSME (§68 row 2) | The 15/45-day period runs from the **earlier** of the supplier's invoice date and the bill date; Medium enterprises are recorded but outside the rule; a due date past the legal date is warned, not refused | Confirm with the CA |
| A10 | GST registration type (§75 row 2) | An SEZ bill under LUT that charges tax is **warned**, not refused | OK? |
| A11 | Last rate (§55 G6) | Shown in the line's side panel ("SI-12 on 09-03-2026 · 5% off", with *Use the last price*), not as helper text under the rate | OK? |
| A12 | Messaging (§51) | Switching overdue reminders on sends one at once for **every** bill already overdue, however old | Cap it (e.g. only bills overdue under 90 days)? |
| A13 | Messaging | Real WhatsApp / SMS / email sending is proven only against fakes | Needs one firm's Meta WhatsApp account, MSG91 + DLT, and a mail app password to verify -- see `docs/MESSAGING_SETUP_GUIDE.md` |
| A14 | Party adjustments (§74 row 2) | Rounding on a receipt or payment is capped at 10.00 (per-firm setting); bank charges are a receipt's only; a write-off / write-back / set-off above 1,000.00 needs `PARTY_ADJUSTMENT_APPROVE` and someone other than its drafter | Confirm the two amounts |
| A15 | Set-off | Refused only when both parties have a PAN and they differ | OK, or require the PANs to be known? |
| A16 | TCS (206C(1H)) | Still charged on a receipt's full amount, deductions included | Low -- the section ended 1 April 2025 |
| A17 | Business profiles (§17) | A profile written at runtime -- including a seeded one's features -- is written to every store, each reported as written or failed; deleting one now answers per store | OK that editing a seeded profile changes it for every firm? |
| A18 | Reorder (§42.9) | Draft orders are grouped per supplier per warehouse; the supplier is the one last billed (there is no preferred-supplier field); with no maximum level the suggestion is only the shortfall | Add a preferred supplier per product (§69 rows 1-3)? |
| A19 | Offer cap (§59 item 3) | Over the cap, the latest-applied offer gives back first | OK? |
| A20 | Ship-to and place of supply (§67 row 3) | An unregistered buyer's place of supply follows the ship-to (IGST s.10(1)(a)); a registered buyer keeps its GSTIN's state even when goods go elsewhere (bill-to-ship-to, s.10(1)(b)) | Confirm with the CA |
| A21 | Proof of delivery (§67 row 6) | "Delivered" is a flag set only by a proof, not a new status; recording it needs `SALES_UPDATE` | OK? |

## B. Open questions the backlog already records

| # | Backlog | Question |
| --- | --- | --- |
| B1 | Firm audit trail (Also open, after §33) | Should a firm administrator read their own firm's audit trail? Today only the platform tier can. Recommended: split a firm-scoped `FIRM_AUDIT_LOG_VIEW` |
| B2 | §16 custom fields | May a firm administrator change their own business profile once trading? Refuse or convert a custom field's type change (recommended: refuse) |
| B3 | §36 onboarding | Which tools are firms coming from, and real export files from them (Tally XML import is built only against real files) |
| B4 | §70 rows 9-10 | FIFO costing as a firm option? A *warn* rather than *refuse* policy for negative stock at the counter? |
| B5 | §75 row 3 | One GSTIN or PAN on several customer accounts (branches of one company) -- allow? (Goes with A7) |
| B6 | §41 | Districts / cities / PIN codes: which source, its licence, and may the server download it |
| B7 | §42.14, §42.6, §39, §48 | Customer/vendor portal (needs outside access), salesman mobile app and field collections, phone layouts -- product direction and timing |
| B8 | Low value -- keep or drop? | §42.15 BOM / job work / recurring invoices / marketplaces; §55 G11-13, N1, N2, N7-N9; §74 row 6 fixed assets; §63 item 5 TCS 27EQ (206C(1H) ended 1 April 2025) |
| B9 | §71-73 | Sign-in/branding, menu A or B, dialog review -- **parked by you** |
| B10 | §3, §47 | A clean-machine installer test needs a spare PC; the window icon needs your `.ico` |
| B11 | §2, §43 | Licensing -- deferred by you |
