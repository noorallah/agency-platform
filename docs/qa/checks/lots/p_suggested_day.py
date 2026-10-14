"""Probe: the day the switch preview suggests (no `on`) must not be refused for a firm that trades."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("p_suggested_day")
admin = firm_admin(state("lots")["average_firm"])
if must(admin.get(f"{INV}/lot-settings"), "settings")["costing_method"] != "AVERAGE":
    print("ok p_suggested_day (firm already switched; skipped)")
    raise SystemExit(0)
pv = must(admin.get(f"{INV}/lot-settings/switch-preview"), "preview")
c0.eq(pv["refusals"], [], f"the suggested day {pv['suggested_on']} is a usable default for a firm whose stock moved since")
c0.done()
