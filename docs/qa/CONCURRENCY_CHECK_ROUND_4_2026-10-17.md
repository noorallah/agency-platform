# Concurrency check, round 4 -- the 15-minute soak, 2026-10-17

Item 30m, the soak. New script `docs/qa/checks/concurrency/run_soak.py`
(`--soak MINUTES`), run against the backend on localhost:8000 at main
`952eb80c`, TEST01 only, no app code changed. It reuses the sign-in, helpers
and `Firm` class of `run_concurrency.py`.

## What ran

Five signed-in desks on five threads for **15 minutes (901 s)**, each looping
on what its role does in a day, with 0.2 to 1 s between actions. Shared
masters (3 stocked items at 5,000 each, 4 customers, 1 vendor) were made at
the start. The order and delivery-note stages were switched off for the run
(counter bills) and put back afterwards.

| Desk | Does |
| --- | --- |
| Firm admin (two desks) | purchase order, submit, approve, goods receipt, complete; counter bill, approve; sales order, approve; customer save with `If-Match`; list, stock and report reads |
| Seller | types sales orders and counter bills; list reads |
| Manager | approves what the Seller left; sales order, approve; list reads |
| Accountant | receipts against approved bills (20 to 236 against 118.00 a piece, so some over-allocate on purpose); list and trial balance reads |

## Counts per action

ok = 2xx; refused = 4xx with a message; 5xx = server error or dropped call.
No 4xx came without a message, no call was refused for who the caller was
(403) and no sign-in had to be repeated.

| Action | ok | refused | 5xx |
| --- | ---: | ---: | ---: |
| sales order create | 932 | 0 | 0 |
| sales order approve | 845 | 87 | 0 |
| sales invoice create | 608 | 52 | 0 |
| sales invoice approve | 565 | 43 | 0 |
| receipt create | 381 | 209 | **19** |
| purchase order create / submit / approve | 317 each | 0 | 0 |
| goods receipt create | 317 | 0 | 0 |
| goods receipt complete | 291 | 26 | 0 |
| customer edit (If-Match) | 199 | 8 | 0 |
| list reads | 890 | 0 | 0 |
| stock reads | 117 | 0 | 0 |
| trial balance reads | 282 | 0 | 0 |
| **Total** | **6,378** | **425** | **19** |

Refusals, all named: 409 "This record changed since you loaded it. Reload and
try again." on sales order approve (87), bill create (52), bill approve (43),
goods receipt complete (26), receipt create (16) and customer edit (8); 422
on receipts: 75 "An allocated invoice does not belong to this party ... or
is already settled in full" (the soak pays bills it already paid in full) and
about 118 "Invoice ... has N outstanding, so M cannot be allocated to it"
(the intended over-allocations, refused correctly).

## After the run

| Check | Result |
| --- | --- |
| No 5xx | **FAIL** -- 19 x 503 on `POST /receipts`, D-CONC-6 below |
| No document number repeated in a series | ok -- every number read back from the server: 932 sales orders, 608 sales invoices, 381 receipts, 317 purchase orders, 317 goods receipts; 0 repeated, 0 unnumbered |
| No negative stock | ok -- 100 stock rows in TEST01, none below zero (on hand or reserved); the three soak items ended at 5,921 / 5,772 / 5,833 |
| Journals balanced | ok -- trial balance of all 45 accounting periods: total debit = total credit, `is_balanced` true |

## Defect

**D-CONC-6 (Medium, Live).** 19 of the 609 receipt calls (3 percent)
answered 503 "The database is temporarily unavailable."
The server's error log shows `DeadlockDetected` "while locking tuple in
relation customers": a receipt and a bill approval for the same customer take
the customer row and another row in opposite orders. Nothing is written and a
retry works, but the user sees a server error. Registered in `docs/DEFECTS.md`;
not fixed here.

## Notes for the next run

- The 409 "changed since you loaded it" answers on bill create, bill approve,
  sales order approve, receipt create and goods receipt complete are the
  D-CONC-1, D-CONC-2 and D-CONC-4 shape. Those fixes are listed as merged but
  "not re-run live"; this soak saw them again on the running backend, which
  may have been started before those fixes (not checked). Restart the backend at
  current main and re-run `--soak 15` to settle it. The
  messages are named, so they are not counted as failures here.
- A purchase invoice and payment leg, and a year close, are not in the soak.

## Re-run after the D-CONC-6 fix (#1687), 2026-10-17

Same script, same command (`run_soak.py --soak 15`), TEST01 only, against
the backend on localhost:8000 at main `fa43390a`. The backend processes were
created at 08:50:17, fifteen seconds after the #1687 merge (08:50:02), so
the fix was loaded. Run tag ZWNJU, 901 s, five desks.

| Action | ok | refused | 5xx |
| --- | ---: | ---: | ---: |
| sales order create | 862 | 0 | 0 |
| sales order approve | 779 | 80 | 0 |
| sales invoice create | 608 | 40 | 0 |
| sales invoice approve | 551 | 55 | 0 |
| receipt create | 400 | 169 | **0** |
| purchase order create / submit / approve | 284 each | 0 | 0 |
| goods receipt create | 284 | 0 | 0 |
| goods receipt complete | 263 | 21 | 0 |
| customer edit (If-Match) | 146 | 7 | 0 |
| list reads | 885 | 0 | 0 |
| stock reads | 96 | 0 | 0 |
| trial balance reads | 281 | 0 | 0 |
| **Total** | **6,007** | **372** | **0** |

- **503s: 0** (round 4 had 19 on `POST /receipts`). Unnamed refusals: 0.
  Re-sign-ins after a 401: 0.
- Refusals are all named: 409 "This record changed since you loaded it"
  (so approve 80, bill create 40, bill approve 55, goods receipt complete 21,
  customer edit 7) and 169 receipt 422s (33 "allocated invoice does not
  belong to this party ... or is already settled in full", 14 intended
  over-allocations, and the rest the same family). No receipt answered 409
  this time, against 16 in round 4.
- `DeadlockDetected`: none from this run. The error log
  (`backend/logs/server/errors-2026-10-17.log`) was last written at 08:33,
  before the restart, and holds only round 4's entries; the server log shows
  none. The client side agrees: no 503 anywhere.
- Numbers unique: ok -- 862 sales orders, 608 sales invoices, 400 receipts,
  284 purchase orders, 284 goods receipts, each read back, 0 repeated, 0
  unnumbered.
- No negative stock: ok -- 103 stock rows in TEST01, 0 below zero; the three
  soak items ended at 5,740 / 5,715 / 5,732.
- Trial balance: ok -- 45 periods read, 0 unbalanced.
- Script verdict: "ok: no finding", exit 0.

D-CONC-6 is therefore confirmed fixed on the running backend. The 409
answers on bill create, bill approve, sales order approve and goods receipt
complete are still seen with a restarted backend, so they are not from a
stale process; they are named and counted as refusals.
