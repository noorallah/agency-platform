# Offers chosen on the bill line -- API check, 2026-10-15

Main at `e4234673` (#1587, L7 step 9), against the backend already running at
http://127.0.0.1:8000 (not restarted). L7 step 10, cases TC-OFR-001..012 in
`docs/INDEPENDENT_TEST_CASES.md`, kept scripts in `docs/qa/checks/offers/`.

Fixture: `test_fixture.py selling-firm` (firm T1015J6O3-S, a Wholesale firm of
the run's own) and `platform-admin`, both run by `setup.py`, which also makes a
Sales executive and a user of a firm role holding the Sales executive's codes
less `SALES_OFFER_CHOOSE`. Every check makes a scene of its own (an item at
100.00, GST 12%; a customer on 2% with a price list CITY at 4%; TEA-5 and
TEA-11 of the design's worked example, each matched to that item alone), so any
check runs alone and twice. The firm's `promotion_mode` and stage switches are
changed inside a check and put back in a `finally`; read back after the run:
`COMBINE`, all three stages on. Nothing was reset, reseeded or deleted.

`python docs/qa/checks/run.py offers`: **11 of 12 checks clean, 1 failing**
(D-SELL-101), the same on two consecutive runs (about 25 seconds a run).

**All three settings were driven** (TC-OFR-007 prices one line under
`COMBINE`, `BEST_OFFER` and `ASK`; the rest run under `COMBINE`). The money
of the design's worked example came back to the paisa: step 1 (taxable 855.00,
GST 102.60, 957.60), step 2 (1,045.00, 125.40, 1,170.40), step 3 (1,056.00,
126.72, 1,182.72) and step 4 (5.5 + 0.5 free, 522.50, 62.70, 585.20).

## Per case

| Case | Result | Figures |
| --- | --- | --- |
| TC-OFR-001 candidates and reasons | pass | At 9: TEA-5 applied 45.00 "5% off", key = its `version_group_id`; TEA-11 not applied "11 + 1 free"; CITY (key = list id) 36.00 and `CUSTOMER` 18.00, "An offer gives this line its discount."; WELCOME listed unavailable (no coupon). At 11: 55.00 + 1 free. Two previews saved no order. |
| TC-OFR-002 the hint | pass | At 9: TEA-11 2 more "1 free", CITY 1 more "6% off", two hints. At 3: TEA-5 2 more "5% off", not available; no hint from TEA-11 (8 short) or CITY (7 short). Typed 0%: no hint, every candidate "A discount is typed on this line." |
| TC-OFR-003 a choice on an order line | pass | CITY + TEA-11 by a Sales executive: 44.00 from the price list, 1 free; rows CITY and TEA-11 chosen, TEA-5 REFUSED 55.00; one `sales_order.offer_chosen` audit row by him. The start sent back is stored as the server's, no audit row. |
| TC-OFR-004 refusals | pass | Typed 3% beside a choice: 422 "two answers on one line"; TEA-5 chosen at 3: 422 "Line 1: offer TEA5-... does not apply to this line any more. Choose again."; unknown offer and arrangement keys: 422; nothing saved. Preview: line 1 `choice_refused` with the same words and priced from the start (12.00), line 2's choice stands. |
| TC-OFR-005 does not combine | pass (expectation corrected, N1) | SOLO-3 (priority 5, does not combine) applied 27.00; TEA-5 after it "Does not combine with SOLO3-..."; both chosen: 422 "TEA5-... does not combine with SOLO3-..."; TEA-5 alone: 45.00, chosen, SOLO-3 passed over. |
| TC-OFR-006 without the permission | pass | Candidates listed; preview `choice_refused` names `SALES_OFFER_CHOOSE` and prices 55.00; save 403 naming it, nothing saved; the start sent back saves; the Sales executive's same choice saves. |
| TC-OFR-007 three settings | pass | COMBINE 55.00 + 1 free. BEST_OFFER: TEA-11 alone + CITY 44.00, 1 free; TEA-5 + TEA-11 chosen: 422 "the firm gives the best one offer a line"; TEA-5 alone: 55.00, TEA-11 passed over 1 free. ASK starts as BEST_OFFER; ticking both: 55.00 + 1 free, both chosen. |
| TC-OFR-008 part share | **fail** (D-SELL-101) | 6 = 5.5 + 0.5; 4 = 3.6667 + 0.3333. 5.5 with TEA-11 as part share: 0.5 free, TEA-5 27.50, taxable 522.50, GST 62.70, 585.20; TEA-11 row `part_share` true. Refusals: 5 ("PIECE is counted in whole numbers, so 5.4545 PIECE cannot be entered"), free typed, a discount offer, an offer without the switch ("cannot be billed as a part share"; no `part_share` listed). **TEA-5's row is stored chosen.** |
| TC-OFR-009 counter bill | pass | Stages off: bill preview lists and takes CITY + TEA-11; bill 44.00 + 1 free, its line carries the order line's rows; one order behind it with the same rows; TEA-11 `free_quantity_claimed` 0 before approval, 1 after. Stages on: a bill of a dispatched note with `offer_choice` on its line: 422 "what a line takes is chosen where its price is set". |
| TC-OFR-010 quotation to order | pass | Quotation preview and save take CITY + TEA-11 (44.00 + 1 free, TEA-5 passed over); send, accept, convert: the order line keeps 44.00 from the price list, 1 free, the same rows. |
| TC-OFR-011 saved rows, edit | pass | Read carries the rows; a `PUT` without `offer_choice` keeps the choice (44.00); `"offer_choice": null` returns the line to the start (55.00 + 1 free, none chosen, none passed over). |
| TC-OFR-012 reports | pass | Two approved counter bills of 11 (one chosen, one not). Discount by product: 2 lines, 2,200.00, arranged 44.00, by offer 55.00, `chosen_lines` 1, `chosen_discount` 44.00, `passed_over` 1, `passed_over_amount` 55.00. Discount by offer and product: TEA-11 2 lines 2 free; TEA-5 1 line 55.00. |

## Findings

### D-SELL-101 (Low): a choice that leaves `offers` out marks every offer the server applied as chosen

- Sent: `POST /api/v1/sales-orders`, one line of 5.5 pieces, `"offer_choice": {"part_share": "<TEA-11's version_group_id>"}` (no `offers`), under `COMBINE`.
- Came back: 201, priced right (0.5 free, TEA-5 27.50). The line's `offers` rows: TEA-11 APPLIED `chosen: true`, `part_share: true` (right), and **TEA-5 APPLIED `chosen: true`**.
- The same with `"offer_choice": {"discount_from": "<CITY's id>"}` alone: TEA-11's free piece, which the server would have given anyway, is stored `chosen: true`.
- The design (3.2): `chosen` is "whether a person put it there". Nobody chose TEA-5; the server applied it. The saved view's "chosen by a person" and anything that counts chosen rows overstate what was chosen. Prices, tax and claims are not affected.
- Where: `_judge` in `backend/app/promotions/services/offer_choice.py` -- when `choice.offers is None`, `named` is taken as every promotion row the line ended with, and each is marked chosen. Should be the part-share offer alone (and none for a `discount_from`-only choice).
- Check: `tc_ofr_008.py` step (2), left failing.

## Notes (not defects)

- **N1. An offer that does not combine ends the stack where it applies.** The
  first draft of TC-OFR-005 put SOLO-3 (does not combine) after TEA-5 and
  expected it passed over; the engine applied both (45.00 + 25.65), because
  `allow_stacking` off means "nothing after me", as the design's section 2
  says ("evaluation stops at the first that does not"). The case now ranks
  SOLO-3 first, and the refusal reads "TEA5-... does not combine with
  SOLO3-...", the shape of the design's own example. The case text was
  corrected; the server was right.
- **N2. A part share whose charged and free do not make whole pieces is
  refused by the preview too**, with 422 and the quantity's words, rather than
  reported in `choice_refused`. It is the line's quantity that is refused, not
  the choice, so the preview has nothing to price; consistent with D-SELL-91.
- **N3. A line's read does not carry `offer_choice`** (design 3.9, last
  sentence). The build chose instead that an edit leaving it out keeps the
  choice (L7 row, step 5), which TC-OFR-011 proves; the rows' `chosen` flags
  are what a screen reads. Recorded, not raised.
- **The screens were not clicked.** The side-panel block, F6, the Part share
  button, the Sales Stages setting and the offer form's switch (step 8) need a
  screen round of their own.
