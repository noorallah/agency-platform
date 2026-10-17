# Module test: Pricing (offers) -- 2026-10-18

Status: **(a) API: 11 of 12 kept checks pass on fixture firm T1016VSH1-S; 1 fails on the already-recorded D-SELL-101 (no new defect). (b) Screens: not run: screen flows blocked by permission. (c) Money check: not run: screen flows blocked by permission.**

## (a) API -- `python docs/qa/checks/run.py offers`

- Firm: T1016VSH1-S (`3c766569-...`). Accounts: Firm admin `t1016vsh1.tradeadmin`, platform admin, a Sales executive (`t1016vsh1.ofrclerk`) and a user of the custom role `ofr-no-choose-t1016vsh1` (a Sales executive less SALES_OFFER_CHOOSE, `t1016vsh1.ofrnochoose`), added by the set-up.
- Set-up for this firm: `docs/qa/checks/offers/setup_vsh1.py` (writes `.state/offers.json` from existing accounts; the older `setup.py` runs the `selling-firm` fixture and builds a new firm instead).
- Check-helper fix (not app code): `ensure_user` in `_offer.py` took the first role of that code in a platform admin's list, which can be another firm's role (same fault as D-IDN-19 / the Collections helper). It now matches the role's `firm_id`.
- Each check makes its own scene (item, customer, offers) in the firm, switches `promotion_mode` for the block and puts it back. Nothing reset or deleted.

| Case | Result |
| --- | --- |
| TC-OFR-001 candidates and reasons in the preview | pass |
| TC-OFR-002 | pass |
| TC-OFR-003 | pass |
| TC-OFR-004 | pass |
| TC-OFR-005 | pass |
| TC-OFR-006 | pass |
| TC-OFR-007 | pass |
| TC-OFR-008 part share of "11 + 1" | **fail**, step (2) only: D-SELL-101 (below). Steps (1), (3), (4) of the case pass: 6 = 5.5 + 0.5, 4 = 3.6667 + 0.3333, money 5.5 + 0.5 free, 27.50 off, taxable 522.50, GST 62.70, 585.20, and all four refusals |
| TC-OFR-009 | pass |
| TC-OFR-010 | pass |
| TC-OFR-011 | pass |
| TC-OFR-012 | pass |

Result: **11 of 12 clean, 1 failing.**

## Defects

No new defect. The one failure is **D-SELL-101** (already in `docs/DEFECTS.md`, live): `POST /api/v1/sales-orders` with a line of quantity 5.5 and `offer_choice` `{"part_share": <TEA-11 key>}` stores TEA-11 `APPLIED chosen part_share` (right) and TEA-5's 27.50 `APPLIED` with `chosen = true`; the check expects `chosen = false` (design 3.2: chosen is whether a person put it there). Prices are right. Seen again here, so it is not specific to the earlier fixture firm.

## (b) Screens
Not run: screen flows blocked by permission.

## (c) Money check
Not run: screen flows blocked by permission.
