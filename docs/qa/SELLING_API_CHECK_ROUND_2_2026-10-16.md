# Selling, API check round 2 (2026-10-16)

Driven over HTTP against the running backend (not restarted, no reseed) with the kept scripts in `docs/qa/checks/selling/`, using the round-1 state file (`.state/selling.json`) and `python docs/qa/checks/run.py selling`.

## Results

Run 1 and run 2: **26 of 26 clean, 0 failing**, both times. A third run after the new probe was added: **27 of 27 clean, 0 failing**.

## D-SELL-104 (still open), figures now

`tc_sell_100.py` step 5 (a draft bill of 500 on stock 50). Recorded with a throwaway script on a fresh item, approval on, nothing in product code changed:

| Step | On hand | Reserved |
| --- | --- | --- |
| start | 50 | 0 |
| draft bill of 500 saved (201) | 50 | **500** |
| a second bill of 1 saved (201), then approved | 50 | 501 |
| the approve of the 1-piece bill | refused 422 "Insufficient available stock for dispatch line." | |
| both drafts cancelled | 50 | 0 |

So a draft the stock cannot cover still holds its full 500 and blocks a sale of 1 that stock could cover; cancelling the draft releases it. Behaviour is unchanged from round 1.

## New probe

`p_sell_line_discount_total` (3 checks, passed). One bill of 2 x 100 with `discount_amount` 20 on the line and `bill_discount_amount` 10 on the bill. The server returns, identical before and after approval:

- Header: `bill_discount_percent` 5.5556, `bill_discount_amount` 10.0000, `bill_discount_source` typed, `bill_discount_typed_as` amount, `line_discount_total` **30.0000**.
- Line 1: `discount_percent` 10.0000, `discount_amount` 20.0000, `bill_discount_amount` 10.0000.
- Totals: `subtotal` 170.0000, `tax_total` 30.6000, `grand_total` 200.6000.

The header `line_discount_total` holds 30, which is the line's 20 plus the bill's 10 share. Stated only; not ruled on.

## Defects

No new failure.
