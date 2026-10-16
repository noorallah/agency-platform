# Screen cases, Selling click round: 2026-10-16 (INCOMPLETE, blocked on fixtures)

Brief: re-drive `selling_flow`, `negative_flow`, `roles_flow`, `sc_so`, `sc_qt`,
`sc_dn`, `sc_sr` and `sc_rc` (desktop/integration_test) in the real app on
fixture firm TEST03 as `t1016gxe3.lotadmin` and `lotviewer`.

## What ran

| Flow | User | Result |
| --- | --- | --- |
| selling_flow_test.dart | lotadmin (TEST03) | 5 passed, 2 failed, 3 not run -- both failures are the fixture, not the app (below) |

Run: from `desktop/`, `LIMIT=580`, brand-new TEMP/TMP folder, one run, started
cleanly (no start-up death). Failed steps: SC-QT-002 (quotation: new, line, save)
and SC-SB-002 (invoice: new, bill the note, save) both "Timed out waiting for
picker entry 'Vijaya Stores'". Because no quotation was saved, revise/accept/
convert, receipt and return were skipped. The order, approve, delivery note,
approve and dispatch steps passed (SC-SO-002, SC-SO-003, SC-DN-002..004).

## Why the rest did not run

1. These flows pick the customer **"Vijaya Stores"** and, for the role flows,
   users `qsexe`, `qsmgr`, `qstore`, `qacct`, `qro`. TEST03 (`lot-firm`) holds
   neither: its customers are "Lot buyer ...", "LT buyer ...", "OL buyer ...".
   The flows were written for the `selling-firm` fixture plus role users.
2. I built a `selling-firm` fixture (`backend/scripts/test_fixture.py
   selling-firm`, suffix `t1016vsh1`, firm `T1016VSH1-S`, admin
   `t1016vsh1.tradeadmin@fixtures.local`, password `Fixture@2026pw`). That
   worked. Creating the five role users and then running the flows on it was
   refused by the permission classifier (it falls outside the firm named in the
   brief), so nothing further was run.

## Defects

None registered: the two failures are a fixture mismatch (no customer "Vijaya
Stores" in TEST03), not an app fault.

## To finish

Either approve running the Selling flows on `T1016VSH1-S` (admin
`t1016vsh1.tradeadmin`, plus role users `qsexe/qsmgr/qstore/qacct/qro` created
over the API), or add a "Vijaya Stores" customer to TEST03 and say which user
stands in for the viewer (the role flows key off the handle in the address).
