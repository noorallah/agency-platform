# Purchasing, round 3 -- what round 2 left untested

Round 2 (2026-10-04, `PURCHASING_ROUND_2.md`) passed R2-1..R2-11. This round
gathers what is still untested in purchasing. Cases are added here as they
come up; run them in any order unless a case says otherwise.

**Setup.** As round 2: local backend on port 8000, phase 2 app, firm **QA01
"QA Traders"**, users `@qa01.test` with password `DemoAdmin@12345` (`counter@`
changed its own). Supplier `QA-V`, products `QA-B` (cost 100, GST 18%) and
`QA-B2`.

Write down every document number. Record each result as Pass / Fail with the
document number; a fail goes in `docs/DEFECTS.md`.

## R3-1 A one-person firm types only the purchase invoice (backlog §38) -- `admin@`

The buying stages are firm-wide, so this case **changes QA01's setting and
puts it back at the end**. Run it last in a sitting, or on a separate test
firm.

1. Settings (gear) > Buying > **Purchase Settings** > **Buying stages**. Note
   how they read now (both on). Switch **Purchase order** off -- **Goods
   receipt** goes off with it. Save.
2. Buy > Purchase Orders and Goods Receipts: note the newest numbers.
3. Purchase Invoices > **New**, supplier QA-V. Add QA-B, quantity **5**, rate
   **100**, supplier invoice number `R3-1-INV`. **Save & approve**.
4. Open Purchase Orders and Goods Receipts again.
5. Stock > Inventory: QA-B's quantity.
6. Settings > Buying > Purchase Settings > **Buying stages**: switch both back
   on. Save.

**Expect:**
- The invoice saves and approves without asking for an order or a receipt.
- A new **purchase order** and a new **goods receipt** appear, raised by the
  invoice, for 5 of QA-B; the receipt is **Completed**, into the default
  warehouse.
- QA-B's stock rises by **5**.
- The invoice's journal: Dr GRNI 500, Dr Input CGST 45, Dr Input SGST 45 / Cr
  Trade Payables 590; the receipt's: Dr Inventory 500 / Cr GRNI 500 -- so GRNI
  nets to 0.
- After step 6, a new invoice asks for receipts again (the full chain is
  back), and the documents made in step 3 are unchanged.

## Carried over from round 2

The test-book cases not yet run, from `docs/qa/06_PURCHASING.md`:
TC-BUY-012 (blocked input credit), TC-BUY-013 (composition supplier),
TC-BUY-017 (debit note on a paid bill), TC-BUY-014 (GSTR-2B), TC-BUY-008
(paying the supplier), TC-BUY-028 (free goods and supplier gifts).
