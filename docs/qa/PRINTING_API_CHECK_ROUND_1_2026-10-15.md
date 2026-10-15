# Printing, API check round 1 (2026-10-15)

Driven over HTTP against the running backend with the kept scripts in `docs/qa/checks/printing/` (`setup.py`, then `python docs/qa/checks/run.py printing`). Two fixture firms from `ready-firm`; every script makes its own product, customers and bills under a fresh tag and puts the firm's print template back as it found it. The PDF text and the page sizes are read from the response bytes (`pdf_text`, `pages` in `_prt.py`; no PDF library is installed, so the page size is the `/MediaBox` of each page: A4 is 595 x 842, a half page 595 x 421). 14 scripts: 8 cases and 6 probes.

| Case | Result | Notes |
| --- | --- | --- |
| TC-SELL-012 | PASS | Two labelled copies, CGST/SGST, HSN, HSN summary, amount in words; a Viewer's save is 403. An unconfigured firm prints three copies (see D-PRT-1 for what the template says). |
| TC-SELL-034 | PASS | `shop` refused, `shop@upi` saved; "Scan to pay by UPI", the UPI ID and the amount owing on A4, half page and roll; part paid asks for the rest; paid and draft print none. The QR image and its payload are not exposed by the API, so they are not checked here (the link is built in `upi_qr.py:29-56`). |
| TC-SELL-096 | PASS | Three bills: one PDF, nine pages, the order of the list (and reversed), same pages as the singles; Viewer allowed; roll refused naming the roll and "one at a time"; an id named twice prints once; challan run prints and refuses an unknown id. |
| TC-SELL-098 | PASS | The firm's valid DGL and FSSAI numbers print above Billed to, the one that ended yesterday does not, the buyer's number prints under Billed to; same on A4, half page and Trade. The warn/block steps (approval) are not part of this print round. |
| TC-SELL-099 | PASS | Short bill: three half pages; 60 lines: A4 pages with the HSN summary; customer on A4 prints full pages on a half-page firm; bulk run keeps each bill's own paper in list order; on an A4 firm the customer's half page is not read. Column headings repeating on the second page and the printed column list are not checked. |
| TC-SELL-103 | PASS | Switch off: 118.00, one Rate column. Switch on: order and bill 100.00, "Rate incl. GST" beside Rate 84.75 on the order, bill and quotation, challan 84.75; the three-line order 648.30; 10% off 90.00 and 20 off 180.00. The switch is a field of the document (`rate_includes_tax` on the order and quotation), not only the firm setting. |
| TC-SELL-109 | PASS | `/print/paper` on A4 and half-page firms, with customer paper, a long bill and a bulk run; `paper=HALF` on an A4 firm is refused with the documented words; the choice is for one print only. |
| TC-SELL-113 | PASS | Preview draws a SAMPLE PDF with the typed terms and the trade columns and saves nothing; a bill prints Standard until Trade is saved, then boxed with Net Payable 118.00 and D.Price 118.000; on half pages the saved Trade is not used; a delivery note cannot be saved as Trade. Stock transfer and contra voucher prints (step 6) are not driven here. |
| p_prt_paper_on_full_firm | PASS | `paper=HALF` is 422 on A4, A5 and roll firms; `/print/paper` offers no choice. `paper` is case-sensitive (`a4` is 422): by design, it is a literal. |
| p_prt_other_firm | PASS | Another firm's bill is 404 on print, print with paper, `/print/paper` and bulk print; another firm's id in the header is 403. |
| p_prt_viewer | PASS | A Viewer prints, asks the paper, runs a bulk print and draws the Preview; cannot save settings (403). |
| p_prt_bulk_unknown | PASS | Unknown id 404 (a run with one unknown prints nothing), empty list, 101 ids, malformed id, extra field, no body all 422. |
| p_prt_layout_readback | PASS | Layout saved and read back; unknown layout, paper, margin under 5 mm, five copies and a bad colour refused; the UPI ID is trimmed and a blank clears it. |
| p_prt_default_copies | **FAIL** | D-PRT-1 below. |

## Defect

### D-PRT-1 (Low): an unconfigured firm's print template lists no copies, though its bills print three

- **Request:** `GET /api/v1/document-framework/print-templates/SALES_INVOICE` for a firm that never saved print settings (`is_customised: false`).
- **Expected:** the three copies a bill of that firm prints (ORIGINAL FOR RECIPIENT, DUPLICATE FOR TRANSPORTER, TRIPLICATE FOR SUPPLIER).
- **Got:** `copy_labels: []`. The same firm's bill prints three copies (`DEFAULT_COPIES` at `backend/app/sales_invoice/services/invoice_print_service.py:73`, used as the fallback at line 565), so the template and the print disagree.
- **Effect:** a client that reads the template and saves it back (as the check helper first did) writes `[]`, which the template defines as "prints the original alone" (`backend/app/document_framework/schemas/document_framework.py:414`), and the firm goes from three copies to one without anybody choosing it. It cost this round two fixture rebuilds. The desktop prefills the labels itself, so the screen is safe; any other client is not.
- **Cause:** `PLATFORM_DEFAULTS` returned by `DocumentPrintTemplateService.get` for a firm with no row carries the schema default `copy_labels = []` (`backend/app/document_framework/services/print_template_service.py:46`, schema default at `document_framework.py:415`); the print side substitutes its own default. One of the two should hold the three labels.
- **Reproduce:** `python docs/qa/checks/run.py printing p_prt_default_copies` (reads firm two, which no other check changes; run `setup.py` again if it says firm two is customised).

## Judged by design

- `paper=a4` in lower case is 422: the query is a literal `HALF` or `A4`.
- A firm on A4 does not read a customer's Bill paper, and `/print/paper` then gives `customer_paper: null` (owner, 2026-10-13/14).
- A bill typed at the counter with the order and note stages off still shows a Delivery note and Sales order line on its print: the chain raises the stages that are switched off (`docs/SALES_CHAIN_RULES.md`).
- The order line stores the rate before tax in `unit_price` (84.7458) and the typed rate in `entered_rate` (100).

## Triage and round 2 (2026-10-15)

- Round 1 (first run): 7 of 13 clean. All six failures were the scripts or the fixture: customer update needs its required fields, the switch "Rate includes GST" is a field of the document, the wrapped column heading "Rate incl.\nGST" needed whitespace folded, the case's "rate as typed" lives in `entered_rate`, `paper=a4` is by design, and the helper saved `[]` copies (D-PRT-1) which made later checks read one copy. The last of these is the one backend finding.
- Round 2 (after the script fixes and a fresh `setup.py`): 13 of 13 clean, then `p_prt_default_copies` added for D-PRT-1: 13 of 14, the one failure being the defect.
- Case text: TC-SELL-103 step 2 "the order line shows the rate 100 as typed" holds for `entered_rate`; the line's rate is 84.75 after tax is taken out. No server change needed. TC-SELL-012 says the copy labels "prefill"; the server's template for an unsaved firm is empty (D-PRT-1).
- Screens not clicked: backend verified, screens not. Nothing was put through a printer.
