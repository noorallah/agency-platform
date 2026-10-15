"""Probe: an over-cap page_size on a master list is a 422 naming the limit, never a 500."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt

c = Check("p_mst_page_size")
a, a2 = api(), api("admin2")
for who, path in ((a, CU), (a, VE), (a, PR), (a2, BR), (a2, WH), (a, f"{VE}/categories")):
    r = who.get(f"{path}?page_size=100000")
    c.eq(r[0], 422, f"{path}: page_size=100000 is 422")
    c.eq(who.get(f"{path}?page=0")[0], 422, f"{path}: page=0 is 422")
c.done()
