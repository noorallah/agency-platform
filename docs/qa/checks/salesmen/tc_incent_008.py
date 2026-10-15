"""TC-INCENT-008: a sales executive may not read payouts, approve or pay them."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_incent_008")
ex = admin("exec")
some = "00000000-0000-0000-0000-000000000001"
c.eq(ex.get(f"{COMM}/payouts")[0], 403, "GET payouts")
c.eq(ex.post(f"{COMM}/payouts/{some}/approve", {})[0], 403, "POST approve")
c.eq(ex.post(f"{COMM}/payouts/{some}/pay", {"paid_on": today().isoformat()})[0], 403, "POST pay")
c.done()
