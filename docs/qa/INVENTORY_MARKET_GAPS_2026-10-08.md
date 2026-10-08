# Inventory, batches and serial numbers: compared with the market, 2026-10-08

A reading study made beside inventory round 1. "This product" is judged from
the routes the running server publishes (`/openapi.json` on `main` 099054e8)
and from the code; the other tools are judged from general knowledge of them,
not from a fresh check. **"?" means not sure**, and those cells should not be
quoted to a customer without checking. `docs/MARKET_COMPARISON.md` holds the
older, product-wide table; its inventory rows were corrected with this study.

## 1. What this product already does

| Capability | Where (server) |
| --- | --- |
| Stock by branch, warehouse and storage location (bin); summaries by firm, branch, warehouse and product | `/api/v1/inventory`, `/inventory/summary/*`, `/warehouses/{id}/storage-nodes` |
| Opening stock as a document, by hand or by file (template, check, apply all or nothing) | `/inventory/opening-stock`, `/opening-stock/import-file` |
| One-step transfer, write-off, adjustment and quarantine hold / release from the stock list | `/inventory/transfers`, `/write-offs`, `/adjustments`, `/quarantine` |
| A stock transfer as a document: dispatch, in transit, receive short or damaged, cancel, challan | `/inventory/stock-transfers` |
| The firm's own reasons for an issue, each with its expense account | `/inventory/adjustment-reasons` |
| A limit per role on an adjustment's value; above it the movement waits for approval | `/inventory/adjustment-limits`, `/adjustment-requests` |
| Physical count by location, saved in progress, posted as one journal; count plans by ABC class; blind sheets | `/inventory/counts`, `/count-plans`, `/abc-classes` |
| Repacking and bulk breaking with wastage; kits assembled, taken apart and assembled at dispatch | `/inventory/repacks`, product components |
| Batches with manufacturing and expiry dates, MRP, PTR and PTS; lots; earliest expiry first, first in first out, or picked by hand; stop-sale, alert and return-to-supplier days by product, category or firm; shelf life | `/batch-serial/batches`, `/lots`, `/sale-settings` |
| Serial numbers with warranty dates and a trail of the documents that moved each one | `/batch-serial/serials`, `/serials/{id}/trail` |
| Units and packs with their own barcodes, read wherever a document is written | `/uom-framework/barcode-lookup` |
| Moving weighted-average cost; landed cost added to stock on hand | `product_valuations`, `LANDED_COST` movements |
| Reports: stock valuation as on any day with the books beside it, the bank's stock statement, ageing with turnover, slow-moving, dead stock, free goods, expiry dashboard, returns due to the supplier, below reorder | `/inventory/reports/*`, `/batch-serial/batches/*`, `/purchases/reports/below-reorder` |
| Incoming, outgoing and projected stock; reservations that lapse; reorder planning into requisitions or draft orders | `/inventory/summary/by-product`, `/purchases/reorder-planning` |
| Stock alerts on Home; photographs and files attached to a movement or a count | `/inventory/alerts`, `/inventory/transactions/{id}/attachments` |
| Barcode labels for products and for a goods receipt | `/products/labels`, `/goods-receipts/{id}/labels` |

## 2. Comparison

Y = yes, P = partly, N = no, ? = not sure.

| # | A distributor expects | This product | Tally Prime | Marg | Busy | Zoho Inventory | ERPNext |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Several warehouses, and bins inside one | Y | Y (godowns, nested) | Y | Y | P (bins on higher plans) | Y |
| 2 | Batch, expiry, earliest expiry first | Y | Y | Y | Y | Y | Y |
| 3 | Serial numbers with warranty | Y | P | Y | Y | Y | Y |
| 4 | **A serial number follows its goods through a transfer** | **N** (D-STK-40; section 3, gap 1) | P | Y | Y | Y | Y |
| 5 | Transfer as a document with goods in transit | Y | P (stock journal; no transit) | Y | Y | Y | Y |
| 6 | Count by location, blind, by plan | Y | P (physical stock voucher) | P | P | P | Y |
| 7 | **A count typed or scanned elsewhere and brought in as a file** | N (gap 2) | Y (import) | Y | Y | Y | Y |
| 8 | Adjustment reasons with their own accounts; approval above a limit | Y | N (voucher class only) | N ? | P | P (reasons, no limit) | P (workflow) |
| 9 | Repacking, kits | Y | Y (stock journal, BOM) | P | Y | Y (composite items) | Y |
| 10 | Costing method chosen per item: FIFO, average, last purchase | P (moving average only; gap 3) | Y (many) | Y | Y | P (FIFO or average, per organisation) | Y (FIFO, average, LIFO) |
| 11 | Valuation as on a past day, with the books beside it | Y | Y | Y | Y | Y | Y |
| 12 | Bank stock statement | Y | P (from stock summary) | P ? | P ? | N | N |
| 13 | Ageing, slow-moving, dead stock | Y | Y | Y | Y | P | Y |
| 14 | Reorder level, incoming and projected | Y | Y | Y | Y | Y | Y |
| 15 | Selling below zero stock: allowed, warned or refused, as the firm chooses | P (dispatch refuses; an adjustment may go below zero; no switch; gap 4) | Y (warn) | Y | Y | Y | Y (setting) |
| 16 | Barcode labels | Y | P | Y | Y | P | Y |
| 17 | Stock freeze while a count is open | N (gap 5) | N | N ? | N ? | N | P |
| 18 | A transfer between two GST registrations of one firm billed as a supply | N here (a compliance question; gap 6) | Y | Y | Y | P | Y |

## 3. The gaps, and what was decided

Decided by the convention of the tools above, as the owner asked for every
module round; each may be overruled.

1. **Serial numbers on a transfer, and on opening stock -- needed; the next
   unit of the inventory pass builds it (D-STK-40).** Every tool that tracks
   serials moves them with the goods. Here neither transfer moves a serial's
   warehouse and a dispatch refuses a unit that is not in the warehouse it
   ships from, so a firm with a shop and a store room cannot ship a moved
   unit until somebody edits each serial by hand. Opening stock of such goods
   is a quantity, with the serials typed afterwards one by one.
2. **A count brought in as a file -- should have, backlog.** A count of
   several thousand lines is typed on the sheet today. The import framework
   (`app/common/file_import.py`) already carries six imports; this would be
   the seventh. Not a defect, and not needed to trade.
3. **Other costing methods -- not built, backlog, low.** Moving weighted
   average is one of the two methods AS 2 and Ind AS 2 allow, and the one a
   distributor's accountant expects. FIFO costing per item is a change to
   every posting module and is not asked for.
4. **A firm's switch for negative stock -- backlog, low.** Dispatch already
   refuses to ship what is not there, which is the safe convention; an
   adjustment below zero is a deliberate, recorded act (D-STK-12, kept).
5. **Freezing stock during a count -- not built.** Only ERPNext comes near
   it; the count here adjusts by difference from the quantity read when the
   sheet was opened, which is what the others do.
6. **A transfer between two registrations as a taxed supply -- for the
   compliance pass.** It belongs with the e-way bill and the tax invoice, and
   needs the accountant's reading of the firm's own registrations.
