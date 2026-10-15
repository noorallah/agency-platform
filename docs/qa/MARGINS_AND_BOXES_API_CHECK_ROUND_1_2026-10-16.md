# Lot margins (L3) and boxes and pieces (L5) -- API check, round 1, 2026-10-16

Main at `b9b7f9de` (#1601), backend already running at that head (not restarted,
migrated or reset). Fixture: `lot-firm` TEST03 (`5ed9e4ff-...`) with product
LOT-MARGIN (retail 25 / wholesale 12.5), lots TEST03-M1 and TEST03-M2, customers
LOT-R (Retailer) and LOT-W (Wholesaler); `lots/setup.py` re-run. `box_piece/setup.py`
turns on the selling and buying `box_and_piece_entry` switches on TEST03 (they stay on)
and makes product BP-BOX12 (sold and bought in BOX, 1 BOX = 12 PIECE).

## Tally

| Folder | Result |
| --- | --- |
| `python docs/qa/checks/run.py lots` | 29 of 29 clean (TC-LOT-001..022 plus 7 probes) |
| `python docs/qa/checks/run.py box_piece` | 7 of 7 clean |

New: `lots/tc_lot_015..022.py`, `box_piece/` (`_bp.py`, `setup.py`, `p_bp_01..07`).
`run.py` enumerates a folder by name, so `box_piece` needed no change.

## Findings

**No server defect.** Every first-run failure was the check or the case text:

| Case | Expected (as written) | Got | Verdict |
| --- | --- | --- | --- |
| TC-LOT-015 | product created with `goods_type_id` | 422 extra field | Goods type reaches a product through its **category**; case text corrected. |
| TC-LOT-018 step 3 | refused naming wholesale and retail | 422 "Line 1: PTS 112.00 cannot exceed the PTR 88.00 ..." | Server right, wording differs; text corrected. |
| TC-LOT-019 | user with `BATCH_UPDATE` but not `BATCH_PTR_PTS` | n/a | `BATCH_PTR_PTS` is a business feature, not a permission; the 403 is driven with the Viewer; text corrected. |
| TC-LOT-021 | taxable value field | no `taxable_amount` on the bill line | The 200.00 is `gross_amount`; check and text corrected. |
| TC-LOT-022 step 3 | bare bill line refused naming both prices | 422 "must name the document it bills" | TEST03 has order and note stages on; the check switches them off and restores them. |
| p_bp_03 | message says "pack" | "a box of this item holds 12, not 10" | Check wording only. |

## Not driven

Screen-only steps: TC-LOT-019 step 1 display, TC-LOT-020 renaming in the screen box,
TC-LOT-021 steps 2 and 4 (figures dropping on unsaved edits; print and PDF carry no
cost or margin), TC-LOT-022 steps 1-2 (the counter screen splitting after a second).
A user holding `BATCH_UPDATE` without the PTR/PTS feature was not made. Box and piece:
quotation, sales invoice from a bare line, purchase invoice/return, challan print and
the desktop cells were not driven.
