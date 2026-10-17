# Concurrency check, round 2 -- 2026-10-17

Item 30m, parts 1b and 2a. Same script as round 1
(`docs/qa/checks/concurrency/run_concurrency.py`), run against the backend on
localhost:8000 after the D-CONC-1 fix (bcf36685). Accounts made the normal way
by `setup.py` (no `--adopt`): three fresh fixture users on TEST01. Scenarios e,
f and g are new; f uses a third session of the Firm admin because the Sales
manager and Seller may not edit products.

## Results

| Scenario | What raced | Result |
| --- | --- | --- |
| a | 5 bills drafted at once by 4 users, then approved at once | **ok** -- D-CONC-1 is fixed: 5 x 201 drafts, 5 x 200 approvals, numbers SI-26-27-000080..084 none repeated. |
| b | 4 receipts of 100.00 against one 118.00 bill | ok -- 1 x 201, 3 x 409; bill owes 18.00 (wording: D-CONC-2, still open). |
| c | 1 order approved by 3 users | ok -- 1 x 200, 2 x 409; 7 reserved once. |
| d | 1 customer saved by 3 users, same If-Match | ok -- 1 x 200, 2 x 409; version 1 -> 2. |
| e | 1 order cancelled by 3 users at once | ok on outcome -- always 1 x 200, no 500, reservation back to 0, order cancelled. Losers answered 409 + 409, or 422 "Reserved quantity cannot become negative." + 409: D-CONC-4. |
| f | 1 product saved by 3 users, same If-Match | **FAIL, intermittent** -- 3 runs of 5 held (1 x 200, 2 x 409, version 1 -> 2); 2 runs gave **200 + 200 + 409** and version 1 -> 3: a lost update. D-CONC-3. |
| g | 2 delivery notes of the same 7 ordered pieces: made, approved, then each dispatched by 2 users at once | ok -- the second note is refused at approval (422, "0 left to deliver of the 7 ordered"); the dispatch race gave 1 x 200, 1 x 409, 2 x 422 "Only approved delivery notes can be dispatched"; stock 100 -> 93, once. There is no bulk-dispatch endpoint (bulk is approve and cancel only), so the same note raced from two desks stands in for it. |

## Defects

**D-CONC-3 (Medium, Live).** See `docs/DEFECTS.md`. `PUT /products/{id}` with
the same `If-Match` from three sessions returns two 200s about two times in
five. Customers hold in the same race, so it is specific to the product path.

**D-CONC-4 (Low, Live).** A cancel loser sometimes hears an inventory
message instead of "already cancelled".

## Not driven

Redeeming the same loyalty points, posting vouchers into a period being
closed, last units of one batch, and the 15-minute five-user soak.
