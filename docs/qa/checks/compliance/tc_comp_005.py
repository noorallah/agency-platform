"""TC-COMP-005: an invoice to a buyer with no GSTIN is refused locally (firm one)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_005")
a = api()
C = firm()["invoices"]["C"]
n = len(rows_of(a.get(f"{EINV}/registrations?page_size=100")))
c.refused(a.post(f"{EINV}/invoices/{C}/register", {}), 422, "the customer has no GST number", "invoice C is refused")
c.eq(data(a.get(f"{EINV}/invoices/{C}")[1]), None, "no registration row was made")
c.eq(len(rows_of(a.get(f"{EINV}/registrations?page_size=100"))), n, "the list did not grow")
c.done()
