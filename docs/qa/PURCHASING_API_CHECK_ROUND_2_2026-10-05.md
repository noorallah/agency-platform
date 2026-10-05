# Purchasing: checked through the API, round 2, 2026-10-05

Round 1 is `PURCHASING_API_CHECK_2026-10-05.md` and is left as it was. This
round was driven after the fifteen defects of round 1 were fixed and merged
(`main` at `270cd500`, stores at `20261005_0327`, backend restarted on it).
Same method: the real server over HTTP, fixture firms only, books read back
through the API, nothing read from the database, no application code touched.
The scripts are the round 1 scripts, re-run from `scratchpad/buying2/` with
their logs beside them (`q2.py` re-drives the defects, `b01.py` to `b10b.py`
the cases, `x2.py` to `x5.py` the regression hunts, `g01.py` and `r01.py` the
generic and books checks; `cmp.py` diffs a log against its round 1 twin).

| | Round 1 | Round 2 |
| --- | --- | --- |
| Pass | 74 | **76** (021 and 075 now pass) |
| Fail | 2 | **0** |
| Differs (case text) | 7 | 7: 006, 009, 022, 023, 025, 030, 035 (the case file has not been edited yet) |
| Partly | 8 | 8: 019, 020, 024, 032, 054, 062, 068, 084 |
| Not driven | 1 | 1: 055 |

**All fifteen round 1 defects are fixed.** No regression was found in any of
the 92 cases: every line of every round 2 log matches its round 1 line except
where a fix was meant to change it. Four new findings came out of the
regression hunt, none caused by the fixes: BUYQ-16 to BUYQ-19 below.

The backend did not stop answering and was never restarted. Free memory fell
to 0.35 GB by the end; see "Not verified" for what that seems to have done to
large list reads.

**Where the data went.** `TEST01` for the cases on the buying fixtures, and
firms of this round's own: `T100517LD-G` (`compliance-firm`), `T1005498P-R`
(`ready-firm`), `T1005NDZH-E` and `T1005ZZT4-E` (`electronics-firm`),
`T10050UOS-P` (`pharma-firm`).

## The round 1 defects, driven again

Each on a fresh fixture, by its original reproduction (`q2.py`, `q2.log`).

| Id | Result | What it does now, with the data used |
| --- | --- | --- |
| BUYQ-1 | Fixed | `po-approved` t1005g0tu and t1005thu7. Pass 6, reject 4 for return: sellable 6, quarantine 4. Return of the 4 naming QUARANTINE (PR-2026-2027-000031) and, on the second fixture, naming no condition at all (PR-2026-2027-000034): **sellable 6, quarantine 0**; the movement reads `current_quantity_delta` 0, `quarantine_quantity_delta` -4. Two more named QUARANTINE with none held: refused at completion "This location holds 0.0000 in quarantine, so 2.0000 cannot be returned from it." An ordinary return of one passed unit takes sellable 6 to 5; cancelling each return puts its own bucket back (5 to 6; quarantine 0 to 4) |
| BUYQ-2 | Fixed | `po-received` t10059k5b and t1005hgur: 10 received, 9 sold. Return of 3: refused at completion "This location holds 1.0000 available, so 3.0000 cannot be returned to the supplier from it."; stock stays 1. Return of 1 completes (0 left). `po-received` t1005s1q1 with the product set `allow_negative_stock`: a return of 2 with 0 on hand completes at -2, as the fix says it should |
| BUYQ-3 | Fixed for new documents | New requisitions are `PRQ-2026-2027-000001` (T1005498P-R) and `PRQ-2026-2027-000026` (TEST01); returns stay `PR-…`. The four requisitions TEST01 already held keep their `PR-` numbers (000016, 017, 024, 025) beside the returns of the same number: nothing renumbers old rows |
| BUYQ-4 | Fixed | Landed cost LCV-2026-2027-000001 (T1005498P-R) and LCV-2026-2027-000005 (TEST01) post under their own number; Bill of Entry under `BOE-2026-2027-000001`; a refund's reversal is `PR-2026-2027-000042-RF1-REV`. Cancelling the landed cost and the Bill of Entry still finds the journal and mirrors it (`…-REV` POSTED, the original REVERSED) |
| BUYQ-5 | Fixed | `po-invoiced` t1005f08x and t1005tc8n. Bill paid 708.00, return of 2 (236.00), refund of 100: the statement lists `REFUND PR-2026-2027-000042-RF1` and closes **-136.00**; payables for the supplier -136.00, books check difference 0.00. Refund reversed: a `REFUND_REVERSAL …-RF1-REV` line, closing -236.00, still 0.00 difference. `GET /vendors/{id}/balance-confirmation` answers a PDF |
| BUYQ-6 | Fixed | T1005498P-R: a bill line sent with no unit is stored with the receipt line's (`purchase_uom_id` and `invoice_uom_id` both PIECE); the HSN summary row reads unit PIECE. TEST01's HSN row for a product of its own: PIECE. Bills approved before the fix still show a blank unit |
| BUYQ-7 | Fixed | T1005498P-R, `PUT /finance/tds-sections/settings/194C` with a null `rate_percent`, `annual_threshold_amount`, `lower_rate_percent`, `rate_without_pan_percent` or `is_enabled`: 422, each in its own words ("The rate cannot be blank: leave it out to keep what is saved."). `{}` saves. A null `single_threshold_amount` on 194J, which is lawful, saves |
| BUYQ-8 | Fixed | T1005498P-R, number `ab8337223` at INMAA1: a second draft is refused **at save** while the first is a draft and again once it is posted, "Bill of Entry ab8337223 at INMAA1 on 2026-10-05 is already BOE-2026-2027-000001."; the same typed `AB8337223` / `inmaa1` is refused; editing another draft onto the number is refused; after the first is cancelled the number saves again. TEST01 (`po-received` t1005jaq4, 4613771): second save refused the same way. TC-BUY-075 step 3 on T100517LD-G: refused at save |
| BUYQ-9 | Fixed | T1005498P-R and T1005ZZT4-E, stages off: "A bill in USD needs its exchange rate: the rupees one USD was worth on the bill's date." An order with no rate still says "A purchase order in USD needs…", which is right for an order |
| BUYQ-10 | Fixed | Capital-goods bills PI-T1005498P-R-HO-2026-2027-000003, PI-2026-2027-000142 (TEST01) and PI-T1005ZZT4-E-HO-2026-2027-000002: four journal lines, Dr 1500 36,500.00, Dr 1320 3,285.00, Dr 1330 3,285.00 / Cr 2100 43,070.00, and no line on 2300. The cancel mirrors the four |
| BUYQ-11 | Fixed | T1005498P-R. Order line of 0 with nothing free: 422 "Line 1 orders a quantity of 0 and nothing free. Type a quantity, or leave the line off the order."; the same as the second line of a good order names line 2. Receipt of 0, bill of 0 (off a receipt and typed alone), return of 0: 422 in the same pattern. Rate contract at rate 0: "A rate contract line needs a rate above 0: the price agreed for one unit." Quote at rate 0: "A quoted rate is above 0. Leave out a line the supplier did not quote." **An order line of 0 ordered with 2 free still saves** |
| BUYQ-12 | Fixed | T1005498P-R. Bill, return and requisition: `ETag` on POST, GET and PUT; a PUT with the stale tag answers 409 "This record changed since you loaded it. Reload and try again."; with the current tag, or with none, 200. `GET /purchases/requisitions`: 20 rows by default with `pagination` (23 records, 2 pages); `page_size=100000` 422; page 2 returns the last 3 |
| BUYQ-13 | Fixed | T1005498P-R and T100517LD-G, USD bill of 1,000 at 83 revalued at 85 as of today: `books_check` reads `difference` 0.00, `unrealised_revaluation` 2,000.00 and the note "The account includes 2000.00 of unrealised exchange revaluation on this date, reversed the next day; the bills are shown at the rate they were booked at." Two days on: no note, 0.00. Narrowed to the supplier: 83,000.00 both sides |
| BUYQ-14 | Fixed | A `ready-firm` (T1005498P-R) was provisioned from the running server; `logs/server/server-2026-10-05.log` and `uvicorn-run.log` both went on growing, and a request made after the provision (`GET /vendors?search=qa-marker-1FDF`) is in `uvicorn-run.log`. Later requests of this round are in the server log with their durations |
| BUYQ-15 | Fixed | T1005498P-R: a requisition line naming TEST01's supplier, or an id that is nobody's, answers 422 "Unknown supplier(s): …" on create and on update |

## The 92 cases again

Figures are the round 1 figures unless a cell says otherwise; the documents
are this round's. "As round 1" in the last column means the log matched line
for line.

### Cases 001 to 028

| Case | Fixture and documents this round | Result |
| --- | --- | --- |
| TC-BUY-001 | `buy-ready` t1005wpe8, PO-TEST01-HO-2026-2027-000230: draft 1,180.00; approve on a draft 422; submit, approve; no journal, no stock | Pass |
| TC-BUY-002 | `po-approved` t1005cnwg: edit withdraws the approval, `status` in the body ignored, re-approved | Pass |
| TC-BUY-003 | `po-approved` t1005ah2g, GRN-…-000174 (4) and 000175 (6): 400.00 and 600.00 to 1200 / 2300; one more refused | Pass |
| TC-BUY-004 | `po-received` t10058t25, GRN-…-000176 cancelled: -4, `-REV` journal, order PARTIALLY_RECEIVED | Pass |
| TC-BUY-005 | `po-invoiced` t1005se7e, GRN-…-000179: cancel refused, version unchanged | Pass |
| TC-BUY-006 | t10058t25, PR-2026-2027-000045: Dr 2300 200.00 / Cr 1200 200.00, total 236.00 | Differs, as round 1 |
| TC-BUY-007 | `po-approved` t10059mas, PO-TEST01-HO-2026-2027-000239: register (239 rows), not yet received (32), by supplier and by product each list it once; overdue and by buyer answer 200 with no rows | Pass |
| TC-BUY-008 | t1005se7e, PI-2026-2027-000084 paid by PY-2026-2027-000026, 708.00 | Pass |
| TC-BUY-009 | `po-received` t1005zn44, PR-…-000046: no credit, refund refused. `po-invoiced` t1005e29t, PR-…-000047: refund 100 (`…-RF1`), over-refund and cancel refused, reversal now referenced `PR-2026-2027-000047-RF1-REV` | Differs, as round 1 (fixture) |
| TC-BUY-010 | `po-received` t1005xgpp, PR-…-000048: REPLACEMENT reopens, CREDIT closes, 2 more received | Pass |
| TC-BUY-011 | `po-invoiced` t100505jb, PR-…-000049 credit 236.00 applied to PI-…-000087 (354.00 left); delete refused | Pass |
| TC-BUY-012 | `buy-ready` t100599m9, PI-…-000088 (Dr 5450 180.00) and 000089 (eligible). 3B on T100517LD-G, PI-T100517LD-G-HO-2026-2027-000001: eligible 90 + 90, blocked 90 + 90, net 0 | Pass |
| TC-BUY-013 | `buy-ready` t10051ckh, composition supplier with GSTIN 29ABCDE6084F1Z5, PI-…-000094 300.00, no tax; UNREGISTERED with a GSTIN refused | Pass |
| TC-BUY-014 | T100517LD-G, PI-…-000002, 000003, 000004: MATCHED, DIFFERENT, NOT_IN_BOOKS; match and undo; MATCHED_ONLY holds back 72 + 72 | Pass |
| TC-BUY-015 | T100517LD-G: SALES basis, avg/day 1, level 14, maximum 44, suggested 34; draft PO-…-000005 | Pass |
| TC-BUY-016 | `po-invoiced` t10056cc9, PR-…-000050: to bill 4, then 0; complete; typed quantities refused | Pass |
| TC-BUY-017 | `buy-ready` t10051v57, PI-…-000092 (paid), 000093 (590.00), DBN-TEST01-HO-2026-2027-000007: credit 118.00, 472.00 left, cancel restores; refund of 50 on DBN-…-000008 blocks its cancel | Pass |
| TC-BUY-018 | T100517LD-G: preferred supplier at 90.00, fallback at 100, inactive refused | Pass |
| TC-BUY-019 | T100517LD-G, PO-…-000008 and the `b03b` orders: list 90 over catalogue 80 over product 100; standing 5%; hint, WARN, REFUSE; lead time | Partly, as round 1 |
| TC-BUY-020 | `po-approved` t1005sjbq. Requisitions **PRQ-2026-2027-000027 and 000028**; orders PO-…-000156 (V) and 000157 (V2) carry the PRQ number as reference; amend keeps APPROVED at revision 1 | Partly, as round 1; the number is now its own |
| TC-BUY-021 | `po-approved` t1005221s. GRN-…-000217: pass 6, write off 4 (Dr 5500 400.00). GRN-…-000218: pass 6, 4 kept for return; PR-2026-2027-000052 returns them: **sellable 12, quarantine 0**. GRN-…-000219 cancelled on hold: quarantine back to 0 | **Pass** (was Fail) |
| TC-BUY-022 | T100517LD-G, PI-…-000009 and PO-…-000025: a custom-role approver is refused over tolerance (403, bulk REFUSED) and over budget under NEEDS_APPROVAL; the Purchase Manager approves PI-…-000006 | Differs, as round 1 |
| TC-BUY-023 | `po-invoiced` t1005g6sj, PRN-2026-2027-000004, PY-…-000030 and 000031; bank file refused for the supplier with no account. `buy-ready` t1005lti0, PRN-…-000006: CSV, one row | Differs, as round 1 |
| TC-BUY-024 | `po-received` t1005yupo and `po-invoiced` t1005r5py: performance row, price trend, ratings 1 to 5, own rating deleted | Partly, as round 1 |
| TC-BUY-025 | `po-invoiced` t100570nn: accrual refused before the period ends. `buy-ready` t1005pln8, PI-…-000104 dated 2026-10-04: accrue 12.00, reverse, accrue `-2`, settle by party adjustment | Differs, as round 1 |
| TC-BUY-026 | `po-received` t10052z2q, voucher LCV-2026-2027-000006, journal **`LCV-2026-2027-000006`**: Dr 1200 600.00, Dr 5200 400.00 / Cr 5210 1,000.00; cancel mirrors it (`…-REV`). t10054z3e, LCV-…-000008: valuation 600.00 to 1,200.00 and back | Pass |
| TC-BUY-027 | `buy-ready` t1005c5vx, opening bill OB-00002, PR-…-000051: 200 applied, 300 left, delete refused, cancel gives the 236.00 back | Pass |
| TC-BUY-028 | `po-approved` t100573se and t1005tfq3, GRN-…-000210, WO-2026-2027-000005 and 000006: free-issue refusals, 6940, the free goods report, gifts and 194R | Pass |

### Cases 029 to 053

| Case | Fixture and documents this round | Result |
| --- | --- | --- |
| TC-BUY-029 | `po-invoiced` t1005cz9d, PI-2026-2027-000105: register row 600.00 / 54.00 / 54.00 / 708.00; draft PI-…-000106 absent, approved present, cancelled absent | Pass |
| TC-BUY-030 | Same fixture: product of its own with HSN 84346685: quantity 6, 600.00, 108.00, bills 1, **unit PIECE**. The fixture's product still has no HSN and sits in the blank-HSN row | Differs, as round 1 (the fixture product); the unit is fixed |
| TC-BUY-031 | `po-received` t1005w09q, PI-…-000109: not claimable 108.00, Dr 5450 108.00 | Pass |
| TC-BUY-032 | `po-invoiced` t1005fu2v, DBN-TEST01-HO-2026-2027-000009, PR-…-000054 (billed), 000055 (unbilled, not listed) | Partly, as round 1 |
| TC-BUY-033 | `po-invoiced` t1005ibt9: 708.00 in October; narrowed, books check 0.00 (`unrealised_revaluation` 0) | Pass |
| TC-BUY-034 | Same, PY-…-000034 of 200.00: Owed 508.00, Paid 200.00; branch note; Paid with a branch 422 | Pass |
| TC-BUY-035 | `po-received` t1005smrg, PR-…-000056 off the unbilled receipt: no credit; PI-…-000112 708.00 | Differs, as round 1 |
| TC-BUY-036 | `po-received` t1005y4ln, PI-…-000113 approved with Paid now, PY-…-000036 708.00 cash | Pass |
| TC-BUY-037 | `po-received` t10050u25, PI-…-000114: 800 refused and the bill stays DRAFT; 300 by bank (PY-…-000037), 408.00 left | Pass |
| TC-BUY-038 | t1005y4ln: PY-…-000036 reversed, the bill APPROVED and owing 708.00 | Pass |
| TC-BUY-039 | `po-received` t10059tfa, PI-…-000115: the Purchase Manager's Paid now 403 with the case's words | Pass |
| TC-BUY-040 | `po-invoiced` t1005sy28: PDF and PNG attached, count 2 then 1, audit rows | Pass |
| TC-BUY-041 | Same bill: wrong name, wrong contents, over 10 MB all 422 | Pass (size wording, see corrections) |
| TC-BUY-042 | `po-received` t1005w0aw: file on a completed receipt; Read Only reads only; Warehouse adds | Pass |
| TC-BUY-043 | `buy-ready` t1005i3yu, PI-…-000118: 194C 2%, 800.00, owes 46,400.00; 28,000 + 5,000 charges proposes 660.00 | Pass |
| TC-BUY-044 | `buy-ready` t1005mc41, PI-…-000120, 121, 122: nothing, 800.00, 1,400.00 | Pass |
| TC-BUY-045 | `buy-ready` t1005er2f, PI-…-000123 to 126: 8,000.00 with no PAN; 400.00 for an individual and for P / H PANs | Pass |
| TC-BUY-046 | `buy-ready` t10053uxo, PI-…-000127, 128: nothing, then 3,500.00; technical 800.00 | Pass |
| TC-BUY-047 | `buy-ready` t1005i04p and t1005seut, PY-…-000038 (advance with TDS 1,000), PI-…-000130: nothing proposed; PY-…-000040 applied to PI-…-000140 leaves 9,000.00 | Pass |
| TC-BUY-048 | `po-received` t1005z85q, PI-…-000131, 132: 0 typed; 500 typed against 1,600.00 proposed; total refused; no section refused; audit keeps the override | Pass |
| TC-BUY-049 | T100517LD-G: defaults, saves, refusals; **a null rate now answers 422**; 194J off proposes nothing | Pass |
| TC-BUY-050 | `po-received` t1005kd5t, PI-…-000135: TCS 0.71, owes 708.71, Dr 1430 0.71 | Pass |
| TC-BUY-051 | `po-received` t1005njl9, PI-…-000137: 1.00, 0, 0.71 | Pass |
| TC-BUY-052 | `po-received` t1005uk9m, PY-…-000039 of 709.00; the cancelled bill's TCS mirrored | Pass |
| TC-BUY-053 | t1005kd5t: row Q3 2026-27, 708.00 / 0.1 / 0.71; the quarter total on TEST01 is now 2,124.00 / 2.42 because round 1's bills are in it | Pass |

### Cases 054 to 092

| Case | Fixture and documents this round | Result |
| --- | --- | --- |
| TC-BUY-054 | T100517LD-G: messaging off refused; on with no account refused; the channel cannot be enabled without a passed Test | Partly, as round 1 |
| TC-BUY-055 | | Not driven (no WhatsApp account) |
| TC-BUY-056, 057 | `buy-ready` t1005r98y, RFQ-2026-2027-000005: 95.00 lowest, 96.00 chosen with a reason, PO-TEST01-HO-2026-2027-000210 at 96.00, RFQ CLOSED | Pass |
| TC-BUY-058 | `buy-ready` t1005uf2l, RFQ-…-000006 from requisition **PRQ-2026-2027-000029**; second start refused naming both; requisition ORDERED | Pass |
| TC-BUY-059 | `buy-ready` t1005pun2: Read Only reads; Warehouse 403; Purchasing raises | Pass |
| TC-BUY-060, 061 | `buy-ready` t1005oe5b, RC-2026-2027-000010, PO-…-000213: 90.00 from the contract; drawn 15 / 5, then 25 / 0 with the warning, then 10 / 10 | Pass (see BUYQ-17 for the number) |
| TC-BUY-062 | Same: overlap, ended contract (RC-…-000013), edit, close, delete, cancel | Partly, as round 1 |
| TC-BUY-063, 064 | `electronics-firm` T1005NDZH-E, GRN-…-000003: range, short receipt refused, three units; duplicates refused four ways | Pass |
| TC-BUY-065 | T1005NDZH-E and T1005ZZT4-E (GRN-…-000001): cancel removes units; a sold unit blocks the cancel; returns name units; cancel puts the unit back | Pass |
| TC-BUY-066, 067, 069 | `buy-ready` t1005jjjp, PO-…-000217 (25 + 4 free, 29 on hand, 2,500.00 to stock), 000218 to 221; overlap and all-suppliers rules | Pass |
| TC-BUY-068 | `buy-ready` t10054eoj, PO-…-000224: the gift line of 0 ordered and 2 free still saves after BUYQ-11 | Partly, as round 1 |
| TC-BUY-070 | T100517LD-G, PO-…-000031, GRN-…-000012, PI-…-000011: 83,000.00 through 1200, 2300 and 2100 | Pass |
| TC-BUY-071 to 073 | PI-…-000012, 013, 014; PY-2026-2027-000002, 003, 004: loss and gain of 1,000.00; part payment and reversal; the five refusals | Pass |
| TC-BUY-074 | PI-…-000015, BOE-2026-2027-000001 (number 5392622): duty 9,350.00 to stock, IGST 16,983.00, average 9,235.00 | Pass |
| TC-BUY-075 | BOE-…-000002 (5832917): typed BCD, 5,940.00 / 3,960.00; cancel of the first; **the duplicate is refused at save** "Bill of Entry 5832917 at INMAA1 on 2026-10-05 is already BOE-…"; Purchasing cannot post | **Pass** (was Fail) |
| TC-BUY-076 | PI-…-000011: revaluation loss 2,000.00, second run refused, paid at 84 (PY-…-000001) | Pass |
| TC-BUY-077 | `buy-ready` t1005tgkv, PO-…-000227, GRN-…-000274, PI-2026-2027-000142, FA-00003: no stock, four-line journal | Pass |
| TC-BUY-078 | `po-received` t1005n33w (GRN-…-000273 refusal); t1005tgkv: cancel takes FA-00003 off; delete and cost refused | Pass |
| TC-BUY-079 to 081 | T100517LD-G, FA-00001, FA-00002, DEP-00001 (294.50, 1,240.00, 1,534.50); disposals -1,205.50 and +740.00; DEP-00003 cancelled; 25% block 40,000 / 40,000 / 15,000 / 65,000; permissions | Pass |
| TC-BUY-082 to 084 | `pharma-firm` T10050UOS-P, batch QA-PTR-1: 120 / 90 / 80, then PTR 92; caps; Retailer 92, Stockist 80, others 100 | Pass; 084 Partly, as round 1 |
| TC-BUY-085 | T1005ZZT4-E: `ptr` refused 403 by the feature gate | Pass |
| TC-BUY-086 | T1005ZZT4-E, stages off, PI-T1005ZZT4-E-HO-2026-2027-000001: refusal now in the bill's words; 83,000.00 | Pass |
| TC-BUY-087 | T100517LD-G, PI-…-000017 at 84.50 (variance 1,500.00), PO-…-000039, 000040, GRN-…-000019: the six steps | Pass |
| TC-BUY-088 | T1005ZZT4-E, PI-…-000002, FA-00001: no stock, four-line journal | Pass |
| TC-BUY-089 | PI-…-000017: 84,500.00 in the register and the HSN summary, unit PIECE | Pass |
| TC-BUY-090 | `buy-ready` t10054ip6, GRN-…-000275: capital goods marked at the dock; billed as stock refused; cancel reverses nothing | Pass |
| TC-BUY-091, 092 | T100517LD-G, PI-…-000019, DBN-T100517LD-G-HO-2026-2027-000001 (8,300.00), PR-T100517LD-G-HO-2026-2027-000001 (16,600.00, stamped USD at 83); capital-goods return refused (t1005tgkv) | Pass |

## Regressions looked for

`x2.py`, `x3.py`, `x4.py`, `x5.py`.

| Area | What was driven | Finding |
| --- | --- | --- |
| Returns: unbilled, billed, paid, replacement, refund | Cases 006, 009, 010, 011, 016, 017, 027, 032, 035 above | As round 1 |
| Returns in another currency | Case 092 | As round 1 |
| Returns of serial units | Case 065 on two firms | As round 1 |
| Returns of a batch-tracked product | T10050UOS-P, receipts GRN-…-000004 and 000005 into new batches. A return naming the batch completes and takes the batch from 10 to 8 (cancel puts it back). **A return naming no batch saves, approves, and is refused at completion** "This location holds 0 available, so 2.0000 cannot be returned to the supplier from it. Name the batch the goods are leaving." An unknown batch is refused at completion too | Does not block the screen: the desktop return editor starts each line on the receipt line's batch (`purchase_return_editor_dialog.dart:365-366`). It is late and avoidable for any other client: BUYQ-19 |
| Returns of goods that are reserved | T10050UOS-P, the fixture's scarce product (8 on hand, 10 reserved by an approved sales order): return of 1 refused "This location holds -2.0000 available…" | Right by the new rule (available, not on hand); noted because the figure reads oddly |
| Free-goods-only line | `buy-ready` t1005n1n8 and t1005nt0v, PO-…-000231, 000234: order line of 0 with 2 free saves and approves; the receipt line of 0 with 2 free completes (gift stock 2, order RECEIVED); a bill naming that line at 0 saves and approves (1,180.00, order INVOICED and complete) | Works. **The free units cannot be returned**: BUYQ-16 |
| A line that did not arrive | Two-line order: the absent line sent as 0 is refused, left off is accepted (order PARTIALLY_RECEIVED) | Right; the desktop leaves such lines off |
| Everything on a line rejected | Receipt of 4 with 4 rejected: saves (accepted 0) and completes | Right |
| Capital goods | Cases 077, 078, 088, 090, 092(3) | As round 1, without the 0.00 line |
| Landed cost and Bill of Entry cancel | Cases 026, 074, 075 and the BUYQ-4 re-check | The journal is found by its new reference and mirrored |
| Supplier statement, balance confirmation, payables | BUYQ-5 and BUYQ-13 re-checks, cases 033 to 035, 091 | Agree |
| Requisitions | Cases 020, 058 with the paged list and `PRQ-` | As round 1 |

### `SI` and `RC`: one prefix, two documents

Both are, as `PR` was.

| Prefix | The two documents | Do numbers collide? |
| --- | --- | --- |
| `RC` | Customer **receipt** (`RECEIPT`, `app/settlements/services/settlement_service.py:2286`) and supplier **rate contract** (`RATE_CONTRACT`, `app/rate_contracts/services/rate_contract_service.py:73`) | **Yes.** T1005498P-R: rate contracts RC-2026-2027-000002, 000003, then receipts RC-2026-2027-000002, 000003; again for 000004 and 000005. TEST01: receipts RC-2026-2027-000005 and 000006 beside the rate contracts of those numbers. BUYQ-17 |
| `SI` | **Sales invoice** (`SALES_INVOICE`, `app/sales_invoice/services/sales_invoice_service.py:285`) and the **reverse-charge self-invoice** a purchase bill is given at approval (`RCM_SELF_INVOICE`, `app/purchase_invoice/services/purchase_invoice_service.py:196`) | **Yes.** T1005498P-R: self-invoice SI-26-27-000002, then an approved sales invoice SI-26-27-000002. T100517LD-G: self-invoices SI-26-27-000004 and 000005, then a sales invoice SI-26-27-000004. BUYQ-18 |

Why one direction is safe and the other is not: a number is issued by stepping
over numbers already held by documents **of the same type** and by **journal
references** (`transactional_document_service.py:418`). Receipts and sales
invoices post journals under their own number, so a rate contract or a
self-invoice issued later steps over them. Rate contracts and self-invoices
post no journal under their number, so the next receipt or sales invoice walks
straight onto it.

## Generic checks

Re-run in T1005498P-R (`g01.py`, `g01.log`): **149 requests, none unexpected,
no 500.** Against round 1's table the changed cells are:

| Check | Round 1 | Round 2 |
| --- | --- | --- |
| Quantity 0 on an order, receipt, bill, return line | 201 | 422 (an order line of 0 with 2 free: 201) |
| Rate 0 on a quote, a rate contract | 200, 201 | 422, 422 |
| Stale `If-Match` on a bill, a return, a requisition | 200 | 409 |
| `page_size=100000` on the requisition list | 200 | 422 |
| Requisition naming another firm's supplier | 409 | 422 "Unknown supplier(s): …" |

Every other cell is as round 1: mandatory fields, negative quantity and rate,
over the source quantity, unknown ids, another firm's product, 403 for the
VIEWER and the Purchasing user, `page_size` over the cap, `status` not
writable, steps skipped, and cancel or reverse putting stock and ledger back.

### The books at the end

| Firm | Trial balance | Payables report against 2100 |
| --- | --- | --- |
| T1005498P-R | balanced, 87,602.00 | 86,062.00 against 88,062.00, difference 0.00 with 2,000.00 of unrealised revaluation named |
| T100517LD-G | balanced, 904,199.76 | 343,773.76 against 345,773.76, difference 0.00 with 2,000.00 named |
| T1005ZZT4-E | balanced, 140,570.00 | 126,070.00, agrees |
| T1005NDZH-E, T10050UOS-P | balanced | nothing owed, agrees |
| TEST01 | balanced, 1,749,569.42 | differs by 708.00, the same PI-2026-2027-000003 of 2026-09-18 as in round 1 |

## New findings

None is in `docs/DEFECTS.md`. Each was reproduced twice, on two fixtures or
two firms. None is a regression from the fixes.

| Id | Severity | What | Where |
| --- | --- | --- | --- |
| BUYQ-16 | Medium | Free goods cannot go back on a purchase return: the cap counts the accepted quantity alone | `app/purchase_return/services/purchase_return_service.py:2513-2514` |
| BUYQ-17 | Low | A customer receipt and a supplier rate contract are both numbered `RC-…` and take the same numbers | `app/settlements/services/settlement_service.py:2286`, `app/rate_contracts/services/rate_contract_service.py:73` |
| BUYQ-18 | Medium | A sales invoice and a reverse-charge self-invoice are both numbered `SI-…` and take the same numbers. Both are GST documents with serial numbers that must be unique in a year | `app/purchase_invoice/services/purchase_invoice_service.py:196`, `app/sales_invoice/services/sales_invoice_service.py:285` |
| BUYQ-19 | Low | A return line with no batch, for a product whose stock is in batches, saves and approves and is refused only at Complete, though the receipt line it returns names the batch | `app/purchase_return/services/purchase_return_service.py:1055-1064` |

### BUYQ-16 -- free goods cannot be returned (Medium)

`buy-ready` t1005n1n8 and t1005nt0v (a free-only line), and two more
`buy-ready` runs with 10 bought and 2 free on one line (GRN-TEST01-HO-2026-2027-000283, 000284).

1. Order 10 at 100 with `free_quantity` 2; receive 10 with 2 free and
   complete: 12 on hand, the receipt line reads accepted 10, free 2.
2. `POST /purchase-returns` off that receipt line with
   `current_return_quantity` 12 -> 422 "Return quantity exceeds the available
   source quantity." 11 -> the same. 10 -> 201.
3. On a line that is free goods alone (ordered 0, free 2), a return of 1 ->
   the same 422.

**Expected:** what was received can go back, free units included (a damaged
free carton, or the whole delivery refused). **Actual:** at most the accepted
quantity; a free-only line can never be returned. The only way to take the
units off the books is a write-off.

**Cause:** `_source_quantity` returns `accepted_quantity` for a goods receipt
line and `current_invoice_quantity` for a bill line; neither counts
`free_quantity`. Older than this round; it was never driven before.

### BUYQ-17 -- `RC` is a receipt and a rate contract (Low)

1. T1005498P-R holds receipt RC-2026-2027-000001 (the fixture's).
2. `POST /rate-contracts` twice -> RC-2026-2027-000002, 000003 (stepping over
   the receipt's journal).
3. `POST /receipts` twice -> **RC-2026-2027-000002, 000003**.

Repeated in the same firm (000004, 000005) and on TEST01 (`buy-ready`,
receipts RC-2026-2027-000005 and 000006 where rate contracts of those numbers
stand). **Expected:** a prefix of its own for the rate contract, as the
requisition was given `PRQ`.

### BUYQ-18 -- `SI` is a sales invoice and a self-invoice (Medium)

The RCM rules of the GST template are INACTIVE in a new firm; they were
switched to ACTIVE for this and back to INACTIVE afterwards.

1. T1005498P-R: a sales invoice is raised and approved: SI-26-27-000001.
2. A bill for a product on `RCM_GTA_5` is approved
   (PI-T1005498P-R-HO-2026-2027-000004): reverse charge 50.00, Cr 2270 and
   2280, `self_invoice_number` **SI-26-27-000002**.
3. The next sales invoice is raised and approved: **SI-26-27-000002**.

On T100517LD-G the same: self-invoices SI-26-27-000004 and 000005, then a
sales invoice SI-26-27-000004. **Expected:** the self-invoice series cannot
produce a number a tax invoice will carry (rule 46(b) asks for a serial number
unique in the financial year; GSTR-1's document summary lists both series).
**Cause:** both specs say `prefix="SI"`; the self-invoice posts no journal
under its number, so the sales invoice's step-over never sees it.

### BUYQ-19 -- a batch return refused at the last step (Low)

T10050UOS-P, receipts GRN-T10050UOS-P-HO-2026-2027-000004 and 000005, each 10
into a new batch. `POST /purchase-returns` for 2 off the receipt line with no
`batch_number` -> 201; approve -> 200; complete -> 422 "This location holds 0
available, so 2.0000 cannot be returned to the supplier from it. Name the
batch the goods are leaving." With `batch_number` it completes. The refusal
is right (before BUYQ-2 it took the units from a row with no batch and left
it negative). What is wrong is when: the document is approved before anybody
is told, and the server already knows the batch from the receipt line the
return names. **Expected:** a return line off a receipt line takes that line's
batch when it names none, or the refusal comes at save. The desktop is not
affected: its editor fills the batch from the receipt line.

## Case text to correct

As it stands after the fixes. `docs/INDEPENDENT_TEST_CASES.md` has not been
edited since round 1, so every row here is still to do. Dropped from round 1's
list because the fix made the case right again: TC-BUY-075 step 3 (the
duplicate **is** refused at Save) and TC-BUY-086 (the bill's own words).

| Case | Change |
| --- | --- |
| TC-BUY-006 | **Data:** replace "The return should read `grand_total` **236.00** and post Dr 2100 236.00 / Cr 1200 200.00 / Cr 1300 36.00; a return at **0.00** with the 200.00 charged to 5400 means no price reached the line." with "The return reads `grand_total` **236.00** (D-BUY-31) and, because the receipt has not been billed, posts **Dr 2300 Goods Received Not Invoiced 200.00 / Cr 1200 Inventory 200.00** with no tax and no payable (D-BUY-26)." |
| TC-BUY-009 | **Fixture:** `po-invoiced`, not `po-received`. **Also needs:** "As *po-invoiced*, with the bill for the receipt of 6 paid in full (TC-BUY-008)." |
| TC-BUY-011 | Add: "Delete the supplier before applying the credit to see the refusal for the credit alone; afterwards it is refused for the open bill." |
| TC-BUY-012 | **Also needs:** add "a firm with a GST number for the GSTR-3B step (TEST01 has none)". |
| TC-BUY-019 | Replace "the standing discount fills a blank discount" with "the standing discount fills a blank discount **unless a supplier price list prices the line, whose own discount (0 where none is typed) then applies**". |
| TC-BUY-020 | Replace "numbered in its own **PR** series" with "numbered in its own **PRQ** series". Replace "a line with neither a supplier nor a preferred supplier is refused by name" with "a requisition with such a line saves and can be approved; **Convert to orders** refuses it by name". |
| TC-BUY-021 | Replace "pass 6, reject 4 (once written off, once left in quarantine for a return)" with "pass 6 and reject 4 written off on one receipt; on a second receipt pass 6 and reject 4 left for a return, then return those 4: sellable stays at what passed and quarantine empties. Passed and rejected must add up to everything the line holds." |
| TC-BUY-022 | Replace "held by the administrator only" and "as the **Purchasing manager**" with "a user on a **custom role** that holds PURCHASE_APPROVE without the two over-rights; the seeded *Purchase Manager* holds both and approves". Replace "**Block**" with the screen's name for `NEEDS_APPROVAL`. |
| TC-BUY-023 | **Also needs:** add "a bank account on `<SUFFIX>-V` too, or untick its bill: a run that pays a supplier with no bank account has no bank file". |
| TC-BUY-025 | Replace "a period covering the bill of 708.00" with "a period **that has already ended** and covers a bill dated inside it". The fixture's bill is dated today, so the case needs a bill of its own dated earlier. |
| TC-BUY-030 | **Also needs:** add "an HSN code on `<SUFFIX>-B` (the fixture creates it with none), or a product of the case's own with one". "With its unit" is right again for bills approved after the fix. |
| TC-BUY-035 | Replace the return "off the **receipt of 4** (which no bill names)" with "off the **receipt of 6 after its bill has been approved and paid**". |
| TC-BUY-041 | Replace "The file is … MB; the most a file may be is 10 MB." with "The file is larger than 10 MB, the most it may be." |
| TC-BUY-049 | Add: "'Nothing has changed.' is the screen's; the server saves again." A blank rate sent to the server now answers "The rate cannot be blank: leave it out to keep what is saved." |
| TC-BUY-063 | Replace "but 2 are entered: enter 1 more" with "but 2 serial numbers are entered: enter 1 more". |
| TC-BUY-070 | The server's words: currency `US` is "A currency is its three-letter ISO code, such as USD or EUR."; an order with no rate is "A purchase order in USD needs its exchange rate: the rupees one USD was worth on the purchase order's date." Add: "the order starts in USD on screen; the server saves an order that names no currency in rupees." |
| TC-BUY-075 | Step (4): a Bill of Entry with no item cannot be saved at all (validation), so "Add at least one line before posting." is not reachable over the API. Step (3) is right as written. |
| TC-BUY-087 | Step (4): replace "'A bill in USD needs its exchange rate: the rupees one USD was worth on the bill's date.' (the server uses the bill's wording for an order too)" with "'A purchase order in USD needs its exchange rate: the rupees one USD was worth on the purchase order's date.'" |
| New, after BUYQ-11 | Wherever a case says to leave a quantity at 0 on a line that did not arrive, say "leave the line off": a line of 0 with nothing free is now refused on an order, a receipt, a bill and a return. |
| New, after BUYQ-2 | TC-BUY-006, 009 to 011, 032, 035: add "the goods must still be on hand: a return for more than the location holds is refused at Complete". |

## Still to walk on screen

Unchanged from round 1: every label, banner, toast, dialog and tooltip the
cases quote; TC-BUY-055 and the template refusal of 054 (a WhatsApp Business
account that passes Test); the read-only state of a screen for a role without
the permission (015, 049, 059, 069, 081); the amendment title on the print
(020); the bank file download (023); a late receipt (024). New this round:

- The 409 on a bill, a return and a requisition (BUYQ-12): what the screen
  says when somebody else saved first, and whether it sends `If-Match` at all.
- The requisition list now paged at 20: that the screen reaches page 2.
- The new refusals of BUYQ-1, 2, 8 and 11 as the screens show them, and that
  the return editor's batch box is filled from the receipt line (BUYQ-19).

## Not verified

- **Nothing was read from the database.**
- **Connection resets on a large list read.** `GET /finance/journal-entries?page_size=100`
  on T100517LD-G (136 KB) was reset by the peer (WinError 10054) 5 times in
  10, and at `page_size=50` twice in 10; at 20 never. `GET /purchase-invoices?page_size=100`
  (113 KB) and `GET /vendors?page_size=100` were never reset in 10 tries. The
  server's own log shows each of those journal requests completed with 200 in
  25 to 56 ms, so the loss is after the handler. Free memory was 0.35 GB when
  this was measured. Round 1 saw three such resets. Not explained; it may be
  the machine and not the application.
- **One 503 that was not mine:** `POST /sales-invoices` at 21:12:39 failed
  with a PostgreSQL deadlock (an AccessExclusiveLock against an
  AccessShareLock), at the moment this round's `compliance-firm` was being
  provisioned and another session was selling. Noted because provisioning a
  firm while people work may do this again.
- BUYQ-14 was checked by one provision and by the log growing afterwards, not
  by reading alembic's configuration path.
- BUYQ-3: only new requisitions were checked; the four old `PR-` requisitions
  on TEST01 keep numbers a return also carries.
- BUYQ-18: whether GSTR-1's document summary shows the clash was not read.
- Still not driven, as in round 1: the supplier catalogue file import, the
  planner rounding to an order multiple, a sales line ignoring a supplier
  price list (019); *Raise requisition* from the reorder report (020); a late
  receipt (024); the HSN row falling by a debit note and a return (032); an
  expired rate contract (062); a price list or price level against a batch's
  PTR (084).
- TEST01's 708.00 (PI-2026-2027-000003, cancelled 2026-09-18 with its journal
  standing) was again left alone.
