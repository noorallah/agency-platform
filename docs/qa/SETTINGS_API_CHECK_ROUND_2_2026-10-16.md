# Settings sections: API check round 2 (2026-10-16)

Backlog 148, rows T1 and T2. Driven over HTTP against the running backend at
`http://127.0.0.1:8000`, reusing the round 1 fixture state (ready firm `T1015ENN7-R`,
bare firm `T10159UQO-F`; every sign-in still worked). `python docs/qa/checks/run.py settings`,
run twice. No product code was changed.

## What was driven

- The ten round 1 checks again, unchanged, now that S1 (#1593) and S2 (#1594) are fixed.
  `tc_conf_015` already holds the Firms and People legs: Firms as the platform administrator
  answers 200 with steps `business-profiles` then `firms` (Done, count equal to the firm
  list), and People as a Firm admin shows only `roles`, `user-templates`, `users`.
- New `p_set_state_moves_after_save` (as the ready firm's Firm admin). Each record is made
  through its own endpoint, the section re-read, the record read back, then removed:
  - Approval levels: `PUT /api/v1/approvals/rules/SALES_ORDER` (one level), count moved
    by one, the held rules put back, count back.
  - Numbering series: `POST /api/v1/document-framework/numbering-rules`, count +1, then
    `DELETE` (204), count back.
  - Promotions: `POST /api/v1/promotions` (ACTIVE, 5% line discount), "offers" +1 and
    "running" +1, read back, `DELETE`, detail back.
  - Route builder: new territory, `PUT /api/v1/sales-territories/{id}/customers` with the
    fixture customer, "shops" +1 and "rounds" +1, emptied, territory deleted, detail back.
- Left behind: nothing in the steps' counts (all restored); the deleted rows stay as
  soft-deleted records.

## Results

| Id | Result |
| --- | --- |
| `tc_conf_010` .. `tc_conf_014` | clean |
| `tc_conf_015` People, Firms | clean (S1 and S2 fixed) |
| `p_set_unknown_and_unauthenticated`, `p_set_other_firm_and_roles`, `p_set_read_writes_nothing`, `p_set_people_rows_offered` | clean |
| `p_set_state_moves_after_save` | clean (27 checks) |

Run tally: `10 of 10 checks clean` twice for the round 1 set; the new probe clean twice
(11 checks, 11 clean).

## Defects

None found.

## Not driven

- Packaging levels: the ready firm has no product (`GET /api/v1/products` is empty) and
  making one was out of scope; the endpoint is `POST /api/v1/uom/products/{id}/packaging-levels`.
- Units of Measure To do and Roles To do (every store is seeded), Custom field rules for a
  category outside `FXAMB`, Control accounts To do (see round 1).
- Firms count moving after a firm is created (would leave a firm behind).
- The checks' lint: the older kept scripts still carry long lines under the backend ruff
  and black settings; only the new probe is clean.
