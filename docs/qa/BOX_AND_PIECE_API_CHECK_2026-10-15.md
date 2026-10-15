# Boxes and pieces (L5) -- API check, step 12, 2026-10-15

Main at `566a3525` (#1576), backend restarted (the uvicorn started at 06:15
had survived `schtasks /end`; it was stopped by its process id and the task run
again), TEST01, fresh `product-master` and `platform-admin` fixtures
(`t1015qvno`, `t1015tels`), goods-types state rewritten by its `setup.py`.

`python docs/qa/checks/run.py goods_types tc_mast_034`: **1 of 1 clean.**
TC-MAST-034 drives the product import's *PiecesPerPack* and *PackUnit* columns
end to end: the template headings, the three problems by column (a fraction,
an unknown pack unit, the stock unit as the pack unit), the old program's
heading *Pieces per case* read as PiecesPerPack, the three passed-over
warnings (an existing product, a unit set on the row, a PackUnit with no size),
the rules written (1 Box = 12 Piece, 1 Case = 10 Strip, the set's 10 over the
row's 6, none for one per pack or the existing product), the product answering
a selling and a buying pack of 12 Box, and a sales order line for the imported
item written at its box of 12 (29 pieces). No defect found in step 12.

**The rest of the goods-types folder: 16 of 36 clean, every failure in the
checks, not the server.** TC-MAST-027, 028 and 030 and the probes that create
products send no brand, and a product has needed one since backlog 138
(2026-10-13): the server refuses them as it should. TC-MAST-029 and 032 need
the second-firm accounts `setup_firms.py` writes, which this run did not make.
TC-MAST-031 reads documents TEST01 no longer has under the fresh fixture.
Bringing those checks up to the brand rule is a check-maintenance job, owed.

Not covered here: no screen was clicked; the earlier L5 steps were proved by
unit and widget tests, and only the import and one order line were driven
over HTTP in this round.
