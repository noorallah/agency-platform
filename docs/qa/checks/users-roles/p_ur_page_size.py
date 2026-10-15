"""Probe: page_size over the cap, and below 1, on every list of the module."""
from _ur import *

c = Check("p_ur_page_size"); sc = Scene()
try:
    for who, a in (("firm admin", sc.admin), ("platform admin", sc.platform.inside(one()))):
        for path in (U, R, T, "/api/v1/permissions", f"{U}/lookup?q=qa.test", "/api/v1/audit-logs"):
            joiner = "&" if "?" in path else "?"
            for size, want in ((101, 422), (0, 422), (-1, 422), (100, 200)):
                st, body = a.get(f"{path}{joiner}page_size={size}")
                c.eq(st, want, f"{who}: GET {path} page_size={size}")
            c.eq(a.get(f"{path}{joiner}page=0")[0], 422, f"{who}: GET {path} page=0")
            c.eq(a.get(f"{path}{joiner}page_size=abc")[0], 422, f"{who}: GET {path} page_size=abc")
finally:
    sc.cleanup()
c.done()
