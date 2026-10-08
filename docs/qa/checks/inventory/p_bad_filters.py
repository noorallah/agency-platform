"""Probe: a filter value the server cannot read is a 422 naming it, never a 500."""
from _inv import *

c = Check("p_bad_filters")
w = World()
for p in ("/api/v1/inventory?status=nonsense", "/api/v1/batch-serial/batches?status=nonsense",
          "/api/v1/batch-serial/serials?status=nonsense", "/api/v1/batch-serial/lots?status=nonsense",
          "/api/v1/inventory/transactions?transaction_from=notadate", "/api/v1/inventory/transactions?transaction_to=2026-13-45",
          "/api/v1/inventory/ledger?transaction_from=notadate", "/api/v1/inventory/opening-stock?status=zzz",
          "/api/v1/inventory/counts?status=zzz", "/api/v1/inventory/export?status=nonsense"):
    st, b = w.admin.get(p)
    c.ok(st in (200, 422), f"{p.split('/api/v1/')[1]} is not a 500", (st, message(b)[:60]))
c.done()
