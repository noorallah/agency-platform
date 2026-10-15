"""TC-CONF-010: Settings > Tax state, read as the cases read it, then saved."""

from _settings import Check, data, message, shape, steps, suffix, total, who, grow

c = Check("tc_conf_010")
ready = who("ready_admin", "ready")
bare = who("bare_admin", "bare")
plat = who("platform")
held = __import__("common").state()

# Step 3 of the case: a finished firm, from the GST template.
got = shape(c, ready, "tax", "ready")
c.eq(got["rates-and-profiles"][0], "DONE", "ready: rates and profiles done")
c.ok(got["rates-and-profiles"][1].endswith("from the GST template"),
     "ready: rates read 'from the GST template'", got["rates-and-profiles"])
c.eq(got["tax-rules"][0], "DONE", "ready: tax rules done")
c.ok(got["tax-rules"][1].endswith("from the GST template"),
     "ready: rules read 'from the GST template'", got["tax-rules"])
for step, detail in (("tax-settings", "Set for this firm"), ("gst-documents", "Off"),
                     ("tds-purchases", "Off")):
    c.eq(got[step][0], "OPTIONAL", f"ready: {step} optional")
    c.eq(got[step][1], detail, f"ready: {step} detail")

# Step 8: a firm with no tax set up: To do exactly while there is no data.
profiles = total(bare, "/api/v1/tax-framework/profiles")
rules = total(bare, "/api/v1/tax-framework/rules")
got = shape(c, bare, "tax", "bare")
c.eq(got["rates-and-profiles"][0], "DONE" if profiles else "TODO",
     f"bare: rates state follows its {profiles} profiles")
c.eq(got["tax-rules"][0], "DONE" if rules else "TODO",
     f"bare: rules state follows its {rules} rules")
if not profiles and not rules:
    c.eq(got["rates-and-profiles"][1], "None yet", "bare: rates say none yet")

# Saved: the GST template moves both rows to Done, "from the GST template".
if not profiles or not rules:
    status, answer = plat.post(f"/api/v1/firms/{held['bare_id']}/apply-tax-template", {})
    c.ok(status in (200, 201), "apply-tax-template saves", f"{status} {message(answer)[:200]}")
    after = steps(bare, "tax")
    c.eq(after["rates-and-profiles"][0], "DONE", "bare after template: rates done")
    c.eq(after["tax-rules"][0], "DONE", "bare after template: rules done")
    c.ok(after["rates-and-profiles"][1].endswith("from the GST template"),
         "bare after template: rates from the template", after["rates-and-profiles"])

# Saved: one more profile in the ready firm is one more in the count.
status, answer = ready.get("/api/v1/tax-framework/systems?page_size=5")
systems = data(answer) if status == 200 else []
if c.ok(bool(systems), "a tax system is offered", f"{status} {message(answer)[:150]}"):
    grow(c, ready, "tax", "rates-and-profiles", "/api/v1/tax-framework/profiles",
         {"tax_system_id": systems[0]["id"], "code": f"S{suffix(5)}", "name": "Settings check profile"})


# Saved: each singleton screen of a step, on the bare firm: read, put back,
# change one value, put it back; the step is read again after each leg.
from _settings import singleton

singleton(c, bare, "/api/v1/tax-framework/settings", "tax", "tax-settings",
          detail_for=lambda v: "Set for this firm")
singleton(c, bare, "/api/v1/tax-framework/gst-compliance-settings", "tax",
          "gst-documents", flip=("einvoice_applicable_from", "2026-04-01"),
          detail_for=lambda v: "E-invoice on" if v.get("einvoice_applicable_from") else "Off")
singleton(c, bare, "/api/v1/finance/tds-194q/settings", "tax", "tds-purchases",
          detail_for=lambda v: "On" if v.get("is_enabled") else "Off")
c.done()
