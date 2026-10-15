"""TC-CUST-003: the credit policy is readable by the seller and writable only with CUSTOMER_MANAGE_SETTINGS."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *

c = Check("tc_cust_003")
a, s = api(), api("seller")
st, got = a.get(f"{CU}/credit-settings")
c.eq(st, 200, "admin reads the policy")
g = data(got)
if not g.get("is_configured"):
    c.eq((g["enforcement"], D(g["warn_at_percent"]), D(g["block_at_percent"])), ("WARN", D(80), D(100)), "default policy: warn at 80, block at 100")
c.eq(s.get(f"{CU}/credit-settings")[0], 200, "seller reads the policy")
put = s.put(f"{CU}/credit-settings", {"enforcement": "OFF", "warn_at_percent": "80", "block_at_percent": "100"})
c.eq(put[0], 403, "seller write refused")
c.eq(data(a.get(f"{CU}/credit-settings")[1])["enforcement"], g["enforcement"], "policy not changed by the refusal")
c.done()
