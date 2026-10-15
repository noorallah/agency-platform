# Salesmen module, API check round 1 (2026-10-15)

Driven over HTTP against the running backend with the kept scripts in `docs/qa/checks/salesmen/` (`setup.py`, then `python docs/qa/checks/run.py salesmen`). Two fixture firms from `ready-firm`; every script makes its own records under a fresh tag. 17 scripts: 16 pass, 1 fails.

| Case | Result | Notes |
| --- | --- | --- |
| TC-SELL-114 | PASS | Salesman with no user saved, listed, offered, named on a counter bill. |
| TC-SELL-115 | **FAIL** | See below. |
| TC-SELL-116 | PASS | Order, note and bill refused with the switch on; quotation saves; all save with it off. |
| TC-SELL-117 | PASS | Order By on Standard and Trade; none when no salesman; still printed after the entry is deleted (a delete of an entry a bill names is refused 409, so the entry stays); none on HALF and THERMAL80. The PDF text is read from the response, `pdf_text` in `_sm.py`. |
| TC-SELL-118 | PASS | Case-insensitive name clash refused on create and on edit. |
| TC-TERR-007 | PASS | Entry accepted on a round, listed in Coverage; a user id refused with the documented words. |
| TC-INCENT-006 | PASS (case text stale) | Commission is earned on net of tax since 2026-09-24 (`docs/COMMISSION_FRAMEWORK.md`). The script asserts 420.00 and 80.00; the case text still says 495.60 and 94.40 (the tax-inclusive bases). The case text needs correcting, not the server. |
| TC-INCENT-007 | PASS | Needs three people: accrue (admin), approve (a second Firm admin), pay (not the approver). Accrual is driven per salesman, because an unfiltered accrue takes every salesman of the firm. Overlap refusal is 409, not 422. |
| TC-INCENT-008 | PASS | Sales executive gets 403 on list, approve and pay. |
| TC-INCENT-013 | PASS | Band reached 300.00, each band 350.00, both/neither slab refused 422, edit to percent clears the amount. Two salesmen stand in for "another ended month". |
| TC-INCENT-014 | PASS | Periods by start and days, 236.00/20.00 and 472.00/40.00, overlap refused, bad day counts refused. |
| p_sm_read_write_split | PASS | Viewer and executive read; add, edit, delete and restore are 403. |
| p_sm_other_firm | PASS | Another firm's salesman is 404 on read, edit and delete; refused on bill, order and quotation. |
| p_sm_inactive | PASS | Inactive is not the starting choice, not in the active list, refused on a new bill and order. |
| p_sm_delete_in_use | PASS | In use: 409 "Make the salesman inactive instead"; unused: deletes, 404, restores. |
| p_sm_required_scope | PASS | Quotation and sales return save with the switch on. |
| p_sm_order_keeps | PASS | Note and bill keep the order's salesman, not the account manager. |

## Failure

### TC-SELL-115: a customer with an account manager on a round starts on the round's salesman

- **Request:** `GET /api/v1/salesmen/starting-choice?customer_id=<C1>` as a user tied to no entry. C1 has `salesman_id` = Bala (the account manager) and is on a round whose primary salesman is Chitra (`PUT /api/v1/sales-territories/{route}/customers`).
- **Expected:** Bala (the case: "`QA-C01` starts on Bala (account manager)"; `starting_choice.py` lists the account manager before the round).
- **Got:** Chitra, `source: ROUND`. The same customer with no round answers Bala, `source: ACCOUNT_MANAGER`, so putting the customer on a round displaces the account manager.
- **Also fails:** the same answer after Asha is made inactive (the fall-through step).
- **Reproduce:** `python docs/qa/checks/run.py salesmen tc_sell_115`.

## Triage and round 2 (2026-10-15)

- **TC-SELL-115: not a server defect.** The fixture put Bala (the account manager) on no round, and the starting choice passes over an account manager who does not cover the customer's round, because he would be refused on save (decided in build step 3, #1522; `docs/design/SALESMAN_LIST_DESIGN.md`). The script now puts Bala on the round (not primary) and adds a fourth customer whose round Bala does not cover, which starts on the round's primary salesman. The case text says both.
- **TC-INCENT-006 / 007: case text corrected** to the net-of-tax figures (420.00 and 80.00), commission being earned on the sale net of tax since 2026-09-24.
- **Round 2** (`run.py salesmen`, the same backend): **17 of 17 clean.** No defect found in the module; nothing found elsewhere.
- Screens not clicked: backend verified, screens not.
