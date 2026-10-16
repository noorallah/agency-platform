# Screen cases, offers on the bill line (L7): click tests against the real server, 2026-10-16

Flow: `desktop/integration_test/sc_ofl_test.dart`. Build row L7, steps 8 and 9
(`docs/CUSTOMER_BUILD_TASKS.md`); the cases are TC-OFR-001..012 in
`docs/qa/09_PRICING_AND_INCENTIVES.md` and their HTTP halves are
`docs/qa/checks/offers/tc_ofr_*.py`.
Firm **TEST03** (*Test Fixtures Lot Firm*), the `lot-firm` fixture reused as
it stood (offers setting *Combine*, all three stages on). Users:
`t1016gxe3.lotadmin@fixtures.local` (Firm admin, holds `SALES_OFFER_CHOOSE`)
and `t1016gxe3.lotviewer@fixtures.local` (VIEWER: `SALES_VIEW`, no
`SALES_CREATE`, no `SALES_OFFER_CHOOSE`), password `Fixture@2026pw`. Window
1600x1000.

Every run makes its own scene over HTTP, as the admin, **before the app
starts**, named with the minute and the user (`1436A` = 14:36, admin) -- the
worked example of `docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md` section 1:

- item `0O<tag>` (*OL tea <tag>*) at 100.00, GST 12%, 50 pieces in MAIN by a
  posted opening stock;
- customer *OL buyer <tag>* (`OC<tag>`) on a standing rate of 2%, with his own
  price list `CITY<tag>` at 4%;
- `TEA5-<tag>` (5% off a line of 5 or more, priority 10) and `TEA11-<tag>`
  (buy 11 get 1 free, priority 20, *Allow a part share*), both on the item
  alone;
- a draft order and a draft quotation of 11 choosing CITY + TEA-11.

Every value on screen is set beside what the server returned for the same
lines (`POST .../preview`) or for the saved document.

## How to run it

From `desktop/` in Git Bash, one run at a time, each in a brand-new
`TEMP`/`TMP` folder:

```
IT_EMAIL=t1016gxe3.lotadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=580 bash integration_test/run.sh sc_ofl_test.dart
IT_EMAIL=t1016gxe3.lotviewer@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=580 bash integration_test/run.sh sc_ofl_test.dart
```

`IT_PART=order`, `refused`, `share`, `quote`, `counter`, `settings`, `promo`
or `saved` (comma separated) runs those parts; the scene is made every time.
The admin was run in two halves (`order,refused,share,quote` and
`counter,settings,promo,saved`). The viewer runs `settings`, `promo` and
`saved`. Three runs died at start-up ("did not complete",
`PathNotFoundException ... flutter_test_listener`) and were simply run again;
no `LNK1104` this time.

## Settings changed and put back

- **TC-OFR-009** turns the order and note stages off over HTTP (with HO and
  MAIN as defaults) for the counter bill, puts the settings back right after
  the save and again in `finally`. Read back over HTTP after the run: order,
  note and quotation stages **true**.
- **TC-OFR-007** sets the offers setting to *Best one, the bill maker may add
  more* (`ASK`) **on the screen**, and puts the value it read (`COMBINE`)
  back over HTTP in `finally`. Read back after the run: `promotion_mode`
  **COMBINE**, stages true/true/true, line cap null, boxes and pieces true.

## What was clicked, and the values seen

| Id | Step | Firm admin | Viewer | Screen vs server |
| --- | --- | --- | --- | --- |
| TC-OFR-002 (1) | New order, line of 9 | PASS | — | Block: TEA5 ticked "applied" 45.00; TEA11 unticked "Nothing earned on this line yet.", *Part share: 8.25 + 0.75 free*; CITY 36.00 and Standing rate 18.00 "An offer gives this line its discount."; under the quantity "2 more: 1 free". Every row as the preview |
| TC-OFR-001 (2) | Quantity 11 | PASS | — | TEA5 55.00 and TEA11 "1 free" ticked "applied"; CITY 44.00, Standing rate 22.00; hint "11 more: 1 more free" (the server's next round); server 55.00 off, 1 free |
| TC-OFR-003 (1) | CITY ticked | PASS after fix | — | CITY and TEA11 ticked, TEA5 "Not chosen on this line."; side panel "from price list CITY…"; server 44.00 off from the price list, 1 free, nothing refused. Before the fix the tick was refused and dropped (D-UI-115) |
| L7 keys | F6, arrows, Space, Enter | PASS after fix | — | F6 put focus on `sales-order-offers`; Space on TEA5 ticked it and unticked CITY; Down to CITY, Space: CITY back, TEA5 off; Enter handed focus back to the quantity box |
| TC-OFR-003 (2) | Order saved | PASS after fix | — | "Order drafted."; rows TEA11 APPLIED chosen 1 free, CITY APPLIED chosen 44.00, TEA5 REFUSED 55.00 (passed over); line 44.00 off |
| TC-OFR-004 (2)/(5) | TEA5 untick + tick at 9, quantity 3 | PASS | — | Under the block, in red, the server's words: "Line 1: offer TEA5-… does not apply to this line any more. Choose again."; the line priced from the start (12.00 from CITY); TEA5 a hint row "2 more to get 5% off" |
| TC-OFR-004 (1) | 11, CITY ticked, then 3% typed, saved | PASS | — | "A discount typed on the line decides it; clear it to choose."; every tick disabled; saved (no 422): 3% typed, no row chosen -- no `offer_choice` sent beside the typed discount |
| TC-OFR-008 (1) | Line of 6 | PASS | — | TEA11 row's button "Part share: 5.5 + 0.5 free"; server `part_share` 5.5000 + 0.5000 |
| TC-OFR-008 (2) | Part share pressed, saved | PASS | — | Quantity box 5.5; note "0.5 free from TEA11-…"; server 5.5 + 0.5 free, 27.50 off by TEA5, TEA11 APPLIED chosen part share |
| TC-OFR-010 (1) | New quotation of 11, CITY ticked | PASS | — | Before the tick as the preview; after, CITY and TEA11 ticked, TEA5 not chosen; server 44.00 |
| TC-OFR-010 (2) | Quotation saved | PASS | — | "QT-… drafted"; rows CITY and TEA11 chosen, TEA5 passed over |
| TC-OFR-009 (1) | Counter bill (stages off), 11, CITY ticked | PASS | — | As the bill preview; no bill offers listed (server `bill_candidates` empty) |
| TC-OFR-009 (2)-(3) | Bill saved as a draft | PASS | — | "Invoice created as a draft."; the bill line and the order raised behind it both carry CITY and TEA11 chosen, TEA5 passed over at 55.00; draft cancelled (200), stages put back |
| TC-OFR-007 | Settings > Selling > Sales stages > Open: offers setting | PASS | PASS | Shows *Combine offers* as the server; the admin's list holds the three settings, *Best one, the bill maker may add more* the third; read only for the viewer |
| TC-OFR-007 (5) | Third setting chosen, Save | PASS | — | Line cap box shown under it; "Sales stages saved."; server `ASK` |
| TC-OFR-007 (5) | Under ASK a line of 11 | PASS | — | TEA11 and CITY 44.00 ticked; TEA5 "Best offer only: TEA11-… was worth more (100.00 against 55.00) on line 1."; server 44.00 off, 1 free |
| TC-OFR-007 (6) | TEA5 ticked as well, saved | PASS | — | Both ticked, nothing refused; saved 55.00 off and 1 free, TEA5 and TEA11 chosen |
| L7 offer form | TEA11 opened | PASS | PASS after fix | Admin (Edit): *Allow a part share* ticked, editable, server true. Viewer (Open): the view now says "A part share may be billed: …"; before the fix it said nothing (D-UI-119) |
| L7 offer form | TEA5 (a discount) opened | PASS | PASS | No *Allow a part share* box and no part-share sentence |
| L7 step 9 | Draft order of the scene reopened | PASS after fix | PASS after fix | Admin (Edit): the block priced as saved, CITY and TEA11 ticked, TEA5 "Not chosen" (before the fix TEA5 ticked and applied, CITY not: D-UI-117). Viewer (Open): the line's Remarks read "Offers: TEA11-… · 1 free · chosen by a person; Price list CITY… · 44.00 off · chosen by a person; TEA5-… · passed over" (before: nothing, D-UI-118) |
| TC-OFR-011 (2) | The reopened draft saved unchanged | PASS | — | "Order updated."; version 4 -> 4; rows unchanged: CITY and TEA11 chosen, TEA5 passed over |
| L7 step 9 | Draft quotation of the scene opened | PASS after fix | PASS after fix | Open (no Edit on a quotation): "Line 1. Offers: TEA11-… · 1 free · chosen by a person; Price list CITY… · 44.00 off · chosen by a person; TEA5-… · passed over" (before: "11.0000 × 100.0000 less 4.0000%" only, D-UI-118) |

Tallies (last result of each step, the HTTP set-up step included): Firm
admin passed 23, failed 0, not run 3 (TC-OFR-005, 006, 012); Viewer passed 6,
failed 0, not run 4 (the same three and the read-only block). No app error and
no overflow in any run.

## Defects

| Id | Severity | Screen | What | Status | Guard |
| --- | --- | --- | --- | --- | --- |
| D-UI-115 | Medium | Offers block of the new order, quotation and counter bill | Ticking a price list (or the standing rate) while a discount offer showed ticked sent `{"discount_from": <CITY>, "offers": [TEA5, TEA11]}`; the server refuses that ("TEA5 gives a discount, and the line takes its discount from CITY. Choose one of them."), so the screen showed the refusal and dropped the choice: the worked example's choice of CITY over TEA-5 could not be made with one tick. The widget tests had pinned the wrong payload. | Fixed: `LineOfferChoice.toggle` takes the discount offers out of the set when a standing arrangement is ticked; free goods stay | `offer_choice_click_round_test.dart`: *ticking a price list over an applied discount offer … (D-UI-115)*; `offer_choice_block_test.dart` expectations corrected |
| D-UI-116 | Low | Offers block | The Gives column showed "1 free" beside an offer that gives the line nothing ("Nothing earned on this line yet.", worth 0) and "0.00" beside one out of reach; the design leaves it blank (its TEA-24 row) | Fixed: blank where the candidate is unavailable or worth nothing | `offer_choice_click_round_test.dart`: *an offer that gives the line nothing shows no Gives figure (D-UI-116)* |
| D-UI-117 | Medium | Sales order and quotation editors, a saved draft reopened | The editor priced the reopened draft from the start, without its stored choice: the block showed TEA5 ticked and applied and CITY not, the totals 55.00 off, while the saved order (and its next save, which keeps the stored choice) said 44.00 from CITY | Fixed: `LineOfferChoice.hold` reads the choice back from the line's `offers` rows (chosen rows only) and the order and quotation editors send it, so the draft is priced and saved as it was | `offer_choice_click_round_test.dart`: *a reopened draft is priced with the choice it was saved with … (D-UI-117)* |
| D-UI-118 | Medium | Sales order, quotation and sales bill views (Open) | Step 9's "applied / chosen by a person / passed over" showed only in the editor's side panel; the view a reader opens -- the only way the viewer, and anyone on a quotation, sees a saved document -- said nothing of the offers | Fixed: `savedOffersLine`; the order and bill views add "Offers: …" to the line's Remarks, the quotation view a line per document line | `offer_choice_click_round_test.dart`: *a document's view says what each line was priced with … (D-UI-118)* |
| D-UI-119 | Low | Promotions, the offer's view (Open) | *Allow a part share* is on the form only; a user without the right to edit opens the view, which did not say whether a part share may be billed | Fixed: the view says it for an offer giving free goods | `promotion_page_test.dart`: *an offer giving free goods says on its view whether a part share may be billed (D-UI-119)*, *a discount offer says nothing of a part share (D-UI-119)* |

Observations, not registered:

- Unticking the one discount offer after ticking it leaves `discount_from`
  `offers`, so the line takes no discount at all (CITY and the standing rate
  "Not applied."). Consistent with "the person chose offers", but a bill
  maker may expect the standing arrangement back.
- The hint under the quantity at 11 reads "11 more: 1 more free" -- the
  server's next round, inside the rule (no more short than the quantity
  typed), but long for a line that already earned its free piece.
- `openSetUp(tester, 'sales/promotions')` in `integration_test/harness.dart`
  no longer reaches Promotions (Settings now opens one screen per subject:
  section *Pricing* > *Pricing* > the *Promotions* tab), so `sc_of_test.dart`
  will fail at its first step; this flow navigates by the subject tabs.
- D-SELL-101 (a part share leaves TEA-5 marked chosen) was not checked on the
  screen.

## Not clicked

- The read-only block for a user who may sell but lacks
  `SALES_OFFER_CHOOSE` (TC-OFR-006): TEST03 has no such user, and the viewer
  cannot raise a document. Covered by `offer_choice_block_test.dart`
  (*without SALES_OFFER_CHOOSE the block is read-only*).
- TC-OFR-005 (SOLO-3, an offer that does not combine) and TC-OFR-012 (the
  discount reports): HTTP (`tc_ofr_005.py`, `tc_ofr_012.py`).
- The bill's offers under the totals with a bill-level offer present: the
  scene has none, and the note was checked only as absent with an empty
  `bill_candidates`.
- A draft counter bill reopened, a converted quotation (TC-OFR-010 (3)) and a
  bill of a delivery note; the bill view's "Offers: …" was built but not
  clicked.
- The tax invoice print ("Offer: TEA-11"): the printing round.
- The 800x600 layout.
