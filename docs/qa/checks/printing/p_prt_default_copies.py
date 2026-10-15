"""Probe: a firm that never saved print settings is told the copies it actually prints (D-PRT-1).

Reads firm two, which no other check changes. A bill prints three copies for
such a firm (``DEFAULT_COPIES``), so the template the screen reads has to say
three, or a client that saves what it read cuts the firm to one copy.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("p_prt_default_copies")
b = admin("admin2")
got = must(b.get(PRINT_TEMPLATE), "template")
if got.get("is_customised"):
    raise SystemExit("PRECONDITION firm two has saved print settings; run setup.py again")
c.eq(len(got.get("copy_labels") or []), 3, "the unsaved default template lists the three copies a bill prints")
c.done()
