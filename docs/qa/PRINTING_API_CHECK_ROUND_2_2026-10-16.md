# Printing, API check round 2 (2026-10-16)

Driven over HTTP against the running backend (not restarted, no reseed, no settings changed) with the kept scripts in `docs/qa/checks/printing/`, using the round-1 state file (`.state/printing.json`) and `python docs/qa/checks/run.py printing`. The backend venv has no PDF library, so the PDF text is read with `pdf_text` in `_prt.py`.

## Results

Run 1 and run 2: **14 of 14 clean, 0 failing**, both times. That is the 8 cases (TC-SELL-012, 034, 096, 098, 099, 103, 109, 113) and the 6 probes (`p_prt_paper_on_full_firm`, `p_prt_other_firm`, `p_prt_viewer`, `p_prt_bulk_unknown`, `p_prt_layout_readback`, `p_prt_default_copies`). `p_prt_default_copies`, the round-1 failure for D-PRT-1, passes on this tree: the unsaved firm's template lists three copies.

## New probe

`p_prt_trade_discounts_apart` (12 checks, passed on two runs). A counter bill of 2 x 100 with 20 off the line and 10 off the bill: the API holds line discount 20, bill discount 10, taxable 170, tax 30.60, grand total 200.60. The full-page Trade print shows Gross 200.00, Line discounts -20.00, Discount on bill -10.00 and Taxable value 170.00 as separate figures that add up (200 - 20 - 10 = 170), with CGST 15.30 and SGST 15.30. The half-page print shows "Discount on bill" and carries the bill's tax (each head 15.30). The template is put back after each print.

## Defects

No print defect. One observation on the API, not on the print:

- **Header `line_discount_total` includes the bill-discount share.** On the bill above `line_discount_total` is `30.0000` while the one line's `discount_amount` is `20.0000` and `bill_discount_amount` is `10.0000` (the line also carries its `bill_discount_amount` share of 10). The print is right (Line discounts 20.00, Discount on bill 10.00), so the header figure is 20 + 10, which its name does not say. A client that prints or shows "Line discounts" from the header would double-count the bill discount against `bill_discount_amount`. Request: `POST /api/v1/sales-invoices` with `lines[0].discount_amount=20`, `bill_discount_amount=10`, then `GET /api/v1/sales-invoices/{id}`. Expected `line_discount_total` 20 (or a name that says it holds both); got 30. Left for the owner to rule on; the probe sums the lines instead.

## Not driven

- Screens: nothing clicked; nothing sent to a printer.
- The QR image and payload, column headings repeating on page two, and stock transfer and contra voucher prints (as in round 1).
- Half-page GST summary beyond the tax heads: the summary table is not read cell by cell.
