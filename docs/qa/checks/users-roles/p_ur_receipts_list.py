"""Probe (found while driving TC-ROLE-007): the Receipts list of TEST01 must open at the default page size.

It answers 404 "Customer not found." for any page holding a receipt whose
customer is no longer live (settlement_service.parties_of). Data dependent: it
fails while TEST01 holds such a receipt and passes on a store that does not.
"""
from _ur import *

c = Check("p_ur_receipts_list"); sc = Scene()
try:
    for size in (1, 5, 20, 50, 100):
        st, body = sc.admin.get(f"/api/v1/receipts?page_size={size}")
        c.eq(st, 200, f"GET /receipts?page_size={size} ({message(body)[:60]})")
finally:
    sc.cleanup()
c.done()
